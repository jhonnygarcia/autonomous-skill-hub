# Diseño: multi-repo por sesiones enraizadas y humano en el bucle

**Fecha:** 2026-08-12
**Estado:** **Dirección decidida por Jhonny (2026-08-12)** — un ticket multi-repo
deja de manejarse desde una sola sesión. La Fase 1 se reparte en una sesión
enraizada por repo. Pendiente: el plan de implementación en
`docs/superpowers/plans/`.
**Alcance:** plugin `ticket-agent` (Fase 1) + `apps/orchestrator` (runner y UI)

## Propósito

Hoy un ticket que toca varios repos se analiza desde **una sola sesión** enraizada
en el repo principal, con los demás montados por `--add-dir`. Eso funciona para
leer código, pero pierde la configuración agéntica de los repos secundarios: sus
reglas, sus hooks, su MCP. El resultado es un agente que escribe código del front
aplicando las convenciones del back, con total confianza y sin que nada lo detecte.

Este diseño hace dos cosas:

1. **Reparte la Fase 1 en una sesión por repo**, cada una enraizada en el suyo, y
   consolida los hallazgos en un único análisis que incluye lo que ningún repo
   podía ver solo: el contrato entre ellos.
2. **Convierte las costuras entre fases en puntos de decisión humana explícitos**,
   marcados y contados, en vez de dejarlos como prosa que nadie relee.

No cambia las Fases 2 y 3: siguen siendo una sola sesión, y el motivo está en
"Lo descartado".

---

## 1. El problema, medido

### 1.1 Qué carga realmente `--add-dir`

Verificado en la documentación oficial (tabla de excepciones de
`/docs/en/permissions`), no deducido:

| Configuración del repo montado | ¿Se carga? |
|---|---|
| `.claude/skills/` | **Sí**, con recarga en vivo |
| `.claude/agents/` (subagentes) | **Sí** |
| `.claude/settings.json` | Solo las claves `enabledPlugins` y `extraKnownMarketplaces` |
| `CLAUDE.md`, `.claude/rules/`, `CLAUDE.local.md` | **No**, salvo con `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` |
| `.claude/commands/`, output styles | **No** |
| Hooks (dentro de `settings.json`) | **No** |
| `.mcp.json` | **No** |

Conclusiones que ordenan el resto del diseño:

- **Skills y agents ya viajan hoy.** Cualquier preocupación por colisión de skills
  entre repos es sobre el estado actual, no sobre este cambio.
- **Las reglas del proyecto no viajan.** Es la pérdida que más duele y la que
  motiva el reparto.
- **Hooks y `.mcp.json` no viajan por ninguna vía.** Ninguna variable de entorno
  los recupera. Solo una sesión enraizada en ese repo los tiene.

### 1.2 El coste de cargar de más

Medido sobre este repo:

```
CLAUDE.md (de los gordos)        17,3 KB   ~4.800 tokens
SKILL.md change-implementation   11,4 KB   ~3.150 tokens
frontmatter de una skill          0,4 KB     ~112 tokens   ← lo único que carga hasta invocarse
```

Un `CLAUDE.md` extra son ~10-15% más de prefijo cacheado. Una tarea reintentada en
Fase 2b son 50-150k tokens **no** cacheados. **No cargar las reglas sale más caro
que cargarlas**, y por goleada. El coste solo vuelve a ser decisión con 5+ repos
montados y `CLAUDE.md` grandes.

Una skill cuesta ~112 tokens hasta que se invoca: el volumen de skills nunca es el
problema. El riesgo es de **nombres y descripciones ambiguas**, y se mitiga en los
repos cliente (que las descripciones digan el stack), no aquí.

---

## 2. Decisiones de arquitectura

| Decisión | Elección | Por qué |
|---|---|---|
| Reparto | Solo Fase 1 | Es independiente por repo y read-only. `plan` es el contrato y `implement` tiene orden entre repos |
| Ejecución de los hijos | Secuencial, bajo el mismo lock global | Un solo log, una fila en `runs`, cero cambios de esquema. Paralelizar es optimización posterior |
| Quién lanza los hijos | El runner | Que lo hiciera el agente por `Bash` los dejaría fuera del log, del lock y del sandbox |
| Traspaso del brief a los hijos | **Inline en el prompt** | Un hijo no puede leer el repo principal sin montarlo, y montarlo le filtra configuración de vuelta |
| MCP en los hijos | **Ninguno** | El brief lleva el ticket. Los hijos no necesitan `ADO_ORG`, ni token, ni `ticket-agent.json` |
| Salida de los hijos | Directorio scratch del runner, montado con `--add-dir` | Sin `.claude/` dentro, no filtra configuración. No ensucia repos cliente |
| Formato del enrutado | Una línea con palabra clave, regex, último match | Mismo patrón que `HUELLA` (`app.py:171`), probado. JSON generado por LLM falla en el peor punto posible |
| Dirección del fallo | Ante cualquier duda, **sondear de más** | Un repo de más cuesta una sesión; uno de menos cuesta el ticket, y nadie lo detecta |
| Documentos | **Se quedan en el repo** | Descartada la ruta externa configurable (ver "Lo descartado") |
| Decisiones abiertas | Marcadores `DECIDIR` / `BLOQUEA` en los entregables | El humano no puede intervenir a media corrida (headless); sí entre fases |
| Continuación de sesión | Opcional, decisión del humano desde la UI | Solo el humano sabe si su ajuste **añade** o **corrige** |

