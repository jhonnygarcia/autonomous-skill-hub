# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

Personal hub of Claude Code plugins. **Read `docs/STATUS.md` when starting a session**:
it's the living document with roadmap, decisions, and pending work; update it (and the
checkboxes in `docs/superpowers/plans/`) when closing a milestone.

The repo has two independent artifacts:

1. **`plugins/ticket-agent/`** — plugin installable in *other* repos. It doesn't run
   here; it's only edited here.
2. **`apps/orchestrator/`** — local app (FastAPI + React) that queues tickets and
   runs them by invoking the plugin against the target repo.

## Commands

Orchestrator — backend (`apps/orchestrator/backend/`):

    python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000   # no --reload, see Rules
    .venv/Scripts/python -m pytest tests/ -v
    .venv/Scripts/python -m pytest tests/test_app.py::test_name -v   # a single test

Orchestrator — frontend (`apps/orchestrator/frontend/`): `npm run dev` (5173),
`npm run build` (tsc -b + vite), `npm run lint` (oxlint).

Plugin: `claude plugin validate .` from the root must pass before committing.

### Bringing the app up

Two processes, two terminals, backend first — the frontend proxies `/api` to it and
a Vite that starts against a dead backend just serves a UI whose every request fails.

    # terminal 1 — backend
    cd apps/orchestrator/backend
    .venv/Scripts/uvicorn app:app --port 8000

    # terminal 2 — frontend
    cd apps/orchestrator/frontend
    npm run dev

Then open **http://localhost:5173**. That is the whole app: the frontend proxies
`/api/*` to port 8000, so the backend is never browsed directly.

**Use `localhost`, not `127.0.0.1`, for the frontend.** Vite binds to `::1` only and
uvicorn binds to `127.0.0.1` only, so `http://127.0.0.1:5173` refuses the connection
while `http://localhost:5173` works — on Windows `localhost` resolves to `::1` first.
The dev proxy is unaffected either way: Vite reaches the backend server-side, not
from the browser. Verifying the two are up:

    curl http://localhost:5173/api/tickets   # through the proxy: proves both
    curl http://127.0.0.1:8000/projects      # backend alone

First run only: create the venv and install (the two lines above), and
`npm install` in the frontend. Both are already provisioned in this working copy.

If something behaves oddly, **suspect the process before the code** — see Rules. To
check who holds the ports, in PowerShell:

    Get-NetTCPConnection -LocalPort 8000,5173 -State Listen |
      Select-Object LocalAddress, LocalPort, OwningProcess

## Architecture

**ticket-agent plugin.** The logic lives in markdown, not code: each command delegates
to its skill, which defines the whole procedure. Changing the agent's behavior means
editing the SKILL.md. There are three phases, and they're three separate runs:

| Command | Skill | Input | Output |
|---|---|---|---|
| `/ticket-agent:analyze <id>` | `ticket-comprehension` | the work item | `docs/tickets/<id>-analysis.md` |
| `/ticket-agent:plan <id>` | `change-planning` | that analysis | an OpenSpec change |
| `/ticket-agent:implement <id>` | `change-implementation` | that change | commits on `ticket-agent/<id>` |

Data arrives via the official Azure DevOps MCP (`.mcp.json`), which connects with the
target repo's `ADO_ORG` env var and filters domains; `project` comes from the target
repo's `.claude/ticket-agent.json`. Phase 1 is read-only: any `*_write` MCP tool is
forbidden.

**Phase 2 consumes the analysis, not the work item.** If the file doesn't exist, it
stops and asks for Phase 1 to run first — the analysis is the interface between the
two. It writes to `openspec/changes/<id>-<slug>/` in the target repo and validates with
the OpenSpec CLI (`@fission-ai/openspec`, via `npx`). It also doesn't write product
code: its deliverable is the plan.

**Phase 2b executes the plan, task by task.** It reads the change's `tasks.md`, delegates
each task to a subagent, runs the "Check" that the task itself declares, commits its
paths (`<id> task N: <subject>`, one commit per task), and checks the box. **It stops on
a branch with commits: no push, no PR** — the `git log` is the record of progress. Its
preconditions are hard: no plan, several changes for the same id, or being outside the
`ticket-agent/<id>` branch all stop it with `HUELLA: nada`.

