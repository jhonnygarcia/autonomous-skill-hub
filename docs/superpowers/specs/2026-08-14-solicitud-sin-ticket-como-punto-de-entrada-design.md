# Solicitud sin ticket como punto de entrada

> Diseño. 2026-08-14. Estado: **analizado, sin aprobar para implementar**.
> Decisiones 1, 2 y 3 votadas por el humano el 2026-08-14.
> Revisado contra el código el mismo día: dos correcciones y dos mejoras (§10).
> Tercera pasada con dos requisitos del humano y dos adiciones votadas (§11).

## 1. Qué se pide

Hoy el único punto de entrada es un work item de Azure DevOps: se teclea `3320`,
el agente lo lee por MCP y produce `docs/tickets/3320-analysis.md`. Se pide poder
arrancar también desde algo que el humano **describe**, sin ticket:

> «necesito agregar una nueva feature donde se implemente un nuevo formulario que
> pueda persistir…»

Y que de ahí en adelante el recorrido sea el mismo: analizar, planificar,
implementar.

## 2. El hallazgo que decide el diseño

**La dependencia de Azure DevOps está concentrada en un solo punto, y es más chico
de lo que parece.**

De las seis fases, **cuatro ya no tocan el work item**:

| Fase | De qué se alimenta hoy | ¿Necesita el work item? |
|---|---|---|
| `analyze` | el work item, por MCP | **sí** |
| `brief` | el work item, por MCP | **sí** |
| `survey` | el brief, **inline en su prompt** | no — ya corre sin MCP |
| `consolidate` | el brief y los surveys, archivos | no — ya corre sin MCP |
| `design` | `docs/tickets/<id>-analysis.md` | no |
| `implement` | `openspec/changes/<id>-*/tasks.md` | no |

`PHASE_ALLOWED_TOOLS` ya deja a `survey` y `consolidate` **sin MCP**, y el comentario
en `app.py:76-80` explica por qué: el survey «recibe el brief inline en su prompt, así
que no necesita `ADO_ORG`, ni token, ni `.claude/ticket-agent.json` en ese repo — es una
sesión de comprensión de código pura».

Es decir: **el mecanismo de "la fuente viaja fuera de Azure" ya existe, ya está
construido y ya se midió en producción** (sesión novena, ticket 3320). Lo que pide el
usuario no es una arquitectura nueva; es aplicar ese mismo mecanismo dos fases más
arriba.

**Consecuencia:** esto no es un tipo nuevo de ticket ni un pipeline paralelo. Es una
**fuente distinta para la etapa 1**. Etapas 2 y 3 no se enteran — exactamente por la
misma razón por la que hoy no se enteran de cuál de las dos rutas de etapa 1 corrió: el
análisis es la interfaz.

## 3. Las tres decisiones tomadas

### 3.1 La llave es autogenerada, con prefijo: `R-1`, `R-2`, …

El id del ticket es la llave de todo lo que se escribe en disco:

    docs/tickets/R-7-analysis.md
    rama  ticket-agent/R-7
    openspec/changes/R-7-formulario-persistente/

Una solicitud no tiene id, así que el backend lo deriva del id de su fila con el
prefijo `R-`. El prefijo no es cosmético: sin él, la solicitud local número 7 y el work
item #7 escriben **el mismo archivo en el mismo repo**, y el segundo pisa al primero sin
que nadie lo note. Es el mismo error que ya se cometió una vez y está anotado en
`STATUS.md`: *«ambas rutas de fase 1 escriben `docs/tickets/<id>-analysis.md` por
diseño, así que `consolidate` pisó el análisis de sesión única de 3320 y la comparación
lado a lado se perdió»*.

Descartado el slug tecleado por el humano: obliga a validar unicidad por proyecto,
seguridad como nombre de archivo **y** como nombre de rama, y es un campo más que llenar
para algo que la máquina puede resolver sola.

`R-7` es un nombre de rama git válido y un nombre de archivo válido en Windows y POSIX.

**Y el prefijo reparte el espacio de nombres entre los dos modos** (§4.6): el
orquestador acuña **solo números** (`R-<rowid>`); un humano usando el plugin sin
orquestador elige su llave a mano y la guía le pide **una palabra**, no un número
(`R-form-clientes`). Numérico contra slug: la colisión entre modos es imposible por
construcción, sin coordinar nada.

