# Diseño: Fase 2 — del análisis al plan de cambios

**Fecha:** 2026-08-09
**Estado:** Aprobado por Jhonny (7 decisiones votadas en brainstorming)
**Alcance:** una skill y un comando nuevos en `ticket-agent`, más el orquestador
mínimo para lanzarlos. **No se escribe código de producto.**
**Ticket de validación:** User Story **3323** — *Carrier API V2 Migration - XPO*.

## Propósito

La Fase 1 produce un análisis fiel de un work item. Ese análisis no es accionable:
describe el problema, no el cambio. La Fase 2 cierra ese hueco produciendo un
**plan de cambios que otro agente pueda ejecutar** — archivo por archivo, con el
espejo del que se copia y la comprobación que lo valida.

La Fase 2 **no escribe código de producto**. Su entregable es un documento. Escribir
el código es una fase posterior, con sus propios permisos y guards.

## Decisiones (votadas)

| # | Decisión | Por qué |
|---|---|---|
| 1 | El entregable es **solo el plan**, ningún `.cs` tocado | Mantiene la corrida en solo lectura + escribir markdown, igual que la Fase 1. Ni ramas ni permisos de escritura que resolver todavía |
| 2 | El plan se escribe **para el agente que lo implemente**, no para un humano | Manda el listado verificable sobre la prosa: destino, espejo con líneas, contrato, comprobación |
| 3 | **Consume el análisis de Fase 1; sin él se detiene** | Dos skills pequeñas encadenadas. El análisis es la interfaz: si sale mal, se ve en el archivo y se re-corre la Fase 1 sola |
| 4 | **Se adopta OpenSpec** como formato, con su carpeta en el repo destino | Formato probado y pensado para agentes. Se asume la dependencia del CLI |
| 5 | Si el repo destino no tiene `openspec/`, **la corrida lo inicializa** | Un solo botón funciona siempre, sin un paso manual previo por repo |
| 6 | Bash acotado a **`Bash(npx openspec:*)`** | El agente puede inicializar y validar; cualquier otro comando se deniega solo |
| 7 | Se lanza con un botón **Planificar** en el detalle del ticket | El camino real (headless, `allowedTools`, etiquetas de repos) es justo donde han aparecido los fallos; probar por fuera de él da resultados falsos |

## Estructura

| Dónde | Qué |
|---|---|
| `plugins/ticket-agent/commands/plan.md` | comando `/ticket-agent:plan <id>`, delega en la skill |
| `plugins/ticket-agent/skills/change-planning/SKILL.md` | el procedimiento completo |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | `version` → **0.4.0** |
| `apps/orchestrator/backend/app.py` | fase → comando; `Bash(npx openspec:*)`; estado `planned` |
| `apps/orchestrator/frontend/.../TicketDetail` | botón **Planificar** |

Skill nueva y hermana, no una rama dentro de `ticket-comprehension`: cada skill
tiene un trabajo, y la de comprensión ya es larga.

## Procedimiento de la skill

1. **Configuración** — lee `.claude/ticket-agent.json` del repo destino (`project`,
   `autonomy`), igual que la Fase 1.
2. **Precondición: el análisis** — `docs/tickets/<id>-analysis.md` debe existir. Si
   no está, **detente** y di que hay que correr la Fase 1 primero. No lo generes.
3. **Precondición: OpenSpec** — si no existe `openspec/` en la raíz del repo,
   `npx openspec init`.
4. **Lee el análisis.** De ahí salen el alcance, los criterios de aceptación, el
   código afectado y las referencias citadas. **No vuelvas al MCP de Azure DevOps**:
   el análisis es la interfaz entre fases. Si le falta algo, eso es un fallo de la
   Fase 1 y se reporta como tal.
5. **Estudia el patrón en el código.** Abre los archivos que el análisis señala y
   los equivalentes ya resueltos que vayan a servir de espejo. Cada afirmación
   sobre el código se comprueba abriéndolo.
6. **Escribe el change** en `openspec/changes/<id>-<slug>/`:
   `proposal.md`, `tasks.md`, `design.md` y `specs/<capability>/spec.md`.

   - `<slug>`: el título del work item en kebab-case, sin puntuación y recortado a
     unas 5 palabras. Para el 3323 (*Carrier API V2 Migration - XPO*):
     `openspec/changes/3323-carrier-api-v2-migration-xpo/`.
   - `<capability>`: el nombre de la capacidad del sistema que se toca, no el del
     ticket — es la carpeta que OpenSpec reutiliza entre cambios. Sale del proyecto
     o módulo afectado según el análisis; para el 3323, `carrier-gateway`. Si ya
     existe una capacidad en `openspec/specs/` que encaje, se usa esa en vez de
     inventar una nueva.
7. **Valida** — `npx openspec validate`. Si falla, corrige y revalida. **A la
   segunda validación fallida, para**: deja el change escrito y reporta qué no pasa.
8. **Cierre** según `autonomy`, igual que la Fase 1.

## Reglas de oro

Heredan de `ticket-comprehension` y añaden una:

