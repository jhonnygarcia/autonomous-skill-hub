# Idioma de los entregables — diseño

**Fecha:** 2026-08-19
**Estado:** diseñado, sin implementar

## El problema

Hoy el idioma de lo que produce el agente **no se elige: emerge**. Y emerge
inconsistente, en dos ejes a la vez.

Los templates de las skills están mezclados. `ticket-comprehension` y
`change-planning` escriben encabezados en inglés (`## What it asks for`,
`## Missing information`); `repo-survey` los escribe en español (`## Veredicto`,
`## Qué exige de este repo`, `## Rutas afectadas`). Ninguna de las seis SKILL.md
dice una palabra sobre idioma — un grep de `idioma|language|español|English`
sobre todo `plugins/ticket-agent/` no devuelve nada.

Y la prosa sigue al insumo. El survey real de la corrida 5
(`apps/orchestrator/backend/logs/5/survey-tenant.md`) está íntegro en español
porque el work item lo estaba, bajo encabezados que la skill escribió en
español, mientras el análisis de la misma familia de tickets sale bajo
encabezados en inglés.

Lo que se pide: **un radiobutton en la UI que decida el idioma de todo lo que el
agente produce y de toda su interacción con el humano** — los `.md` generados,
las preguntas `DECIDIR`/`BLOQUEA`, las propuestas — y, en un segundo tiempo, de
la propia UI.

## Decisiones

Las nueve que fijan el diseño, con su razón:

1. **Las SKILL.md siguen siendo instrucción en inglés.** Lo que varía es el
   producto, no el procedimiento. Mantiene la regla del proyecto y evita
   mantener seis skills por duplicado.
2. **Una sola perilla global**, en la tabla `settings`, junto a `archive_dir`.
   No por proyecto ni por corrida: un mismo ticket con el análisis en español y
   el plan en inglés es peor que la molestia de cambiar una perilla, porque la
   fase 2 consume la fase 1.
3. **Default `es`**, que es lo que hoy sale de hecho. No se retraduce nada de lo
   ya escrito.
4. **Los marcadores que el humano lee y edita se traducen**
   (`## Decisiones para ti`, `DECIDIR`, `BLOQUEA`, `Propuesta:`,
   `**Respuesta:**`, `## Corridas`, `## Hallazgos`). Es lo pedido, y su costo
   está acotado: seis regex y tres funciones.
5. **`HUELLA:` y `SONDEAR:` no se traducen**, en ningún modo. Sus valores
   (`ok|parcial|nada`) viven en `runs.artifact_state`, los lee el fold del
   estado del ticket, los pinta `status.ts` y con ellos se nombra la carpeta del
   archivo. El humano no los edita nunca.
6. **El JSON de la API normaliza los marcadores al español.** `puntos[].tipo` y
   las claves `{decidir, bloquea}` son literales de contrato: el frontend no se
   entera de que existen dos idiomas. Ver «El defecto silencioso», abajo.
7. **`specs/<capability>/spec.md` de OpenSpec se queda en inglés siempre.** Su
   esqueleto entero pertenece al parser de un CLI de terceros. Ver «OpenSpec».
8. **Los mensajes de commit de `implement` se quedan en inglés siempre.** El
   `git log` de un repo de cliente es infraestructura compartida y reescribirlo
   es caro; que dependa de una perilla de esta app no es una propiedad deseable.
9. **El vocabulario que el runner escribe dentro de un `.md` sigue la perilla**,
   pero al **agregar a un archivo que ya existe deduce el idioma del archivo**,
   no de la perilla. Ver «La cuarta categoría».

## Las cuatro categorías de texto

`CLAUDE.md` clasifica hoy el texto del proyecto en tres categorías, y la regla
de idioma se apoya en esa clasificación. Este cambio **agrega una cuarta**, y es
la única que varía en tiempo de ejecución:

