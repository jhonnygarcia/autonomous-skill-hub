# Estado del proyecto — Autonomous Skill Hub

> Documento vivo. Actualízalo al cerrar cada hito o al tomar una decisión.
> Última actualización: 2026-08-10 (avance por fases, huellas y timeline — implementado)

## Propósito

Hub personal de plugins de Claude Code que captura la experiencia de Jhonny como
skills/agents/hooks reutilizables. Primer objetivo: un agente que lee un ticket de
Azure DevOps, lo comprende a cabalidad (relaciones, adjuntos, wiki, reglas del
proyecto), y por fases llegará a diseñar, implementar, probar y validar el código
con guards — instalable en cualquier proyecto y capaz de aprender de cada uno.

## Roadmap y estado

| Fase | Qué entrega | Estado |
|---|---|---|
| 0 — Fundación del hub | Marketplace de plugins + esqueleto ticket-agent | ✅ Hecha |
| 1 — Comprensión de tickets | Skill `ticket-comprehension` + `/ticket-agent:analyze` (solo lectura) | ✅ **Aceptada** (3311 y 3322) — skill **v0.3.0** |
| Orquestador (transversal) | App local: cola SQLite + runner CLI headless + UI React | ✅ Ciclo completo con dos fases lanzables + **avance por fases, huellas y timeline implementados y validados con corrida real** (2026-08-10) |
| 2 — Del análisis al plan de cambios | Skill `change-planning` + `/ticket-agent:plan` → change de OpenSpec | ✅ **Construida y validada** (3323) — skill **v0.4.2**, n=1 |
| 2b — Del plan al código | Ejecutar el plan: escribir código, rama, PR | 📋 Futura — la Fase 2 se quedó deliberadamente en el documento |
| 3 — Pruebas | Unitarias ligadas a criterios de aceptación + integración | 📋 Futura |
| 4 — Guards | Agents revisores read-only + hooks deterministas | 📋 Futura |
| 5 — Aprendizaje por proyecto | Memoria local que alimenta las skills | 📋 Futura (OpenSpec también candidato aquí) |

## Qué existe y dónde

- **Marketplace**: `.claude-plugin/marketplace.json` — instalar con
  `/plugin marketplace add <ruta-del-hub>` + `/plugin install ticket-agent@autonomous-skill-hub`.
- **Plugin ticket-agent**: `plugins/ticket-agent/` — `.mcp.json` (MCP oficial de
  Azure DevOps, org por env `ADO_ORG`, dominios filtrados, auth `az login`),
  skill `ticket-comprehension`, comando `analyze`, README de instalación.
- **Orquestador**: `apps/orchestrator/` — backend FastAPI+SQLite (`backend/app.py`,
  **18 tests** pytest), README de arranque. No hay archivo de configuración: los
  proyectos están en la BD y se editan desde la UI.
  Frontend (Vite+React+Tailwind+shadcn), una vista por archivo:
  `App.tsx` (conmutador de vistas y estado), `Sidebar`, `ProjectHeader`,
  `TicketList`, `TicketDetail`, `Projects` (ajustes), `estado.ts` (etiquetas,
  bloqueo por corrida activa, duraciones).
- **Diseños**: `docs/superpowers/specs/` (hub+fase1, orquestador, navegación de la
  UI). **Planes** con checkboxes: `docs/superpowers/plans/`.
- Configuración por proyecto destino: `.claude/ticket-agent.json` (org, project,
  `autonomy: supervised|autonomous`) + `ADO_ORG` en settings del proyecto.

## Decisiones clave (y por qué)

1. **Plugin delgado que reusa piezas públicas**: MCP oficial de Microsoft +
   skills de superpowers; solo se crea lo que codifica experiencia propia.
2. **Suscripción, jamás API key**: la ejecución programática usa el CLI headless
   (`claude -p`) — el Agent SDK exige `ANTHROPIC_API_KEY`. El runner además
   elimina `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` del entorno del subproceso
   (test que lo garantiza).
3. **SQLite sin ORM, un ticket a la vez** (lock global): cola local transitoria.
4. **El estado del pipeline vive en el orquestador; el análisis vive en el repo
   del proyecto** (`docs/tickets/<id>-analysis.md`) — una fuente de verdad por cosa.
