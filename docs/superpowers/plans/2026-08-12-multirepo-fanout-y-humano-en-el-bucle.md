# Multi-repo por sesiones enraizadas y humano en el bucle — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Diseño:** `docs/superpowers/specs/2026-08-12-multirepo-fanout-y-humano-en-el-bucle-design.md`
(dirección decidida por Jhonny el 2026-08-12).

**Goal:** Que un ticket que toca varios repos se analice con **una sesión enraizada
en cada uno** —cargando sus reglas, sus hooks y su MCP— y se consolide en un único
análisis que incluya el contrato entre repos; y que las costuras entre fases sean
puntos de decisión humana marcados y contados, con continuación de sesión opcional.

**Architecture:** La Fase 1 se parte en tres fases lanzables: `brief` (lee el work
item y enruta), `survey` (una sesión por repo enrutado, secuencial, sin MCP) y
`consolidate` (funde y produce la tabla de contrato). El runner gana un directorio
scratch montado con `--add-dir`, un parser de la línea `SONDEAR:` y una bifurcación
de prompt/argv para continuar sesiones. Las Fases 2 y 3 no cambian de forma, pero
`implement` gana la variable que carga las reglas de los repos montados. El sello
`HUELLA:` sigue decidiendo el estado de cada corrida.

**Tech Stack:** Python 3 + FastAPI + SQLite sin ORM (backend), pytest, markdown para
las skills, React+TS para la UI.

## Global Constraints

- **Suscripción, jamás API key.** El runner elimina `ANTHROPIC_API_KEY` y
  `ANTHROPIC_AUTH_TOKEN` del entorno del subproceso. No reintroducirlas.
- **Nunca `uvicorn --reload` en Windows**: deja hijos huérfanos reteniendo el 8000.
  Al probar a mano, reiniciar el backend a mano.
- **Tocar una skill obliga a subir `version` en
  `plugins/ticket-agent/.claude-plugin/plugin.json`** — y el sello
  `by ticket-agent vX.Y.Z` de la plantilla en `ticket-comprehension/SKILL.md`. **Son
  dos sitios** y el segundo se desincroniza en silencio. Tarea 13.
- **Los literales de contrato no se traducen en ninguna dirección**: `HUELLA` y sus
  valores, el nuevo `SONDEAR`, `DECIDIR`/`BLOQUEA`, `docs/tickets/<id>-analysis.md`,
  las rutas `/modelos` y `/artefacto?ruta=`, la clave `fases`. **Leer `STAMP_RE`
  antes de tocar cualquiera.**
- **Política de idioma:** prompt-facing (lo que lee el agente) en inglés; UI-facing
  (`motivo`, detalles de `HTTPException`) en español; este plan y el spec, español.
- **La dirección del fallo del enrutado es siempre hacia sondear de más.** Ningún
  camino puede estrechar la lista de repos por un fallo de parseo.
- Antes de dar por bueno un test, responder: **¿qué tendría que romperse para que
  este test fallara?** Si no hay respuesta concreta, el test no prueba nada.
- Ruta del backend: `apps/orchestrator/backend/`. Tests con
  `.venv/Scripts/python -m pytest tests/ -v` desde ahí.
- Los tests del runner usan `ORCH_CLAUDE_CMD` con `tests/fake_claude.py`: **el
  backend es testeable entero sin que existan las skills nuevas.** Por eso las
  tareas de backend van antes que las de plugin.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/app.py` | Variable de entorno, `session_id`, resume, parser de enrutado, tres fases nuevas, fan-out |
| `backend/tests/test_app.py` | Se extiende con cada tarea de backend |
| `backend/tests/test_enrutado.py` | **Nuevo.** Tabla de casos del parser |
| `plugins/ticket-agent/skills/ticket-brief/SKILL.md` | **Nueva.** Recolecta y enruta |
| `plugins/ticket-agent/skills/repo-survey/SKILL.md` | **Nueva.** Qué exige el ticket de ESTE repo |
| `plugins/ticket-agent/skills/analysis-consolidation/SKILL.md` | **Nueva.** Funde y produce el contrato |
| `plugins/ticket-agent/commands/{brief,survey,consolidate}.md` | **Nuevos.** Los tres comandos |
| `plugins/ticket-agent/skills/{ticket-comprehension,change-planning,change-implementation}/SKILL.md` | `DECIDIR`/`BLOQUEA`, `autonomy`, línea de continuación |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | `version` |
| `plugins/ticket-agent/README.md` | Las tres fases nuevas y los marcadores |
| `CLAUDE.md` | El mecanismo de todo lo anterior |
| `frontend/src/api.ts` | El tipo `Phase` gana los campos de continuación; `run()` envía `resume` |
| `frontend/src/Timeline.tsx` | Contador de decisiones y checkbox de continuación |

---

### Task 1: Las reglas de los repos montados llegan a `implement`

Independiente de todo lo demás y valiosa sola: las Fases 2 y 3 siguen en una sola
sesión en cualquier versión del diseño, así que sin esto las reglas de los repos
extras **nunca** llegan al agente que escribe su código.

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Produces: el entorno del subproceso lleva `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`
  cuando —y solo cuando— la fase es `implement` y el ticket tiene extras.

- [x] **Step 1: Escribir el test que falla**

En `tests/test_app.py`, dos casos que verifican el entorno con el que se lanzó el
subproceso (el mismo mecanismo con el que ya se comprueba que las variables de
Anthropic se eliminan):

- ticket **con** extras + fase `implement` → la variable vale `"1"`
- ticket con extras + fase `analyze` → la variable **no está**
- ticket **sin** extras + fase `implement` → la variable **no está**

Expected: los tres fallan, el primero porque la clave no existe.

- [x] **Step 2: Implementar**

En `execute_run`, junto a la construcción de `env`:

```python
# Las reglas de un repo montado no se cargan solas: `--add-dir` da acceso a los
# archivos, no descubrimiento de configuración. Solo en `implement`, que es donde
# importa que el agente OBEDEZCA las reglas del repo ajeno mientras escribe en él;
# en Fase 1 los surveys ya las metieron por escrito en el análisis.
if extras and phase == "implement":
    env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] = "1"
