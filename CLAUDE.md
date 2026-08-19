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

**The ticket copies `org`, `project`, `repo_path`, `extra_dirs`, and `ado_pat` from
the project when created** — the same way a line item locks in a price. That's why
deleting a project doesn't break old tickets, and there's no FK between the two
tables.

**`ado_pat` is an optional Azure DevOps PAT, write-only in the API.** The plugin
already supports a token (`ADO_AUTH=envvar` reads `ADO_MCP_AUTH_TOKEN` instead of the
`az login` session — see the README's `ADO_AUTH` table); this is the UI's way to set
one. `ProjectIn.ado_pat` is tri-state: omitted leaves the stored value untouched
(`GET /projects` never returns it, so the form has nothing to resend), `""` clears
it, anything else replaces it. `project_out` reports only `ado_pat_configured`, a
boolean — never the value. `ticket_out` has to pop `ado_pat` explicitly, because it
builds its response with `dict(t)` over every column: an allowlist would have been
one more place to remember to update; a pop next to the one place the ticket becomes
an API response can't be forgotten as easily. When a ticket carries a token AND the
phase is one of `PHASE_MCP`, `execute_run` sets `ADO_AUTH=envvar` and
`ADO_MCP_AUTH_TOKEN` in the subprocess environment; otherwise it sets neither, and
`${ADO_AUTH:-azcli}` in the plugin's `.mcp.json` keeps governing exactly as before.
The `PHASE_MCP` gate isn't optional: `run_fan_out` reuses the SAME `env` dict for
every `survey` child, and `survey` children are rooted in a secondary repo on
purpose — CLAUDE.md's own multi-repo section says those sessions need no `ADO_ORG`,
no token and no `ticket-agent.json`, and reusing an ungated `env` would hand a
credential straight into exactly the repos that isolation exists to protect.

**FastAPI's default validation-error handler echoes the whole offending body back**
in Pydantic v2's `errors()[…]["input"]` — a `POST /projects` that 422s (a missing
`name`, say) put `ado_pat`'s value straight into the response. The caller already
knows the value, so this wasn't escalation, but it landed in browser devtools, any
proxy or access log recording error bodies, and the frontend's error toast.
`strip_secrets_from_validation_errors`, registered with
`@app.exception_handler(RequestValidationError)`, strips `input` from every error
entry and keeps the rest (`loc`, `msg`, `type`).

**This is a secret at rest in plaintext in `orchestrator.db`.** Write-only in the API
means it doesn't leak *through the API* — it says nothing about the file on disk.
Whoever can read `orchestrator.db` can read every configured token; there is no
encryption at rest. Inside the **runner**, the token never reaches a log, the
journal, `run.json`, or an error message: `cmd` (what gets logged and put in
`run.json` via `run_meta`) is the argv list, never the env dict, and `run_meta`'s
ticket fields are an explicit allowlist that was never grown to include it. That
guarantee stops at the runner's own boundary, though: the **child process's own
stdout is the log** (`logs/<run_id>.log`, served verbatim as `log_tail` by
`GET /tickets/{tid}`), and `implement` carries `Bash` with no specifier — an agent
that runs something like `env` or `printenv` writes the PAT straight into that log,
and nothing in the orchestrator would catch it. Handing a credential to an agent
that can run arbitrary shell is a real exposure, not a hypothetical one; this is a
property of the design, not a bug to fix here.

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