5. **OpenSpec: adoptado** (2026-08-10) como formato de salida de la Fase 2, con su
   carpeta en el **repo destino**, no aquí. El paquete es `@fission-ai/openspec` — *no*
   `openspec`, que es otro y no existe como ejecutable. Sigue siendo candidato para la
   memoria viva de la Fase 5.
6. **Un ticket abarca N repos, pero escribe en uno** (2026-08-08). El 3311 manda los
   arreglos de backend a `ProvidenceTMSTenant`, repo hermano del primario. Un proyecto
   declara un `repo_path` (cwd de la corrida, donde se escribe el análisis) y
   `extra_dirs` que el runner monta con `--add-dir`. La decisión 4 no cambia.
   **Corolario (2026-08-09): montar no basta.** Ver "Lo aprendido".
7. **Los proyectos viven en la BD y se editan desde la UI** (2026-08-08), no en un
   archivo. Con `extra_dirs` siendo una lista, el JSON a mano dejaba de tener gracia;
   y un proyecto que no se puede dar de alta desde la UI es un agujero en el producto.
   El ticket **copia** los datos del proyecto al crearse (como una línea de pedido
   guarda el precio), así que no hay FK y borrar un proyecto no rompe el historial.
8. **No construir descubrimiento de CLAUDE.md**: Claude Code ya los carga en cascada
   desde `cwd` hacia arriba, cruzando el límite del repo. Comprobado en el 3311, que
   absorbió tres niveles — incluido `D:/Companies/ProvidenceSolutions/CLAUDE.md`, que
   está fuera del repo — sin que nadie se lo dijera.
9. **Un proyecto tiene repos; el usuario marca cuál es el principal** (2026-08-09).
   La API expone una lista plana `repos: [{path, label, primary}]`. Por dentro se
   siguen guardando separados porque el runner los usa distinto, pero eso deja de
   ser un concepto que el usuario tenga que entender. La `label` no es decorativa:
   viaja al prompt. El nombre del proyecto es editable — renombrar es seguro porque
   los tickets copian sus datos al crearse (decisión 7).
10. **El proyecto es el contexto de la UI** (2026-08-09, spec
    `2026-08-09-orchestrator-ui-navegacion-design.md`): barra lateral de proyectos,
    cabecera que muestra qué repos verá el agente, y el panel derecho pasa a ser el
    ticket al elegirlo. Tres vistas con `useState`, sin router.
11. **La Fase 2 entrega un documento, no código** (2026-08-10, spec
    `2026-08-09-fase-2-plan-de-cambios-design.md`). El plan se escribe **para el agente
    que lo implemente**: destino, espejo con `archivo:línea`, y cómo se comprueba. Eso
    deja la corrida en solo lectura + escribir markdown, así que no hay ramas ni
    permisos de escritura que resolver todavía. Escribir el código es una fase aparte.
12. **Dos skills encadenadas, no una con dos modos** (2026-08-10). `change-planning`
    consume `docs/tickets/<id>-analysis.md` y **se detiene si no existe**. El análisis
    es la interfaz: si sale mal, se ve en el archivo y se re-corre la Fase 1 sola.
13. **El estado de una corrida no se deduce del código de salida** (2026-08-10).
    `claude -p` sale con 0 aunque el agente se detenga sin hacer nada, así que `planned`
    llegó a significar "el subproceso no petó". Ahora la skill cierra con un sello y el
    runner decide por la **última** coincidencia en el log. Ver "Lo aprendido" para por
    qué *última* y no *presente*. **Generalizado el 2026-08-10**: el sello es
    `HUELLA: <ok|parcial|nada> — <ruta>`, lo cierran **las dos** skills, y rige toda
    fase. `PLAN:` se conserva solo como alias legado para no romper logs viejos.
14. **El avance vive en `runs`, no en una columna de estado** (2026-08-10, spec
    `2026-08-10-avance-por-fases-y-timeline-design.md`, **implementado el 2026-08-10**).
    El sello `PLAN:` se generaliza a `HUELLA: <ok|parcial|nada> — <ruta>` para toda fase,
    `runs` gana la huella, `current_phase` se borra y `tickets.status` pasa a calcularse.
    La UI del ticket se convierte en un recorrido de fases con la acción y el artefacto
    de cada una, y el artefacto se lee dentro de la app. Revierte a propósito la decisión
    de retirar el stepper: allí eran 6 fases apagadas en **cada fila de la lista**; aquí
    salen una vez, en el detalle, donde el camino pendiente es contexto.