1. **Lo que no se pudo leer se reporta; jamás se rellena con suposiciones.**
2. **Toda cifra ajena al work item cita su fuente** — `archivo:línea`, commit o comando.
3. **Toda tarea cita el espejo del que se copia, con `archivo:línea`.** "Crear
   `XpoRateCall.cs`" sin decir de dónde se copia no es una tarea, es un deseo.
4. **Lo bloqueado se declara bloqueado, no se planifica alrededor.** Si el análisis
   dice que un verbo no está cableado, `tasks.md` no lleva una tarea para ese verbo:
   lleva un bloqueo con su motivo y la referencia que lo respalda.

La regla 4 existe por lo aprendido en la Fase 1: un agente prefiere entregar algo
completo antes que admitir un hueco. En la corrida del 3322 eso se manifestó como
"fuera de este repo, no inspeccionado"; aquí se manifestaría como una tarea que
parece ejecutable y no lo es.

## Cambios en el orquestador

**Backend.** Hoy `execute_run` hardcodea `prompt = f"/ticket-agent:analyze {ado_id}"`
y `run_ticket` inserta siempre `phase="analyze"`. Pasan a derivarse de la fase de la
corrida:

| Fase | Comando |
|---|---|
| `analyze` | `/ticket-agent:analyze <id>` |
| `design` | `/ticket-agent:plan <id>` |

`POST /tickets/{tid}/run` acepta la fase en el cuerpo, con `analyze` por defecto para
no romper a quien ya llama sin ella. `--allowedTools` suma `Bash(npx openspec:*)`.
Estado del ticket al terminar bien una corrida `design`: **`planned`**.

Las fases siguen restringidas a las ejecutables: pedir `implement` responde `400`.

**Frontend.** Botón **Planificar** junto a "Ajustar y re-correr", visible solo con el
ticket en `analyzed` o `planned`, y bloqueado mientras haya una corrida activa —
la misma regla que ya aplica `estado.ts`. La lista de corridas muestra la fase.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| No existe `docs/tickets/<id>-analysis.md` | La skill se detiene y pide correr la Fase 1. La corrida termina en `error` con el motivo en el log |
| `npx` no disponible o sin red | La skill se detiene y lo dice. **No hay plan B escribiendo los archivos a mano**: `openspec validate` es parte del trato (consecuencia asumida de la decisión 4) |
| `openspec validate` falla dos veces | Deja el change escrito y reporta qué no pasa. No lo borra: un change inválido revisable vale más que nada |
| El análisis existe pero le falta el código afectado | Se planifica lo que se pueda y el resto va a "Información faltante", señalando que el fallo es de la Fase 1 |
| Se pide una fase no ejecutable | `400` del backend, sin lanzar subproceso |

## Pruebas

**Del orquestador** (pytest, con `fake_claude.py`):

- una corrida `design` invoca `/ticket-agent:plan <id>` y no `:analyze`;
- el argv incluye `Bash(npx openspec:*)`;
- una corrida `design` con éxito deja el ticket en `planned`;
- pedir una fase no ejecutable devuelve `400`;
- sin fase en el cuerpo, sigue siendo `analyze`.

**De la skill** — corrida real sobre el **3323**, en este orden: Fase 1 (su análisis
aún no existe) y luego Fase 2. Se acepta si:

1. `npx openspec validate` pasa;
2. las tareas citan `AbfRateCall.cs:<líneas>` como espejo concreto, no "sigue el
   patrón de ABF";
3. **GetDocs aparece como bloqueado**, no como tarea — el hallazgo 4 del Feature
   #3319 dice que no hay ningún `UseV2(..., CarrierVerb.GetDocs)` en el gateway,
   así que el verbo no se puede migrar todavía aunque el ticket lo pida.

El punto 3 es el examen. Es el mismo tipo de prueba que fue leer de verdad
`ProvidenceTMSTenant` en la Fase 1: mide si el agente admite un hueco en vez de
taparlo.

## Por qué el 3323 y no el 3320

El 3323 es de 3 puntos, solo backend, y su Feature padre **#3319** trae un inventario
verificado con la *Definition of Done* por carrier. El patrón a replicar ya existe
escrito dos veces en el repo: `PTMS.CarrierGateway/Carriers/Abf/` (10 archivos) y
`Estes/` (7). XPO tiene su integración legacy completa (`XPORateCall.cs`,
`XpoTenderCall.cs`, `XpoTrackCall.cs`, `XPODocumentCall.cs`) y **cero archivos en V2**.

Es el caso más favorable para generar un plan — "replica este patrón" — y a la vez
trae la trampa de GetDocs. Un candidato fácil con un examen dentro.

El 3320 se descartó: es un buen bug, pero no tiene patrón de referencia ni un padre
que fije la Definition of Done.

## Fuera de alcance

- Escribir código de producto, crear ramas, escribir tests del repo destino, abrir PR.
- Las fases `implement`, `test`, `guards` y `pr`: siguen declaradas y no ejecutables.
- Reintroducir el stepper de fases en la UI (se retiró con motivo; vuelve cuando haya
  fases de verdad que mostrar).
- Adoptar OpenSpec en este hub. Se adopta en el **repo destino**, que es donde vive
  el cambio planificado.