The analysis is written to the target repo (`docs/tickets/<id>-analysis.md`), never here.

**Orchestrator.** `backend/app.py` is a single file: SQLite without an ORM (`projects`,
`tickets`, and `runs` tables), FastAPI routes, and the runner. `execute_run` launches
`claude -p "/ticket-agent:analyze <id>"` as a subprocess with `cwd` = the ticket's
`repo_path`, streaming the stream-json to `logs/<run_id>.log`; the UI reads the tail via
`GET /tickets/{id}`. A global `asyncio.Lock` serializes runs — one at a time, on
purpose.

Projects are registered from the UI and live in the `projects` table (there's no
config file). A project has a primary `repo_path` and optionally `extra_dirs`: sibling
repos the ticket needs to read, which the runner mounts with `--add-dir`. Paths are
validated against disk when saved.

**The API doesn't expose that internal shape**: externally a project has a single
`repos: [{path, label, primary}]` list, and `project_out`/`repos_columns` translate in
each direction. The `label` isn't decorative — the runner injects it into the prompt,
because `--add-dir` grants access but not attention: without naming the repos for it,
the agent ignores them.

**The ticket copies `org`, `project`, `repo_path`, and `extra_dirs` from the project
when created** — the same way a line item locks in a price. That's why deleting a
project doesn't break old tickets, and there's no FK between the two tables.