15. **`ProvidenceTMSTenant` es el conejillo de indias** (2026-08-10). Lo que las corridas
    dejen ahí —análisis, `openspec/`, lo que instale `openspec init` en `.claude/` y
    `.opencode/`— **no hay que versionarlo ni revertirlo**. Se están probando el plugin y
    el orquestador, no ese repo. Sí merece la pena **medir** la huella que dejan: eso es
    evidencia sobre la herramienta.

## Aceptación de la Fase 1 — cerrada el 2026-08-08

Corrida sobre el ticket **3311** en el repo TMS, dos veces: con la skill v0.1.0 y,
tras corregirla, con la v0.2.0. El archivo `docs/tickets/3311-analysis.md` se
escribió en ambas.

**La incidencia del archivo que no aparecía queda explicada, y no era la skill.**
En modo headless, `--permission-mode acceptEdits` **no** auto-aprueba las tools del
MCP: se deniegan solas y el agente se queda sin poder leer el work item. El runner
del orquestador no pasaba `--allowedTools`. Ya lo pasa, con test que lo fija.

**Qué salió bien en v0.1.0** (verificado contra el work item real): los 15 criterios
de aceptación completos y en orden; "Qué pide" fiel sin interpretar de más; las
deducciones todas etiquetadas `DEDUCIDO`; el padre #285 resumido con honestidad
("no tiene descripción" ≠ "no pude leerlo"); los 2 comentarios con sus cifras
exactas; e "Información faltante" autodelatándose.

**Qué falló, y qué se cambió en la skill (v0.2.0):**

| Fallo | Arreglo |
|---|---|
| `docs/quote-visibility-rules.md` y el Bug #3271 listados **sin leerlos**, excusados con el límite de "1 nivel" — que solo aplica a `relations`, no a lo que el ticket cita en su texto | Paso propio y obligatorio (2.6) + sección *Referencias citadas* en la plantilla |
| Dos cifras del repo **sin fuente y equivocadas**: "5 commits" (eran 12) y el 27 % de la línea base A.6 atribuido al guion completo | Segunda regla de oro: toda cifra ajena al work item cita `archivo:línea`, commit o comando. Y sección propia *Estado del trabajo en el repo*, separada de lo que dice el ticket |
| La plantilla no tenía dónde poner los comentarios pese a que 2.2 obliga a leerlos | Sección *Comentarios* de primer nivel; ante contradicción gana el comentario más reciente |

**Verificación de la v0.2.0**: leyó el #3271 (sacó el modelo de cascada y el punto
de control `QuoteVisibilityService.IsPricingOwnerMember`) y las 121 líneas de
`quote-visibility-rules.md` (6 reglas de display que condicionan la v2 y que la
v0.1.0 no tenía). Todas las cifras citan fuente; el 27 % ya se atribuye a A.6.
De propina detectó una incoherencia interna de `ESTADO.md` (declara 179/179 en un
sitio y 144/144 en otro).

## Segunda jornada — 2026-08-09

**El orquestador completó el ciclo real.** Alta de proyecto por API con validación
de rutas (`400`/`409` correctos), encolado, corrida del **3322 en 5m33s** con
estado `analyzed`, y log en vivo. Se verificó el argv del subproceso:
`--allowedTools mcp__azure-devops … --add-dir …Tenant --add-dir …TMS.wiki`.

**Fase 1 con n=2, y la predicción falló.** Se temía que la skill se rompiera con un
Bug —el contenido vive en `Microsoft.VSTS.TCM.ReproSteps`, no en `System.Description`,
y la forma es Repro/Expected/Actual—. Lo manejó sin problema: sacó **5 criterios
explícitos** de un ticket cuya línea `AC:` es una sola frase, y discriminó bien que
el load **16791** citado en el texto es un dato de producción, no un work item que
haya que abrir. Además **contradijo la hipótesis del ticket con evidencia**: los
iconos de excepción no están gateados por rol (`load-icon-exception.component.ts:21`
solo cubre HotLoad), así que la causa raíz está en el backend.

**Rediseño de la UI del orquestador** (spec propio, ver decisión 10), en respuesta a
que "todo estaba en una misma pantalla y no era intuitivo". Además: repos como lista
plana con principal marcado por el usuario, nombre de proyecto editable, un único
botón de alta y ancho completo.