### 3.2 Se habilitan las dos rutas de etapa 1

`analyze` (un repo) y el fan-out `brief` → `survey` → `consolidate` (varios repos).

El costo de habilitar la segunda es **una rama en un segundo SKILL.md**, porque
`survey` y `consolidate` no cambian ni una línea: ya trabajan sobre el brief y sobre
archivos, nunca sobre el work item.

Y el beneficio no es teórico. La ganancia medida del fan-out (sesión novena) fue que el
survey enraizado en el repo **secundario** localizó la causa raíz con `file:line` en un
archivo que **no está en el repo primario**, donde una sesión única habría buscado. Una
solicitud como «una feature nueva con formulario que persiste» es, por construcción,
front + back: es justo el caso donde el fan-out gana.

### 3.3 La descripción se persiste como `docs/tickets/<llave>-request.md`

La descripción vive en la BD del orquestador (columna `request`), y **el runner la
proyecta a un archivo en el repo primario antes de lanzar** las fases `analyze` y
`brief`.

Tres razones, en orden de peso:

1. **El análisis necesita una fuente citable.** La regla de oro 2 del skill exige que
   todo dato que no venga del work item cite `file:line`, un commit o el comando que lo
   produjo. Si la solicitud solo existe dentro del prompt, el análisis no tiene a qué
   apuntar cuando dice «el usuario pidió X». Con el archivo, la solicitud es una fuente
   de primera clase igual que cualquier otro documento del repo.
2. **Sobrevive a que se borre la BD.** Ya pasó una vez (2026-08-11): se perdieron
   proyecto, tickets y ~10 corridas. Lo que sobrevivió fue lo que estaba escrito en el
   repo destino. Una solicitud que solo vive en SQLite es el único insumo del pipeline
   que no tiene copia fuera.
3. **Lo escribe el runner, no el agente.** Mismo argumento que ya gobierna la rama y el
   hook de contención: *un límite que depende de que el agente obedezca un archivo
   markdown no es un límite*. El runner ya muta el repo del cliente (`prepare_branch`),
   así que escribir un archivo no es una clase nueva de comportamiento.

La BD sigue siendo la fuente de verdad; el archivo es una **proyección** que se
reescribe desde la BD en cada corrida. Así, editar la descripción en la UI y relanzar
no deja el archivo desincronizado.

## 4. Diseño

### 4.1 Modelo de datos: una columna, no dos

    ALTER TABLE tickets ADD COLUMN request TEXT;

Y nada más. **No se agrega una columna `source`**: es derivable —
`request IS NOT NULL` ⟺ es una solicitud local — y una columna derivada es una columna
que se puede desincronizar. `ticket_out` la expone al frontend como `origen: "ado" | "local"`.

**`ado_id` no necesita migración de tipo.** SQLite tiene tipado dinámico con afinidad de
columna: una columna con afinidad INTEGER guarda `'R-7'` como texto sin convertir (la
conversión solo ocurre cuando el texto *parece* un número), y sigue guardando `'3320'`
como entero. Lo único que cambia es:

- `TicketIn.ado_id: int` deja de ser `int`;
- `ticket_out` devuelve `str(t["ado_id"])` para que la API no alterne entre número y
  string según el origen;
- el frontend tipa `ado_id: string`.

No hay `ORDER BY ado_id` ni comparaciones numéricas sobre esa columna en el código, así
que no hay nada más que ajustar.

**La columna se sigue llamando `ado_id` aunque guarde `R-7`.** Renombrarla a `clave`
toca ~30 lugares entre backend, frontend y tests, y ese churn no compra nada que un
comentario no compre: esconde bugs reales en el review. Se documenta como deuda
deliberada con un comentario `# ponytail:` en la definición de la tabla.

### 4.2 Creación de la solicitud

`POST /tickets` acepta hoy `{ado_id, project}`. Pasa a aceptar **una de dos formas**:

    {"ado_id": 3320, "project": "TMS"}                  → ticket de Azure, como hoy
    {"request": "necesito…", "project": "TMS"}          → solicitud local

Exactamente uno de los dos campos; los dos o ninguno es `400`, y un `request` vacío o
de puro espacio también — es la única validación que la frontera necesita. La llave se
asigna después del `INSERT`, con el `lastrowid`:

    UPDATE tickets SET ado_id = 'R-' || id WHERE id = ?