**The phase decides the command, the tools, and the final state.** Four tables next to
`PHASES` in `app.py`: `PHASE_COMMANDS` (what's launched), `PHASE_ALLOWED_TOOLS` (which
extra tools — `analyze` intentionally gets an empty list: it's read-only), `PHASE_DONE`
(what state it leaves the ticket in), and `PHASE_NOUN` (what the deliverable is called
in the prompt). Requesting a phase not in `PHASE_COMMANDS` returns `400` without
launching a subprocess — `PHASES` also declares `guards` and `pr` so the UI knows they
exist, but they can't be launched.

The runner passes `--allowedTools` with the MCP: in headless mode, `--permission-mode
acceptEdits` does **not** auto-approve MCP tools, and without that flag the agent can't
read the work item.

**What sandboxes `implement` is the runner, not the skill** — a boundary that depends on
the agent obeying a markdown file isn't a boundary. `prepare_branch` creates or checks
out `ticket-agent/<id>` before launching (and saves the name in `runs.branch`), and
`settings_for` injects via `--settings` (inline JSON, without writing anything to the
client repo) a `PreToolUse` hook on Bash: `hooks/deny_push.py`, which denies `git push`,
`git remote add|set-url`, `gh pr create`, and `az repos pr create`. It's a latch against
accidents, not armor: it fails open on events it doesn't recognize, and its regex
anchors the verb to the start of the command specifically so it doesn't deny a
`git commit -m "... git push ..."`. `implement` carries `Bash` **with no specifier** on
purpose: it's verified that `Bash(x:*)` enables the tool and doesn't scope it, so
pretending otherwise would be worse.

**The exit code isn't enough to know whether a deliverable was produced**: `claude -p`
exits 0 even if the agent stopped without doing anything. That's why the three skills
are required to close with a stamp (`HUELLA: ok|parcial|nada — <ruta>`, with the partial
note reserved after a ` · ` on the same line) and the runner requires it for every
phase, not just `design`. The stamp keyword and its values stay in Spanish on purpose:
`STAMP_RE` matches those literal tokens, so translating them would break the check —
and that regex is wider than the line above suggests. It also accepts a legacy `PLAN:`
keyword and the values `validado|sin-validar|no-escrito`, which `LEGACY_STATES` folds
back onto `ok|parcial|nada`, and it takes a plain hyphen as well as an em dash. The
path capture is `[^"\\]+`, which stops at a double quote — the stamp travels nested
inside the stream-json, so a caveat containing `"` gets silently clipped. Read the
regex before touching any of it. It decides based on the **last** match in the log —
anchoring on the last one
isn't incidental: the skill's body travels through the log and contains all three stamp
values literally, so checking for mere presence would make the check find itself.

**Progress is folded from `runs`, not stored separately.** `GET /tickets/{id}` returns
`fases`: one entry per `PHASES` name with the state of its most recent run.
`tickets.status` is no longer a source column — it's computed by folding those phases on
every read — and `current_phase` disappeared from the table: it existed since the first
commit, was initialized to `analyze`, and nothing ever wrote to it. `Timeline.tsx` is the
detail view that renders that journey, with the button to launch each phase next to its
stamp.

**`GET /tickets/{tid}/artefacto?ruta=...`** serves what a run declared it wrote, not a
file explorer: it requires all four at once — the path was declared by a run of THIS
ticket (or falls under a directory that was declared, at any depth), falls inside the
main repo or one of the ticket's extras, is a regular file, and is truncated to 512 KB
without splitting a multibyte character.

**The model and effort are also chosen per phase**, from Settings in the UI
(`Models.tsx` → `GET/PUT /modelos`). They live in the `phase_config` table and nowhere
else: empty means "whatever the CLI resolves in the target repo", which is the
default behavior. `model_for` reads them **at launch time**, not at startup, because on
Windows the backend isn't hot-reloaded. The model goes into argv, so it's validated
against `MODEL_RE` — one starting with `-` would be another flag.

The plugin has no equivalent knob: neither the skills nor the commands have a model
field, only the subagents do. That's why `.claude/ticket-agent.json` accepts
`subagent_model`, which Phase 2b passes to each `Task`, and nothing else (see the
plugin's README).

Env var overrides (used by tests): `ORCH_DB`, `ORCH_LOGS`,
`ORCH_CLAUDE_CMD` (JSON with the CLI's argv — `tests/fake_claude.py` substitutes it).

## Project rules

- **Subscription, never an API key.** Programmatic execution uses the headless CLI
  (`claude -p`), not the Agent SDK. The runner strips `ANTHROPIC_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN` from the subprocess environment, and a test guarantees it:
  don't reintroduce those variables or switch to a client that requires them.
- **Touching a skill requires bumping `version` in `plugin.json`.** That version is the
  cache key: `claude plugin update` brings nothing if it doesn't change, so a change
  committed here never reaches the installed plugin and the test comes out false.
  There are **two** places, and the second one drifts silently: the analysis template
  in `ticket-comprehension/SKILL.md` stamps `by ticket-agent vX.Y.Z` so the written
  file proves which version produced it. It sat at `v0.5.2` while the plugin was at
  `v0.7.1` — a stamp that lies is worse than no stamp. Bump both.
- **Never `uvicorn --reload` on Windows**: the reloader leaves orphaned children
  holding port 8000, and the backend keeps serving stale code without warning. When
  something behaves oddly, suspect the process before the code.
- **Phase 2 requires Node with `npx` and network access** (package `@fission-ai/openspec`;
  note it is *not* called `openspec`). An `--allowedTools` specifier like
  `Bash(npx ...:*)` has to match **literally** the start of the command or it gets
  denied — and even then it enables the Bash tool, it doesn't scope it to that command.
- A new plugin: a folder under `plugins/<name>/` with `.claude-plugin/plugin.json`,
  skills under `skills/<name>/SKILL.md`, commands under `commands/*.md`, and a registry
  entry in `.claude-plugin/marketplace.json`.
- Designs go in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
- **Code, comments, and process docs in English; Spanish only in UI text.**
  Planning documents (`docs/superpowers/plans/`, `docs/superpowers/specs/`) are
  exempt from this rule and can stay in Spanish. Three categories decide it:
  **prompt-facing** strings (`PHASE_NOUN`, `repos_text`, `adjustment_text`,
  `DENY_REASON`) are read by the agent, so they're English and track the skills.
  **UI-facing** strings (`HTTPException` details, `NO_STAMP_REASON` and the other
  `motivo` text) are read by you in the browser, so they stay Spanish.
  **Contract literals** (the `HUELLA` stamp and its values, the `/modelos` and
  `/artefacto?ruta=` route paths, JSON keys like `fases`) are matched byte-for-byte
  somewhere, so they don't get translated in either direction — read
  `STAMP_RE` before touching any of them.
