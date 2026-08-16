# Orquestador agnóstico de engine — diseño

**Fecha:** 2026-08-16 · **Estado:** decidido el rumbo, construcción por etapas ·
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
2. **Probar `codex exec` a mano** en la fase `plan` de dos o tres tickets, con el
   `SKILL.md` pegado como prompt. `plan` no toca Azure (consume el análisis), así que
   es la prueba más barata que existe.
3. Recién entonces, el registro `ENGINES` con `claude` y `codex`.
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