| Categoría | Quién lo lee | Idioma | Ejemplos |
|---|---|---|---|
| **prompt-facing** | el agente | inglés fijo | `PHASE_NOUN`, `repos_text`, `adjustment_text`, `PACK_HEADER`, las SKILL.md |
| **UI-facing** | el humano, en el browser | español fijo (fases 4-5 lo hacen bilingüe) | `HTTPException`, las etiquetas de `status.ts`, el cromo de los `.tsx` |
| **contract literals** | un parser, byte a byte | ninguno: no se traducen | `HUELLA`, `SONDEAR`, `ok\|parcial\|nada`, las claves JSON, las rutas de las rutas HTTP |
| **deliverable-facing** ← nueva | el humano, en un `.md` del repo destino | **sigue la perilla** | el journal completo, las razones que se guardan en `runs.artifact_path`, las notas del archivo |

La cuarta es la que convierte esto en algo más que inyectar una línea al prompt.

## Arquitectura

### 1 · La perilla

Una fila en `settings`: clave `idioma`, valor `es` | `en`. `GET /idioma` →
`{idioma}`; `PUT /idioma` valida contra el conjunto y responde 400 si no.
Calcado de `GET/PUT /archivo` (`app.py:991-1013`), **leído en el momento en que
se necesita y nunca cacheado al arranque** — en Windows el backend no se
recarga, que es la razón documentada de `setting()` y `model_for()`.

En la UI, una tercera `Section` en `Settings.tsx`: `[+] Idioma`, aside
`global · aplica a la siguiente corrida`, dos radios. `Settings.tsx` ya es
exactamente ese marco; `Models` y `Archive` sólo ponen contenido.

### 2 · El idioma del entregable

**El prompt manda; `.claude/ticket-agent.json` es el respaldo.**

Un `LANGUAGE_PROMPT[idioma]` que se concatena en **los tres constructores de
prompt que existen**, y son tres, no uno:

1. el del hijo único, en `execute_run` junto a `repos_text` (`app.py:2329`);
2. **el de cada hijo del fan-out** (`SURVEY_PROMPT`, `app.py:2370`), que es un
   constructor aparte y donde el olvido no se nota: el survey saldría en el
   idioma que al hijo le parezca;
3. el de resume (`app.py:2321`), porque la perilla pudo cambiar entre corridas
   — y a diferencia de `repos_text`, que ahí se omite a propósito por estar ya
   en el contexto, el idioma es justamente lo que pudo haber cambiado.

Pero **el prompt solo no alcanza**, y esto es lo que no es obvio: las SKILL.md
llevan los encabezados del documento escritos como literales. Si `repo-survey`
dice «escribe `## Veredicto`» y el prompt dice «escribí en inglés», el agente
recibe dos órdenes contradictorias y resuelve como quiera. Por eso la fase 0
existe: normalizar los seis templates a encabezados en inglés y agregar a cada
skill una sección `## Output language` con su lista de excepciones.

Para el plugin corriendo **standalone**, sin orquestador, el respaldo es una
clave `language` en `.claude/ticket-agent.json`, al lado de `autonomy` y
`subagent_model`. `ensure_ticket_agent_config` (`app.py:1282`) la escribe desde
la perilla cuando **crea** el archivo; su promesa de no sobreescribir uno
existente no se toca.

Orden de precedencia, escrito en cada skill: **prompt → `ticket-agent.json` →
español**.

### 3 · Los marcadores bilingües

Seis regex ganan una alternancia:

| Regex | app.py | Cambio |
|---|---|---|
| `DECISION_RE` | :1674 | `(?:DECIDIR\|DECIDE\|BLOQUEA\|BLOCKS)` — alimenta el contador del timeline |
| `DECISION_ITEM_RE` | :1702 | ídem — alimenta el panel de decisiones |
| heading en `_decision_items` | :1743 | `## (?:Decisiones para ti\|Decisions for you)` |
| `PROPOSAL_RE` | :1707 | `(?:Propuesta\|Proposal):` |
| `ANSWER_BLOCK_RE` | :1829 | `\*\*(?:Respuesta\|Answer):\*\*` |
| `mark` del journal | :1245, :1271 | `## Hallazgos` **o** `## Findings`, el que el archivo tenga |