**Every run leaves a snapshot, and no phase ever reads it.** With `archive_dir` set
(Settings → `GET/PUT /archivo`, table `settings`, read at snapshot time like
`model_for`), `archive_run` copies to
`<archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<YYYYMMDD-HHMM>/`: `entrada/`
at launch (every `docs/tickets/<llave>-*` file plus any tree a previous good run
declared — the human's ticked `DECIDIR` boxes live nowhere else), `salida/` at close
(the declared path, request and journal, taken **after** the journal line so the copy
carries this run), and `run.json` (enough to read the folder after a DB wipe). The
declared path is resolved the same way `artifact_on_disk` resolves it —
`ticket_roots(ticket)`, primary repo first, then the extras — because a phase can
leave its deliverable in a mounted repo; `entrada`'s own files stay primary-only,
since `docs/tickets/...` genuinely lives there. Trees over
`ARCHIVE_TREE_MAX_FILES`/`_BYTES` are skipped with a journal line, and `copy_into`
stops counting the instant either cap is crossed instead of walking (and `stat`-ing)
the rest of the tree first — a stamp clipped to `docs` used to make every launch and
close of that ticket pay for the whole `docs/` tree, under the global lock, only to
copy nothing. A failed copy is a journal line, never an error run. `runs.archive_path`
is the folder; NULL means nothing archived — but it is **not** the same thing as
`runs.restorable`, a second nullable column set at close from a single `exists()`
check on `<archive_path>/salida/<artifact_path>`. The two disagree in two cases, both
real archives with no one-click way back. A fan-out `survey`: its HUELLA is an
absolute scratch path outside every repo, so `archive_path` still gets set (the
folder exists, request/journal got copied into it) while `restorable` stays 0 —
nothing a restore could put back. And a deliverable that lives in an EXTRA repo, not
the primary one: `declared_root(ticket, path)` (the same primary-then-extras order
`ticket_roots`/`copy_into_any` use) reports WHICH root a hit came from, and
`restorable` is set only when that root is the primary `repo_path` — `restore_run`'s
`dest` and its containment check are shaped for the primary repo alone
(`Path(t["repo_path"]) / rel`), so restoring a path archived from a mounted repo would
silently write that repo's content into the primary one, the same cross-repo mix-up
Decision D's archive-side fix exists to prevent, just moved to the restore side.
`restore_run` itself checks `restorable`, not just the two UI buttons — a direct
`POST /restaurar` on such a run 404s too. The archive still keeps the file either way
(that value stands on its own); recording the root and widening `restore_run` to a
second root is real design work and stays undone on purpose, deferred rather than
folded into this fix. Both the Timeline's and the run history's Restore button key off
`restorable`, never off `archive_path` alone, and treat NULL (every row before the
column, same convention as `artifact_exists`) as not-restorable. **A record, never an
input**: a test guards this by deleting the archive and leaving it deleted — never
recreating an empty directory before the next run — and confirming that next run
still produces its own deliverable and its own stamp regardless. The one door back is
`POST /tickets/{tid}/restaurar {run_id, overwrite}`: it copies that run's `salida/`
to the repo, refuses while a run is active, needs `overwrite` for an existing file,
and **never overwrites a tree** — `implement` ticks `tasks.md` inside the tree `design`
declared, and putting the older tree back would untick real progress. It journals
itself as `restaurar · ok`, with the source run as its own `extra` note (`· desde run
N`) rather than `note=`, which renders as `· reserva: ...` — the label a `parcial`
stamp's caveat owns, not a restore's provenance.

The retryable 409 (an existing file, no `overwrite`) is the one `/restaurar` refusal
the frontend may resend with `overwrite: true`; every other detail in this file is
Spanish prose, reworded at will (see the language rule below), which is exactly why
the UI can't key off it. It's tagged `{"code": "existe_archivo", "msg": <sentence>}`
instead of a plain string — a ticket whose declared path or OpenSpec slug happens to
contain the literal word "overwrite" used to make the (never retryable) tree refusal
match a substring check too, reopening the confirmation dialog forever. `api.ts`'s
`json()` surfaces `.msg` for display and carries `.code` on the thrown `ApiError` for
the one caller that branches on it.

**`entrada_rels(ticket)` runs its own DB query, and it's evaluated as an argument to
`archive_run` — before that function's own `try` even starts.** A locked DB there
(`sqlite3.OperationalError`) used to escape straight into `execute_run`'s background
task, past every guard, with the run already marked `running`: neither `POST /run` nor
`POST /restaurar` would ever stop 409ing on it, recoverable only by editing the DB.
The entrada call site now wraps both `entrada_rels(ticket)` and `archive_run` in one
`try`/`except`, and `archive_run` itself moved its own `archive_folder` call (another
DB read) inside its `try` — every DB and filesystem access on that path now answers to
the same handler `archive_run`'s docstring already promised: never raises.

Of `execute_run`'s three early returns, only two close before the entrada snapshot;
the `survey` phase's no-brief return closes *after* it, so a run that hits it keeps
an `entrada/` and a `run.json` and never gets a `salida/`. Reviewed and kept as-is
rather than made uniform.

**`org` and `project` used to be labels here, not configuration — reversed on
2026-08-17.** Until then the runner never exported `ADO_ORG` and never wrote
`.claude/ticket-agent.json`: the subprocess only inherited the backend's environment,
and Claude Code resolved both from the *target repo's* own `.claude/settings.json`
and `.claude/ticket-agent.json` once `cwd` landed there. That meant a project
registered in the UI with a correct org still failed if the repo on disk lacked its
two files, and it failed with "MCP not connected" — which reads like a wrong org and
sends you to the wrong file, not to the missing one. STATUS.md #21's decision ("the
UI is the product and the plugin is the engine: every friction of using the plugin
bare is a feature the UI owes") makes that failure the orchestrator's to fix, since
it already has both values as columns on the ticket.

So now it does two things, both in `execute_run`, right before launching, and both
gated on `phase in PHASE_MCP` — the phases that actually stop without them, and
the same gate that keeps a `survey` fan-out child (rooted in a SECONDARY repo on
purpose) from ever seeing either:
- **Exports `ADO_ORG`** from `ticket["org"]` into the subprocess environment, but
  **only when it isn't already set and non-empty** — the repo's own
  `.claude/settings.json` is the more specific setting and must win over a label
  typed in the UI, so this is a fallback, not an override. `env.get("ADO_ORG")` is
  what's checked, not `"ADO_ORG" in env`: an inherited `ADO_ORG=""` (trivially
  produced by `set ADO_ORG=` on Windows) must count as absent, or the MCP builds
  `https://dev.azure.com/` and lands right back on the failure this feature exists to
  eliminate. Symmetrically, `check_org` rejects an empty `org` at `POST`/`PUT
  /projects` time, so the UI can't hand the runner an empty value to export in the
  first place.