---

## 3. El flujo completo

```
  ¿el proyecto tiene extra_dirs?
  │
  ├── no ──► [analyze]  ── el de hoy, sin cambios ──► docs/tickets/<id>-analysis.md
  │
  └── sí
       │
       ▼
   [1a] BRIEF                    cwd = principal · MCP sí
        /ticket-agent:brief <id>
        lee work item, relaciones, adjuntos, comentarios, wiki
        → docs/tickets/<id>-brief.md
          · qué pide el ticket + criterios de aceptación literales
          · ambigüedades
          · sección "Decisiones para ti"
          · línea SONDEAR:
       │
       │   ◆ CHECKPOINT HUMANO ─ revisas el brief, editas la línea SONDEAR
       ▼
   [1b] SURVEY  (uno por repo enrutado, secuencial)
        cwd = <repo>  ·  MCP no  ·  brief inline en el prompt
        /ticket-agent:survey <id>
        → <scratch>/<run_id>/survey-<label>.md
       │
       ▼
   [1c] CONSOLIDATE              cwd = principal · MCP no
        /ticket-agent:consolidate <id>
        lee el brief + todos los surveys
        → docs/tickets/<id>-analysis.md   ← misma ruta que hoy
          · la tabla de contrato entre repos
          · los surveys como apéndice
          · "Decisiones para ti"
       │
       │   ◆ CHECKPOINT HUMANO
       ▼
   [2] plan  ──►  [3] implement       sin cambios estructurales
```

**Propiedad clave: aguas abajo no cambia nada.** Las dos ramas producen
`docs/tickets/<id>-analysis.md`, que es la precondición de la Fase 2. El plugin y
el runner de las fases 2 y 3 no se enteran de cuál de los dos caminos se usó.

---

## 4. Fase 1a — brief y enrutado

### 4.1 Qué es y qué no es

Es el `ticket-comprehension` de hoy **recortado**: recolecta el work item y decide
el enrutado. **No analiza código** — de eso se encargan los surveys, cada uno con
las reglas de su repo cargadas.

### 4.2 Disciplina de tamaño

El brief **viaja inline en el prompt de cada hijo**, así que su coste se paga N
veces. Un ticket con 15 relaciones y 4 adjuntos puede producir 40 KB.

**Tope: ~4 KB.** Si no cabe, hay algo copiado que debería resumirse. Es un brief,
no el análisis.

### 4.3 Los criterios de aceptación van literales

Los surveys **no pueden volver al work item**. Lo que el brief no diga, no existe
para ellos. Es el mismo cuello de botella que ya hay entre `analyze` y `plan`,
ahora multiplicado por N — y por eso cada omisión aquí cuesta más que en ningún
otro documento del sistema.

### 4.4 La línea de enrutado

```
SONDEAR: back, front
```

- Un regex, mismo tratamiento que `HUELLA`: **último match gana**, porque el
  cuerpo de la skill viaja por el log y contiene el literal.
- Las etiquetas se cotejan contra las que el prompt le dio (`repos_text`), sin
  distinguir mayúsculas.
- **Se parsea la lista de etiquetas y nada más.** Se descarta llevar `write`/`read`
  por repo: el runner no actúa sobre ese dato (los surveys son read-only todos, y
  `prepare_repos` ya ramifica todos los repos a propósito). Parsear un dato sobre
  el que no se actúa es superficie de fallo regalada. El matiz leer/escribir va en
  la prosa del brief, que el consolidador sí lee.

**Degradación, en este orden:**

| Situación | Qué hace el runner |
|---|---|
| Línea ausente | Sondea **todos** los repos montados, y lo escribe en el log |
| Alguna etiqueta no casa | Sondea **todos**, y lo escribe en el log |
| Una sola etiqueta | **No hace fan-out**: cae al `/ticket-agent:analyze` de hoy |
| Lista válida de 2+ | Sondea esos |

