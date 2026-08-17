# Using ticket-agent

Already installed? ([INSTALL.md](INSTALL.md) if not.) This page is the day-to-day:
what each command does, what it leaves on disk, where you're supposed to intervene,
and every configuration key that exists.

1. [The shape of it](#the-shape-of-it)
2. [Stage 1 · Understand the ticket](#stage-1--understand-the-ticket)
3. [Stage 2 · Plan the change](#stage-2--plan-the-change)
4. [Stage 3 · Implement](#stage-3--implement)
5. [Where everything lands](#where-everything-lands)
6. [Tickets that span several repos](#tickets-that-span-several-repos)
7. [Configuration reference](#configuration-reference)
8. [Running it headless](#running-it-headless-the-way-the-orchestrator-does)
9. [Habits worth having](#habits-worth-having)

## The shape of it

An Azure DevOps work item goes in; commits on a branch come out — in three stages
that **you launch one at a time**:

    /ticket-agent:analyze 3311     →  docs/tickets/3311-analysis.md
    /ticket-agent:plan 3311        →  openspec/changes/3311-<slug>/
    /ticket-agent:implement 3311   →  commits on branch ticket-agent/3311

Nothing chains itself, and that's the design, not a missing feature. Between every
two stages there's **a file on disk** you read, correct and approve. An agent that
ran all three unattended would compound its first misunderstanding three times.

Every command takes one argument — the work item id — and every one of them ends
with a stamp telling you what it actually produced:

| Stamp | Means |
|---|---|
| `HUELLA: ok — <path>` | the deliverable is written and complete |
| `HUELLA: parcial — <path> · <caveat>` | written, but with a gap it names |
| `HUELLA: nada — <reason>` | nothing was written, and why |

`parcial` and `nada` are not failures to hide: they're the agent telling you it hit
something it can't decide. Read the reason before re-running.

---

## Stage 1 · Understand the ticket

    /ticket-agent:analyze 3311

Read-only: work item, its comments, its relations one level out, its attachments,
the linked wiki, your repo's rules, and the code the ticket touches. No writes to
Azure DevOps ever — the MCP's write tools are forbidden to this phase.

It produces `docs/tickets/3311-analysis.md`, structured always the same way:

    ## What it asks for
    ## Acceptance criteria          ← explicit and implicit, verbatim where possible
    ## Ambiguities and open questions
    ## Relations context            ← what the parent/sibling tickets add
    ## Comments / Cited references / Reviewed attachments
    ## Applicable project rules     ← from your CLAUDE.md, your conventions
    ## Affected code                ← real paths, with the pattern to follow
    ## State of work in the repo    ← is any of this already done?
    ## Risks and dependencies
    ## Missing information
    ## Decisiones para ti           ← the part you answer

**Now read it.** This is the cheapest place in the whole flow to catch a
misunderstanding: it's one file, and nothing has been written yet. Correcting a
paragraph here costs a minute; catching the same error after Stage 3 costs the day.

Re-running the command rewrites the file, so if you edited it, either keep your
edits somewhere or correct by conversation instead of re-running blind.

> **If the ticket touches more than one repo**, this single command is the wrong
> tool — it would analyze the other repos under *this* repo's conventions. Use the
> `brief` → `survey` → `consolidate` route instead:
> [Tickets that span several repos](#tickets-that-span-several-repos).

### Answering the open decisions

Every deliverable closes with a short, bounded list — so you don't have to hunt
through 8 KB looking for the weak spots:

    ## Decisiones para ti

    - [ ] **DECIDIR** — ¿el `trendId` lo expone el back o lo calcula el front?
          Propuesta: el back, sigue el patrón de `Controllers/Trends.cs:88`.
          Si no respondes, sigo con la propuesta.

    - [ ] **BLOQUEA** — el ticket no dice si el export respeta el filtro activo.

You answer **by editing the file**: tick the box and write your answer underneath.
Same convention as a `tasks.md` checklist, no second format to learn.

    - [x] **DECIDIR** — ¿el `trendId` lo expone el back o lo calcula el front?
          Lo expone el back. Y de paso incluye el `sourceId`, lo va a necesitar.

| Marker | If you leave it unticked |
|---|---|
| `DECIDIR` | carries a defensible proposal — the next stage proceeds with it **and writes down that it did** (or stops, if `autonomy: supervised`) |
| `BLOQUEA` | has no defensible default — the next stage refuses to start, in either mode |

A ticked answer **beats the plan's own text** downstream. That's the point: it's
your correction, applied later, without you having to rewrite the whole document.

---

## Stage 2 · Plan the change

    /ticket-agent:plan 3311

Reads `docs/tickets/3311-analysis.md` — **the analysis, not the work item.** The
analysis is the interface between the stages; if the file isn't there it stops and
asks you to run Stage 1 first.

Then it studies the existing pattern in your code and writes an OpenSpec change:

    openspec/changes/3311-export-trends/
      proposal.md          ← what changes and why
      design.md            ← the decisions, and its own ## Decisiones para ti
      tasks.md             ← the executable checklist
      specs/<capability>/spec.md

It validates the change with the OpenSpec CLI and **writes no product code**. The
deliverable is the plan.

Each task in `tasks.md` names its test and its check as two separate lines:

    - [ ] 3. Add the trendId field to the list response
          Destination: src/Api/Controllers/TrendsController.cs
          Mirror:      src/Api/Controllers/ReportsController.cs:120
          Test:        tests/Api/TrendsControllerTests.cs::returns_trend_id
          Check:       dotnet test --filter TrendsControllerTests

They're separate because only the planner can make the test a *deliverable*. Without
that, the test gets written after the code and passes on its first run, which proves
nothing. Work with no runnable test says so honestly: `Check: manual — verify in the
UI that the column appears`.

**Read `tasks.md` before implementing.** It's the contract Stage 3 executes to the
letter, and it's much cheaper to argue with here.

---

## Stage 3 · Implement

**Create the branch first — this stage doesn't create it for you:**

    git checkout -b ticket-agent/3311
    /ticket-agent:implement 3311

Four preconditions, all of which stop the run with `HUELLA: nada` rather than
improvising:

| Precondition | If it fails |
|---|---|
| a plan exists for the id | `missing plan for 3311` |
| exactly **one** change folder matches | `multiple changes for 3311` — you pick |
| you're on branch `ticket-agent/3311` | `repo isn't on ticket-agent/3311` |
| no unanswered `BLOQUEA` (nor `DECIDIR`, if supervised) | `N decisiones sin resolver` |

Then, per task in `tasks.md`:

1. An **implementer** subagent writes the test first and watches it fail, then makes
   it pass.
2. A **reviewer** subagent looks at the diff with a clean context — the agent driving
   the phase wrote the implementer's prompt, so it can't be the one to review it.
3. The driving agent **re-runs the `Check` itself**. It doesn't take the subagent's
   word for the green.
4. It commits that task's paths — `3311 task 3: add trendId to the list response`,
   one commit per task — and ticks the box.

Findings graded `critical` or `important` trigger one retry. `minor` findings, and
anything the plan explicitly ordered, never block — they're appended to `tasks.md`
under `## Review notes`, because a summary in chat dies with the session and
`tasks.md` is what you'll open tomorrow.

A task that fails twice stops the run with `HUELLA: parcial`, leaving the remaining
boxes unticked and the earlier commits intact. Fix, and re-launch: the ticked boxes
tell it where to resume.

**It stops on a branch with commits: no push, no PR.** That's enforced by the
orchestrator with a hook that denies `git push`, `git remote add`, `gh pr create` and
`az repos pr create`. Running by hand there's no hook — but the skill still doesn't
push. The `git log` is the record of progress; what goes out is your call:

    git log --oneline main..ticket-agent/3311
    git push -u origin ticket-agent/3311

---

## Where everything lands

**The plugin itself lives in your user directory, not in any repo:**

    ~/.claude/plugins/     # Windows: C:\Users\<you>\.claude\plugins\

Installed once, available in every repo you open. Nothing of it is copied into your
projects. What *does* live in each project is its configuration and its deliverables:

    your-repo/
      .claude/
        settings.json              ← ADO_ORG, ADO_AUTH        (committable)
        settings.local.json        ← the PAT, if you use one   (gitignored)
        ticket-agent.json          ← organization, project…    (committable)
      docs/tickets/
        3311-brief.md              ← multi-repo route only
        3311-analysis.md           ← Stage 1's deliverable, either route
      openspec/changes/
        3311-export-trends/        ← Stage 2's deliverable
      (branch ticket-agent/3311)   ← Stage 3's deliverable: the commits

Everything is written **in your repo**, in plain markdown, and committable. Nothing
lives in a database, and nothing is hidden in a session that dies when you close the
terminal.

---

## Tickets that span several repos

Skip this section entirely if your ticket lives in one repo.

**Why the normal route doesn't work here.** `analyze` runs in one session rooted in
your main repo. Mounting a sibling repo gives that session the other repo's *files* —
but not its `CLAUDE.md`, not its hooks, not its `.mcp.json`. So it analyzes the second
repo confidently under the **first** repo's conventions, and nothing catches it.
Wrong rules applied with confidence is worse than no rules at all.

So Stage 1 splits into three commands and **one session per repo**:

    /ticket-agent:brief 3311        # → docs/tickets/3311-brief.md
    /ticket-agent:survey 3311       # one session rooted in EACH routed repo
    /ticket-agent:consolidate 3311  # → the same 3311-analysis.md

Stages 2 and 3 are unchanged: `consolidate` writes the same `3311-analysis.md` that
`analyze` would, so nothing downstream learns which route ran.

### 1 · Mount the repos and name them

Two separate jobs, and doing only the first is the classic mistake.

**Mount them** — grant the session file access. Ad hoc, or permanently:

    claude --add-dir ../frontend --add-dir ../shared-lib
    > /add-dir ../shared-lib      # same thing, from inside a running session

    // .claude/settings.json — every session in this repo
    {
      "permissions": {
        "additionalDirectories": ["../frontend", "../shared-lib"]
      }
    }

**Name them in the prompt** — because mounting is not telling. `--add-dir` grants
access; it doesn't make the agent look. A real run had a second repo mounted,
mentioned it fifteen times and never opened it once:

    /ticket-agent:brief 3311

    Mounted alongside this repo: ../frontend (the React app, `front`) and
    ../shared-lib (the shared DTOs, `shared`). This repo is `back`.

**There is no label field anywhere.** Worth stating plainly, because the orchestrator
app has a name box next to each repo and it looks like configuration: it isn't. That
name gets interpolated into the prompt text the runner sends, and nothing more. No
skill reads a repo name from `ticket-agent.json`, from `settings.json` or from any
other file — all of them expect it in the prompt. **Running by hand, you are the
runner:** if you don't write the labels, they don't exist.

Keep them short, and use the same word everywhere — the routing line is next.

### 2 · The brief, and the routing line

`brief` reads the work item and writes `docs/tickets/3311-brief.md`, ending in:

    SONDEAR: back, front

Edit that line before surveying — it's the cheapest place to add or drop a repo.
Miss it, empty it, or name a repo that doesn't exist and **every** mounted repo gets
surveyed. The failure direction is always "one repo too many", never one too few: a
repo left out is a hole in the analysis that the plan then consumes without knowing.

### 3 · One survey per repo, each in its own session

This is the whole point of the split: the survey **must** run from a session whose
working directory *is* that repo, or it inherits the wrong rules.

    cd ../frontend
    claude
    > /ticket-agent:survey 3311

That session needs no `ADO_ORG`, no token and no `ticket-agent.json` — the brief
travels in the prompt and Azure DevOps is never contacted from there. Paste the
brief's contents in, and don't mount the sibling repos: that would put the main
repo's rules back in front of the session you just went to the trouble of isolating.

Collect each survey into the main repo's `docs/tickets/` before the last step. The
scripted version of this loop is in
[Running it headless](#the-survey-child-by-hand).

### 4 · Consolidate

Back in the main repo, `/ticket-agent:consolidate 3311` merges the surveys and adds
the one thing no single repo could produce:

| Qué | Lo espera | Lo ofrece | Veredicto |
|---|---|---|---|
| `GET /api/trends/export` | front | back | ✅ cuadra |
| campo `trendId` en la lista | front | — | ❌ hueco |

That table is where mismatched endpoints, duplicated work and the same concept under
two different names surface — before anyone writes code.

`analyze` stays available for these tickets too: it's the fallback if the split gets
stuck, and the baseline to compare against. Both write the same file.

---

## Configuration reference

### `.claude/ticket-agent.json` — in each project, committable

    {
      "organization": "cr360dev",
      "project": "CallRevu Development Lifecycle Management",
      "autonomy": "supervised",
      "subagent_model": "sonnet"
    }

Written by hand for standalone use. Driven through the orchestrator app instead,
this file is created for you (`organization`/`project` only, from the project's
saved configuration) the first time a phase in `PHASE_MCP` runs and finds it
missing — it never overwrites one you already committed, and never invents
`autonomy` or `subagent_model`.

| Key | Required | Values | What it does |
|---|---|---|---|
| `organization` | yes | the org subdomain | must match `ADO_ORG`; nothing validates it |
| `project` | yes | display name, spaces, decoded | what the skill queries work items in |
| `autonomy` | no | `supervised` (default) · `autonomous` | whether an unanswered `DECIDIR` stops the next stage |
| `subagent_model` | no | `opus` · `sonnet` · `haiku` · a full id | the model for Stage 3's per-task subagents |

Anything unrecognized in `autonomy` is treated as `supervised`, and there are no
other keys — the file is deliberately small. In particular there is **no key for the
other repos' paths and no key for their labels**: the paths are a session permission
(below), and the labels live in the prompt.

**`autonomy` in practice.** Both modes stop at the end of every stage and hand you
the file; `autonomous` never chains one stage into the next. The only difference is
the unanswered `DECIDIR`:

| | unanswered `DECIDIR` | unanswered `BLOQUEA` |
|---|---|---|
| `supervised` | the next stage stops | stops |
| `autonomous` | proceeds with the proposal, and records that it did | stops |

**`subagent_model` is the only model knob the plugin applies itself**, and it reaches
only the subagents Stage 3 launches per task — not the agent driving the stage.
Without it they inherit the session's model, which is what you want almost always.
It exists for the opposite case: dropping to a cheaper model for mechanical task work
while the driving stays on the good one.

### `.claude/settings.json` — the environment and the mounts

    {
      "env": {
        "ADO_ORG": "cr360dev",
        "ADO_AUTH": "envvar"
      },
      "permissions": {
        "additionalDirectories": ["../frontend", "../shared-lib"]
      }
    }

| Setting | Where it goes | What it does |
|---|---|---|
| `env.ADO_ORG` | `settings.json` | the org the MCP server connects to. **Required for standalone use** — an orchestrator-driven run supplies it as a fallback when the repo doesn't already export one |
| `env.ADO_AUTH` | `settings.json` | auth mode; unset = the `az login` session |
| `env.ADO_MCP_AUTH_TOKEN` | `settings.local.json` or the real environment | the PAT, when `ADO_AUTH=envvar`. **Never committed** — an orchestrator-driven run can source this from a PAT saved per project in its own UI instead (plaintext in `orchestrator.db`; see that app's `CLAUDE.md`) |
| `permissions.additionalDirectories` | any of the three settings files | the other repos' paths. Relative paths work |

`additionalDirectories` is valid in `.claude/settings.json` (the team's),
`.claude/settings.local.json` (yours alone) and `~/.claude/settings.json` (all your
projects). It grants access only — see
[mount them and name them](#1--mount-the-repos-and-name-them).

Full auth table and PAT setup: [INSTALL.md, step 3](INSTALL.md#step-3--pick-how-it-authenticates).

### Choosing the model and effort

A plugin can't change the model of the session running it — neither skills nor
commands have a field for that. It's chosen from outside, and each route covers a
different scope:

| What you want | How |
|---|---|
| this session only | `/model opus` and `/effort high` before launching the command |
| every session in a repo | `"model"` in that repo's `.claude/settings.json` |
| Stage 3's per-task subagents | `subagent_model` in `.claude/ticket-agent.json` |
| a different model per stage, without editing anything | the hub's orchestrator app: Settings → model per phase |

`effort` has no per-invocation equivalent: it doesn't travel into a subagent.

---

## Running it headless, the way the orchestrator does

Everything above assumes an interactive session, which is the normal way. But the
orchestrator drives the exact same plugin through `claude -p`, and you can too — for
a script, a CI job, or to run the multi-repo fan-out without babysitting three
sessions. This is the shape it uses, straight from the runner:

    claude -p "/ticket-agent:analyze 3311" \
      --output-format stream-json --verbose \
      --permission-mode acceptEdits \
      --allowedTools mcp__azure-devops Read Glob Grep Task Write Edit \
      --add-dir ../frontend

Run it **with the target repo as your working directory** — that's what makes Claude
Code load its `CLAUDE.md`, its hooks, its `.mcp.json` and the two config files.

Four things that are not obvious, and each one cost a debugging session:

- **`--permission-mode acceptEdits` does not auto-approve MCP tools in headless
  mode.** Without `mcp__azure-devops` in the allowlist, the agent simply cannot read
  the work item — and it reports it as a connection problem.
- **That MCP name depends on where the server comes from.** When the target repo has
  its own `.mcp.json` it's `mcp__azure-devops`, which is what the orchestrator's real
  runs show. When the server comes from the plugin instead, the tools are namespaced
  `mcp__plugin_ticket-agent_azure-devops__*` and the allowlist entry must match that.
  Check with `/mcp` in an interactive session before scripting it.
- **`implement` needs more**: `Bash` in the allowlist, the branch created beforehand,
  and — if extra repos are mounted and it will write in them —
  `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` in the environment, so it obeys
  *their* conventions instead of applying this repo's with confidence.
- **The exit code lies.** `claude -p` exits 0 even when the agent stopped without
  writing anything. The `HUELLA:` stamp in the output is the only reliable signal —
  that's why the runner greps for it, and why every skill is required to emit one.

### The survey child, by hand

The fan-out is just one headless run per repo, each rooted in that repo, with the
brief **inline in the prompt** — that's what lets those repos need no `ADO_ORG`, no
token and no `ticket-agent.json`. Same template the runner builds:

    cd ../frontend
    claude -p "/ticket-agent:survey 3311

    You are rooted in the repo \`front\` (D:\\code\\frontend), and this session is the
    only one that sees ITS rules, hooks and configuration. Answer only for this repo.

    Write the survey to <path>/survey-front.md and nothing else: this repo is
    read-only for you.

    --- Ticket brief (the work item is NOT reachable from here; this is all of it) ---
    $(cat ../main-repo/docs/tickets/3311-brief.md)
    --- end of brief ---" \
      --permission-mode acceptEdits \
      --allowedTools Read Glob Grep Task Write Edit

Note what's *missing*: no MCP in the allowlist — the child never contacts Azure
DevOps — and no sibling repos mounted. The runner mounts only a scratch directory
for the output, deliberately: mounting the other repos would put the main repo's
rules back in front of this session, which is the exact defect the split exists to
remove.

Then collect each `survey-<label>.md` into the main repo's `docs/tickets/` and run
`/ticket-agent:consolidate 3311` there.

---

## Habits worth having

- **Read the analysis before planning, and `tasks.md` before implementing.** Both are
  short, and both are the last cheap place to catch a wrong assumption.
- **Answer `DECIDIR` even when you agree with the proposal.** Ticking the box is your
  record that a human looked at it.
- **Re-running a stage rewrites its deliverable.** If you hand-edited it and want to
  re-run, save your version or correct by conversation instead.
- **One ticket, one branch.** Stage 3 refuses to run anywhere else, and that's what
  keeps two half-finished tickets out of the same diff.
- **Trust `HUELLA: parcial` over the absence of an error.** The command exits happily
  either way; the stamp is the honest signal.

## Doing this at scale

Running the multi-repo route by hand means opening a session in each repo, in order,
and remembering where you were. The hub's local app —
[`apps/orchestrator/`](apps/orchestrator/) — does that part: a queue of tickets, a
button per stage, the deliverables rendered inline, the open decisions counted next
to each phase, and the model picked per stage. Same plugin underneath, launched as
`claude -p` against your repo. It's optional: the plugin works on its own from any
session, which is what this page describes.