Y tres funciones que **escriben dentro de un archivo que ya existe** deducen el
idioma **del archivo, nunca de la perilla**:

- **`_write_answer`** (:1801) elige `**Respuesta:**` o `**Answer:**` según el
  marcador del ítem, que `DECISION_ITEM_RE` ya captura en el grupo 2. Sin esto,
  un análisis viejo en español respondido con la perilla en inglés queda mitad y
  mitad, y `_pre_answer_id` deja de reconocer sus propias respuestas — el 409 de
  «ya respondida» se degrada al de «el archivo cambió», que es el mensaje
  equivocado.
- **`_pre_answer_id`** (:1834) desanda con la misma detección.
- **`append_journal` / `journal_note`** (:1245, :1271) buscan el encabezado que
  el archivo tenga. `JOURNAL_HEADER` sólo usa la perilla cuando **crea** el
  journal.

`DECISION_INDENT` (seis espacios) es agnóstico al idioma y no se toca.

#### El defecto silencioso

`api.ts:73` tipa `tipo: "DECIDIR" | "BLOQUEA"` y `Decisions.tsx:86,90,91`
compara contra `"BLOQUEA"`. Si el parser empieza a devolver `BLOCKS`, **ninguna
comparación falla ruidosamente**: todo ítem bloqueante se pinta con el estilo
amarillo de `DECIDIR`. La señal más grave del sistema —«esto detiene la fase
siguiente»— se degrada en silencio a la más leve.

De ahí la decisión 6: **el marcador viaja traducido en el documento, y el JSON
de la API lo normaliza a `DECIDIR`/`BLOQUEA`**. El frontend no cambia una línea
por este motivo, y no hay una segunda copia de la tabla de traducción viviendo
en TypeScript.

### 4 · OpenSpec, y por qué el entregable de la fase 2 no es traducible entero

Verificado contra el paquete instalado (`@fission-ai/openspec@1.9.0`, en el
caché de npx). El validador exige, con nivel:

**ERROR — la corrida cierra en `parcial`:**

| Literal | Archivo | Dónde |
|---|---|---|
| `## Why`, `## What Changes` | `proposal.md` | `validator.js:639` |
| `## Purpose`, `## Requirements` | `specs/**/spec.md` | `validator.js:636`, `specs-apply.js` |
| `## ADDED\|MODIFIED\|REMOVED\|RENAMED Requirements` | deltas | `spec-structure.js`, `archive.js` |
| `### Requirement: <texto>` | deltas | `requirement-blocks.js` |
| `#### Scenario:` como header nivel 4 | deltas | `requirement-text.js` |
| ≥1 delta; ≥1 escenario por requirement ADDED/MODIFIED | | `constants.js` |

**Sólo guidance, no ERROR:** el `SHALL`/`MUST` dentro del texto del requirement.
El comentario del propio validador lo dice: *«missing **English** SHALL/MUST
keywords are guidance unless strict mode is enabled»* (`validator.js:108`). La
skill corre `validate --changes --no-interactive`, **sin `--strict`**, así que
hoy es warning y se deja como está: subir la vara volvería rojas corridas que
hoy pasan, y no es el trabajo de este cambio.

**`tasks.md` sí lo parsea** OpenSpec (`task-progress.js:21` para los `- [ ]`,
`task-numbering.js` para los grupos `## N.`) pero **es puramente estructural:
agnóstico al idioma**.

De ahí el reparto:

| Archivo del change | Idioma |
|---|---|
| `specs/<capability>/spec.md` | **inglés siempre**, en los dos modos |
| `proposal.md` | cuerpo según la perilla; `## Why` y `## What Changes` en inglés |
| `design.md` | según la perilla, `## Decisiones para ti` incluido — OpenSpec no lo mira |
| `tasks.md` | según la perilla; las etiquetas `Mirror:`/`Reuse:`/`Test:`/`Check:` quedan en inglés, porque son el contrato entre dos skills que están escritas en inglés |