## Tercera jornada — 2026-08-10

**La v0.3.0 pasó su prueba de fuego.** Re-corrido el 3322 con la instrucción de ajuste:
**26 invocaciones con ruta dentro de `ProvidenceTMSTenant`** (antes 0), cero apariciones
de "no inspeccionado", 24 archivos `.cs` citados frente a 5. Y respondió la pregunta: el
recorte está en `BaseProviderGroupService.cs:1559-1575`, donde a un rol cliente que no es
*pricing owner* se le borran las excepciones de categoría `Audit` — y Rate Change (311)
es Audit. Montar un repo no basta; **nombrárselo en el prompt con su etiqueta, sí**.

**Fase 2 construida y validada sobre el 3323** (*Carrier API V2 Migration - XPO*), en
cuatro tareas con revisión por subagente entre cada una. Los tres criterios de aceptación
en verde en la segunda corrida: `openspec validate --changes` pasa, 10 de 15 espejos
citan `archivo:línea`, y **GetDocs aparece bajo `## Bloqueado` con cero tareas asociadas**.

El plan que produjo tiene 21 tareas y 5 bloqueos, y **encontró dos huecos del gateway que
no estaban en el análisis**, comparando código: `ApiRateService.V2.cs:103-108` fuerza
`AuthType.Basic` con `TokenUri: null`, así que el Rate de XPO viajaría sin bearer; y el
adaptador V2 de Track anula el `AuditTrackingResponse` que el legacy de XPO **sí** genera,
documentado como *"Gap B: verified equal"* porque se evaluó contra ABF, que no lo genera.

**El 3323 resultó mejor candidato que el 3320.** Su Feature padre **#3319** trae un
inventario verificado con la *Definition of Done* por carrier, y el patrón a replicar ya
está escrito dos veces en el repo (`Carriers/Abf/`, `Carriers/Estes/`). El agente eligió
Estes como espejo en vez de ABF —y tenía razón: XPO es REST + OAuth como Estes, mientras
ABF no tiene token— y **leyó los 9 archivos que cita**, así que los números de línea no
están inventados.

## Cuarta jornada — 2026-08-10 (tarde): avance por fases, huellas y timeline

**Implementado el spec entero**, con `subagent-driven-development`: 8 tareas, 21 commits
(`4044a91..76f6f5d`) contando la oleada de la revisión final y el arreglo del repaso
visual. Plan en `docs/superpowers/plans/2026-08-10-avance-por-fases-y-timeline.md`, con
las 53 casillas marcadas. Backend: **66 tests** (antes 18). Frontend: build y lint verdes.

Lo que hay ahora que antes no había: las dos skills cierran con `HUELLA:`; `runs` guarda
`artifact_state` y `artifact_path`; `current_phase` desapareció y `tickets.status` se
**calcula** de las corridas; `GET /tickets/{id}` devuelve `fases`; hay un visor de
artefactos (`GET /tickets/{tid}/artefacto`) y un `Timeline.tsx` que pinta el recorrido con
el artefacto legible dentro de la app.

**Lo que más costó no fue construirlo, fue que la revisión lo tumbara tres veces.** El
visor de artefactos necesitó **tres rondas** de arreglo, cada una cerrando un agujero que
la anterior había abierto: (1) `..` sin normalizar dejaba leer `.env` y `.git/config` del
repo del cliente y de los repos hermanos; (2) al resolver las rutas para cerrar eso, una
declarada que resuelve a la raíz se volvió comodín (`HUELLA: ok — ..` es alcanzable); (3)
el predicado que arreglaba eso fundía dos preguntas en un `any` y volvía a fallar con
raíces anidadas (un `extra_dir` que contiene al `repo_path`). Cerrado y verificado con
**638 vectores** contra el endpoint real —seis configuraciones de raíces, junctions NTFS,
ADS, nombres 8.3, UNC y comodines de toda grafía—: cero fugas, y los 30 casos legítimos
siguen sirviendo.

**La prueba de fuego pasó.** Re-corrida la Fase 1 sobre el **3322** con el plugin v0.5.1,
**8m14s**, y el recorrido entero se cerró fuera del laboratorio por primera vez:

