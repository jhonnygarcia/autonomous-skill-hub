# Orquestador agnóstico de engine — diseño

**Fecha:** 2026-08-16 · **Estado:** etapas 1, 2 y 3 hechas; queda la 4 (engines sin MCP en fase 1) ·
**Decisión asociada:** 18 en `docs/STATUS.md`

## El problema

El orquestador es, mirado de frente, un **wrapper**: lanza un prompt contra un repo,
con un modelo y un effort, y recoge lo que quedó escrito en disco. Nada de eso es
propio de Claude Code. Pero el runner sí lo es: invoca comandos `/ticket-agent:*` que
solo existen como plugin de Claude, parsea su `stream-json`, y hasta hace una hora
inyectaba un hook `PreToolUse` con `--settings`.

Consecuencia práctica: un cliente con Copilot y sin suscripción de Anthropic no puede
usar la herramienta, y un ticket no puede planearse con Codex aunque convenga.

La suscripción la pone el usuario en su máquina — eso queda fuera de esta herramienta,
igual que hoy queda fuera `az login`.

## El contrato de una corrida

Lo que el orquestador necesita de un engine, y nada más:

1. Se lanza como **subproceso** con `cwd` en el repo primario y termina solo.
2. Recibe **un prompt** por argumento o stdin.
3. Deja **archivos en disco** (el entregable de la fase).
4. Escribe en su salida la línea **`HUELLA: ok|parcial|nada — <ruta>`**.
5. Opcionalmente expone un **id de sesión** para continuar (si no, `puede_continuar`
   queda en `false`, que es lo que ya pasa con los hijos de fan-out).

Los puntos 3 y 4 ya son agnósticos: `HUELLA` es texto plano y el archivo entre fases
es la interfaz que hace que la fase 2 no sepa quién escribió el análisis. Lo acoplado
es cómo se lanza (1, 2) y de dónde se lee la huella y la sesión.

## Codex, verificado a mano contra un binario real (2026-08-16)

Instalado `codex-cli 0.147.0`. Lo de abajo no viene de la documentación: sale de
correrlo. **Esta sección manda sobre la tabla general** para todo lo que sea Codex.

### Los flags que necesita el runner

| Lo que hace el runner hoy con Claude | En `codex exec` |
|---|---|
| `-p "<prompt>"` | prompt **posicional**, o `-` leyendo de stdin. **`-p` en Codex es `--profile`**, no el prompt |
| `cwd=repo_path` | `-C, --cd <DIR>` |
| `--add-dir <extra>` | `--add-dir <DIR>` (y son directorios *escribibles*, no solo legibles) |
| `--model` | `-m, --model` |
| `--effort` | `-c model_reasoning_effort=<v>` con `v` ∈ `none·minimal·low·medium·high·xhigh` (la lista salió de un error del propio binario) |
| `--output-format stream-json` | `--json` (JSONL) |
| `--permission-mode acceptEdits` | **`--approve-for-me`** — y ojo: en 0.118 esto era `--full-auto`, que en 0.147 **ya no existe** en `exec` |
| `--allowedTools` | `-s, --sandbox read-only\|workspace-write\|danger-full-access` |
| `--resume <id> --fork-session` | `codex exec resume <id>` / `--last` |
| — | `-o, --output-last-message <FILE>`: el mensaje final en un archivo limpio. **No tiene equivalente en Claude y es mejor sitio para leer la huella que el log** |
| — | `--ignore-user-config`: hace la corrida reproducible, pero también tira los MCP del `config.toml` |

Sin `--approve-for-me`, `exec` corre **read-only** y rechaza toda escritura aunque se
pase `--sandbox workspace-write`: la primera corrida de prueba leyó el archivo de
entrada y no pudo escribir el de salida.

### Tres cosas que cambian el diseño

1. **`STAMP_RE` y `read_stamp` funcionan sobre el JSONL de Codex sin tocar una línea.**
   Comprobado sobre un log real: `read_stamp(run.jsonl) → ('ok', 'salida.md')`. La
   huella es de verdad agnóstica. Lo único que falla es `SESSION_RE`: Codex emite
   `"thread_id"`, no `"session_id"` — un regex por engine y nada más.