en la misma transacción. Se deriva del `id` de la fila y no de un contador propio porque
el `id` ya es único y monótono, y un segundo contador es un segundo lugar donde
desincronizarse.

**El título no es un campo nuevo.** Hoy `tickets.title` se lee del análisis cuando
`analyze` cierra bien. Para una solicitud eso deja la lista mostrando `R-7` a secas hasta
la primera corrida, que es mala experiencia para algo que el humano acaba de escribir.
Se llena en la creación con la primera línea no vacía de la descripción, truncada, y el
análisis lo sobrescribe después igual que hoy. Cero campos nuevos en el formulario.

### 4.3 El runner

Dos cambios en `execute_run`, los dos condicionados a `ticket["request"]` — y uno que
se consideró y se descartó:

**a) Proyectar el archivo, solo en `analyze` y `brief`.**

    if ticket["request"] and phase in ("analyze", "brief"):
        p = Path(ticket["repo_path"]) / "docs" / "tickets" / f"{ticket['ado_id']}-request.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ticket["request"], encoding="utf-8")

Solo en esas dos fases, por dos razones de peso desigual: las fases de aguas abajo
consumen el análisis, no la solicitud, así que escribirlo ahí no sirve a nadie; y
`implement` es la fase donde el runner razona sobre la limpieza del árbol
(`check_clean` en el POST, `prepare_repos` bajo el lock) — hoy el guard ignoraría un
untracked, pero meter escrituras del runner justo entre sus dos verificaciones es un
hábito que no conviene adquirir por un archivo que esa fase ni lee.

**b) El MCP se queda — la primera versión de este diseño lo quitaba, y se
contradecía a sí misma.** Quitarlo sonaba a la misma decisión ya tomada para `survey` y
`consolidate` («no hay work item que leer»), pero §4.4 exige que el paso 6 del skill
siga aplicando entero: *leer los work items citados por id*. Sin MCP eso es imposible, y
es probablemente **el** caso común en una org real — el humano escribe «igual que
hicimos en el 3271» sin pensarlo como una cita. Quitar el MCP también mataba la búsqueda
de wiki (paso 5), que sirve a una solicitud tanto como a un ticket.

Así que `PHASE_MCP` **no se toca** (cero código), el prompt niega el work item principal
(punto c), y la degradación honesta cuando el MCP no conecta —proyecto que no está
realmente en Azure— la resuelve el skill: §4.4. El riesgo de que el agente salga a
buscar `R-7` en Azure es una búsqueda que devuelve nada, no un error.

**c) Nombrar la fuente en el prompt.** Un bloque nuevo, hermano de `repos_text` y
`adjustment_text`, en inglés porque es texto que lee el agente:

    There is no Azure DevOps work item for this request: it does not exist and
    must not be searched for. The whole request is in `docs/tickets/R-7-request.md`,
    written by the human who asked for it. Read it; it is the source, and the
    analysis cites it like any other document in the repo.

Nombrar el archivo **y** negar el work item, las dos cosas: la lección de la corrida
3320 es que lo que el prompt no nombra, el agente lo inventa (escribió
`SONDEAR: main, tms` cuando la etiqueta era `tenant`).

### 4.4 El plugin

Dos skills tocadas, `ticket-comprehension` y `ticket-brief`, con **la misma rama** en
ambas:

En el paso 2 (Recolección), un corte al inicio — y **la señal es la llave, no el
prompt**: *si el id empieza con `R-`, no hay work item; la fuente completa es
`docs/tickets/<id>-request.md`. Si ese archivo no existe, detenerse y guiar a crearlo* —
el mismo patrón que el paso 1 ya usa con `ticket-agent.json`. Dispararse por la llave y
no por el bloque del runner es lo que hace que el modo solo-plugin (§4.6) funcione: una
sesión interactiva que teclea `/ticket-agent:analyze R-form-clientes` no tiene runner
que le inyecte nada. El bloque del prompt de §4.3(c) queda como refuerzo, no como
disparador. *Se saltan 2.1 a 2.4 (work item, comentarios, relaciones, adjuntos) porque
no hay nada que leer ahí.* **Los pasos 5, 6 y 7 siguen aplicando**: la wiki se busca con los términos clave
de la solicitud igual que con los de un ticket; la solicitud puede citar documentos del
repo por ruta o work items por id — «como el bug #3271» — y eso hay que leerlo igual; y
las reglas del proyecto anfitrión condicionan el análisis venga de donde venga.

