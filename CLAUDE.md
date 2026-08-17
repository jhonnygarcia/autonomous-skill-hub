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
editing the SKILL.md. **Three stages, six commands, and every one of them is its own
run** — a ticket that mounts several repos takes the second route through stage 1:

| Stage | Command | Skill | Input | Output |
|---|---|---|---|---|
| 1 · one repo | `/ticket-agent:analyze <id>` | `ticket-comprehension` | the work item, or `R-<key>` | `docs/tickets/<id>-analysis.md` |
| 1 · several | `/ticket-agent:brief <id>` | `ticket-brief` | the work item, or `R-<key>` | `docs/tickets/<id>-brief.md` + `SONDEAR:` |
| | `/ticket-agent:survey <id>` | `repo-survey` | that brief, inline | one survey per routed repo |
| | `/ticket-agent:consolidate <id>` | `analysis-consolidation` | brief + surveys | the SAME `<id>-analysis.md` |
| 2 | `/ticket-agent:plan <id>` | `change-planning` | that analysis | an OpenSpec change |
| 3 | `/ticket-agent:implement <id>` | `change-implementation` | that change | commits on `ticket-agent/<id>` |

`R-<key>` is a request instead of a work item — `docs/tickets/<id>-request.md`, read
in place of the MCP; `analyze` alone also takes raw prose and derives the key itself.
Detailed below, alongside the ticket that copies a project's data.

**Both stage-1 routes end in the same file**, which is why stages 2 and 3 never learn
which one ran, and why the list's stepper still shows three dots. `analyze` stays
offered on multi-repo tickets: it's the fallback and the baseline. `PHASE_DONE` gives
`brief` and `survey` their own states (`briefed`, `surveyed`) so an interrupted fan-out
doesn't look finished — only `consolidate` leaves the ticket `analyzed`.

Data arrives via the official Azure DevOps MCP (`.mcp.json`), which connects with the
target repo's `ADO_ORG` env var and filters domains; `project` comes from the target
repo's `.claude/ticket-agent.json`. Phase 1 is read-only: any `*_write` MCP tool is
forbidden.

**The plugin owns no Azure DevOps code**: `.mcp.json` runs `npx -y @azure-devops/mcp`,
which is downloaded on every start, so `npx` is as required for Phase 1 as it is for
Phase 2's OpenSpec. Its `-d` list (`core work-items search wiki repositories`) is what
keeps the tool surface small; widening it widens what the agent can reach.