2. **La huella miente, y el runner se lo cree.** En la corrida donde la escritura fue
   rechazada, Codex terminó con **exit 0** y `HUELLA: ok — salida.md` **sin haber
   escrito el archivo**. El contrato existe precisamente para atrapar "terminó sin
   hacer nada" y no lo atrapó, porque asume que el agente dice la verdad. Esto no es un
   problema de Codex: es un agujero del contrato que Claude también puede atravesar.
   **Arreglo: el runner verifica en disco la ruta que la huella declara.** Si la huella
   dice `ok` y el archivo no existe, la corrida no es `ok`.

3. **El binario en el PATH miente.** `where codex` daba 0.118.0 (instalado por nvm)
   mientras el binario del app en `%LOCALAPPDATA%/Programs/OpenAI/Codex/bin` era
   0.147.0, y el modelo por defecto del usuario (`gpt-5.6-sol`) **solo funciona en el
   nuevo**: el viejo devuelve `400 … requires a newer version of Codex`. El registro de
   engines necesita **ruta configurable por engine**, no un nombre de comando pelado
   — igual que `ORCH_CLAUDE_CMD` ya hace para las pruebas.

Nota aparte: Codex **también tiene hooks** (`[[hooks.SessionStart]]` en `config.toml`,
con `--dangerously-bypass-hook-trust`). No cambia la decisión 18: son formatos
distintos por CLI, que es justo el argumento para no apoyarse en ninguno.

### La prueba real: `analyze` completo con Codex

Corrida a mano el 2026-08-16 contra `ProvidenceTMSTenant`, sobre una solicitud `R-`
(`R-notas-cliente`) porque es la entrada que no necesita Azure. El prompt fue un
**prompt pack**: el `SKILL.md` de `ticket-comprehension` entero, inline, más el párrafo
que niega el work item. 12.7 KB de prompt, `gpt-5.6-sol` con effort `high`.

**Salió bien, y con más obediencia de la esperada.**

- Primera corrida: **paró en la precondición correcta** — faltaba
  `.claude/ticket-agent.json` — y cerró con
  `HUELLA: nada — falta .claude/ticket-agent.json; el procedimiento prohíbe continuar`.
  El contrato de parada funciona en un engine que nunca vio la skill instalada.
- Segunda: escribió el análisis (14.6 KB) con **las 14 secciones de la plantilla, en
  orden**, el sello `by ticket-agent v0.11.0`, `DECIDIR — PROPUESTO` en los criterios
  deducidos y un `BLOQUEA` real (qué roles son "personal de oficina", sin default
  defendible). Escribió además el journal con su línea en `## Corridas` y un
  `## Hallazgos` con un problema de autorización que no le habíamos preguntado.
- **No inventó rutas**: 31 de 32 citas resuelven a archivos reales (la restante es una
  abreviatura de directorio, no un invento). Y **no invento el work item**, que es el
  fallo que enseñó la corrida 3320.

Costo de esa corrida: 6.95 M tokens de entrada (6.66 M cacheados) y 21 K de salida.
No es gratis y hay que medirlo por fase antes de prometer nada.

**El hallazgo que cambia el diseño: Codex lee fuera del repo raíz.** `-C` es un
directorio de trabajo, **no un límite**. La corrida leyó por su cuenta el `CLAUDE.md`
del directorio padre y archivos del repo vecino `../ProvidenceTMS/.../ClientApp`, y armó
con eso la sección de frontend — etiquetándola honestamente como "repo vecino", eso sí.
Claude Code no puede hacer eso: está confinado a `cwd` + `--add-dir`.

Corta para los dos lados y hay que decidirlo, no heredarlo:

- A favor: el análisis salió más rico, con el contrato entre repos sin fan-out.
- En contra: **es exactamente el defecto que el diseño multi-repo existe para evitar** —
  leer un repo vecino bajo las reglas del repo primario— pero ahora sin que nadie lo
  haya montado, y sin techo: puede leer cualquier cosa del disco.

Consecuencia para el registro: cada engine necesita declarar también su **límite de
lectura**, no solo el de escritura. En Codex hay que buscarlo en la configuracion de
sandbox; queda por verificar cuál es el flag exacto.

Nota lateral: el repo ya tiene `AGENTS.md` junto al `CLAUDE.md`. Codex lee `AGENTS.md`
de forma nativa, así que el archivo de reglas cross-engine ya existe y no hay que
inventarlo.

### Y `plan`: paró en el `BLOQUEA`, que es el mejor resultado posible