Con una degradación declarada: **si el MCP no está conectado** —un proyecto que no está
realmente en Azure—, los work items citados y la wiki van a «Missing information» con
esa causa, y el análisis **continúa**: el archivo de solicitud es la fuente, el MCP es
suplementario. Es la primera regla de oro aplicada tal cual; lo único nuevo es decir
explícitamente que aquí «MCP no conectado» no es un error que detiene, como sí lo es
cuando la fuente entera vive en Azure.

El paso 1 (leer `.claude/ticket-agent.json`) **se mantiene tal cual**. Ya no se usa
`project` para consultas MCP, pero el archivo carga `autonomy`, que es lo que gobierna si
un `DECIDIR` sin responder detiene la corrida — y eso importa más aquí que con un ticket.

Y **dos reglas nuevas**, que son la parte sustantiva del cambio en el plugin:

1. **Lo que la solicitud no dice no se deduce en silencio.** Va a
   `## Decisiones para ti` como `- [ ] **DECIDIR**` con una propuesta, o como
   `- [ ] **BLOQUEA**` si no hay default defendible. Esto es el hermano de la regla de oro
   1 («lo que no se pudo leer se reporta, no se rellena con supuestos») aplicado a lo que
   no se escribió. Un work item pasó por un refinamiento; un párrafo tecleado a las
   11 de la noche, no.
2. **Los criterios de aceptación se proponen, no se inventan.** Un work item los trae;
   una solicitud no tiene ninguno. El análisis los redacta y los marca como propuesta
   (`DECIDIR`), nunca como si vinieran dados. Un criterio de aceptación inventado que
   se presenta como dado es exactamente el fallo de 3320 —la afirmación negativa que
   suena a honestidad y nadie verifica— trasladado a la etapa 1.

Los comandos `analyze.md` y `brief.md` cierran hoy con *«si `$ARGUMENTS` está vacío o no
es un número de work item, pide el ID y detente»*. Esa línea rechazaría `R-7`: pasa a
aceptar también la forma `R-<clave>` — número acuñado por el orquestador o slug elegido
por el humano, indistintamente.

**Bump de versión a `v0.10.0`, en los dos lugares.** `plugin.json` porque la versión es
la llave de caché de `claude plugin update`, y la plantilla de análisis en
`ticket-comprehension/SKILL.md` que estampa `by ticket-agent vX.Y.Z` — ya se desincronizó
una vez (`v0.5.2` mientras el plugin iba en `v0.7.1`) y un sello que miente es peor que
no tener sello.

### 4.5 La UI

- **Crear**: donde hoy hay un `<Input>` de 40 caracteres con placeholder `3332`
  (`TicketList.tsx:92`), una alternancia entre ese input y un `<textarea>`. Sin wizard:
  el usuario de esta app es «técnicamente competente pero ocasional» (sesión séptima), y
  dos controles visibles le sirven mejor que tres pasos.
- **El placeholder del textarea es la mitigación de calidad más barata del diseño.**
  El riesgo número uno (§6) es la solicitud vaga, y el momento de mejorarla es mientras
  se escribe, no cuando el análisis vuelve lleno de `DECIDIR` — la lección de la sesión
  séptima: *la respuesta tiene que llegar cuando se toma la decisión*. El placeholder
  sugiere la estructura sin imponerla: *«qué necesitas, dónde vive hoy (pantalla,
  módulo, repo), por qué, y cómo sabrás que quedó bien»*. Y la línea de ayuda debajo —
  el mismo patrón que hoy explica `…/_workitems/edit/3332` — avisa que la primera línea
  será el título en la lista. Costo: dos strings.
- **Listar y ver**: `#{t.ado_id}` ya renderiza `#R-7` sin tocar nada. La distinción es
  legible en la propia llave, así que no hace falta un badge.
- `api.ts`: `ado_id: number` → `string`, `create` acepta las dos formas, y el `onAdd`
  del formulario deja de pasar `Number(adoId)` (el input numérico conserva su filtro
  `\D`; el textarea no lo hereda).

### 4.6 Los dos modos: con orquestador y con el plugin solo

El plugin ya es usable sin orquestador — una sesión interactiva en el repo destino que
teclea `/ticket-agent:analyze 3320` — y este cambio tiene que sostener ese modo, no
solo la UI. La regla que lo garantiza: **el archivo de solicitud es el contrato, y el
orquestador es solo una de las dos maneras de producirlo.**