Un fallo de parseo es un problema de **coste**, nunca de **corrección**. No existe
ningún camino por el que el sistema se estreche solo.

### 4.5 El enrutado es una optimización, no una garantía

Un survey de un repo irrelevante devuelve `Veredicto: not-touched` y se acabó. Con
2-3 repos, enrutar ahorra una sesión barata; con 6 empieza a importar.

De ahí que **no pueda ser una pieza de la que dependa la corrección**, y que no
merezca un mecanismo frágil.

### 4.6 El prompt inclina la balanza explícitamente

No "decide qué repos aplican", sino, literal en la skill:

> Incluye cualquier repo sobre el que tengas duda razonable. Sondear uno de más
> cuesta una sesión; omitir uno que importaba cuesta el ticket entero, y nada
> aguas abajo lo detecta.

### 4.7 El checkpoint humano sustituye al parseo a media secuencia

El brief es **su propia fase lanzable**. Termina, el humano ve la línea, la edita
si hace falta, y lanza la siguiente fase. El runner la lee **del archivo, al
arrancar**.

Esto elimina la parte más frágil del diseño original: `execute_run` no se convierte
en una máquina de estados con un parseo delicado en el punto de máximo
apalancamiento. La decisión de mayor riesgo del flujo pasa a estar confirmada por
un humano en tres segundos.

---

## 5. Fase 1b — el survey

### 5.1 Contexto de ejecución

| Aspecto | Valor |
|---|---|
| `cwd` | El repo sondeado — **carga su `CLAUDE.md`, sus reglas, sus skills, sus agents, sus hooks y su `.mcp.json`** |
| MCP de Azure DevOps | **No.** No lo necesita y no se configura |
| Entrada | El brief, inline en el prompt |
| Salida | `<scratch>/<run_id>/survey-<label>.md`, vía `--add-dir` |
| Escritura en su propio repo | **Prohibida.** Es read-only sobre el código |

El directorio scratch no tiene `.claude/` dentro, así que montarlo no filtra
configuración: es un buzón, no una raíz.

### 5.2 El esqueleto