- **`.claude/ticket-agent.json` used to be created here too, silently, on every
  launch. It isn't anymore (2026-08-18)** — see the preflight below. The writer
  (`ensure_ticket_agent_config`, next to `journal_note`) survives unchanged as
  `POST /preparar`'s implementation: it writes only `organization` and `project`, the
  two keys the orchestrator has an actual source for; it never overwrites an existing
  file, whatever it contains — a human may have tuned it, or added `autonomy` or
  `subagent_model`, keys the orchestrator has no value for and won't invent; and it
  returns `"created"`, `"exists"`, or `"error: <reason>"` and **never raises**. That
  last property was load-bearing while the call sat between `set_run(status="running")`
  and every guarded region of `execute_run`: a `.claude` that's a file instead of a
  directory, an ACL denial, or a full disk raised `OSError` straight into a
  `BackgroundTask` — reaching nobody, leaving the run row `running` forever, and 409ing
  `POST /run`/`POST /restaurar` on that ticket permanently. Moving the write in front of
  the run retires that whole failure mode instead of catching it: no run exists yet when
  it fails, and the error is a 409 the human reads.

What `app.py` reads `org`/`project` for beyond this is still just display and the
"another project's ticket is running" message — registering a repo in the
orchestrator still isn't the same as configuring it, it's just less likely to be
missing now.

**`preflight` is what has to be true before a run is worth launching.** One function
(next to `ensure_ticket_agent_config`), one shape — `{ok, bloqueos, avisos}`, each entry
`{que, msg, reparable, fases}` — and two callers: `GET /tickets/{tid}/preflight`, which
the Timeline asks once when you open a ticket, and `POST /run`, which asks again and
**400s before inserting the run row**. The panel can be stale by the time you click, and
nothing forces a caller through it at all; the 400 is the gate, the panel is the warning.

It checks four things: the primary repo is still on disk, the ticket's extras still are,
`.claude/ticket-agent.json` exists, and there's a credential — `ado_pat` set, or
`az account show` exiting 0. Three properties decide its shape:

- **Phase-independent, with each entry naming the `fases` it blocks** (`null` = all of
  them). The credential and the config are only needed by `PHASE_MCP`, so a machine with
  no `az login` still runs `survey` and `consolidate`. One call per ticket instead of one
  per phase matters because the credential check **spawns `az`**: six of those on merely
  opening a ticket is a tax on looking. `preflight_blockers(pf, phase)` turns it back
  into a per-phase answer, and the frontend repeats that same filter.
- **`az account show` proves a session, not access to the ticket's org.** That would be
  `az devops project list --org ...` — seconds and a network round trip on every launch.
  This catches the failure that actually happens (no session at all) and doesn't pretend
  to catch the other one. `ORCH_AZ_CMD` (JSON argv, same convention as
  `ORCH_<ENGINE>_CMD`) is how the tests substitute it; no `az` on the PATH reads as not
  logged in, which is the same answer.
- **Exactly one blocker is `reparable`**, and it's the config file — the orchestrator has
  `organization` and `project` as columns, so `POST /tickets/{tid}/preparar` can write it
  and answer with the fresh preflight in one round trip. It journals itself (`creaste
  .claude/ticket-agent.json desde la UI`) for the same reason `restaurar` does. Everything
  else needs you to leave the app: `az login`, or fix the path in the project.