| | Con orquestador | Solo plugin |
|---|---|---|
| La llave | `R-<n>`, acuñada por la BD | `R-<slug>`, elegida por el humano (§3.1) |
| El archivo `-request.md` | lo proyecta el runner desde la BD | lo escribe el humano; si falta, el skill se detiene y guía a crearlo |
| La rama del skill | se dispara por la llave `R-` (§4.4) | la misma — por eso funciona sin runner |
| El bloque de prompt de §4.3(c) | refuerzo | no existe, y no hace falta |
| Modelo y effort por paso | `phase_config` desde Settings, leído al lanzar — **cero cambios** | `/model` y `/effort` de la sesión antes de cada comando + `subagent_model` en `ticket-agent.json`, como hoy |
| `analyze`, `design`, `implement` | fases del runner | comandos directos, como hoy con un ticket |
| El fan-out (`brief`→`survey`→`consolidate`) | el runner lanza un hijo por repo | manual: el humano abre una sesión en cada repo — **igual que hoy con un ticket de Azure**; el fan-out automático es azúcar del orquestador en ambos orígenes |
| La rama git y la contención de `implement` | `prepare_branch` + hook vía `--settings` | el humano crea la rama; sin hook — **igual que hoy**, no es una regresión de este cambio |

La columna derecha no describe trabajo nuevo: describe lo que la elección de §3.3
(persistir la solicitud como archivo) y el disparador por llave de §4.4 compran gratis.
Si la solicitud viviera solo en la BD y la rama del skill se disparara por el prompt
del runner, el modo solo-plugin no existiría.

**Y una comodidad standalone que la UI no usa** (votada el 2026-08-14): `analyze`
acepta prosa. Si `$ARGUMENTS` no es ni un número ni una llave `R-`, el skill deriva un
slug corto del contenido, escribe él mismo `docs/tickets/R-<slug>-request.md` con la
prosa recibida, y continúa como si le hubieran pasado esa llave. Si el archivo ya
existe, elige otro slug — no lo pisa. La rama es standalone por construcción: el
orquestador siempre manda la llave, nunca la prosa. Solo `analyze`; `brief` sigue
exigiendo llave, porque el fan-out standalone es manual de todos modos.

### 4.7 El journal por ticket

**Votado el 2026-08-14, versión completa.** `docs/tickets/<id>-journal.md` en el repo
primario, para tickets de Azure y solicitudes por igual: el registro de qué se hizo,
qué falta y qué se encontró, para retomar mañana lo que no cerró hoy — y el único
historial que sobrevive a la BD (ya se perdió una vez) o que existe en modo
solo-plugin.

Dos secciones, y el orden importa:

    # Journal — R-7

    ## Corridas
    2026-08-14 · analyze · ok · docs/tickets/R-7-analysis.md · 6m12s
    2026-08-15 · design · parcial · openspec/changes/R-7-form/ · 8m01s
       · reserva: falta decidir persistencia

    ## Hallazgos
    - AR auto-marca BilledOn al abrir la pantalla
      (UpdateArReadyToProcessCommand.cs:36-43) — no está en ningún ticket

- **`## Corridas` la escribe el runner**, una línea por corrida cerrada — también las
  de error, con su motivo: es exactamente lo que un humano que vuelve quiere ver. Es
  código: determinista, testeable, con lo que solo el runner sabe (duración, rama,
  sesión, `← resume de <sesión>`). Inserta antes del encabezado `## Hallazgos`, así la
  otra sección puede crecer por el final.
- **`## Hallazgos` lo alimentan las skills**, con lo que encuentran **fuera del alcance
  de su entregable** — la clase de cosa que hoy no tiene hogar: el hallazgo AR de 3320
  vive en el STATUS.md de este hub, que es el repo equivocado. Lo que sí es del
  entregable va al entregable, como siempre.
- **Ninguna fase lo consume como autoridad.** El análisis y el plan siguen siendo las
  interfaces; el journal es registro. Si una fase lo leyera como insumo, sería una
  segunda fuente de verdad que puede mentir — la regla «una fuente de verdad por cosa»
  aplica igual que el primer día.

