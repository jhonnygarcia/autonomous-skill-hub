# Estado del proyecto — Autonomous Skill Hub

> Documento vivo. Actualízalo al cerrar cada hito o al tomar una decisión.
> Última actualización: 2026-08-10 (Fase 2 construida y validada sobre el 3323)

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
| Orquestador (transversal) | App local: cola SQLite + runner CLI headless + UI React | ✅ **Ciclo completo verificado**, ahora con dos fases lanzables — ⏳ falta el repaso visual de la UI |
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
    llegó a significar "el subproceso no petó". Ahora la skill cierra con un sello
    (`PLAN: validado` | `sin-validar` | `no-escrito`) y el runner decide por la **última**
    coincidencia en el log. Ver "Lo aprendido" para por qué *última* y no *presente*.

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

## Pendientes inmediatos

- [ ] **Repaso visual de la UI**: sigue sin poder verificarse (el navegador con el perfil
  de devtools es el de Jhonny y el MCP no puede adjuntarse si ya está abierto). Recorrer
  las tres vistas, los cinco estados vacíos, y ahora también el botón *Planificar*.
- [ ] **Segundo ticket para la Fase 2.** Está aceptada con **n=1**, y la lección de la
  Fase 1 fue justo esa: el 3311 salió perfecto y el fallo solo apareció con el segundo.
  Buen candidato: otro carrier del #3319, que ejercita el mismo camino con otra forma.
- [ ] **Decidir qué se hace con `Bash` en el runner.** Ver "Lo aprendido": el
  especificador no acota. Hoy `analyze` va con la lista vacía, pero la Fase 2 tiene Bash
  disponible de facto para más que `npx`.
- [ ] **Revertir o commitear la huella de `openspec init` en `ProvidenceTMSTenant`**:
  dejó 6 skills en `.claude/skills/openspec-*`, `.claude/commands/opsx/`, y 6 comandos
  más `skills/` en `.opencode/`. Todo sin trackear. Es más de lo que el spec anunciaba.
- [ ] **Quitar `organization` de `.claude/ticket-agent.json`** — duplica `ADO_ORG`,
  que no se puede eliminar porque el MCP la necesita como env var al arrancar.
- [ ] **Deuda menor anotada** (de la revisión final, ninguna bloqueante): el `title` del
  botón *Planificar* oculta una de las dos razones cuando coinciden; el log se lee entero
  para quedarse con 4 KB; el `assert` de las claves de fase desaparece con `python -O`;
  "Enviar ajuste" siempre lanza `analyze`, no hay forma de re-planificar con instrucciones.

## Lo aprendido (2026-08-10)

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
- **Las columnas de fase del orquestador ya no están deshabilitadas: no están.**
  Al llegar la Fase 2 hay que decidir cómo se representa el avance por fases.
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

> Lee docs/STATUS.md para situarte. Vamos por los pendientes en este orden:
>
> 1. **Levanta el orquestador**: backend en `apps/orchestrator/backend`
>    (`.venv/Scripts/uvicorn app:app --port 8000`, **sin `--reload`**) y frontend
>    en `apps/orchestrator/frontend` (`npm run dev`). Antes de dar nada por bueno,
>    comprueba que el proceso del 8000 arrancó **después** de la última modificación
>    de `app.py` — ya nos engañó tres veces.
> 2. **Segunda prueba de la Fase 2**, que hoy está aceptada con n=1. Elige otro carrier
>    del Feature #3319 (mismo camino, otra forma), dalo de alta, corre `analyze` y luego
>    *Planificar*. Comprueba tres cosas en el log y en el change: que
>    `openspec validate --changes` pasa, que los espejos que cita los **abrió de verdad**
>    (cuenta las lecturas, no las citas), y que lo que no se puede hacer está bajo
>    `## Bloqueado` en vez de convertido en tarea.
> 3. Con el resultado, dime si `change-planning` necesita ajuste. Si sí: edítala,
>    **sube `version` en `plugin.json`**, `claude plugin update
>    ticket-agent@autonomous-skill-hub`, y re-corre.
> 4. **Repaso visual de la UI**, que sigue pendiente desde el rediseño: las tres vistas,
>    los cinco estados vacíos, y el botón *Planificar* en sus cuatro situaciones
>    (sin análisis, con análisis, con corrida activa, y tras una Fase 2 fallida).
> 5. Al cerrar, actualiza docs/STATUS.md.

Contexto que ya no hace falta rehacer: el plugin está instalado a nivel de usuario
(**v0.4.2**), el TMS configurado (`ADO_ORG` en `.claude/settings.json`), y el proyecto
dado de alta en la BD del orquestador con `ProvidenceTMSTenant` como repo principal.
El 3322 y el 3323 ya están analizados, y el 3323 además planificado.

Cuatro trampas conocidas: **subir `version`** al tocar una skill o el cambio no llega al
plugin instalado; **no usar `uvicorn --reload`**, que deja procesos huérfanos reteniendo
el 8000 y sirve código viejo sin avisar; el paquete de OpenSpec es **`@fission-ai/openspec`**,
no `openspec`; y **el código de salida de `claude -p` no dice si el agente hizo algo** —
para eso está el sello `PLAN:`.