- El agente estampó `HUELLA: ok — docs/tickets/3322-analysis.md`, con `/` y como última
  línea. El log trae **6 coincidencias del sello**: 4 son el cuerpo de la skill filtrado
  (incluido el ejemplo `parcial` que menciona el 3323), y la buena está a **190 caracteres
  del final**. *Anclar en la última coincidencia no era una precaución teórica: sin ella
  esta corrida habría leído un ejemplo de la documentación como si fuera su resultado.*
- El runner guardó `artifact_state='ok'` y una ruta limpia; la fase salió `ok`, el ticket
  se plegó a `analizado` y **`Plan` se desbloqueó solo**.
- El visor sirvió el documento de 28,6 KB dentro de la app (200), y siguió devolviendo
  400 a la travesía. El análisis estampa `ticket-agent v0.5.1`, así que el archivo prueba
  qué versión lo produjo.

**Repaso visual hecho** (el que se arrastraba desde el rediseño del 2026-08-09). Un solo
defecto real: el riel del timeline estaba acotado a su fila con `bottom-0` y en las fases
apagadas medía 4px, así que el recorrido se veía como círculos sueltos justo en el tramo
pendiente. Arreglado en `8f3e6a2`. Consola limpia, sin desbordamiento horizontal, y el
modo oscuro legible — aunque **la app no tiene interruptor de tema**, así que los `dark:`
son inversión a futuro.

## Pendientes inmediatos

- [ ] **Segundo ticket para la Fase 2, y que sea el 3320.** Está aceptada con **n=1**.
  Otro carrier del #3319 mediría repetibilidad del caso fácil: mismo padre con su
  *Definition of Done*, mismo espejo, misma tarea de "replica esto". El **3320**
  (*"Ready To Pay" no persiste*) es la forma opuesta — repro determinista pero **sin
  padre rico y sin patrón que copiar**. Ahí la regla central de la skill (*toda tarea cita
  su espejo con `archivo:línea`*) no se puede cumplir, y la salida honesta que tiene
  escrita para ese caso **nunca se ha ejercitado**. Lo que hay que mirar: si inventa
  espejos para cumplir la forma, o si declara las tareas como investigación pendiente.
- [x] ~~**Repaso visual de la UI**~~ — hecho el 2026-08-10 con el MCP de chrome-devtools,
  al liberarse el navegador. Un defecto real (el riel del timeline), arreglado.
- [ ] **Decidir qué se hace con `Bash` en el runner.** Ver "Lo aprendido": el
  especificador no acota. Hoy `analyze` va con la lista vacía, pero la Fase 2 tiene Bash
  disponible de facto para más que `npx`.
- [ ] **Quitar `organization` de `.claude/ticket-agent.json`** — duplica `ADO_ORG`,
  que no se puede eliminar porque el MCP la necesita como env var al arrancar.
- [ ] **Añadir un interruptor de tema a la UI.** La paleta oscura está completa y con el
  contraste verificado (ratio WCAG AA contra `#0a0a0a`), pero hoy solo se alcanza forzando
  la clase `.dark` a mano: no hay forma de llegar a ella desde la app.

**Deuda menor anotada** (ninguna bloqueante):

- El log se lee entero para quedarse con los últimos 4 KB (`leer_huella`) y con 8 KB
  (`log_tail`). Hoy pesan cientos de KB; con logs de MB tocaría un `seek` desde el final.
- El `assert` que cuadra las claves de las cuatro tablas de fase desaparece con `python -O`.
- Toda corrida `success` se pinta del color de "analizado" en el historial, aunque su fase
  esté en rojo por no haber declarado huella. Confunde con los datos pre-contrato.
- `leer_huella` no des-escapa comillas JSON dentro de una ruta; una reserva vacía
  (`ruta · `) deja la ruta con el punto medio pegado. Ambos cosméticos, sin consecuencia.
- TOCTOU teórico en el visor entre `is_file()` y `open()`. Un solo usuario local y el único
  escritor es el propio agente; el peor caso es un 500.
- `puedeLanzar` duplica los textos de bloqueo de `bloqueo()` en `estado.ts`.
- Los planes de las jornadas anteriores tienen casillas sin marcar
  (`fase-0-1`: 15/20, `orchestrator`: 31/32, `fase-2`: 30/32) pese a estar cerradas.

## Lo aprendido (2026-08-10, tarde)