**La línea de corrida tiene dos escritores posibles, y eso hay que resolverlo, no
ignorarlo.** En solo-plugin no hay runner, así que la skill cierra apuntando su propia
línea (la instrucción vive junto a la de la `HUELLA`). Orquestada, eso duplicaría cada
línea — el runner escribe la suya, más rica. La resolución es el patrón de refuerzo ya
usado en §4.3(c): **el prompt del runner le dice a la skill que el journal de corridas
lo lleva él**; sin runner no hay quien lo diga y la skill escribe. El modo de fallo es
una línea repetida en un archivo de registro — cosmético, y falla hacia el lado seguro.

## 5. Lo que no cambia — y por qué es la prueba de que el diseño es correcto

- **El camino del ticket de Azure: cero.** Las dos formas de `POST /tickets` conviven
  en el mismo endpoint, la misma tabla y las mismas fases; los tests existentes tienen
  que seguir verdes sin tocarlos, y eso es parte del criterio de aceptación (§8).
- **El modelo y el effort por fase: cero.** `phase_config` es por fase, no por origen;
  `model_for` (`app.py:1142`) se lee al lanzar y se aplica igual al hijo único y a cada
  hijo del fan-out (`app.py:1272,1292`). Una solicitud local corre con la configuración
  de la fase que corre, exactamente como un ticket.
- **`design` e `implement`: cero líneas.** Consumen el análisis y el plan, y ya se
  verificó en producción que no vuelven al work item.
- **`survey` y `consolidate`: cero líneas.** Ya corren sin MCP y ya reciben su insumo
  fuera de Azure.
- **`STAMP_RE` y el contrato de la `HUELLA`: cero.**
- **El visor de artefactos, el guard de rutas, el hook de contención, la rama, el
  lock: cero.**
- **El fold de fases y `tickets.status`: cero.**

Si este cambio obligara a tocar la etapa 2 o 3, sería señal de que el análisis dejó de
ser la interfaz entre etapas. No la obliga.

## 6. Riesgos y bordes

**El riesgo real es de calidad, no de mecánica.** Una descripción libre es
ambiguo por construcción y el agente va a rellenar huecos. Las dos reglas nuevas de §4.4
son la mitigación, y son la parte del cambio que más merece medirse en la primera corrida
real: *¿el análisis de una solicitud vaga sale con `DECIDIR` honestos, o sale con un
alcance inventado que se lee con la misma confianza que uno derivado de un work item?*
Ese es el fallo que este proyecto ya conoce con otro nombre — la afirmación que suena a
honestidad y nadie verifica.

**Y el bucle de iteración para lo vago ya existe; no hay que construirlo.** Solicitud
ambigua → análisis con sus `DECIDIR` → el humano marca las casillas editando el archivo
→ `design` consume las respuestas. Es exactamente la costura entre fases que ya gobierna
todo el pipeline, aplicada al caso donde más falta hace: un párrafo tecleado a las 11 de
la noche produce más `DECIDIR` que un work item refinado, y eso es el mecanismo
funcionando, no fallando. Las instrucciones de ajuste por corrida cubren el resto.

**El archivo de solicitud NO choca con el guard de árbol limpio** — se verificó, porque
la primera versión de este diseño afirmaba lo contrario. `is_dirty` (`app.py:360-366`)
ignora las entradas `??` **a propósito**, precisamente porque `docs/tickets/` y
`openspec/` viven sin trackear en el repo del cliente: lo que bloquea `implement` es
trabajo *trackeado* a medias, que sí es del usuario. `<llave>-request.md` es un
untracked más en una carpeta que ya funciona así.

**El paso 6 se vuelve más importante y menos predecible.** Una solicitud humana cita
cosas de manera informal («el formulario que hicimos para clientes»), sin ids ni rutas.
El paso 6 exige leer referencias explícitas; una referencia vaga no es explícita, así que
cae en `DECIDIR`. Correcto, pero significa que las primeras solicitudes van a producir
análisis con varias decisiones abiertas. Eso es la función del mecanismo, no un defecto.

**`repo_label` y el `SONDEAR:`** funcionan igual: el ruteo lo decide `brief` a partir del
contenido, y ya falla ancho (ante la duda, sondea todos los repos). Una solicitud mal
ruteada pierde la optimización, nunca la correctitud.

## 7. Fuera de alcance, y por qué

- **Crear el work item en Azure a partir de la solicitud.** Sería el camino inverso, y
  requiere una herramienta `*_write` del MCP, que la etapa 1 prohíbe explícitamente.
  Cambio aparte, con su propia conversación sobre permisos.