**Deuda preexistente que esto destapa.** `change-planning/SKILL.md` **no
documenta ninguno de esos literales**: su template de `proposal.md` muestra
`**[Behavior]** / - From: / - To:` y `## Missing information`, pero no incluye
`## Why` ni `## What Changes`, que son obligatorios. Hoy la fase 2 depende de
que el agente los deduzca del scaffolding que deja `openspec init`. Deja de ser
ignorable: no se puede escribir «esto no se traduce» sin nombrar qué es «esto».
Documentarlos entra en la fase 0.

### 5 · Lo citado no se traduce

La regla de oro #2 de `ticket-comprehension` es que todo número que no venga del
work item cita su fuente, y los criterios de aceptación se escriben *«quoted or
faithfully paraphrased»*. Si el work item está en español y la perilla dice
inglés, **traducir una cita literal destruye su valor probatorio**: quien abra el
análisis ya no puede contrastarla contra el ticket, y la fase 2 consume ese
análisis como interfaz.

Regla para las skills, en la misma sección `## Output language`: **la cita
conserva el idioma de la fuente**; si hace falta, la traducción va al lado, y se
ve que es una traducción. Igual para identificadores de código, rutas,
`file:line`, nombres de rama, subjects de commit y mensajes de error copiados de
un build.

### 6 · El vocabulario del runner

Lo que `app.py` escribe hoy en español dentro de `docs/tickets/<id>-journal.md`,
que es un archivo del repo destino:

- `JOURNAL_HEADER` (`# Journal — <id>`, `## Corridas`, `## Hallazgos`) — :692
- los separadores de cada línea: `· rama`, `· ← resume de`, `· reserva:` — :1236-1242
- `NO_STAMP_REASON`, `NO_BRIEF_REASON`, `NO_SURVEYS_REASON`, que además **se
  guardan en `runs.artifact_path`** — :422, :690, :636, :2356
- las notas del archivo: `archivo: no copiado — …`, `más de N archivos` — :1465, :1556
- `creaste .claude/ticket-agent.json desde la UI` — :2621
- `desde run N` — :2720
- `<tipo> respondida: <pregunta>` — :2964
- y en el log del fan-out, `HUELLA: nada — ningún repo pudo sondearse` — :2098

Todos pasan a tener dos formas, elegidas por la perilla al **crear** y por el
archivo al **agregar**. Los nombres de fase (`analyze`, `design`, `restaurar`,
`decision`) son identificadores y no se traducen.

Nota: `CONSOLIDATE_PROMPT` tiene hoy un `"ninguno"` español incrustado en un
prompt inglés (`app.py:2341`). Es prompt-facing: se corrige a `"none"` de paso,
no se hace bilingüe.

### 7 · i18n de la UI

Sin dependencia nueva. Un `strings.ts` con dos `Record<string, string>`, una
función `t(k)`, y el idioma leído una vez al arrancar desde `GET /idioma`;
cambiar la perilla dispara `location.reload()`. Son ~30 líneas de máquina.

Un provider con contexto y re-render no compra nada acá: la perilla es global y
su propio aside ya dice «aplica a la siguiente corrida».

El trabajo real es la extracción, medida: **287 líneas en 18 archivos**,
concentradas en `Models.tsx` (51), `Timeline.tsx` (45) y `ProjectForm.tsx` (39).

### 8 · Mensajes del backend

**49 `HTTPException` con detalle en español** salen como toast. Con la UI en
inglés y los toasts en español el trabajo se ve a medias, así que entran — al
final, en su propia fase, porque son 49 ediciones mecánicas y ninguna cambia
comportamiento. Un dict `MSG[clave][idioma]` leído con `setting("idioma")`.

Las razones que se **guardan** (`NO_BRIEF_REASON` y familia) no son de esta
fase: son deliverable-facing y las cubre la fase 3.

## Lo que no se hace, y por qué

- **No se retraduce nada de lo ya escrito.** El archivo y el journal son
  registro histórico; reescribirlos sería falsificar lo que una corrida produjo.