Segunda corrida encadenada, mismo engine, misma máquina: el prompt pack de
`change-planning` contra el análisis que Codex acababa de escribir. **No escribió el
plan**, y eso es exactamente lo correcto: leyó el `## Decisiones para ti`, encontró un
`BLOQUEA` sin responder y cuatro `DECIDIR` sin marcar, y cerró con

    HUELLA: nada — 5 decisiones sin resolver

sin inicializar OpenSpec y sin proceder en silencio con ningún `DECIDIR` — el repo tiene
`autonomy: supervised`. Dejó además su línea en el journal.

**Esto es lo que valida el diseño entero.** La costura humana entre fases —`DECIDIR`
propone y sigue, `BLOQUEA` para— no era un mecanismo, es una convención escrita en
markdown, y la duda razonable era si un engine que nunca vio la skill la respetaría.
La respeta. Y el journal acumuló las dos corridas en `## Corridas` conservando
`## Hallazgos` al final, con dos engines de la misma familia pero ninguna instalación
del plugin de por medio.

Costo: 338 K tokens de entrada (297 K cacheados), 3.8 K de salida — un orden de
magnitud menos que `analyze`, porque paró temprano.

**`npx @fission-ai/openspec` bajo Codex: probado el 2026-08-17 y funciona** — pero por
una razón que no hay que celebrar. `npm view` contactó el registry y `npx cowsay@1.6.0`
descargó un paquete que no estaba en caché, o sea red abierta. Solo que eso es cierto
**en Windows**, donde Codex no sandboxea de esa forma; donde sí lo hace (Linux, macOS)
`workspace-write` viene **sin red** por defecto. Apoyarse en la plataforma más débil es
publicar una fase que funciona en la máquina donde se construyó y muere en la del
compañero. Por eso `codex_argv` pasa `-c sandbox_workspace_write.network_access=true`
en las fases que corren comandos (`PHASE_NETWORK`, derivado de quién lleva Bash). La
clave está verificada, no adivinada: `--strict-config` la acepta y rechaza una
inventada.

### La etapa 3, verificada por el orquestador de verdad (2026-08-17)

No con fakes: `ORCH_CODEX_CMD` apuntando al binario real y una corrida completa por
`POST /tickets/{id}/run`, sobre una solicitud `R-` en `ProvidenceTMSTenant`.

    engine   : codex
    status   : success
    estado   : parcial
    huella   : parcial -> docs/tickets/R-1-analysis.md
    session  : 01a00fd1-f5e6-7433-9c7b-38b5f0f69ee6
    continuar: True
    motivo   : wiki unavailable and configured code-graph project not indexed

El análisis salió con sus 12 secciones, el sello `v0.11.0`, 6 `DECIDIR` y 1 `BLOQUEA`,
y el journal acumuló **las tres corridas** —dos que pararon por falta de
`.claude/ticket-agent.json` y la buena— con duración y la línea de reserva, escritas por
`append_journal`, con `## Hallazgos` de la skill debajo. O sea: el `JOURNAL_CLAIM` viaja
dentro del pack y se obedece, y `split_reserve` parsea el ` · ` de un `parcial` que
escribió Codex.

Dos cosas se rompieron y solo aparecieron aquí, no en los tests:

1. **Con el prompt por stdin el log guardaba la línea de argv y nada más** — registraba
   que algo se lanzó, no qué se pidió. El runner ahora escribe el prompt bajo su propio
   encabezado. El test que debía atraparlo pasaba porque el fake devolvía el prompt como
   eco: un fake demasiado servicial es un test que no afirma nada.
2. **`survey` armaba sus hijos con Claude fijo**, así que elegir otro engine ahí se
   habría guardado y luego ignorado. Ahora se rechaza con el motivo escrito.

### La fase 2 entera bajo Codex, con OpenSpec de verdad (2026-08-17)

La última duda abierta, cerrada. `design` lanzada por `POST /tickets/{id}/run` con
`engine: codex` sobre el análisis `R-1` (ticket sintético del hub, así que responder sus
decisiones no decide nada del cliente):

    status : success
    huella : ok -> openspec/changes/R-1-nota-interna-ficha-cliente

Dentro de la corrida, el comando real y su salida real:

    npx --yes @fission-ai/openspec@latest validate --changes --no-interactive
    ✓ change/R-1-nota-interna-ficha-cliente
    Totals: 1 passed, 0 failed (1 items)      exit 0

