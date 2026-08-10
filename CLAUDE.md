# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contexto

Hub personal de plugins de Claude Code. **Lee `docs/STATUS.md` al iniciar sesión**:
es el documento vivo con roadmap, decisiones y pendientes; actualízalo (y los
checkboxes de `docs/superpowers/plans/`) al cerrar un hito.

El repo tiene dos artefactos independientes:

1. **`plugins/ticket-agent/`** — plugin instalable en *otros* repos. No se ejecuta
   aquí; aquí solo se edita.
2. **`apps/orchestrator/`** — app local (FastAPI + React) que encola tickets y los
   corre invocando el plugin sobre el repo destino.

## Comandos

Orquestador — backend (`apps/orchestrator/backend/`):

    python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000   # sin --reload, ver Reglas
    .venv/Scripts/python -m pytest tests/ -v
    .venv/Scripts/python -m pytest tests/test_app.py::test_nombre -v   # un solo test

Orquestador — frontend (`apps/orchestrator/frontend/`): `npm run dev` (5173),
`npm run build` (tsc -b + vite), `npm run lint` (oxlint).

Plugin: `claude plugin validate .` desde la raíz debe pasar antes de commitear.

## Arquitectura

**Plugin ticket-agent.** La lógica vive en markdown, no en código: cada comando delega
en su skill, que define el procedimiento completo. Cambiar el comportamiento del agente
= editar el SKILL.md. Hay dos fases, y son dos corridas distintas:

| Comando | Skill | Entrada | Salida |
|---|---|---|---|
| `/ticket-agent:analyze <id>` | `ticket-comprehension` | el work item | `docs/tickets/<id>-analysis.md` |
| `/ticket-agent:plan <id>` | `change-planning` | ese análisis | un change de OpenSpec |

Los datos llegan por el MCP oficial de Azure DevOps (`.mcp.json`), que se conecta con la
env var `ADO_ORG` del repo destino y filtra dominios; el `project` sale de
`.claude/ticket-agent.json` del repo destino. Fase 1 es solo lectura: cualquier
herramienta `*_write` del MCP está prohibida.

**La Fase 2 consume el análisis, no el work item.** Si el archivo no existe, se detiene
y pide correr la Fase 1 — el análisis es la interfaz entre ambas. Escribe en
`openspec/changes/<id>-<slug>/` del repo destino y valida con el CLI de OpenSpec
(`@fission-ai/openspec`, vía `npx`). Tampoco escribe código de producto: su entregable
es el plan.

El análisis se escribe en el repo destino (`docs/tickets/<id>-analysis.md`), nunca aquí.

**Orquestador.** `backend/app.py` es un solo archivo: SQLite sin ORM (tablas `projects`,
`tickets` y `runs`), rutas FastAPI y el runner. `execute_run` lanza
`claude -p "/ticket-agent:analyze <id>"` como subproceso con `cwd` = `repo_path` del
ticket y va volcando el stream-json a `logs/<run_id>.log`; la UI lee el tail vía
`GET /tickets/{id}`. Un `asyncio.Lock` global serializa las corridas — una a la vez,
a propósito.

Los proyectos se dan de alta desde la UI y viven en la tabla `projects` (no hay
archivo de configuración). Un proyecto tiene un `repo_path` primario y opcionalmente
`extra_dirs`: repos hermanos que el ticket necesita leer y que el runner monta con
`--add-dir`. Las rutas se validan contra el disco al guardar.

**La API no expone esa forma interna**: hacia fuera un proyecto tiene una sola lista
`repos: [{path, label, primary}]`, y `project_out`/`repos_columns` traducen en cada
sentido. La `label` no es decorativa — el runner la inyecta en el prompt, porque
`--add-dir` da acceso pero no atención: sin nombrarle los repos, el agente los ignora.

**El ticket copia `org`, `project`, `repo_path` y `extra_dirs` del proyecto al crearse**
— igual que una línea de pedido guarda el precio. Por eso borrar un proyecto no rompe
los tickets viejos y no hay FK entre ambas tablas.

**La fase decide el comando, las tools y el estado final.** Cuatro tablas junto a
`PHASES` en `app.py`: `PHASE_COMMANDS` (qué se lanza), `PHASE_ALLOWED_TOOLS` (qué tools
extra, y `analyze` lleva la lista vacía a propósito: es solo lectura), `PHASE_DONE` (en
qué estado deja al ticket) y `PHASE_NOUN` (cómo se llama el entregable en el prompt).
Pedir una fase que no está en `PHASE_COMMANDS` devuelve `400` sin lanzar subproceso.

El runner pasa `--allowedTools` con el MCP: en headless, `--permission-mode acceptEdits`
**no** auto-aprueba las tools MCP y sin esa bandera el agente no puede leer el work item.

**El código de salida no basta para saber si hubo plan**: `claude -p` sale con 0 aunque
el agente se haya detenido sin hacer nada. Por eso `change-planning` está obligada a
cerrar con un sello (`PLAN: validado` | `sin-validar` | `no-escrito`) y el runner decide
por la **última** coincidencia en el log — anclar en la última no es un detalle: el
cuerpo de la skill viaja en el log y contiene los tres sellos literalmente, así que
comprobar la mera presencia hace que la comprobación se encuentre a sí misma.

Overrides por env var (los tests los usan): `ORCH_DB`, `ORCH_LOGS`,
`ORCH_CLAUDE_CMD` (JSON con el argv del CLI — `tests/fake_claude.py` lo sustituye).

## Reglas del proyecto

- **Suscripción, jamás API key.** La ejecución programática usa el CLI headless
  (`claude -p`), no el Agent SDK. El runner elimina `ANTHROPIC_API_KEY` y
  `ANTHROPIC_AUTH_TOKEN` del entorno del subproceso, y hay un test que lo garantiza:
  no reintroduzcas esas variables ni cambies a un cliente que las exija.
- **Tocar una skill obliga a subir `version` en `plugin.json`.** Esa versión es la
  clave de cache: `claude plugin update` no trae nada si no cambia, así que el
  cambio committeado aquí no llega al plugin instalado y la prueba sale falsa.
- **Nunca `uvicorn --reload` en Windows**: el recargador deja hijos huérfanos
  reteniendo el 8000 y el backend sigue sirviendo código viejo sin avisar. Ante un
  comportamiento raro, sospechar del proceso antes que del código.
- **La Fase 2 exige Node con `npx` y acceso a red** (paquete `@fission-ai/openspec`;
  ojo, *no* se llama `openspec`). Un especificador de `--allowedTools` como
  `Bash(npx ...:*)` tiene que coincidir **literalmente** con el principio del comando
  o lo deniega — y aun así habilita la herramienta Bash, no la acota a ese comando.
- Un plugin nuevo: carpeta en `plugins/<nombre>/` con `.claude-plugin/plugin.json`,
  skills en `skills/<nombre>/SKILL.md`, comandos en `commands/*.md`, y registro en
  `.claude-plugin/marketplace.json`.
- Diseños en `docs/superpowers/specs/`, planes en `docs/superpowers/plans/`.
- Documentación y comentarios en español (el repo es consistente en eso).