- **Un test verde no es una prueba; a veces es una coartada.** Salieron **cinco** tests
  placebo, todos con la misma forma: el montaje no puede producir el fallo que el test
  dice prevenir. El de anclaje del sello pasaba igual con `hits[0]` porque
  `json.dumps` escapaba el guion largo a `—` y los sellos señuelo nunca casaban. La
  batería de travesía de rutas montaba un **archivo** declarado, contra el que la travesía
  era imposible por construcción — el caso peligroso (directorio declarado) no lo tocaba
  ninguno de los 8 tests, y por eso 50 tests pasaron en verde con un agujero que dejaba
  leer `.env`. `test_current_phase_ya_no_existe` corría sobre una BD recién creada, cuyo
  `CREATE TABLE` nunca tuvo esa columna, así que jamás ejecutaba el `DROP COLUMN` que
  decía proteger. **La pregunta que los destapa: ¿qué tendría que romperse para que este
  test fallara?** Si no hay respuesta concreta, el test no prueba nada.
- **Arreglar un agujero abre el siguiente si arreglas la grafía y no la propiedad.** El
  visor necesitó tres rondas. La segunda cerró `''` filtrando esa cadena en el SQL y
  **amplió** el comodín a `'.'`, `'..'` y `'x/..'`. La que funcionó no filtra grafías:
  exige que la ruta declarada, ya resuelta, quede **estrictamente dentro** de una raíz.
  Filtrar cadenas es jugar al gato y al ratón; afirmar una propiedad se acaba.
- **La revisión adversarial encuentra lo que la revisión amable no.** Los tres agujeros
  del visor salieron de pedirle al revisor que *atacara* el endpoint con vectores
  concretos, no que lo leyera. El que solo leyó el código dio Spec ✅.
- **Los huecos viven en las costuras, y ninguna revisión por tarea los ve.** La Tarea 1
  escribió en las skills "explica la reserva en el resumen, **no** en la línea del sello";
  las Tareas 3 y 6 necesitaban esa reserva para mostrarla, como pedía el diseño. Cada
  tarea era correcta por separado. Solo la revisión de la rama entera lo vio.
- **El plan es una hipótesis, no una verdad.** Dos bloques de código que escribí en el
  plan estaban mal y los tests del propio plan los habrían tapado: un `.strip("\n")` que
  trata su argumento como conjunto de caracteres, y una expresión que producía la ruta de
  un directorio cuando la huella tenía un solo archivo dentro. Un implementador que copia
  el plan al pie de la letra hereda sus bugs.

## Lo aprendido (2026-08-10, mañana)

- **Una comprobación puede encontrarse a sí misma.** El runner decidía si hubo plan
  buscando el sello `PLAN: validado` en los últimos 4 KB del log. Pero el cuerpo de la
  skill viaja en el log y contiene los tres sellos literalmente — el último `PLAN:
  validado` está a 393 caracteres del final de `SKILL.md`. En una corrida que aborta
  pronto, la ventana se tragaba la §7 de la propia skill y la corrida se daba por buena:
  el bug que el mecanismo venía a matar, reconstruido por dentro. **Anclar en la última
  coincidencia, no en la presencia.** Lo encontró la revisión final, no los tests.
- **`--allowedTools` con un especificador no acota: habilita.** Poner
  `Bash(npx openspec:*)` no restringió Bash a ese comando — dejó correr `ls`, `find` y
  `git remote -v` en el repo del cliente, y a la vez **bloqueó** la invocación correcta
  del CLI por no empezar con esa cadena literal. Lo peor de las dos cosas. Y como la
  lista se construía sin mirar la fase, la Fase 1 —declarada solo lectura— pasó a
  ejecutar shell sin que nadie lo decidiera. Hoy hay una tabla `PHASE_ALLOWED_TOOLS` y
  `analyze` lleva la lista vacía.
- **El código de salida de `claude -p` no dice nada.** Sale con 0 aunque el agente se
  haya detenido sin hacer nada. Cualquier estado que se derive de él es una mentira
  esperando a ocurrir: `planned` llegó a significar "el subproceso no petó".
- **El nombre del paquete no se adivina.** `npx openspec` no existe; es
  `@fission-ai/openspec`. Costó una corrida entera de 8 minutos descubrirlo.
- **El agente fue más honesto que mi regla.** La skill le mandaba detenerse si el CLI
  fallaba. No se detuvo: escribió el plan igual y abrió su resumen con *"Falta la
  validación: npx está bloqueado por permisos"*, con sección propia y el diagnóstico de
  la causa. Tirar un plan de 21 tareas por no poder validarlo habría sido peor. La regla
  se quedó; lo que se añadió fue el sello, para que el **estado** no pueda mentir aunque
  el agente decida seguir.