- **No se detecta ni se avisa si el análisis quedó en un idioma y el plan en
  otro.** La perilla es global y del humano; detectar el idioma de un `.md`
  técnico —lleno de identificadores en inglés— es una heurística que falla justo
  donde importa. El journal ya deja constancia de cada corrida.
- **No se traducen `HUELLA` ni `SONDEAR`** (decisión 5).
- **No se agrega `--strict` al validador de OpenSpec.** Volvería rojas corridas
  que hoy pasan, y es una decisión de calidad ajena a esta.
- **No hay tercer valor «auto».** Dos opciones, como se pidió.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El marcador traducido rompe `Decisions.tsx` en silencio | La API normaliza `tipo` al español (decisión 6). Un test lo fija. |
| Un journal a medio traducir tras cambiar la perilla | Al agregar, el idioma se deduce del archivo, no de la perilla. |
| Una corrida en inglés sobre un work item en español degrada la fidelidad | La regla de las citas: lo citado conserva su idioma. |
| El agente traduce los literales de OpenSpec y la fase 2 cierra `parcial` | La sección `## Output language` los lista explícitamente, y la fase 0 los documenta por primera vez. |
| `_pre_answer_id` deja de reconocer respuestas propias | `ANSWER_BLOCK_RE` bilingüe + detección desde el ítem. Test de ida y vuelta en los dos idiomas. |

## Fases

| # | Qué | Tamaño |
|---|---|---|
| 0 | Normalizar los 6 templates; `## Output language` con su lista de excepciones; documentar los literales de OpenSpec en `change-planning`; fijar los commits en inglés en `change-implementation`. Bump de `plugin.json` **y de los 3 sellos de versión** (`plugin.json`, el sello del análisis en `ticket-comprehension`, el de la colección en `ticket-brief`) | 8 archivos, sin código |
| 1 | Perilla: `settings.idioma`, `GET/PUT /idioma`, `LANGUAGE_PROMPT` en los tres constructores de prompt, `language` en `ticket-agent.json`, radio en `Settings.tsx` | ~60 líneas backend, ~50 frontend |
| 2 | Marcadores bilingües: 6 regex, detección desde el archivo en 3 funciones, normalización de `tipo` en la API | ~40 líneas |
| 3 | Vocabulario del runner: journal, razones persistidas, notas del archivo | ~40 líneas |
| 4 | i18n de la UI: `strings.ts` + `t()` + extracción | 287 líneas, 18 archivos |
| 5 | Los 49 `HTTPException` | mecánico |

Las fases 0-3 son el producto completo; 4 y 5 son el acabado. Cada una entrega
valor sola.

## Tests

**Costo medido en la suite existente:** 114 líneas de `test_app.py` tocan
marcadores traducibles, repartidas en **26 de 252 funciones**. Casi todas son
fixtures que escriben un `## Decisiones para ti` de prueba, no aserciones sobre
el idioma. La forma barata es un helper de fixture parametrizado por idioma y
correr el grupo de decisiones en los dos, en vez de 26 reescrituras.

Lo que hay que fijar con un test nuevo:

1. `PUT /idioma` rechaza cualquier valor fuera de `{es, en}`.
2. El directivo de idioma llega al prompt del hijo único **y al de cada hijo del
   fan-out** — los dos fakes (`fake_claude.py`, `fake_codex.py`) hacen eco del
   prompt, así que se verifica sobre el eco.
3. Un análisis en inglés con `**DECIDE**` se parsea, y `GET /decisiones`
   devuelve `tipo: "BLOQUEA"` para un `**BLOCKS**` — la normalización.
4. Responder un ítem en un documento español escribe `**Respuesta:**` **aunque
   la perilla diga inglés**, y viceversa.
5. Ida y vuelta de `_pre_answer_id` en los dos idiomas.
6. `append_journal` sobre un journal con `## Findings` inserta antes de ese
   encabezado y no crea un `## Hallazgos` paralelo.
7. Lo de siempre, que este cambio no debe romper: los finales de línea se
   preservan (`\r\n` y `\n`), y responder un ítem toca sólo los bytes de ese
   ítem.