**The credential is the machine's, not the repo's.** `--authentication ${ADO_AUTH:-azcli}`
means the default is the `az login` session and no token exists in any file. Setting
`ADO_AUTH=envvar` switches to a PAT in `ADO_MCP_AUTH_TOKEN` (`pat` and `interactive`
also exist; `interactive` can't work headless, so never in the orchestrator). The
default lives in the `${VAR:-default}` expansion, which is why unsetting `ADO_AUTH`
keeps today's behavior — the token path is opt-in. The full table is in the plugin's
README; when it changes, that table is what gets updated.

**The missing-credential failure looks like a configuration failure.** The skill
reports "MCP not connected", which reads as a wrong `ADO_ORG` and sends you to the
wrong file. Same for an org/`organization` mismatch — nothing validates that the two
agree. Check `az account show` and `az devops project list --org ...` before
suspecting the JSON.

**A multi-repo ticket splits Phase 1 into one session per repo.** `brief` reads the
work item and writes `docs/tickets/<id>-brief.md` ending in a `SONDEAR: back, front`
line; `survey` runs one CLI child rooted in each routed repo — which is the only way
that repo's `CLAUDE.md`, hooks and `.mcp.json` load at all; `consolidate` merges them
into the same `<id>-analysis.md` that `analyze` produces, so Phase 2 never learns
which route ran. Design and rationale in
`docs/superpowers/specs/2026-08-12-multirepo-fanout-y-humano-en-el-bucle-design.md`.

Four things that decide the shape and aren't obvious:

- **The children carry no MCP.** The brief travels **inline in their prompt**, so the
  secondary repos need no `ADO_ORG`, no token and no `ticket-agent.json`. That's also
  why the brief has a ~4 KB budget: its cost is paid once per routed repo. And it's
  why `PHASE_MCP` had to exist — `mcp__azure-devops` used to travel fixed in argv for
  every phase, so an empty `PHASE_ALLOWED_TOOLS` did **not** take it away.
- **A child mounts only the scratch dir** (`logs/<run_id>/`), never its sibling repos.
  Mounting them would put the primary repo's rules back in front of it, which is the
  defect the split exists to remove. The scratch holds no `.claude/`, so it leaks no
  configuration.
- **`SONDEAR:` fails wide.** Absent, empty, or with one unknown label → survey
  **every** mounted repo. Routing is an optimization; a repo left out is a hole in the
  analysis that the plan consumes without knowing. Same last-match anchoring as
  `STAMP_RE`, and for the same reason: the skill's own example carries the literal.
- **Each child's verdict is read from its own stretch of the log**, not from the
  file's last stamp — otherwise a good survey vouches for a silent one that follows.
  The run's stamp is written by the runner: the phase's verdict is the set of them,
  and no child can speak for the rest. A fan-out records no `session_id`, so
  `puede_continuar` stays false for it without a special case anywhere.

**The seams between phases are where the human decides.** `claude -p` has no TTY, so
a skill that stops to ask hangs until the timeout — but each phase is its own process
with a file in between. So the deliverables close with `## Decisiones para ti`:
`- [ ] **DECIDIR**` carries a proposal and, unanswered, the next phase proceeds with
it **and records that it did**; `- [ ] **BLOQUEA**` has no defensible default and
stops the next phase. The human answers by editing the file and ticking the box —
same convention as `tasks.md`, no second format. `autonomy` finally governs
something: it decides whether an unanswered `DECIDIR` stops the run.

**Continuing a session is the human's call, and only theirs.** `runs.session_id` is
captured from the stream (first match — the id is stable, and a run that died halfway
is precisely one worth continuing), and `resume: true` adds `--resume … --fork-session`.
**The slash command is not resent**: the session already ran the skill, and sending it
again restarts the procedure from step 1 and rewrites the deliverable. The stamp
reminder in the resume prompt isn't optional either — the runner demands `HUELLA` on
every run. Only the human knows whether their adjustment **adds** scope (continue) or
**corrects** what the agent understood (fresh, so the correction doesn't compete with
the reasoning behind the mistake), which is why `puede_continuar`/`continuaciones` are
computed in the backend and merely displayed.

**Phase 2 consumes the analysis, not the work item.** If the file doesn't exist, it
stops and asks for Phase 1 to run first — the analysis is the interface between the
two. It writes to `openspec/changes/<id>-<slug>/` in the target repo and validates with
the OpenSpec CLI (`@fission-ai/openspec`, via `npx`). It also doesn't write product
code: its deliverable is the plan.

**Phase 2b executes the plan, task by task.** It reads the change's `tasks.md`, delegates
each task to a subagent, runs the "Check" that the task itself declares, commits its
paths (`<id> task N: <subject>`, one commit per task), and checks the box. **It ends on
a branch with commits and opens no PR** — the `git log` is the record of progress, and
whether that branch becomes a pull request is the human's decision, taken outside the
run. It doesn't push on its own either, but nothing stops it if you ask — the branch
is the agent's own. Its preconditions are hard: no plan, several changes for the same
id, or being outside the `ticket-agent/<id>` branch all stop it with `HUELLA: nada`.

**A task carries `Test` and `Check` as two separate lines** — the test file the
implementer writes first, and the command anyone can run afterwards — because the
planner is the only one who can make the test a deliverable, and without that the test
gets written after the code and is green on its first run. Phase 2b orders the subagent
red first and wants both outputs back. **The green is re-run by the driving agent
itself; the red can only ever be the subagent's word**, since the code exists by the
time the driver looks. A task whose report shows no red still commits, and gets written
down as `unverified` rather than silently counted as proven. `Check: manual — ...` is
the declared escape hatch for what has no runnable test (config, renames, copy); an
invented `--filter` that matches nothing exits 0, which is why faking one is worse than
declaring it.

**The per-task review is a second subagent with a clean context, and it can't stop the
plan on taste.** The driving agent wrote the implementer's prompt, so it can't be the
reviewer — that's self-review at one remove. Findings come graded: only `critical` and
`important` reach the retry, `minor` never does, and a finding against something the
plan explicitly ordered doesn't either — the plan is this phase's contract and there is
no human mid-run to break the tie. All three of the non-blocking kinds land in a
`## Review notes` section appended to `tasks.md`, because a summary in chat dies with
the session and `tasks.md` is what the human opens.

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

**`--add-dir` grants file access, not configuration discovery.** From a mounted repo
Claude Code loads `.claude/skills/` and `.claude/agents/` — and nothing else that
matters: not its `CLAUDE.md`, not `.claude/rules/`, not its hooks, not its
`.mcp.json` (of `settings.json` only `enabledPlugins` and `extraKnownMarketplaces`).
So an agent working in a mounted repo has the **primary** repo's rules, which is
worse than having none: it applies the wrong conventions with confidence, and
nothing downstream catches it. `execute_run` sets
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` **only in `implement` and only when
there are extras** — that's where obeying the other repo's rules while writing in it
is what matters, and by then Phase 1 has already put them into the analysis in
writing. **Hooks and `.mcp.json` of a mounted repo are recovered by nothing**; only a
session rooted in that repo has them, which is the whole reason for the multi-repo
design in `docs/superpowers/specs/2026-08-12-...`.

**The ticket copies `org`, `project`, `repo_path`, and `extra_dirs` from the project
when created** — the same way a line item locks in a price. That's why deleting a
project doesn't break old tickets, and there's no FK between the two tables.

**`POST /tickets` accepts one of two shapes, never both.** `{ado_id, project}` is a
work item, as always; `{request, project}` is a free-text request that replaces it —
a paragraph the human typed instead of an Azure DevOps id. `create_ticket` enforces
the XOR: both fields or neither is `400`, and a `request` that's empty or pure
whitespace is `400` too. A request's key is minted after the `INSERT`, from the row's
own `lastrowid` — `UPDATE tickets SET ado_id = 'R-' || id` — instead of a second
counter, because the row id is already unique and monotonic and a second counter is a
second place to drift. The `R-` prefix isn't cosmetic: without it, local request 7 and
work item #7 write the same `docs/tickets/<id>-analysis.md`, and the second silently
overwrites the first — the same collision `consolidate` already caused once between
the two Phase-1 routes (see `docs/STATUS.md`, ninth session). The prefix also splits
the namespace between the two ways of minting a key: the orchestrator mints only
numbers (`R-7`); a human running the plugin standalone, with no orchestrator to mint
anything, picks a word instead (`R-form-clientes`, see the plugin's README) — numeric
against slug, so the two modes can never collide without coordinating anything.
There's no `source` column: `origen` in `ticket_out` (`"ado" | "local"`) is derived
from `request IS NOT NULL`, because a stored copy of something derivable is a copy
that can disagree with it. And `ado_id`'s type follows origin, not table: an Azure
ticket carries an `int`, a request carries the `str` `"R-7"` — SQLite's column
affinity stores both without conversion, so nothing else needed to change.

**The request is projected to a file, and only for the two phases that read it.**
The database stays the source of truth; before launching `analyze` or `brief`,
`execute_run` writes `ticket["request"]` to `docs/tickets/<id>-request.md` in the
primary repo, rewritten from the DB on every launch so editing the request in the UI
and relaunching never leaves a stale file behind. Only those two phases: downstream
phases consume the analysis, not the request, and `implement` is where the runner
reasons about the clean-tree guard (`check_clean` in the POST, `prepare_repos` under
the lock) — adding a runner-side write between those two checks is a habit not worth
acquiring for a file that phase never reads anyway. The MCP is **not** removed for a
request — the first draft of this design did, and it was wrong: a request can cite a
real work item ("like we did in 3271"), and the skill's step 6 still has to read it.
So `PHASE_MCP` is untouched, and the prompt does the negating instead —
`REQUEST_PROMPT` names the file and states plainly that there is no work item for
this request and it must not be searched for. Naming the file **and** denying the
work item, both: run 3320 taught that what a prompt doesn't name, the agent invents.

**The journal is a record, never an input.** `docs/tickets/<id>-journal.md`, in the
primary repo, for Azure tickets and requests alike — the run history that survives a
wiped database (it happened once, 2026-08-11) and the only trace a plugin-only
session leaves. `append_journal` inserts one line per closed run under `## Corridas`,
right before the `## Hallazgos` heading, so that section keeps growing at the file's
end where the skills append their own out-of-scope findings; it runs at all four
places a run closes (three early returns plus the main close), including error runs,
with their reason. `JOURNAL_CLAIM`, appended to the fresh and resumed prompts, tells
the skill the runner already owns `## Corridas` for this run so it doesn't write a
second, duplicate line — the skill still owns `## Hallazgos`. **Fan-out survey
children don't get it**: a child mounts only its own repo and the scratch dir, never
the primary repo where the journal lives, so a claim about a file it can't reach
would be an instruction it can't obey; `repo-survey/SKILL.md` already tells it to put
out-of-scope findings under `## Hallazgos fuera de alcance` in its own survey
document, and `analysis-consolidation` carries them into the journal afterwards. No
phase reads the journal to decide anything: a test guards that deleting it changes
nothing about a subsequent `design` run, because a file a phase reads as authority
would be a second source of truth free to disagree with the first.

The journal is written after every run, `implement` included, so it is left
**untracked** in the primary repo like the analysis and the plan before it. That's
safe only because `is_dirty`'s clean-tree guard ignores `??` entries on purpose: what
blocks `implement` is tracked work in progress, not an untracked file the tooling
itself just wrote.

**`org` and `project` are labels here, not configuration.** The runner never exports
`ADO_ORG` and never puts the project name in the prompt: the subprocess inherits the
backend's environment and Claude Code resolves both from the *target repo's*
`.claude/settings.json` and `.claude/ticket-agent.json` once `cwd` lands there. The
only things `app.py` reads them for are display and the "another project's ticket is
running" message. So a project registered in the UI with a correct org still fails if
the repo on disk lacks its two files — the UI shows nothing wrong, because the UI
never had the authority. Registering a repo in the orchestrator is not configuring
it.

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

**What isolates `implement` is the branch, not a hook.** `prepare_branch` creates or
checks out `ticket-agent/<id>` before launching and saves the name in `runs.branch`:
everything the run writes lands there, and `main` is never the run's checkout. That is
the whole containment, and it's the runner's — a boundary that depends on the agent
obeying a markdown file isn't a boundary.

**There is no push guard, on purpose (2026-08-16).** Until this date the runner injected
a `PreToolUse` hook on Bash via `--settings` (`hooks/deny_push.py`) that denied `git
push` and the two PR commands. It was removed for two reasons, and the second is the one
that mattered: a hook is a **Claude Code-only mechanism** — Codex, Gemini, Kimi and
Copilot each contain differently — so anything built on it can't survive the runner
becoming engine-agnostic; and pushing `ticket-agent/<id>` was never dangerous, it is the
agent's **own** branch, while the hook denied it even when the human explicitly asked
for it in a resume. What stays out of the run is the **pull request**: opening one asks
a team to look, and that call is the human's. The skill states this, and no runner-side
mechanism enforces it — see the roadmap decision in `docs/STATUS.md`. `implement`
carries `Bash` **with no specifier** on purpose: it's verified that `Bash(x:*)` enables
the tool and doesn't scope it, so pretending otherwise would be worse.

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

**The engine, the model and the effort are chosen per phase**, from Settings in the UI
(`Models.tsx` → `GET/PUT /modelos`, plus `GET /engines` for the selector's options).
They live in the `phase_config` table and nowhere else: an empty model or effort means
"whatever the CLI resolves in the target repo", which is the default behavior.
`model_for` reads them **at launch time**, not at startup, because on Windows the
backend isn't hot-reloaded. The model goes into argv, so it's validated against
`MODEL_RE` — one starting with `-` would be another flag.

**`ENGINES` is the registry of CLIs the runner can launch** (`claude` and `codex`,
verified against real binaries on 2026-08-16 — the flag-by-flag equivalences and their
surprises are in
`docs/superpowers/specs/2026-08-16-orquestador-agnostico-de-engine-design.md`). Mixing
them per phase works for the same reason the two Phase-1 routes do: **the deliverable is
a file**, so Phase 2 never learns who wrote the analysis. Five things carry the design:

- **The slash command is Claude's spelling of the skill, not the skill.** `/ticket-agent:analyze`
  exists because a plugin is installed, and only Claude Code takes plugins. Every other
  engine gets `PACK_HEADER` + `skill_body(phase)`: the same `SKILL.md`, inline, read from
  `plugins/ticket-agent/skills/` in this repo. One source, two wrappings — which is also
  why `PHASE_SKILL` must stay in sync with `PHASE_COMMANDS` (there's an `assert`).
- **`HUELLA` needed no adapter and `session_id` did.** `STAMP_RE` parses Codex's JSONL
  unchanged, because the stamp is the contract with the skills. The session id is each
  CLI's own shape — Codex spells it `thread_id` — so it moved into
  `ENGINES[...]["session_re"]`. **A resume never crosses engines**: `last_session` filters
  by `runs.engine` (`COALESCE(engine,'claude')`, since every row predating the column was
  Claude), because handing one CLI another's id doesn't fail cleanly — it silently starts
  a fresh session that looks continued.
- **Effort is per engine, not global.** `max` is legal in Claude and dies with a 400 from
  the provider in Codex; `none`/`minimal` are the reverse. Each entry carries its own
  `efforts` tuple, `PUT /modelos` validates against *that* one, and the UI reads the list
  from `GET /engines` instead of keeping a second copy.
- **The binary is `ORCH_<ENGINE>_CMD` before it's the PATH.** On the machine this was
  built, `codex` on the PATH was 0.118.0 while the installed app shipped 0.147.0, and the
  configured model only ran on the newer one. A bare command name is not an address.
- **`API_KEY_VARS` grows with the registry.** "Subscription, never an API key" is the
  project's rule, not Anthropic's: adding an engine without adding its key variable
  quietly reintroduces API billing through the back door.

What is *not* solved: **each engine's read boundary differs and the runner doesn't
control it.** Codex's `-C` is a working root, not a limit — a verified run read the
neighbouring repo and the parent directory's `CLAUDE.md` with nobody mounting them,
which is the very thing the multi-repo fan-out exists to prevent. Claude Code is
confined to `cwd` + `--add-dir`. Until an engine can be told what not to read, that
difference is a property of the engine you pick.

The plugin has no equivalent knob: neither the skills nor the commands have a model
field, only the subagents do. That's why `.claude/ticket-agent.json` accepts
`subagent_model`, which Phase 2b passes to each `Task`, and nothing else (see the
plugin's README).

Env var overrides (used by tests): `ORCH_DB`, `ORCH_LOGS`, `ORCH_SKILLS_DIR`, and one
`ORCH_<ENGINE>_CMD` per engine (JSON with the CLI's argv — `tests/fake_claude.py` and
`tests/fake_codex.py` substitute them). The two fakes are deliberately not each other's
copy: the prompt reaches Codex through **stdin** and its session is a `thread_id`, and a
fake that shared Claude's shape would pass while the runner mixed the two up.

## Project rules

- **Subscription, never an API key.** Programmatic execution uses the headless CLI
  (`claude -p`), not the Agent SDK. The runner strips `ANTHROPIC_API_KEY` and
  `ANTHROPIC_AUTH_TOKEN` from the subprocess environment, and a test guarantees it:
  don't reintroduce those variables or switch to a client that requires them.
- **What a host machine must already have belongs in the plugin's README, and why it
  breaks belongs here.** The two files split one subject: the README is the install
  checklist a dev outside this repo follows (`npx`, the Azure credential and the
  `ADO_AUTH` table, git, the two JSON files); this file explains the mechanism behind
  each one. Changing `.mcp.json`, the auth modes, the `-d` domain list, or what the
  runner passes to the subprocess means editing **both** — the README so the next dev
  can install it, here so the next session doesn't re-derive it. A prerequisite
  discovered by debugging and left undocumented gets discovered again the same way.
- **Touching a skill requires bumping `version` in `plugin.json`.** That version is the
  cache key: `claude plugin update` brings nothing if it doesn't change, so a change
  committed here never reaches the installed plugin and the test comes out false.
  The same applies to anything else the install copies — `.mcp.json` above all: an
  auth mode nobody can pull is an auth mode that doesn't exist.
  There are **three** places, and the last two drift silently: the analysis template
  in `ticket-comprehension/SKILL.md` stamps `by ticket-agent vX.Y.Z` so the written
  file proves which version produced it, and the collection template in
  `ticket-brief/SKILL.md` stamps the same thing (`**Collected:** <date> by
  ticket-agent vX.Y.Z`, found missing during the solicitud-sin-ticket work). The
  analysis stamp already sat at `v0.5.2` while the plugin was at `v0.7.1` — a stamp
  that lies is worse than no stamp. Bump all three.
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
  **prompt-facing** strings (`PHASE_NOUN`, `repos_text`, `adjustment_text`)
  are read by the agent, so they're English and track the skills.
  **UI-facing** strings (`HTTPException` details, `NO_STAMP_REASON` and the other
  `motivo` text) are read by you in the browser, so they stay Spanish.
  **Contract literals** (the `HUELLA` stamp and its values, the `/modelos` and
  `/artefacto?ruta=` route paths, JSON keys like `fases`) are matched byte-for-byte
  somewhere, so they don't get translated in either direction — read
  `STAMP_RE` before touching any of them.