- **Un proyecto sin Azure DevOps.** `projects.org` y `projects.project` siguen siendo
  `NOT NULL`, así que quien nunca use Azure tiene que inventar dos strings al registrar
  el proyecto. Es fricción real pero barata: `CLAUDE.md` ya documenta que esos dos campos
  «son etiquetas aquí, no configuración» — el runner nunca los exporta. Hacerlos
  opcionales es un cambio chico y desacoplado; se hace cuando alguien lo pida, no antes.
- **Editar la descripción después de crear la solicitud.** Hoy no se editan tickets
  (`last_session` depende de que `repo_path` no cambie nunca). Las instrucciones de
  ajuste por corrida ya cubren el caso «quiero decir algo más», y son por fase, que es
  mejor.
- **Renombrar `ado_id` a `clave`.** §4.1.
- **Contención para `implement` standalone.** El hook anti-push solo existe orquestado
  (viaja por `--settings`). El plugin podría embarcarlo condicionado a estar parado en
  una rama `ticket-agent/*`, pero un hook de plugin aplica a *todas* las sesiones del
  repo y bloquearía el push deliberado de esas ramas desde una sesión interactiva.
  Anotado (2026-08-14), no incluido: la fricción no está pagada por ningún incidente.
- **Mostrar el journal en la UI.** El visor de artefactos sirve lo que una corrida
  declaró; el journal no es un artefacto declarado y el humano lo abre en el repo. Si
  la Timeline algún día lo quiere, es una lectura más — cuando alguien lo pida.

## 8. Qué habría que verificar

Lo mínimo que falla si la lógica se rompe, en el estilo de los tests que ya existen —
y escritos para que **mutar el código los ponga en rojo**, que es la única prueba de que
un test prueba algo (nueve placebos encontrados en este proyecto hasta ahora):

| Qué | Cómo falla si se rompe |
|---|---|
| La llave se asigna y lleva prefijo | Crear solicitud → `ado_id == "R-1"`. Con el prefijo borrado, choca con el work item #1. |
| Las dos formas de creación son excluyentes | `{ado_id, request}` juntos → 400; ninguno → 400; `request` en blanco → 400. |
| El archivo de solicitud se escribe, y solo en `analyze`/`brief` | Existe tras `analyze`; **no** se escribe en `implement`: esa fase corre entre las dos verificaciones del guard y el runner no debe meter escrituras ahí. |
| El prompt nombra el archivo y niega el work item | Ambas frases presentes. La corrida 3320 enseñó que lo que el prompt no nombra, el agente lo inventa — y con el MCP presente (§4.3b), la negación en el prompt es la única barrera contra que salga a buscar `R-7` a Azure. |
| El archivo se reescribe desde la BD | Corromper el archivo a mano, relanzar, comparar contra la BD. |
| El journal recibe una línea por corrida cerrada | Correr dos fases (una en error) → dos líneas bajo `## Corridas`, la de error con su motivo. Con el insert roto, la segunda cae bajo `## Hallazgos`. |
| El prompt orquestado reclama el journal para el runner | La frase presente; sin ella, cada corrida orquestada saldría con línea doble. |
| El journal no es insumo de ninguna fase | Borrarlo entero y correr `design` → mismo resultado. Es la prueba de que es registro, no autoridad. |
| El camino de Azure no se movió | Los tests que ya existen, verdes sin tocarlos. |

Y una corrida real de punta a punta con una solicitud de las que motivaron esto —
formulario nuevo, front y back — por la ruta de fan-out. Es donde se ve si el análisis
sale honesto o inventado, que es el único riesgo que este diseño no cierra por
construcción.

## 9. Tamaño estimado del cambio

| Archivo | Qué |
|---|---|
| `apps/orchestrator/backend/app.py` | 1 `ALTER`, `TicketIn`, `create_ticket`, `ticket_out`, 2 puntos en `execute_run`, 1 bloque de prompt nuevo, el escritor del journal |
| `apps/orchestrator/backend/tests/` | los de §8 |
| `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md` | rama de fuente + 2 reglas + journal (línea standalone y Hallazgos) + sello de versión |
| `plugins/ticket-agent/skills/ticket-brief/SKILL.md` | la misma rama de fuente + journal |
| `plugins/ticket-agent/skills/{change-planning,change-implementation,repo-survey,analysis-consolidation}/SKILL.md` | la instrucción del journal (línea standalone y Hallazgos) |
| `plugins/ticket-agent/commands/{analyze,brief}.md` | aceptar `R-<clave>`; `analyze` además acepta prosa (§4.6) |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | `v0.10.0` |
| `apps/orchestrator/frontend/src/{TicketList,api}.ts(x)` | el textarea y el tipo |
| `CLAUDE.md` + `docs/STATUS.md` | el mecanismo y la decisión |