- **Un espejo citado sin abrir es un número inventado.** Por eso se cuentan las lecturas
  en el log, no solo las citas en el documento: el 3323 citó 9 archivos de Estes y los
  leyó los 9.

## Lo aprendido (2026-08-09)

- **`--add-dir` da acceso, no atención.** Montar un repo no hace que el agente lo
  mire: en la corrida del 3322 tenía `ProvidenceTMSTenant` disponible, lo nombró 15
  veces y registró 0 lecturas dentro. Hay que **nombrárselos en el prompt y decirle
  de qué va cada uno** — de ahí que la etiqueta del repo sea funcional y no adorno.
  El runner lo inyecta; `SKILL.md` 2.8 (v0.3.0) dice que esos repos entran en el
  alcance de "Código afectado" en vez de declararse fuera.
- **`uvicorn --reload` deja procesos huérfanos en Windows.** Tres veces seguidas el
  backend siguió sirviendo código anterior y una prueba dio un resultado falso. El
  puerto 8000 quedaba retenido por un hijo del recargador. **Arrancar sin `--reload`
  y reiniciar a mano**; ante un comportamiento raro, sospechar del proceso antes que
  del código.
- **Aceptar con n=1 es aceptar poco.** El 3311 es una épica escrita por el propio
  Jhonny, con criterios numerados: el ticket soñado. La prueba de verdad es el
  ticket de dos frases. Salió bien, pero eso solo se supo al correr el segundo.
- **Un `<select>` no dice qué arrastra.** El origen del rediseño de la UI: el usuario
  elegía proyecto sin ver qué repos montaría el agente. La información tiene que
  estar donde se toma la decisión, no donde se configuró la semana pasada.

## Lo aprendido en la aceptación (2026-08-08)

- **La versión del plugin es la clave de cache.** Editar y committear una skill en el
  hub no llega al plugin instalado: `claude plugin update` no trae nada si `version`
  en `plugin.json` no sube. Tocar una skill obliga a subir versión. La plantilla del
  análisis estampa la versión, así que el archivo generado prueba cuál corrió.
- **La Fase 5 se encoge.** La "memoria por proyecto" que iba a construirse ya existe:
  es el `CLAUDE.md` + `.claude/rules/` del proyecto destino. El 3311 absorbió reglas
  de Angular 21, el gate financiero, el flujo de git y el "developer mode" sin una
  línea de código nuestra. A la Fase 5 solo le queda lo que el agente **aprende
  corriendo** (que faltan las cuentas de B2, qué ordenaba un timeout de 850 ms) — un
  archivo que el agente escribe en el repo destino, no un subsistema.
- **`organization` en `.claude/ticket-agent.json` es redundante** con `ADO_ORG`, y el
  README pedía que "coincidan": dos fuentes para un valor. Pendiente de quitar
  (`ADO_ORG` no se puede eliminar, el MCP la necesita como env var al arrancar).
- **El repo destino se mueve mientras se analiza.** Entre las dos corridas la rama
  `jhonny/quote-v2` pasó de 12 a 19 commits. Por eso las cifras del análisis deben
  citar el comando o el `archivo:línea` que las produjo: sin eso no hay forma de
  distinguir un dato viejo de uno inventado.

## Puntos a considerar / riesgos

- **Límites de la suscripción**: las corridas del orquestador consumen la ventana
  del plan igual que el uso interactivo; análisis largos pueden toparla.
- **Adjuntos e imágenes**: la rama de adjuntos de la skill sigue sin ejercitarse —
  ni el 3311 ni el 3322 tienen. Hace falta un ticket con captura.
- **El stepper de fases se retiró de la UI** al rediseñarla: mostraba 6 fases con 5
  apagadas en cada fila. Vuelve cuando las fases 2-4 existan de verdad.
- **El contrato del sello depende de que el agente obedezca un markdown.** Funcionó en el
  3322 con n=1. Pero si algún día declara la ruta con barras invertidas, la regex captura
  solo el primer segmento (`docs`) y el visor pasa a servir **todo ese directorio**, sin
  fallar de forma visible. Por eso las dos skills lo dicen explícitamente; no hay guarda
  en el backend que lo detecte.