What it deliberately does NOT check: the clean tree (`check_clean` owns that for
`implement`, with a 409 about commits — a second copy would drift), and `npx`/Node (absent,
nothing runs at all, and you'd know long before the preflight). A repo that isn't git is an
**aviso**, not a blocker: only `implement` needs git and `check_clean` already stops it
there — but it's said out loud anyway, because discovering it at the last phase is
discovering it at the worst moment.

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
stamp travels nested inside the stream-json, so a quote the agent wrote in its caveat
(citing a document name, `"doc 09"`) arrives in the log escaped as `\"`, and a backslash
the agent wrote (a Windows path in the caveat) arrives as `\\`. The path capture is
`(?:\\"|\\\\|[^"\\])+` — it lets those two escape pairs through as single "characters"
instead of stopping at their backslash, and `_unescape_stamp` turns them back into `"`
and `\` before the stamp is stored; any OTHER backslash sequence (chiefly `\n`, a real
newline's JSON encoding) still stops the capture, so a stray quote no longer corrupts
`artifact_path` or drops `artifact_note` the way it did in real run 8 of ticket 3359
(fixed 2026-08-17). **The `+` is not cosmetic**: with `*` the capture can be empty, and
`change-planning/SKILL.md` wraps its own example stamp across two lines, leaving
`HUELLA: parcial —` alone on one line — that prose travels through the log like any
other SKILL.md text, so a `*` let it match with an empty capture that, anchored as the
**last** match, silently beat a real stamp earlier in the log (`artifact_state='ok'`
with an empty `artifact_path`). Read the regex before touching any of it. It decides based on the
**last** match in the log — anchoring on the last one
isn't incidental: the skill's body travels through the log and contains all three stamp
values literally, so checking for mere presence would make the check find itself.

**The stamp is the agent's word, and `artifact_exists` is the only place it's checked.**
`claude -p` exiting 0 was never enough, and neither is the stamp: a run verified on
2026-08-16 with `codex exec` had its write rejected by the sandbox, said so in prose,
and still closed `HUELLA: ok — salida.md` with exit 0. Nothing about that is Codex's
fault — the contract always took the agent at its word, and Claude can lie the same way.
At close, `artifact_on_disk` resolves the declared path against the primary repo and the
extras (a **directory** counts: Phase 2's deliverable is `openspec/changes/<id>-<slug>/`)
and the answer is stored. **Checked once, at close, never on read** — the ticket list
deliberately doesn't touch disk (`with_footprint=False`), and a stat per ticket per phase
would undo exactly that.

What the answer is used for is the part that took a decision. It does **not** rewrite the
state the run declared: a false stamp still gives itself away instead of being hidden,
which is the older decision and it stands — the phase shows the `ok` the agent claimed,
next to `entregable: false`. What it stops is that claim **counting as progress**:
`folded_status` won't advance the ticket on it, and `canRunPhase` won't offer the next
phase, with a message that separates "run it first" from "it ran and left nothing".
`artifact_exists` is **nullable and must stay nullable**: NULL means nobody checked,
which is the honest value for every row written before the column. Backfilling it as 0
would call every historical run a liar; as 1, it would vouch for runs nobody verified —
which is why `entregable` is *absent* from a phase rather than `true`, and why the fold
tests `is not False` instead of falsy.

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

**`GET`/`POST /tickets/{tid}/decisiones`** are what makes a `## Decisiones para ti`
item answerable from the UI instead of an editor. Both go through
`declared_file_or_none` — the same door as the artifact viewer — and both 409 while the
ticket has a queued or running run, exactly like `restaurar`: a phase may be reading or
rewriting that same file. `GET` returns `puntos`, one entry per `DECIDIR`/`BLOQUEA`
item under the section, each with `id`, `tipo`, `pregunta` (the question through its
own natural end — the first line ending in `?`, or a blank line, whichever comes
first, NOT just the first physical line: a real analysis wraps a question across two
lines as often as not), `cuerpo` (everything after that, dedented), `propuesta` (the
bold text after `Propuesta:`, or `null`), and `respondido`.

**The markers themselves travel translated, but the API normalizes them before they
leave this module.** A document written in English carries `DECIDE`/`BLOCKS`
instead of `DECIDIR`/`BLOQUEA` (see `MARKERS`); `tipo` in the `GET` response is
always the Spanish pair, via `CANON_TIPO`. The reason is `Decisions.tsx`: it
compares against the literal string `"BLOQUEA"`, and an unnormalized `BLOCKS`
wouldn't fail that comparison loudly — it would silently paint a blocking item in
the warning color instead of the destructive one.

**Both endpoints read and write the file WITHOUT newline translation.**
`Path.read_text()`/`Path.write_text()` silently translate `\r\n` ↔ `\n` — measured on
the real 3359 analysis, answering ONE decision through the naive versions turned all
276 LF line endings into CRLF and grew the file by 305 bytes, which reads as a
whole-file diff to anyone with it in git. `read_text_preserving_newlines` /
`write_text_preserving_newlines` (app.py, opened with `newline=""`) are the fix, and
every caller that rewrites an EXISTING file's content — `append_journal`,
`journal_note`, both decisions endpoints — goes through them. A function that only
ever WRITES FRESH content (`ensure_ticket_agent_config`, which refuses to touch a file
that already exists; the request-file projection, fully regenerated from the DB on
every launch) has nothing to preserve and stays on the plain `Path` calls. New content
these functions insert (a journal line, a `**Respuesta:**` line) has no convention of
its own, so it borrows the file's dominant one (`_dominant_eol`: CRLF if the file uses
it anywhere, LF otherwise) rather than hardcoding `\n`.