Ninguna dependencia nueva. Ninguna tabla nueva. Ningún skill nuevo.

## 10. Segunda pasada — qué cambió y qué se verificó (2026-08-14)

El diseño se revisó contra el código antes de aprobarse, con el prejuicio ya conocido:
*el autor no encuentra sus propios defectos leyendo* (doce defectos en la sesión
séptima, cero hallados por autorevisión). Esta pasada encontró dos, y son de los dos
tipos ya catalogados:

1. **El documento se contradecía a sí mismo** (tipo 1 del catálogo). §4.3 quitaba el
   MCP a la solicitud local mientras §4.4 exigía leer los work items que la solicitud
   cita — imposible sin MCP, y probablemente el caso común («igual que hicimos en el
   3271»). Resuelto a favor de mantener el MCP: cero código, el prompt niega el work
   item principal, y el skill degrada honesto si el MCP no conecta.
2. **El documento estaba simplemente equivocado sobre el código** (tipo 2). §6
   afirmaba que el archivo de solicitud podía chocar con el guard de árbol limpio;
   `is_dirty` (`app.py:360-366`) ignora `??` a propósito, exactamente para los
   artefactos del agente en `docs/tickets/`. El riesgo no existe. De rebote, la
   justificación de §4.3(a) estaba sobreafirmada en la misma dirección y se rebajó.

Dos mejoras entraron con la pasada:

- **El placeholder del textarea como mitigación de calidad** (§4.5): el momento de
  mejorar una solicitud vaga es mientras se escribe, no cuando el análisis vuelve
  lleno de `DECIDIR`. Dos strings.
- **Decir que el bucle de iteración ya existe** (§6): solicitud vaga → `DECIDIR` → el
  humano marca casillas → `design` consume. No se construye conversación; ya está
  construida.

Y tres afirmaciones pasaron de fe a verificadas: no hay `ORDER BY ado_id` ni
comparación numérica sobre esa columna; el título del análisis solo se escribe cuando
se encuentra uno (así que el provisional de la primera línea convive bien con él); y el
input actual filtra `\D` y tipa `number`, así que el cambio de frontend es exactamente
el declarado en §4.5.

## 11. Tercera pasada — los dos modos y el journal (2026-08-14)

El humano sumó dos requisitos: convivir con el camino del ticket (ya era la propiedad
central, ahora es criterio explícito en §5 y §8) y **que funcione con el plugin solo,
sin orquestador**. El segundo destapó un defecto del mismo tipo que el del MCP: la rama
del skill se disparaba por el bloque de prompt que inyecta el runner, así que sin
runner no había modo de entrar en ella. Corregido en §4.4 — el disparador es la llave
`R-` y la existencia del archivo; el prompt del runner queda como refuerzo — y
documentado en el §4.6 nuevo, junto con el reparto del espacio de nombres (§3.1: el
orquestador acuña números, el humano elige slugs; la colisión es imposible sin
coordinación). Modelo y effort por fase: verificado que `model_for` es por fase y no
por origen — cero cambios, anotado en §5.

De la misma conversación salieron dos adiciones votadas y una anotada:

- **El journal por ticket** (§4.7), versión completa: `## Corridas` del runner,
  `## Hallazgos` de las skills, nunca insumo de una fase. Lo que compra no es la
  continuación —esa ya la cubren `tasks.md`, `resume` y `parcial`+ajuste— sino el
  registro: el historial que sobrevive a la BD, el hogar de los hallazgos
  transversales, y el único rastro del modo solo-plugin.
- **`analyze` acepta prosa en standalone** (§4.6): escribe él mismo el `-request.md`
  y sigue. El orquestador nunca manda prosa, así que la rama no lo toca.
- **El hook de contención en el plugin**: anotado en §7, no incluido — la fricción
  (bloquear el push deliberado desde sesiones interactivas) no está pagada por ningún
  incidente.