- **Permisos del runner**: corre con `--permission-mode acceptEdits` más una lista
  explícita de `--allowedTools` (sin ella el MCP se auto-deniega en headless), ahora
  ramificada por fase (`PHASE_ALLOWED_TOOLS`; `analyze` va con la lista vacía).
  **El especificador `Bash(...)` habilita la herramienta, no la acota al comando** —
  verificado en corrida real. Al llegar la fase que escriba código hay que revisar qué
  modo, qué tools y qué guards corresponden, y recordar que los `extra_dirs` son de
  lectura, no sitios donde el agente deba escribir.
- **`openspec init` deja más huella de la esperada** en el repo destino: además de
  `openspec/`, instala 6 skills en `.claude/skills/openspec-*`, `.claude/commands/opsx/`
  y comandos en `.opencode/`. En `ProvidenceTMSTenant` está todo sin trackear, pendiente
  de decidir si se commitea o se revierte.
- **La Fase 2 está aceptada con n=1.** La Fase 1 enseñó que eso es aceptar poco.
- **El orquestador es v1 delgado**: sin SSE, sin corridas paralelas, columnas de
  fases 2-4 deshabilitadas — crecen junto con las fases del agente.
- **Actualizar este documento** y los checkboxes de los planes al cerrar hitos.

## Cómo retomar en una sesión nueva

Prompt sugerido — abrir Claude Code en el hub
(`D:/Companies/Jorge.Gutierrez/autonomous-skill-hub`):

> Lee docs/STATUS.md para situarte. El avance por fases, las huellas y el timeline están
> implementados y **validados con una corrida real**. El objetivo de esta sesión es el
> **segundo ticket de la Fase 2, y que sea el 3320** — está explicado en "Pendientes
> inmediatos" por qué ese y no otro carrier del #3319.
>
> 1. **Levanta el orquestador**: backend en `apps/orchestrator/backend`
>    (`.venv/Scripts/uvicorn app:app --port 8000`, **sin `--reload`**) y frontend en
>    `apps/orchestrator/frontend` (`npm run dev`). Comprueba que el proceso que escucha en
>    el 8000 arrancó **después** de la última modificación de `app.py` — nos ha engañado
>    cuatro veces ya.
> 2. **Da de alta el 3320 y corre la Fase 1.** Ojo a que el proyecto correcto tenga como
>    repo principal el que toque: el 3322 escribe en `ProvidenceTMS` y el 3323 en
>    `ProvidenceTMSTenant`.
> 3. **Encadena la Fase 2** y mira lo que de verdad se está midiendo: el 3320 no tiene
>    padre rico ni patrón que copiar, así que la regla central de `change-planning`
>    (*toda tarea cita su espejo con `archivo:línea`*) **no se puede cumplir**. Lo que hay
>    que ver es si inventa espejos para cumplir la forma o si declara las tareas como
>    investigación pendiente — esa salida honesta está escrita en la skill y nunca se ha
>    ejercitado.
> 4. Comprueba el sello de cierre en el log y el artefacto en el timeline, como se hizo
>    con el 3322.

Contexto que ya no hace falta rehacer: el TMS está configurado (`ADO_ORG` en
`.claude/settings.json`), el proyecto dado de alta en la BD del orquestador y el plugin
instalado a nivel de usuario en **v0.5.1**. El **3322 está analizado con el contrato nuevo**
y su timeline se ve completo, con artefacto abrible. El **3323** está analizado y
planificado, pero **sus corridas son anteriores al sello**, así que sale en rojo y sin
artefacto: eso es correcto, no es un bug — el backfill leyó sus logs y no había sello que
recuperar. `ProvidenceTMSTenant` es el conejillo de indias: lo que las corridas dejen ahí
no hay que versionarlo ni limpiarlo (decisión 15).

Cinco trampas conocidas: **subir `version`** al tocar una skill o el cambio no llega al
plugin instalado; **no usar `uvicorn --reload`**, que deja procesos huérfanos reteniendo
el 8000 y sirve código viejo sin avisar; el paquete de OpenSpec es **`@fission-ai/openspec`**,
no `openspec`; **el código de salida de `claude -p` no dice si el agente hizo algo** —
para eso está el sello `HUELLA:`; y **un test verde puede ser una coartada**: antes de
fiarte de uno, pregúntale qué tendría que romperse para que fallara.