```markdown
# Survey <id> — <label> (<ruta del repo>)

## Veredicto
touched            ← o `not-touched`, y el resto queda vacío

## Qué exige de este repo
(2-6 líneas, sin proponer solución)

## Rutas afectadas
- `src/reports/TrendTable.tsx:112` — el botón de export va aquí

## Espejo a copiar
- `src/reports/CsvExport.tsx:1-90` — el patrón equivalente ya existe
  (o: "no encontrado — busqué `Glob **/*Export*.tsx`")

## Reglas de este repo que aplican
- CLAUDE.md:31 — los componentes nuevos no van al barrel export

## Espero de otros
- de `back`: `GET /api/trends/export?format=xlsx` → binario xlsx   [asumido]
- de `back`: el campo `trendId` ya viene en `GET /api/trends`      [asumido]

## Ofrezco a otros
- el botón de export en la vista de tendencias                     [nuevo]

## No pude determinar
- si el back ya pagina esa respuesta — vive fuera de este repo
```

### 5.3 `Espero de otros` / `Ofrezco a otros` — la pieza central

Sin estas dos secciones el consolidador no puede hacer su trabajo y el reparto no
se justifica.

El consolidador tiene que cazar cinco fallos cruzados, y **ninguno es visible desde
un solo repo**:

| Fallo | Ejemplo |
|---|---|
| Contrato desalineado | el front espera un campo que el back no expondrá |
| Doble implementación | ambos formatean la fecha del xlsx |
| Hueco | cada uno asume que el otro valida |
| Orden | el front no puede empezar sin el endpoint |
| Mismo concepto, distinto nombre | `exportId` atrás, `reportKey` adelante |

En prosa libre los cinco son invisibles: dos textos bien escritos que no se
contradicen *aparentemente*. Declarados en forma cotejable, el trabajo del
consolidador deja de ser interpretación y pasa a ser **cotejo**: cada "espero"
busca su "ofrezco". Sin pareja → hueco. Dos ofertas de lo mismo → duplicado.
Nombres distintos para lo mismo → se ven porque quedan juntos en una tabla.

### 5.4 Cuatro reglas sobre el formato, con su motivo

1. **`Veredicto` en una palabra, primero.** Hace barato equivocarse enrutando de
   más: el consolidador descarta un `not-touched` sin leer el resto.
2. **Cada afirmación es `[verificado <file:line>]` o `[asumido]`.** No es
   decoración: **los `asumido` son exactamente los candidatos a contrato roto**, y
   el consolidador los prioriza. Aplica aquí la Regla de Oro 5 de
   `change-planning`: decir "no existe espejo" exige nombrar la búsqueda hecha.
3. **`No pude determinar` es obligatorio y no puede quedar vacío por pereza.** Es
   la ceguera declarada de esa sesión, y es la materia prima de las preguntas del
   consolidador. Un survey que dice saberlo todo sobre un ticket cruzado miente.
4. **El survey no propone solución.** Ni tareas, ni diseño. Eso es Fase 2, y
   mezclarlo hace que el consolidador reciba N planes parciales incompatibles en
   vez de N observaciones.

### 5.5 Estampa

`HUELLA: ok — <scratch>/<run_id>/survey-<label>.md`, igual que cualquier otra fase.
El runner ya sabe verificarla; no hay contrato nuevo.

---

## 6. Fase 1c — la consolidación

### 6.1 Entrada y salida

- **Entrada:** el brief + todos los surveys + **la lista completa de repos
  montados**, no solo los sondeados.
- **Salida:** `docs/tickets/<id>-analysis.md` — la misma ruta de hoy, con la misma
  estructura de hoy, más dos secciones nuevas.

### 6.2 La tabla de contrato — obligatoria

```markdown
## Contrato entre repos

| Qué | Lo espera | Lo ofrece | Veredicto |
|---|---|---|---|
| `GET /api/trends/export` | front | back | ✅ cuadra |
| campo `trendId` en la lista | front | — | ❌ hueco: nadie lo ofrece |
| formateo de fecha del xlsx | — | back + front | ⚠️ duplicado: decidir dónde |
| paginación de la respuesta | front (no pudo determinar) | — | ❓ sin resolver |

No sondeados: auth-app
```

**Regla dura: si el consolidador no puede producir esta tabla, cierra
`HUELLA: parcial`, no `ok`.**

Sin esa regla, el modo de fallo silencioso de toda la arquitectura es un
consolidador perezoso que pega N documentos, y nadie se entera hasta que el PR no
compila. Esta tabla es lo único que ningún survey pudo escribir solo — es lo que
justifica las N sesiones.

### 6.3 La línea `No sondeados`

Obligatoria siempre que existan repos montados sin sondear. Es la red contra el
enrutado sintácticamente perfecto y semánticamente equivocado: un humano leyendo el
análisis ve el hueco. Hoy no lo vería.

### 6.4 Los surveys van de apéndice

El análisis lleva los surveys al final, como apéndice por repo. Así el humano tiene
**un solo documento en el repo** con todo, y el directorio scratch queda
desechable. Es también lo que permite que los documentos sigan viviendo en el repo
sin que los hijos tengan que escribir en él.

### 6.5 Fallo parcial

Si un survey murió, el consolidador recibe N-1 y **tiene que saberlo**: recibe la
lista de a quién se sondeó y quién falló, y el análisis lleva
`No sondeado: front (la sesión falló)`. Cierra `HUELLA: parcial`.

Sin esto el documento parece completo y **miente por omisión** — el fallo más caro
del sistema, porque la Fase 2 lo consumirá sin saberlo.

---

## 7. El humano en el bucle

### 7.1 La restricción que lo forma

`claude -p` corre sin TTY. **Un agente que se detenga a preguntar se cuelga hasta
el timeout.** "Que el humano decida" no puede significar "el agente pregunta y
espera".

Pero sí hay humano **entre corridas**: cada fase es un proceso separado, con
archivos en disco entre medias, lanzada a mano desde la UI. Las costuras ya
existen. Lo que falta es que señalen dónde mirar.

Hoy, para aportar criterio hay que leer un análisis de 8 KB buscando qué está
flojo. Eso no es participar, es auditar, y nadie lo hace dos veces.

### 7.2 Los marcadores

Cada entregable cierra con una sección de tamaño acotado:

```markdown
## Decisiones para ti

- [ ] **DECIDIR** — ¿el `trendId` lo expone el back o lo calcula el front?
      Propuesta: el back, sigue el patrón de `Controllers/Trends.cs:88`.
      Si no respondes, sigo con la propuesta.

- [ ] **BLOQUEA** — el ticket no dice si el export respeta el filtro activo o
      exporta todo. No hay default seguro: cambia el endpoint.
```

| Marca | Sin respuesta |
|---|---|
| `DECIDIR` | La fase siguiente **sigue con la propuesta y lo registra por escrito** |
| `BLOQUEA` | La fase siguiente no arranca: `HUELLA: nada — <N> decisiones sin resolver` |

La diferencia es si existe un default defendible. **`BLOQUEA` solo cuando no lo
hay**, y la marca debe decir por qué ninguno lo es. Si cada ambigüedad bloquea, la
herramienta deja de ayudar y se convierte en un formulario.

`DECIDIR` no bloquea nunca — pero seguir con la propuesta **sin dejar rastro** es
peor que bloquear: por eso la fase siguiente escribe "seguí con la propuesta, no
fue respondida".

### 7.3 Cómo se responde

Editando el archivo. Se marca la casilla y se escribe debajo:

```markdown
- [x] **DECIDIR** — ¿el `trendId` lo expone el back...?
      Respuesta: el back. Y que venga ya en el listado, no en un endpoint aparte.
```

Es el convenio de casillas que ya usan `tasks.md` y OpenSpec. No se introduce
formato nuevo.

### 7.4 Dónde vive cada marcador

| Documento | Qué se marca |
|---|---|
| `<id>-brief.md` | El enrutado, y las ambigüedades del ticket |
| `<id>-analysis.md` | Las filas `❌ hueco` y `❓ sin resolver` de la tabla de contrato, **convertidas automáticamente en `DECIDIR`** |
| `design.md` (Fase 2) | Las decisiones técnicas y las alternativas descartadas, como propuesta a confirmar |
| `tasks.md` (Fase 2/3) | Ya funciona: editar tareas antes de `implement`, y las `## Review notes` de vuelta |

Las filas de la tabla de contrato son literalmente las preguntas que ningún repo
pudo contestar solo: el sitio exacto donde el conocimiento del humano sobre el
sistema vale más que cualquier exploración.

### 7.5 `autonomy` por fin gobierna algo

El campo de `.claude/ticket-agent.json` es hoy casi decorativo. Pasa a decidir el
tratamiento de los `DECIDIR` sin responder:

- **`supervised`** → un `DECIDIR` sin responder **detiene** la fase siguiente.
- **`autonomous`** → sigue con las propuestas y las registra.

Cualquier otro valor sigue tratándose como `supervised`, con aviso. `BLOQUEA`
detiene en ambos modos.

### 7.6 Lo mínimo en la UI

El mecanismo se cae entero si el humano no ve que hay algo que decidir. En
`Timeline.tsx`, junto al estado de cada fase:

```
analyze   ✓ ok      3 decisiones · 1 bloquea
plan      —
```

Y que el enlace abra el documento — `/artefacto?ruta=` ya sirve lo que una corrida
declaró haber escrito, así que la plomería está puesta.

**Este contador es el cambio más rentable de todo el diseño**: sin él, las
secciones `Decisiones para ti` no las lee nadie.

---

## 8. Continuación de sesión (resume)

### 8.1 Verificado, no supuesto

Comprobado en esta máquina el 2026-08-12:

```
sesión 1:  0b57a98d-e414-4323-810f-167981fc9424   "el código secreto es TULIPAN-49"
resume  →  b1803559-8518-43ae-aebb-0bae36f79db3   (id nuevo; la original intacta)
           recordó TULIPAN-49 sin leer ningún archivo
```

`-p` + `--resume <id>` + `--fork-session` funciona headless. Y el `session_id` ya
está en los logs actuales desde el primer evento (`logs/1.log`), único y estable
durante toda la corrida: capturarlo es un regex sobre un stream que el runner ya
lee.

### 8.2 La decisión es del humano

| El ajuste | Modo | Por qué |
|---|---|---|
| **Añade** — "mira también el repo de auth" | continuar | conserva lo explorado; una sesión fresca lo repite todo |
| **Corrige** — "leíste mal el criterio 3" | nueva | la versión del humano no compite con 40 turnos de razonamiento propio |

**El agente no puede clasificar esto**: no sabe si lo que le dicen es información
nueva o una enmienda. Es la decisión humana por definición.

El riesgo de reanudar cuando había que corregir es concreto: **el contexto que se
reaprovecha contiene el error que se está corrigiendo**, y compite con la
corrección respaldado por todo el razonamiento previo.

### 8.3 El detalle que lo rompería

**Al reanudar no se reenvía el comando slash.** Hoy el prompt es
`/ticket-agent:analyze <id>` + `repos_text` + `adjustment_text`. Mandar eso a una
sesión reanudada hace que el agente **reinicie el procedimiento desde el paso 1**:
relee el work item, vuelve a explorar y reescribe el entregable. Se pierde justo lo
que se venía a aprovechar, y puede duplicar la salida.

El prompt de continuación es:

```
<ajustes del humano>

Close with the same HUELLA line as always, the last one of the message.
```

Ese recordatorio **no es opcional**: el runner exige la estampa en toda corrida.
Sin él, la continuación cierra sin estampa y se marca como error aunque el trabajo
esté bien.

`repos_text` se omite: ya está en su contexto.

**Los flags no se omiten.** `--add-dir`, `--allowedTools` y `--settings` van igual
que en la corrida original: son permisos por invocación, no contexto. Quitarlos
deja al agente sin acceso de escritura a los extras a mitad de conversación.

### 8.4 Guardas

- **Sin sesión previa** → corre fresca y lo dice en el log. Nunca en silencio.
- **`repo_path` distinto al de la corrida anterior** → no se ofrece continuar. Las
  sesiones de Claude Code viven por directorio. Es un `if` con datos que la tabla
  `runs` ya tiene.
- **Siempre `--fork-session`.** Cada corrida guarda su `session_id` propio y de
  cuál vino: la cadena queda trazable y siempre se puede volver atrás.
- **Sin tope duro de continuaciones.** La UI muestra "3ª continuación"; el humano
  decide. El riesgo real —compactación silenciosa al acumular contexto— se gestiona
  viéndolo, no prohibiéndolo. Una sesión reanudada muchas veces puede haber
  compactado y perdido el texto original del ticket, y entonces el resume "barato"
  produce peor resultado sin que se note desde fuera.
- **El modelo puede cambiar entre continuaciones** si se editó en Settings: el
  contexto es texto y sobrevive, pero conviene saberlo.

### 8.5 El lado del plugin

La skill **no puede preguntar a media corrida**. Lo que sí puede es dar al humano
lo que le falta para decidir, en una línea del resumen de cierre:

> Exploré 14 archivos en 3 repos para llegar a esto. Si vas a corregir mi lectura
> del criterio 2 (donde dudé), sesión nueva. Si vas a añadir alcance, continuar te
> ahorra la exploración.

Dos datos que el humano no tiene: **cuánto costaría rehacerlo** y **dónde dudó el
agente**.

Va en el resumen, **nunca en la estampa**: `STAMP_RE` exige que la `HUELLA` sea la
última línea del mensaje.

**No se hace parseable.** Nada de que la UI preseleccione la casilla leyendo una
marca: sería un contrato más que mantener para ahorrar un clic, y ya hay dos
contratos frágiles en el sistema.

---

## 9. Las Fases 2 y 3 siguen en una sola sesión

| Fase | Reparto | Por qué |
|---|---|---|
| `plan` | No | **El plan es el contrato entre repos.** Dos agentes planificando producen dos planes que se contradicen, y el orden de tareas cruza repos (migración antes de usarla, endpoint antes de la llamada) |
| `implement` | No | El front no vería el endpoint que el back acaba de escribir |

**Pero `implement` sí necesita las reglas de los repos extras**, y por eso, aunque
haya fan-out en la Fase 1, hace falta además:

```python
# app.py, construcción del entorno del subproceso
if extras and phase == "implement":
    env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] = "1"
```

Carga `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md` y `CLAUDE.local.md` de
cada directorio montado. Solo en `implement` porque es donde importa que el agente
**obedezca** las reglas mientras escribe; en Fase 1 los surveys ya las metieron por
escrito en el análisis. El condicional no es cosmético: sin extras la variable no
hace nada, y así el log dice por qué está.

**Lo que sigue sin cubrirse en `implement`:** los hooks y el `.mcp.json` de los
repos extras. Ninguna configuración los recupera. Si un repo extra tiene un hook de
seguridad real, hay que replicarlo en el principal a mano.

---

## 10. Cambios por componente

### 10.1 Plugin `ticket-agent`

| Artefacto | Cambio |
|---|---|
| `commands/brief.md` + `skills/ticket-brief/` | **Nuevo.** El `ticket-comprehension` recortado: recolecta y enruta, no analiza código |
| `commands/survey.md` + `skills/repo-survey/` | **Nuevo.** El corazón: qué exige el ticket de ESTE repo, bajo SUS reglas. Sin MCP |
| `commands/consolidate.md` + `skills/analysis-consolidation/` | **Nuevo.** Funde surveys y produce la tabla de contrato |
| `skills/ticket-comprehension/` | Se mantiene para proyectos de un repo. Añade la sección `Decisiones para ti` |
| `skills/change-planning/` | `design.md` marca sus decisiones como `DECIDIR`. Respeta `BLOQUEA` del análisis |
| `skills/change-implementation/` | Respeta `BLOQUEA`. Registra los `DECIDIR` no respondidos |
| Las tres skills existentes | Una línea de recomendación de continuación en el cierre, antes de la estampa |
| `.claude-plugin/plugin.json` | **Subir `version`** |
| `skills/ticket-comprehension/SKILL.md` | **Subir el sello `by ticket-agent vX.Y.Z`** de la plantilla — el segundo sitio, el que se desincroniza en silencio |

### 10.2 Backend (`app.py`)

| Cambio | Detalle |
|---|---|
| `PHASES`, `PHASE_COMMANDS`, `PHASE_ALLOWED_TOOLS`, `PHASE_DONE`, `PHASE_NOUN` | Tres entradas nuevas: `brief`, `survey`, `consolidate`. El `assert` de que las cuatro tablas comparten claves sigue valiendo |
| Herramientas por fase | `brief`: como `analyze` (MCP, sin extras). `survey` y `consolidate`: **sin MCP**, solo lectura + escritura del entregable |
| Selección de camino | Proyecto con 1 repo → `analyze`. Con 2+ → `brief` → `survey` → `consolidate`. Ambos producen `<id>-analysis.md` |
| Lectura del enrutado | Del archivo `<id>-brief.md` al lanzar `survey`, no del log ni a media corrida |
| `survey` como fase multi-hijo | Un subproceso por repo enrutado, **secuencial**, bajo el lock que ya existe. Un solo `logs/<run_id>.log` con cabecera por repo. Una sola fila en `runs` |
| Directorio scratch | `logs/<run_id>/`, creado por el runner, montado en cada hijo con `--add-dir` |
| `runs.session_id` | Nueva columna nullable. Regex sobre el stream que ya se lee |
| `runs.resumed_from` | Nueva columna nullable. La cadena de continuaciones |
| Endpoint de lanzar fase | Acepta `resume: bool` |
| Construcción de prompt y argv | Bifurca en `resume`: sin comando slash, sin `repos_text`, con recordatorio de estampa, con los mismos flags |
| Entorno | `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` si `extras` y fase `implement` |

### 10.3 Frontend

| Cambio | Detalle |
|---|---|
| `Timeline.tsx` | Contador de decisiones por fase: `3 decisiones · 1 bloquea` |
| `Timeline.tsx` | **La caja de ajuste ya existe** (`ajuste-<fase>`, con su `Textarea` y su botón). Gana un radio de dos opciones —*sesión nueva* por defecto, *continuar la anterior* deshabilitada si `puede_continuar` es falso— con el contador de continuaciones y el criterio en una línea |
| `api.ts` | El tipo `Phase` gana `puede_continuar` y `continuaciones`; `run()` envía `resume`. Sin esto el control se pinta y no hace nada |
| `Timeline.tsx` | Las tres fases nuevas en el recorrido, solo para proyectos multi-repo |

`puede_continuar` lo calcula el backend, no la UI: es la misma condición que decide
si el resume se aplica o cae a fresca. Duplicarla en el cliente garantiza que las dos
versiones diverjan.

---

## 11. Contratos literales

Se cotejan byte a byte en algún sitio. **No se traducen en ninguna dirección**, y
se lee `STAMP_RE` antes de tocar cualquiera:

- `HUELLA:` y sus valores `ok` / `parcial` / `nada` (más el legado `PLAN:` con
  `validado` / `sin-validar` / `no-escrito`).
- `SONDEAR:` — **nuevo**, mismo tratamiento: último match del log gana.
- `DECIDIR` / `BLOQUEA` — **nuevos**, dentro de casillas `- [ ]` / `- [x]`.
- `docs/tickets/<id>-analysis.md` — la precondición de la Fase 2.
- Rutas `/modelos`, `/artefacto?ruta=`, y claves JSON como `fases`.

Aplica la política de idioma de `CLAUDE.md`: lo **prompt-facing** (el texto que
lee el agente) en inglés y sigue a las skills; lo **UI-facing** (`motivo`, detalles
de `HTTPException`) en español; los **literales de contrato** no se traducen.

---

## 12. Lo descartado, y por qué

| Descartado | Motivo |
|---|---|
| **`routing.json` parseado por el runner** | JSON de un LLM falla de formas aburridas —comas colgantes, valla de markdown, comillas tipográficas— y falla en el paso 1, matando la corrida en la decisión más importante. Una línea con palabra clave ya está probada en este repo |
| **Llevar `write`/`read` en la línea de enrutado** | El runner no actúa sobre ese dato. Parsear lo que no se usa es superficie de fallo regalada |
| **Ruta de documentos configurable fuera del repo** | Se evaluó y se descarta: los documentos se quedan donde están. Evita tocar el chequeo de seguridad de `/artefacto?ruta=`, una columna nueva, `--add-dir` extra, y que las skills dejen de tener la ruta fija. **`openspec/changes/` no podría moverse en ningún caso**: `npx @fission-ai/openspec validate --changes` opera sobre el `openspec/` del repo, y el modelo de OpenSpec es que la spec vive con el código |
| **Fan-out en `plan`** | El plan es el contrato entre repos: repartirlo produce planes contradictorios |
| **Fan-out en `implement`** | El grupo del front necesitaría montar el back (filtración de configuración de vuelta), y un fallo a mitad deja commits parciales repartidos en dos repos con dos ramas. Fase 2b ya delega cada tarea a un subagente con la ruta destino literal |
| **Hijos en paralelo** | El lock global dejaría de significar algo, `runs` necesitaría `parent_run_id`, y N sesiones concurrentes contra una suscripción es territorio de límites de tasa. Es optimización posterior |
| **Que el agente lance los hijos por `Bash`** | Técnicamente puede (`implement` tiene Bash sin especificador), pero quedan fuera del log, del lock y del sandbox |
| **Subagentes (`Task`) en vez de sesiones** | No cambian la raíz de configuración: un subagente explorando el front sigue sin ver el `CLAUDE.md` del front. No hay atajo |
| **Tope duro de continuaciones de sesión** | Se sustituye por mostrar el contador. Coherente con dejar la decisión al humano |
| **Recomendación de continuación parseable por la UI** | Un contrato más que mantener para ahorrar un clic |
| **Formulario en la UI para responder decisiones** | Significa esquema, validación, sincronización con el archivo y fuente de verdad duplicada, para algo que un editor de texto resuelve. Editando el markdown se puede además añadir contexto que ningún campo previó |
| **Que el agente valide las respuestas del humano** | La herramienta ayuda, no tutela |

---

## 13. Modos de fallo y qué los cubre

| Fallo | Cobertura |
|---|---|
| El enrutado no se parsea | Se sondea todo. Coste, no corrección |
| El enrutado es sintácticamente válido y semánticamente falso | Prompt sesgado a incluir + línea `No sondeados` en el análisis + checkpoint humano sobre el brief |
| Un survey muere | El consolidador recibe la lista de fallidos y lo escribe. `HUELLA: parcial` |
| El consolidador concatena sin consolidar | Sin tabla de contrato → `HUELLA: parcial` |
| Un survey se inventa lo que el otro repo hace | Marca `[asumido]`, y el cotejo `espero`/`ofrezco` lo saca a la superficie |
| Un survey re-corrido se mezcla con uno viejo | Scratch por `run_id`. No se borra nada |
| El brief crece y se paga N veces | Tope de ~4 KB declarado en la skill |
| Una continuación de sesión compacta y pierde el ticket | Contador visible de continuaciones; el humano corta |
| Una continuación reinicia el procedimiento | No se reenvía el comando slash |
| Una continuación cierra sin estampa | Recordatorio explícito en el prompt de continuación |
| Nadie lee las decisiones abiertas | Contador en `Timeline.tsx` |
| Un `DECIDIR` sin responder pasa desapercibido | La fase siguiente lo registra por escrito |
| Colisión de skills entre repos | Ya ocurre hoy. Se mitiga con disciplina de nombres en los repos cliente |
| Hooks y `.mcp.json` de repos extras en `implement` | **Sin cobertura.** Documentado como límite conocido |

---

## 14. Fuera de alcance

- Reparto de `plan` e `implement`.
- Ejecución paralela de los hijos.
- Ruta de documentos externa al repo.
- Recuperar hooks y `.mcp.json` de repos extras durante `implement`.
- Revisión final de rama completa en Fase 2b (pendiente de `2026-08-12`: solo si
  las corridas crecen a 15+ tareas).

---

## 15. Verificaciones hechas para este diseño

| Afirmación | Cómo se comprobó |
|---|---|
| Qué carga `--add-dir` | Tabla de excepciones de la documentación oficial de permisos |
| `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` existe y qué carga | Documentación de memoria de Claude Code |
| `-p` + `--resume` + `--fork-session` funciona headless | Ejecutado en esta máquina: la sesión reanudada recordó un dato sin leer archivos, con id nuevo y la original intacta |
| El `session_id` está en el stream-json | `logs/1.log`: único y estable en toda la corrida |
| Tamaños de `CLAUDE.md` y del frontmatter de una skill | Medidos sobre este repo |
| El MCP autentica con PAT vía `--authentication envvar` | Servidor levantado contra `cr360dev`, work item leído por stdio |

**Sin verificar:** que un survey enraizado produzca mejor resultado que la sesión
única con las reglas cargadas. Es la hipótesis central del diseño y solo se
comprueba con un ticket real de dos repos.

Que siga sin verificar **no reabre la decisión**: la dirección está tomada, y el
motivo no depende de esa medición. Hooks y `.mcp.json` de un repo montado no los
recupera ninguna configuración —solo una sesión enraizada en él—, y eso es un hecho
comprobado, no una hipótesis. Lo que el primer ticket real de dos repos mide es
**cuánto** mejora y dónde flojea el reparto, no si se hace.