```

Expected: los tres tests pasan.

- [x] **Step 3: Documentar el límite que esto NO cubre**

En `CLAUDE.md`, junto a lo de `--add-dir`: la variable carga `CLAUDE.md`,
`.claude/CLAUDE.md`, `.claude/rules/*.md` y `CLAUDE.local.md` de los directorios
montados. **Los hooks y el `.mcp.json` del repo extra siguen sin cargarse por
ninguna vía**, y si uno de ellos importa hay que replicarlo en el principal a mano.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py CLAUDE.md
git commit -m "feat(runner): las reglas de los repos montados llegan a implement"
```

> **Hecha el 2026-08-13.** Tres tests, no dos: se añadió el caso de ticket **sin**
> extras, que es el que impide que la implementación ponga la variable siempre.
> `fake_claude.py` delata la variable con `SAW-EXTRA-CLAUDE-MD`, siguiendo el mismo
> idioma que ya usa para las claves de Anthropic. Suite entera: 156 verdes.

---

### Task 2: Capturar el `session_id` de cada corrida

Gatea la Tarea 3. Sin el id no hay continuación posible.

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Produces: columna `runs.session_id` (nullable) poblada al leer el stream.
  La Tarea 3 la consume.

- [x] **Step 1: Escribir el test que falla**

`tests/fake_claude.py` ya emite stream-json; hacer que emita un evento con
`"session_id":"<uuid fijo>"` (ya lo hace el CLI real desde el primer evento —
verificado en `logs/1.log`). Test: tras una corrida, `runs.session_id` vale ese uuid.

Segundo test: un stream **sin** `session_id` deja la columna en `NULL` y la corrida
termina normal. Un id ausente no puede romper una corrida buena.

Expected: fallan por columna inexistente.

- [x] **Step 2: Migración de la columna**

En `init_db()`, junto a los `ALTER TABLE` que ya existen para bases viejas:

```python
"ALTER TABLE runs ADD COLUMN session_id TEXT",
"ALTER TABLE runs ADD COLUMN resumed_from TEXT",
```

(`resumed_from` se puebla en la Tarea 3; se crea aquí para no migrar dos veces.)

- [x] **Step 3: Extraer el id del stream**

Un regex sobre los chunks que el runner ya lee. **El primer match gana**, al revés
que `STAMP_RE`: el id es único y estable en toda la corrida, y buscar el último
obligaría a esperar al final.

```python
SESSION_RE = re.compile(r'"session_id":"([0-9a-f-]{36})"')
```

Guardarlo con `set_run(run_id, session_id=...)` en cuanto aparezca, no al cerrar: si
la corrida muere a mitad, el id sigue sirviendo para continuarla.

Expected: los dos tests pasan.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/backend/
git commit -m "feat(runner): guarda el session_id de cada corrida"
```

> **Hecha el 2026-08-13.** Tres tests. El tercero nació placebo —usaba `FAKE_BIG`,
> que imprime el relleno *después* del id, así que pasaba sin probar nada— y se
> reescribió con `FAKE_SESSION_LATE`, que empuja el id más allá del primer `read`.
> Mutado a «mira solo el primer chunk», falla.
>
> El `carry` que cubre un id partido entre dos chunks **se queda sin test a
> propósito**: un `read` de pipe puede volver corto, así que esa frontera no se
> coloca de forma determinista desde un test. Dicho en el comentario del bucle y en
> el docstring del test, para que nadie lo confunda con un olvido.
>
> `fake_claude.py` emite el `session_id` por defecto, así todos los tests ejercitan
> la captura; `FAKE_NO_SESSION` cubre el caso contrario. Suite: 159 verdes.
>
> **Aviso para quien ejecute el resto del plan:** no toques archivos del repo con
> `Get-Content`/`Set-Content` de PowerShell 5.1. Sin `-Encoding utf8` explícito, la
> lectura interpreta UTF-8 como cp1252 y cada em dash vuelve como mojibake — incluido
> el de `STAMP_RE`, que deja de casar. Pasó dos veces en esta sesión; se recuperó con
> `git checkout --`. Usa la herramienta de edición, o `git stash` para probar
> mutaciones.

---

### Task 3: Continuar una sesión anterior

Depende de la Tarea 2.

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `runs.session_id` de la Tarea 2.
- Produces: el endpoint de lanzar fase acepta `resume: bool`; `runs.resumed_from`
  queda poblada. La Tarea 15 (UI) lo consume.

- [ ] **Step 1: Escribir los tests que fallan**

Cinco casos, todos sobre el argv y el prompt con los que se lanzó el subproceso:

| Caso | Esperado |
|---|---|
| `resume=true` con sesión previa | argv lleva `--resume <id>` **y** `--fork-session`; el prompt **no** contiene el comando slash |
| `resume=true` con sesión previa | el prompt contiene el recordatorio de la estampa |
| `resume=true` con sesión previa | argv conserva `--add-dir`, `--allowedTools` y `--settings` idénticos a una corrida fresca |
| `resume=true` **sin** sesión previa | corre fresca, con comando slash, y el log lo dice |
| `resume=true` con `repo_path` distinto al de la corrida previa | corre fresca, y el log lo dice |

Expected: los cinco fallan.

- [ ] **Step 2: Implementar la bifurcación**

El detalle que rompe todo si se omite: **al continuar no se reenvía el comando
slash.** Mandarlo hace que el agente reinicie el procedimiento desde el paso 1,
relea el work item y reescriba el entregable — justo lo que se venía a evitar.

```python
prev = ultima_sesion(ticket["id"], phase)   # id + repo_path de la corrida previa
continuar = body.resume and prev and prev["repo_path"] == ticket["repo_path"]

if continuar:
    # Sin el comando: la sesión ya ejecutó la skill. Sin `repos_text`: ya está en
    # su contexto. El recordatorio de la estampa NO es opcional — el runner la
    # exige en toda corrida, y sin él una continuación buena se marca como error.
    prompt = instructions + "\n\nClose with the same HUELLA line as always, the last one of the message."
else:
    prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}" + repos_text(...) + adjustment_text(...)
```

Y en argv, `["--resume", prev["session_id"], "--fork-session"]` cuando `continuar`.
**`--fork-session` siempre**: la corrida original queda intacta y cada fila de `runs`
mantiene su propio id.

Los flags de permisos (`--add-dir`, `--allowedTools`, `--settings`) van igual en los
dos caminos: son permisos por invocación, no contexto. Quitarlos deja al agente sin
acceso de escritura a los extras a mitad de conversación.

Expected: los cinco tests pasan.

- [ ] **Step 3: Sin tope de continuaciones, pero contadas — y expuestas**

`GET /tickets/{id}` gana **dos campos por fase**, dentro de cada entrada de `fases`.
Son el contrato que la Tarea 15 consume, así que se nombran aquí y no se improvisan
en la UI:

| Campo | Significado |
|---|---|
| `puede_continuar: bool` | Hay una corrida previa de esta fase con `session_id`, **y** su `repo_path` coincide con el del ticket |
| `continuaciones: int` | Cuántas encadenadas lleva, siguiendo `resumed_from` |

`puede_continuar` se calcula en el backend a propósito: es la misma condición que
decide si el resume se aplica o cae a fresca (Step 2). Dejar que la UI la deduzca
por su cuenta es garantizar que las dos versiones diverjan.

No se limita el número: la UI lo muestra y el humano decide. El riesgo real —que una
sesión larga compacte y pierda el texto del ticket— se gestiona viéndolo, no
prohibiéndolo.

Test: una fase sin corridas previas reporta `puede_continuar: false`; tras una
corrida con `session_id`, `true`; con el `repo_path` del ticket cambiado, vuelve a
`false`.

- [ ] **Step 4: Commit**

```bash
git add apps/orchestrator/backend/
git commit -m "feat(runner): continuar la sesion anterior de una fase, opcional"
```

---

### Task 4: El parser del enrutado

Función pura, sin tocar el runner. Independiente de las tareas 1-3.

**Files:**
- Create: `apps/orchestrator/backend/tests/test_enrutado.py`
- Modify: `apps/orchestrator/backend/app.py`

**Interfaces:**
- Produces: `repos_a_sondear(texto: str, etiquetas: list[str]) -> list[str]`.
  La Tarea 6 la consume.

- [ ] **Step 1: Escribir la tabla de casos que falla**

`tests/test_enrutado.py`. **Cada caso ambiguo devuelve la lista completa**, nunca
una parcial:

```python
"""La dirección del fallo es lo que se prueba aquí: un enrutado que no se entiende
sondea de más. Un repo de más cuesta una sesión; uno de menos cuesta el ticket, y
nada aguas abajo lo detecta."""

TODAS = ["back", "front", "auth"]

CASOS = [
    # (texto, esperado, por qué)
    ("SONDEAR: back, front",            ["back", "front"], "caso normal"),
    ("SONDEAR: BACK , Front",           ["back", "front"], "sin distinguir mayusculas ni espacios"),
    ("bla\nSONDEAR: back\nSONDEAR: back, front", ["back", "front"], "ultimo match gana, como HUELLA"),
    ("no hay linea",                    TODAS,             "ausente -> todas"),
    ("SONDEAR: back, frontend",         TODAS,             "etiqueta desconocida -> todas"),
    ("SONDEAR:",                        TODAS,             "vacia -> todas"),
    ("SONDEAR: back",                   ["back"],          "una sola: el runner cortocircuita"),
]
```

El caso del último match no es adorno: **el cuerpo de la skill viaja por el log y
contiene el literal `SONDEAR:` en sus ejemplos**. Es exactamente el motivo por el
que `STAMP_RE` ancla en el último, documentado en `app.py`.

Expected: todos fallan, la función no existe.

- [ ] **Step 2: Implementar**

```python
# Mismo tratamiento que STAMP_RE y por el mismo motivo: el cuerpo de la skill viaja
# por el archivo y contiene el literal. Ancla en el último match.
SONDEAR_RE = re.compile(r"^SONDEAR:\s*(.*)$", re.MULTILINE)
```

Cualquier salida distinta de "una lista no vacía cuyas etiquetas están todas en
`etiquetas`" devuelve `etiquetas` entera.

Expected: la tabla pasa.

- [ ] **Step 3: Commit**

```bash
git add apps/orchestrator/backend/
git commit -m "feat(runner): parser del enrutado, que falla siempre hacia sondear de mas"
```

---

### Task 5: Las tres fases nuevas en las tablas

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Produces: `brief`, `survey` y `consolidate` en las cuatro tablas de fase.
  La Tarea 6 consume `PHASE_COMMANDS["survey"]`.

- [ ] **Step 1: Escribir los tests que fallan**

- El `assert` de que `PHASE_COMMANDS`, `PHASE_DONE`, `PHASE_ALLOWED_TOOLS` y
  `PHASE_NOUN` comparten claves sigue pasando con las tres nuevas.
- `survey` y `consolidate` **no** llevan `mcp__azure-devops` en sus herramientas.
  El survey no necesita Azure DevOps: el brief le llega inline en el prompt.
- `brief` sí lo lleva.
- Un ticket **sin** extras no ofrece `brief`/`survey`/`consolidate` en `fases`.
- Un ticket **con** extras no ofrece `analyze`.

Expected: fallan.

- [ ] **Step 2: Implementar**

Añadir las tres entradas. `PHASE_ALLOWED_TOOLS`:

```python
# `survey` corre enraizado en un repo secundario y sin MCP a propósito: el brief le
# llega inline en el prompt, así que no necesita ADO_ORG, ni token, ni
# .claude/ticket-agent.json en ese repo.
"survey": [],
"consolidate": [],
```

Y en `phases_for`, filtrar por si el ticket tiene extras. **Las dos ramas producen
`docs/tickets/<id>-analysis.md`**, así que la Fase 2 no se entera de cuál se usó.

Expected: los tests pasan.

- [ ] **Step 3: Commit**

```bash
git add apps/orchestrator/backend/
git commit -m "feat(runner): fases brief, survey y consolidate"
```

---

### Task 6: El fan-out de `survey`

Depende de las tareas 4 y 5. Es el cambio de fondo del runner.

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `repos_a_sondear` (Tarea 4), `PHASE_COMMANDS["survey"]` (Tarea 5).
- Produces: `logs/<run_id>/` con un survey por repo enrutado.

- [ ] **Step 1: Escribir los tests que fallan**

| Caso | Esperado |
|---|---|
| Brief con `SONDEAR: back, front` | **dos** subprocesos, uno con `cwd` en cada repo |
| Cada hijo | lleva `--add-dir <logs>/<run_id>` y **no** lleva `--add-dir` de los otros repos |
| Cada hijo | recibe el brief **inline en el prompt** |
| Un hijo falla | los demás siguen; la corrida cierra `parcial` nombrando cuál |
| Sin archivo de brief | la fase no arranca: `HUELLA: nada` con motivo legible |
| El log | lleva una cabecera por repo y los hijos concatenados en orden |

Expected: fallan.

- [ ] **Step 2: Implementar**

Secuencial, bajo el lock que ya existe. **Un solo `logs/<run_id>.log`** con cabecera
por repo, **una sola fila en `runs`**: nada de esquema nuevo, nada que cambiar en la
UI de historial.

El hijo hereda el entorno del backend igual que hoy (sin las variables de Anthropic).
No se le pasa `ADO_ORG` ni nada de MCP: no lo necesita.

Un fallo de un hijo **no aborta el resto**. La corrida cierra `parcial` con la lista
de fallidos, que es lo que la Tarea 9 (consolidación) necesita para poder escribir
`No sondeado: <label> (la sesión falló)`.

Expected: los seis tests pasan.

- [ ] **Step 3: Verificar el escenario de un solo repo**

Con `SONDEAR: back` (una etiqueta), el runner **no** hace fan-out. Comprobar que ese
camino no crea el directorio scratch ni lanza hijos.

- [ ] **Step 4: Commit**

```bash
git add apps/orchestrator/backend/
git commit -m "feat(runner): una sesion de survey por repo enrutado"
```

---

### Task 7: La skill `ticket-brief` y su comando

Primera tarea de plugin. El backend ya está entero y probado sin ella.

**Files:**
- Create: `plugins/ticket-agent/skills/ticket-brief/SKILL.md`
- Create: `plugins/ticket-agent/commands/brief.md`

**Interfaces:**
- Produces: `docs/tickets/<id>-brief.md` con la línea `SONDEAR:`, que la Tarea 6
  parsea, y la sección `## Decisiones para ti`.

- [ ] **Step 1: Escribir la skill**

Es el `ticket-comprehension` de hoy **recortado**: recolecta el work item con sus
relaciones, comentarios, adjuntos y wiki, y enruta. **No analiza código** — de eso se
encargan los surveys, cada uno con las reglas de su repo cargadas.

Cuatro cosas no negociables:

1. **Tope de ~4 KB.** El brief viaja inline en el prompt de cada hijo: su coste se
   paga N veces. Si no cabe, hay algo copiado que debería resumirse.
2. **Los criterios de aceptación van literales.** Los surveys no pueden volver al
   work item; lo que el brief no diga, no existe para ellos.
3. **La línea `SONDEAR:`**, con las etiquetas exactas que el prompt le dio.
4. **El sesgo, escrito literal en la skill:** «incluye cualquier repo sobre el que
   tengas duda razonable; sondear uno de más cuesta una sesión, omitir uno que
   importaba cuesta el ticket entero, y nada aguas abajo lo detecta».

Cierra con `HUELLA: ok — docs/tickets/<id>-brief.md`.

- [ ] **Step 2: Escribir el comando** `commands/brief.md`, delegando a la skill.

- [ ] **Step 3: Check**

```bash
claude plugin validate .
```

Expected: pasa. Y comprobar a mano que la línea `SONDEAR:` del **ejemplo** dentro de
la skill no rompe el parser: por eso ancla en el último match.

- [ ] **Step 4: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "feat(plugin): skill ticket-brief, recoleccion y enrutado"
```

---

### Task 8: La skill `repo-survey` y su comando

El corazón del diseño.

**Files:**
- Create: `plugins/ticket-agent/skills/repo-survey/SKILL.md`
- Create: `plugins/ticket-agent/commands/survey.md`

**Interfaces:**
- Consumes: el brief, inline en el prompt.
- Produces: `<scratch>/survey-<label>.md` con las secciones `Espero de otros` y
  `Ofrezco a otros`, que la Tarea 9 cotejará.

- [ ] **Step 1: Escribir la skill con su esqueleto exacto**

Ocho secciones: `Veredicto`, `Qué exige de este repo`, `Rutas afectadas`,
`Espejo a copiar`, `Reglas de este repo que aplican`, `Espero de otros`,
`Ofrezco a otros`, `No pude determinar`.

Cuatro reglas, cada una con su motivo escrito en la propia skill:

1. **`Veredicto` en una palabra, primero** (`touched` / `not-touched`). Hace barato
   equivocarse enrutando de más: el consolidador descarta sin leer el resto.
2. **Cada afirmación es `[verificado <file:line>]` o `[asumido]`.** No es
   decoración: los `asumido` son exactamente los candidatos a contrato roto. Aplica
   la Regla de Oro 5 de `change-planning` — decir «no existe espejo» exige nombrar
   la búsqueda hecha.
3. **`No pude determinar` es obligatorio.** Es la ceguera declarada de esa sesión y
   la materia prima de las preguntas del consolidador. Un survey que dice saberlo
   todo sobre un ticket cruzado miente.
4. **No propone solución.** Ni tareas ni diseño: eso es Fase 2. Mezclarlo hace que
   el consolidador reciba N planes parciales incompatibles en vez de N
   observaciones.

Y: **read-only sobre el código**. Solo escribe su survey en la ruta que le dan.

- [ ] **Step 2: Escribir el comando** `commands/survey.md`.

- [ ] **Step 3: Check**

```bash
claude plugin validate .
```

Expected: pasa.

- [ ] **Step 4: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "feat(plugin): skill repo-survey, que exige el ticket de ESTE repo"
```

---

### Task 9: La skill `analysis-consolidation` y su comando

**Files:**
- Create: `plugins/ticket-agent/skills/analysis-consolidation/SKILL.md`
- Create: `plugins/ticket-agent/commands/consolidate.md`

**Interfaces:**
- Consumes: el brief, los surveys, y **la lista completa de repos montados** (no
  solo los sondeados).
- Produces: `docs/tickets/<id>-analysis.md` — misma ruta y misma estructura que hoy,
  más la tabla de contrato y los surveys de apéndice. La Fase 2 la consume sin
  cambios.

- [ ] **Step 1: Escribir la skill**

La tabla de contrato, con sus cuatro veredictos (`✅ cuadra`, `❌ hueco`,
`⚠️ duplicado`, `❓ sin resolver`), producida cotejando `Espero` contra `Ofrezco`.

**Regla dura: si no puede producir la tabla, cierra `HUELLA: parcial`, no `ok`.**
Sin ella, el modo de fallo silencioso de toda la arquitectura es un consolidador
perezoso que pega N documentos, y nadie se entera hasta que el PR no compila.

Obligatorias también:
- La línea `No sondeados: <labels>` siempre que haya repos montados sin sondear.
- `No sondeado: <label> (la sesión falló)` para los que murieron, y `parcial`.
- Los surveys de apéndice, para que el humano tenga **un solo documento en el repo**
  con todo.
- Las filas `❌ hueco` y `❓ sin resolver` **se convierten en `DECIDIR`** en la
  sección `Decisiones para ti`. Son literalmente las preguntas que ningún repo pudo
  contestar solo.

- [ ] **Step 2: Escribir el comando** `commands/consolidate.md`.

- [ ] **Step 3: Check**

```bash
claude plugin validate .
```

- [ ] **Step 4: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "feat(plugin): skill analysis-consolidation y tabla de contrato"
```

---

### Task 10: `DECIDIR` y `BLOQUEA` en las skills existentes

**Files:**
- Modify: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`
- Modify: `plugins/ticket-agent/skills/change-planning/SKILL.md`
- Modify: `plugins/ticket-agent/skills/change-implementation/SKILL.md`

**Interfaces:**
- Produces: la sección `## Decisiones para ti` en los tres entregables, y el
  tratamiento de los marcadores sin responder. La Tarea 14 (UI) los cuenta.

- [ ] **Step 1: La sección, en las tres**

```markdown
## Decisiones para ti

- [ ] **DECIDIR** — <la pregunta>
      Propuesta: <la propuesta, con su file:line si aplica>
      Si no respondes, sigo con la propuesta.

- [ ] **BLOQUEA** — <la pregunta>
      <por qué no hay default defendible>
```

- [ ] **Step 2: El tratamiento de los no respondidos**

| Marca | Sin responder |
|---|---|
| `DECIDIR` | La fase siguiente sigue con la propuesta **y lo registra por escrito** |
| `BLOQUEA` | No arranca: `HUELLA: nada — <N> decisiones sin resolver` |

**`BLOQUEA` solo cuando no existe default defendible**, y la marca dice por qué
ninguno lo es. Si cada ambigüedad bloquea, la herramienta deja de ayudar y se
convierte en un formulario.

`DECIDIR` no bloquea nunca — pero seguir con la propuesta **sin dejar rastro** es
peor que bloquear.

- [ ] **Step 3: `autonomy` por fin gobierna algo**

En `change-planning` y `change-implementation`:

- `supervised` → un `DECIDIR` sin responder **detiene** la fase.
- `autonomous` → sigue con las propuestas y las registra.
- Cualquier otro valor → `supervised`, con aviso.
- `BLOQUEA` detiene en ambos modos.

- [ ] **Step 4: La línea de recomendación de continuación**

Una línea en el resumen de cierre de las tres, **antes de la estampa** —
`STAMP_RE` exige que la `HUELLA` sea la última línea del mensaje:

> Exploré N archivos en M repos para llegar a esto. Si vas a corregir mi lectura de
> X (donde dudé), sesión nueva. Si vas a añadir alcance, continuar te ahorra la
> exploración.

Dos datos que el humano no tiene: cuánto costaría rehacerlo y dónde dudó el agente.
**No se hace parseable**: la UI no preselecciona nada leyéndola.

- [ ] **Step 5: Check**

```bash
claude plugin validate .
```

Y comprobar a mano que las tres skills siguen cerrando con la `HUELLA` como última
línea en sus ejemplos.

- [ ] **Step 6: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "feat(plugin): marcadores DECIDIR y BLOQUEA, y autonomy los gobierna"
```

---

### Task 11: README del plugin

**Files:**
- Modify: `plugins/ticket-agent/README.md`

- [ ] **Step 1:** Documentar las tres fases nuevas, cuándo aplican (proyectos de 2+
  repos) y que las dos ramas producen el mismo `<id>-analysis.md`.
- [ ] **Step 2:** Documentar `DECIDIR`/`BLOQUEA` y cómo se responden (editando el
  archivo, marcando la casilla).
- [ ] **Step 3:** Documentar que `autonomy` ahora decide qué pasa con un `DECIDIR`
  sin responder.
- [ ] **Step 4: Commit**

```bash
git add plugins/ticket-agent/README.md
git commit -m "docs(plugin): las tres fases nuevas y los marcadores de decision"
```

---

### Task 12: `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1:** El mecanismo del reparto: por qué existe (la tabla de qué carga
  `--add-dir`), por qué solo la Fase 1, y por qué los hijos no llevan MCP.
- [ ] **Step 2:** El contrato `SONDEAR:`, junto a los demás literales, con la nota
  de que ancla en el último match por el mismo motivo que `STAMP_RE`.
- [ ] **Step 3:** El resume: que no se reenvía el comando slash, y por qué el
  recordatorio de la estampa no es opcional.
- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: el mecanismo del reparto multi-repo y de la continuacion"
```

---

### Task 13: Subir la versión — los dos sitios

**Va después de todas las tareas de plugin, nunca antes.** La versión es la clave de
caché: `claude plugin update` no trae nada si no cambia, y un cambio commiteado aquí
nunca llega al plugin instalado.

**Files:**
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json`
- Modify: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`

- [ ] **Step 1:** Subir `version` en `plugin.json`.
- [ ] **Step 2:** Subir el sello `by ticket-agent vX.Y.Z` de la plantilla de análisis
  en `ticket-comprehension/SKILL.md`. **Es el sitio que se desincroniza en
  silencio** — estuvo en `v0.5.2` mientras el plugin iba por `v0.7.1`.
- [ ] **Step 3: Check**

```bash
claude plugin validate .
grep -rn "ticket-agent v" plugins/ticket-agent/skills/
```

Expected: la versión del sello coincide con la de `plugin.json`.

- [ ] **Step 4: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "chore(plugin): sube version, los dos sitios"
```

---

### Task 14: UI — el contador de decisiones

**Sin esto el mecanismo entero se cae**: las secciones `Decisiones para ti` no las
lee nadie si nada avisa de que existen.

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Modify: `apps/orchestrator/frontend/src/Timeline.tsx`

- [ ] **Step 1:** El backend cuenta los `- [ ] **DECIDIR**` y `- [ ] **BLOQUEA**`
  sin marcar en el entregable que la corrida declaró, y los expone en la fase.
  Reusa el mismo camino que `/artefacto?ruta=` ya usa para localizar el archivo.
- [ ] **Step 2:** Test: un entregable con 3 `DECIDIR` (uno ya marcado `[x]`) y 1
  `BLOQUEA` reporta `2 decisiones · 1 bloquea`.
- [ ] **Step 3:** `Timeline.tsx` lo pinta junto al estado de la fase:
  `analyze ✓ ok · 3 decisiones · 1 bloquea`, enlazando al documento.
- [ ] **Step 4: Check**

```bash
npm run build && npm run lint
```

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/
git commit -m "feat(ui): cuenta las decisiones pendientes de cada fase"
```

---

### Task 15: UI — pasar el ajuste y elegir cómo se aplica

**La caja de ajuste ya existe**: `Timeline.tsx` tiene una plegable por fase
(`ajuste-<fase>`) con un `Textarea` y el botón «Correr con este ajuste». Lo que falta
es que ese mismo envío lleve **la decisión de cómo aplicarlo**, y que la decisión
llegue al backend — hoy `api.ts` no tiene por dónde mandarla.

**Files:**
- Modify: `apps/orchestrator/frontend/src/api.ts`
- Modify: `apps/orchestrator/frontend/src/Timeline.tsx`

**Interfaces:**
- Consumes: `puede_continuar` y `continuaciones` de cada fase (Tarea 3, Step 3).
- Produces: el cuerpo de `POST` lleva `resume: boolean` (Tarea 3, Step 2).

- [ ] **Step 1: El transporte, primero**

En `api.ts`:

- El tipo `Phase` gana `puede_continuar: boolean` y `continuaciones: number`.
- `run(id, instructions?, phase, resume = false)` incluye `resume` en el cuerpo.

Sin este paso el checkbox se pinta y no hace nada, que es peor que no tenerlo.

- [ ] **Step 2: El control, dentro de la caja de ajuste**

Un radio de dos opciones —no un checkbox suelto— porque son dos caminos excluyentes
y conviene que se lean juntos:

```
○ Sesión nueva          (por defecto)
○ Continuar la anterior     3ª continuación
```

«Continuar la anterior» **deshabilitada** cuando `puede_continuar` es `false`, con
`title` explicando por qué (no hay sesión previa de esta fase, o el repo cambió).
El contador solo se pinta si `continuaciones > 0`.

**Por defecto, sesión nueva.** Es el camino seguro: una continuación arrastra el
razonamiento que quizá estás corrigiendo.

- [ ] **Step 3: El criterio, en una línea bajo el control**

Es la decisión que solo el humano puede tomar, así que se dice en la UI y no se deja
al recuerdo:

> Si **añades** alcance, continuar ahorra la exploración. Si **corriges** lo que
> entendió, sesión nueva.

- [ ] **Step 4: El reset**

El botón ya limpia `instructions` y cierra la caja al enviar (`Timeline.tsx:238`).
El estado del radio **se resetea igual**, y también al cambiar de `openPhase`: el
estado es único y compartido entre fases, así que sin resetear, la elección hecha en
`analyze` reaparece marcada en `implement`.

- [ ] **Step 5:** El botón sigue deshabilitado sin texto de ajuste. Continuar una
  sesión sin decirle nada nuevo no hace nada: la condición actual es la correcta y
  no se toca.

- [ ] **Step 6: Check**

```bash
npm run build && npm run lint
```

Y a mano, con el backend levantado: lanzar una fase, luego reabrir su caja de ajuste
y comprobar que «Continuar la anterior» ya está habilitada y que el log de la
segunda corrida muestra `--resume` en la línea del comando.

- [ ] **Step 7: Commit**

```bash
git add apps/orchestrator/frontend/
git commit -m "feat(ui): el ajuste elige entre sesion nueva o continuar la anterior"
```

---

### Task 16: La prueba real de dos repos

**No es opcional, y no es una demo.** Es lo único que mide la hipótesis central del
diseño, declarada sin verificar en la sección 15 del spec.

**Files:**
- Modify: `docs/STATUS.md`
- Modify: `docs/superpowers/specs/2026-08-12-multirepo-fanout-y-humano-en-el-bucle-design.md`
  (sección 15)

- [ ] **Step 1:** Dar de alta un proyecto de dos repos con etiquetas reales y correr
  `brief` sobre un ticket que toque los dos. **3320** es el candidato conocido: su
  código vive en un `extra_dir`, y sigue siendo la gran suposición sin ejercitar de
  la Fase 2b.
- [ ] **Step 2:** Revisar el enrutado **antes** de lanzar `survey`. Anotar si acertó
  y, si no, qué le faltaba al prompt.
- [ ] **Step 3:** Correr `survey` y `consolidate`. **Lo que se mide es la tabla de
  contrato**: ¿cazó algo que una sesión única no habría visto? Si la tabla sale
  vacía o trivial, el reparto no está pagando su coste y hay que decir por qué.
- [ ] **Step 4:** Comparar con el `analyze` de una sola sesión sobre el mismo ticket
  — el camino sigue existiendo para proyectos de un repo, así que la comparación es
  posible sin revertir nada.
- [ ] **Step 5:** Escribir el resultado en la sección 15 del spec, con fecha, y en
  `STATUS.md`. **Si el reparto no mejora nada, eso también se escribe.**
- [ ] **Step 6: Commit**

```bash
git add docs/
git commit -m "docs: resultado de la primera corrida multi-repo real"
```

---

## Orden y dependencias

```
1 (env var)          ── independiente, valiosa sola
2 (session_id) ──► 3 (resume) ──────────────────► 15 (UI checkbox)
4 (parser)  ─┐
5 (fases)   ─┴──► 6 (fan-out)
                    │
7 (brief) ──► 8 (survey) ──► 9 (consolidate)
                                  │
10 (marcadores) ──────────────────┴──► 14 (UI contador)
11 (README) · 12 (CLAUDE.md)
                    └──► 13 (version, después de TODO lo de plugin)
                              └──► 16 (la prueba real)
```

Las tareas 1-6 son backend puro y se prueban con `fake_claude.py`: **no necesitan que
existan las skills**. Las 7-13 son plugin. Las 14-15, UI.

## Lo que este plan no hace

Está en la sección 14 del spec y se repite aquí para que nadie lo intente a mitad:

- Repartir `plan` e `implement`.
- Ejecutar los hijos en paralelo.
- Sacar los documentos del repo.
- Recuperar hooks y `.mcp.json` de repos extras durante `implement` — **sin
  cobertura posible**, documentado como límite conocido.