**An item's `id` is a hash of its own exact text, not a line number.** `_decision_items`
(app.py) finds each item's boundary as "up to the next item's start" and hashes that
whole raw slice (`sha256(core)[:16]`) — not just the first line, which the task's own
first draft allowed but which several items in a real analysis collide on (two
questions starting "¿Qué pasa con..."). Hashing the FULL item means an edit ANYWHERE
inside it — question, body, even whitespace — changes the id: `POST /decisiones`
re-parses the file at request time and refuses with 409 if the id it was handed isn't
found, which is what catches a human editing the file by hand between the GET and the
POST, and also what makes re-answering an already-answered item refuse instead of
silently overwriting it (its id changed the moment it was first answered). A submitted
id that no longer matches anything exactly gets ONE more check before the generic "the
file changed" refusal: `_pre_answer_id` undoes exactly what `_write_answer` does (the
checkbox flip, the appended `**Respuesta:**` block) to every already-answered item and
re-hashes it — if that recovers the submitted id, the real story is a stale resubmit
(a slow request, a double click) against an item that's already answered, and the
refusal says that instead of blaming an edit that never happened.

**The answer lands as an indented `**Respuesta:**` line, same convention as
`Propuesta:`.** `_write_answer` ticks the box (`- [ ]` → `- [x]`) and appends
`      **Respuesta:** <text>` — six spaces, the same continuation width the skill
templates already write under a `DECIDIR`/`BLOQUEA` item — right after the item's own
body, so the next phase reads it as one more line of the item's prose, not a foreign
insertion. It's a splice at the item's own recorded offsets: every byte outside that
one item is copied through unchanged, which a test asserts directly. Accepting a
proposal writes the proposal's own text verbatim as the answer (the same string `GET`
already returned as `propuesta`), so "accept" and "answer" close through the exact same
code path. Recorded in the journal like `restaurar` is, for the same reason: a file
that changes with nobody saying so is what makes the next session unable to
reconstruct what happened.

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
- **The sandbox's network is a per-phase flag, and it is not the same everywhere.**
  Phase 2 validates with `npx @fission-ai/openspec`, which downloads on every start.
  Codex's `workspace-write` defaults to **no network** where it really sandboxes (Linux,
  macOS); on Windows it doesn't sandbox that way, so a run there reaches the registry
  without asking — which is the trap, not the reassurance. `codex_argv` passes
  `-c sandbox_workspace_write.network_access=true` for the phases in `PHASE_NETWORK`,
  derived from which phases carry Bash rather than kept as a second list. The key is
  verified, not guessed: `--strict-config` accepts it and rejects an invented one.
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
- **Code, comments, and process docs in English; UI text follows the language knob.**
  Planning documents (`docs/superpowers/plans/`, `docs/superpowers/specs/`) are
  exempt from this rule and can stay in Spanish. Four categories decide it:
  **prompt-facing** strings (`PHASE_NOUN`, `repos_text`, `adjustment_text`)
  are read by the agent, so they're English and track the skills.
  **UI-facing** strings (`HTTPException` details and the rest of the `motivo` text
  that never travels into a deliverable, plus every label, button and toast in the
  frontend) are read by you in the browser, and **since 2026-08-19 they follow the
  same `settings.idioma` knob as the deliverable-facing category below** — not
  "Spanish, fixed" as this rule used to say. On the backend, `MSG`/`msg()` (next to
  `journal_lang`) resolve an error's text against the knob at request time, the same
  way `journal_code` already resolved a deliverable's. On the frontend, two
  mechanisms split the work, and the choice between them is not a preference, it is
  forced by one property of the string:
  - **`t("key")` over a flat `ES`/`EN` dictionary (`strings.ts`)** for a short string
    that translates as a whole — a button label, a toast, an aria-label.
  - **A `Record<Lang, ReactNode>` per component** (`LANGUAGE_INFO`, `ARCHIVE_INFO`,
    `PHASE_INFO`, …) for prose that carries markup — a `<strong>`, a `<code>`, a link
    — **inside** the sentence. The rule that picks one over the other: markup inside
    the sentence → a per-language JSX block; otherwise → the dictionary. The reason
    is that a dictionary needs a key per **fragment** once markup splits a sentence,
    and the cut points a translator needs almost never land in the same place in two
    languages — Spanish and English break a sentence around its bolded clause
    differently, so a fragment-keyed dictionary either produces ungrammatical splices
    or grows one key per sentence anyway, at which point it has stopped being a
    dictionary and should just be the JSX block it was avoiding.
  - **A status badge's colour hangs off the backend STATE, never off the translated
    label.** `status.ts`'s `COLOR` map is indexed by `queued`/`analyzed`/`error`/…
    — the literal the backend returns — and `ticketStatus`/`phaseColor` look up that
    state directly; the *label* shown next to the colour goes through `t()`
    separately. This one is not obvious because it worked by accident until it
    didn't: the map used to be indexed by the (translated) label, and every badge
    silently fell back to one grey the moment a second language existed, with no
    build or lint error to catch it — a `Record<string, string>` doesn't know its
    keys were supposed to be exhaustive.
  - **The hash-route segments (`#/ajustes`, `#/proyecto/…`) are deliberately NOT in
    the dictionary** (`router.ts`'s `SEG_SETTINGS`/`SEG_PROJECT` are plain constants,
    kept outside `strings.ts` on purpose). A route token is an address, not prose:
    translating it would break every existing bookmark on the other language and
    fork the app's URL space in two, one per language, for no reader-facing benefit.
  - **The language is resolved once, before React mounts, never in an effect.**
    `main.tsx` awaits `initLang()` (which reads the `localStorage` cache first, then
    corrects it against `GET /idioma`) and only then calls `createRoot(...).render`.
    Resolving it inside a `useEffect` instead would paint the first frame in
    whatever the stale default is and jump languages after the user has already
    started reading it — worse for a `useState` initial value that reads `t()` once
    and keeps that string forever, since an effect firing later can't retroactively
    fix it. Because the knob is read exactly once per page load, `Language.tsx`'s
    `pick` doesn't try to re-propagate a change through React state — it calls
    `location.reload()` after saving, which is the only way to make `initLang` run
    again.
  **Contract literals** (the `HUELLA` stamp and its values, the `/modelos` and
  `/artefacto?ruta=` route paths, JSON keys like `fases`) are matched byte-for-byte
  somewhere, so they don't get translated in either direction — read
  `STAMP_RE` before touching any of them.
  **Deliverable-facing** strings (the journal's own vocabulary, the reasons stored
  in `runs.artifact_path`, the archive notes) end up inside a `.md` of the TARGET
  repo, which is neither the browser nor a prompt. The knob (`settings.idioma`,
  `lang()`) decides the language ONLY when the file is being CREATED — and once it
  exists, the language is taken from the file, never from the knob: a journal
  created in Spanish keeps growing in Spanish, and an analysis written in Spanish is
  answered in Spanish, whatever the knob says today. `journal_lang`/`marker_lang`
  read a file's own language from headings/markers it already carries;
  `journal_code(ticket)` gives CALLERS of `append_journal`/`journal_note` that same
  answer BEFORE the string reaches those functions — it reads the ticket's journal
  itself (falling back to the knob when it doesn't exist yet) so the `detail`/
  `note`/`extra` text a caller builds (`no_stamp_reason`, `no_brief_reason`,
  `no_surveys_reason`, the archive notes, the fan-out's caveat, a restore's or a
  decision's own note) agrees with the separators (`rama`, `resume`, `reserva`)
  that `append_journal` itself resolves via `journal_lang`. Without this a knob
  flipped mid-ticket used to produce a line whose separators were the file's
  language and whose content was the knob's — the same file holding both.