Y el cambio completo en disco: `proposal.md`, `design.md`, `tasks.md` y
`specs/company-profiles/spec.md`. Antes de eso, `openspec init` creó `config.yaml` —
o sea npx descargó y ejecutó el paquete dentro del sandbox, no desde un caché tibio.
Ninguna denegación del sandbox en todo el log (los `denied` que aparecen son
`AccessDenied` del código C# del repo).

**El primer intento paró**, y también eso es resultado: `HUELLA: nada — 5 decisiones sin
resolver`. Con `autonomy: supervised` un `DECIDIR` sin marcar detiene la fase siguiente,
igual que en Claude. La costura humana no depende del engine.

## Lo verificado por CLI (2026-08-16)

Modo no-interactivo, que es el único que importa aquí:

| | Invocación | Modelo | Effort | Salida estructurada | Resume | MCP por repo |
|---|---|---|---|---|---|---|
| Claude Code | `claude -p` | `--model` | `--effort low…max` | `--output-format stream-json` | `--resume <id> --fork-session` | sí (`.mcp.json`) |
| Codex CLI | `codex exec` | `--model` | `-c model_reasoning_effort=…` | `--json` (JSONL) | `codex exec resume <id>\|--last` | no (`~/.codex/config.toml` global) |
| Gemini CLI | `gemini -p` | `-m` | **no existe** | `--output-format stream-json` | por verificar | sí (`.gemini/settings.json`) |
| Kimi Code CLI | `kimi -p` | `-m` | **no existe** | `--output-format stream-json` | `--session <id>` / `--continue` | no (`config.toml`) |
| Copilot CLI | `copilot -p` | `--model` | **no existe** | **no hay** (texto; `-s` lo limpia) | por verificar con `-p` | no |

Tres conclusiones que cambian el diseño:

- **`effort` no es universal.** El registro necesita `supports_effort` por engine y la
  UI oculta el campo cuando es `false`. No se emula con "piensa más" en el prompt: eso
  es un prompt, no una configuración, y mentiría en la UI.
- **Copilot no tiene salida estructurada.** Se puede orquestar (contrato: proceso +
  huella + archivos) pero nunca dará `session_id`, así que no tendrá continuaciones.
  Es el peor ciudadano headless y va al final de la fila, o no va.
- **Solo Claude y Gemini configuran MCP por repo.** En el resto, el MCP de Azure DevOps
  es configuración global de la máquina → entra en el README como checklist por engine.
  Esto solo afecta a `analyze`/`brief`; las demás fases no tocan Azure.

Nota de riesgo: Gemini CLI está anunciado como reemplazado por **Antigravity CLI** para
tier gratuito/Google One en junio. Otra razón para que sea un adaptador y no supuestos
regados por el runner.

## Lo que casa `app.py` a Claude hoy

| Acoplamiento | Dónde | Peso | Salida |
|---|---|---|---|
| `/ticket-agent:<cmd>` (requiere plugin instalado) | `PHASE_COMMANDS` | bloqueante | *prompt pack*: el `SKILL.md` renderizado inline, como ya viaja el brief a los hijos de survey |
| `SESSION_RE`/`STAMP_RE` sobre `stream-json` escapado | ~220-240, 1141 | bloqueante | parser por engine; `HUELLA` no cambia, cambia dónde se busca |
| `--permission-mode`, `--allowedTools`, `PHASE_MCP` | ~1380 | bloqueante | mapa de permisos por engine (Codex `--sandbox`, Gemini `excludeTools`, Kimi `--auto`, Copilot `--allow-tool`) |
| `--resume --fork-session` | ~1400 | medio | por engine, **nunca cruzado**: `runs.engine` obligatorio |
| `--add-dir` | ~1382-1405 | medio | Codex/Copilot lo tienen; Gemini usa `--include-directories`; Kimi por verificar |
| `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` | ~1420 | bajo | solo Claude; en el resto no hay equivalente, se documenta |
| Strip de `ANTHROPIC_*` | ~1409 | bajo | lista por engine (`OPENAI_API_KEY`, `GEMINI_API_KEY`…), misma regla de "suscripción, no API key" |
| ~~hook `--settings`~~ | — | **resuelto** | eliminado el 2026-08-16, decisión 18 |

Y lo que **no** está acoplado, que es el núcleo: `HUELLA`, `DECIDIR`/`BLOQUEA`, el
journal, el archivo entre fases, la XOR de `POST /tickets`, `PHASE_DONE`, la rama.

## Forma prevista

Una quinta tabla junto a las cuatro `PHASE_*`, con la misma lógica de "la fase decide":

```python
ENGINES = {
  "claude": {"argv": …, "session_re": …, "resume": …, "supports_effort": True,  …},
  "codex":  {…, "supports_effort": True},
  …
}
```

`phase_config` gana columna `engine` (default `"claude"`), `runs` también (para que
`puede_continuar` no cruce engines). La UI de Settings pasa de *(fase → modelo)* a
*(fase → engine, modelo, effort si aplica)*: el mismo `Models.tsx` con un dropdown más
y un campo condicional.

**Esto vive solo en el orquestador.** El plugin es un artefacto de Claude Code
(commands, hooks y `.mcp.json` son su formato) y dentro de una sesión el engine ya está
decidido: elegirlo es una decisión de lanzamiento, o sea del runner. Lo que sí es
portable es el `SKILL.md` — Codex y Kimi leen el mismo frontmatter, y Kimi trae
`/import-from-cc-codex`. La fuente de verdad del procedimiento sigue siendo el markdown;
el plugin pasa a ser *una* de sus empaquetaduras.

## Etapas, y por qué en este orden

1. ~~Quitar el hook~~ — hecho el 2026-08-16. Quitó acoplamiento y restó código.
2. ~~**Probar `codex exec` a mano**~~ — hecho el 2026-08-16 con `analyze` y `plan`
   encadenados sobre una solicitud `R-`. Salió bien: prompt pack obedecido, plantilla
   completa, huella correcta en los dos sentidos (`nada` cuando debía parar), journal
   acumulado. Detalle arriba.
3. ~~**El registro `ENGINES` con `claude` y `codex`**~~ — construido el 2026-08-16,
   decisión 20 en `docs/STATUS.md`. Incluye las dos cosas que la etapa 2 agregó al
   alcance: **ruta del binario por engine** (`ORCH_<ENGINE>_CMD`, porque el PATH mentía)
   y el **límite de lectura**, que resultó no ser configurable — quedó documentado como
   propiedad del engine que elijas, no como perilla del runner.

   Un defecto que solo apareció corriéndolo de verdad: con el prompt por stdin, el log
   guardaba **la línea de argv y nada más**, o sea que algo se lanzó pero no qué se
   pidió. El runner ahora escribe el prompt en el log bajo su propio encabezado. El test
   que debía atrapar eso pasaba porque el fake devolvía el prompt como eco — un fake
   demasiado servicial es un test que no afirma nada.
3b. **`survey` se queda en Claude, y lo dice.** El abanico monta cada hijo enraizado
   en su repo para que vea SUS reglas, SUS hooks y SU `.mcp.json`, y ese montaje es de
   Claude Code. `PUT /modelos` rechaza otro engine para esa fase con el motivo escrito,
   y la UI ni lo ofrece: una configuración ignorada en silencio es peor que una
   rechazada. Portar el abanico a otro engine es trabajo de la etapa 4, no un descuido.

4. Engines sin MCP en fase 1, **solo para tickets `R-`**: una solicitud no necesita
   Azure, su entrada es `docs/tickets/<id>-request.md` que el runner ya proyecta.
5. Copilot al final o nunca.

**El paso 2 va antes que el 3 a propósito.** Hoy en esta máquina solo está instalado
`claude`; construir el registro sin un segundo engine con el que probarlo es construir
sobre supuestos, y una rama de adaptador que nadie ejecuta se pudre. El diseño se
escribe ahora (esto), el código espera a tener contra qué correr.

## Costo honesto

El costo no es el código, es la superficie de prueba: cinco CLIs que cambian cada
semana — Codex ya deprecó sus *custom prompts*, Gemini se convierte en Antigravity —
mantenidos por una persona. Por eso: **diseñar para dos, construir dos, dejar la tabla
para que el tercero cueste poco**. Si el paso 2 muestra que Codex no planea mejor que
Opus, la etapa 3 no se hace y queda solo el desacople, que ya vale por sí mismo: obliga
a que "qué es una corrida" esté escrito y no implícito en unos flags.

## Por verificar cuando cada CLI exista en la máquina

- `--resume` de Copilot combinado con `-p`.
- Equivalente de `--add-dir` en Kimi.
- Si `gemini -p` respeta los comandos custom de `.gemini/commands/` (no haría falta:
  el prompt pack viaja inline, pero cambiaría el empaquetado).
- Valores reales de `model_reasoning_effort` aceptados por el Codex instalado.
