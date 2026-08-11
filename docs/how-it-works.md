# How this works

Three questions, three sections: what the plugin builds, what the front and
back ends are for, and which model runs each step.

---

## 1. What the `ticket-agent` plugin builds

**It doesn't build software: it builds the three artifacts needed to build
it**, and leaves them in the client's repo. The plugin doesn't run in this
repo — here it's only edited. It gets installed in *another* repo (the
product's) and contributes three commands there.

| Command | Skill | Reads | Writes (in the target repo) |
|---|---|---|---|
| `/ticket-agent:analyze <id>` | `ticket-comprehension` | the Azure DevOps work item | `docs/tickets/<id>-analysis.md` |
| `/ticket-agent:plan <id>` | `change-planning` | that analysis | `openspec/changes/<id>-<slug>/` (4 files) |
| `/ticket-agent:implement <id>` | `change-implementation` | that change | **production code**, commits on `ticket-agent/<id>` |

The important part of the architecture: **the logic lives in markdown, not in
code**. Each command is a two-line file that delegates to its skill, and the
`SKILL.md` is the complete procedure — what to read, in what order, what to
write, when to stop. Changing the agent's behavior = editing the `SKILL.md`.
There's no Python engine behind the plugin: the engine is Claude reading
instructions.

### Phase 1 — `analyze`

Read-only, no exceptions (any `*_write` tool from the MCP is forbidden). Reads
the work item via the official Azure DevOps MCP with `expand: All`, its
comments (where they contradict the description, the most recent comment
wins), relations **one level deep**, attachments, the wiki, any work item or
document cited in the text, the host repo's `CLAUDE.md`, and the affected
code. Produces a markdown file with a fixed structure.

Two golden rules govern the whole phase: what couldn't be read goes to
*"Missing information"* with its cause — never filled in with assumptions —
and every figure that doesn't come from the work item cites its source
(`file:line`, a commit, or a command).

### Phase 2 — `plan`

**Consumes the analysis, not the work item.** If
`docs/tickets/<id>-analysis.md` doesn't exist, it stops and asks for Phase 1
to be run: the analysis is the interface between the two, and Phase 2 is
forbidden from going back to the MCP. It studies the pattern in the code (the
"mirror": the carrier already migrated, the twin handler) and writes an
OpenSpec change — `proposal.md`, `tasks.md`, `design.md`,
`specs/<capability>/spec.md` — validated with
`npx @fission-ai/openspec validate`.

It also doesn't write production code. Its deliverable is the plan, and every
task in the plan carries a destination, a mirror with `file:line`, and an
executable "Check". A task without a cited mirror isn't a task, it's a wish.

### Phase 2b — `implement`

The first phase that touches client code. Reads `tasks.md` and, for each
unchecked box, **in order**: delegates the task to a subagent with a clean
context, runs the "Check" the task itself declares, reviews the `git diff` of
the touched paths, commits **those specific paths** (`<id> task N: <subject>`,
one commit per task), and checks the box. A task that fails twice stops the
plan and seals `parcial`.

**Stops on a branch with commits: no push, no PR.** The `git log` is the
record of progress; pushing it is a decision for the human.

---

## 2. Front and back: what they are and how they relate to the plugin

`apps/orchestrator/` is a local app that is **not** part of the plugin. It's
the hand that presses the button.

The plugin works perfectly without it: install it in the client's repo, open
Claude Code there, and type `/ticket-agent:analyze 3323`. The orchestrator
exists so you don't have to do that by hand, repo by repo and phase by phase.

### Backend (`backend/app.py`, FastAPI, port 8000)

A single file. SQLite without an ORM, three tables (`projects`, `tickets`,
`runs`), the HTTP routes, and the runner. What it actually does is this:

```
execute_run  →  claude -p "/ticket-agent:analyze 3323 …"
                  cwd = repo_path of the ticket
                  --output-format stream-json  →  logs/<run_id>.log
```

In other words: it **launches the Claude Code CLI as a subprocess** inside the
target repo, with the plugin's command as the prompt, and streams the output
to a log the UI tails. A global `asyncio.Lock` serializes runs — one at a
time, on purpose.

And it does three more things the plugin can't do for itself:

- **Containment.** What restricts `implement` is set by the runner, not the
  skill: a limit that depends on the agent obeying a markdown file isn't a
  limit. The runner creates the `ticket-agent/<id>` branch before launching,
  and injects via `--settings` a `PreToolUse` hook on Bash that denies
  `git push`, `git remote add|set-url`, `gh pr create`, and
  `az repos pr create`.
- **Per-phase permissions.** `analyze` runs without `Bash`; `design` carries
  only OpenSpec's `npx`; `implement` carries `Bash`. In headless mode,
  `--permission-mode acceptEdits` does **not** auto-approve MCP tools, so they
  have to be listed by hand or the agent can't even read the work item.
- **Knowing whether there was a deliverable.** `claude -p` exits with code 0
  even if the agent stopped without writing anything. That's why all three
  skills are required to close with a stamp —
  `HUELLA: ok|parcial|nada — <ruta>` — and the runner looks for it in the log,
  keeping the **last** match (the body of `SKILL.md` travels in the log and
  contains all three stamps literally; checking for mere presence would make
  the check find itself).

### Frontend (`frontend/`, React + Vite, port 5173)

The backend's UI, nothing more. Registers projects (org, project, repos with a
label), creates tickets, launches each phase with a button, shows the
ticket's timeline with each run's stamp, and serves the artifact the run
declared it wrote.

Zero relation to the plugin: if the front end were deleted tomorrow, the
plugin would keep working the same.

### A ticket's full journey

```
[UI] register project   →  repos + org + project in SQLite
[UI] register ticket    →  copies org/project/repos from the project (like a line item on an order)
[UI] "analyze" button   →  POST /tickets/{id}/run {phase:"analyze"}
                              ↓
[backend] global lock → subprocess `claude -p "/ticket-agent:analyze 3323"`
                              ↓
[Claude Code in the client repo] loads the plugin → loads the skill → ADO MCP
                              ↓
                        docs/tickets/3323-analysis.md  +  "HUELLA: ok — …"
                              ↓
[backend] reads the stamp from the log → runs.artifact_state = ok
[UI] the phase turns green, with a button to view the artifact
```

And the same, button by button, for `design` and `implement`. The ticket's
progress isn't stored in any column: it's folded from the `runs` table on
every read.

---

## 3. Which model runs each step

**Short answer: the same one, and it's not pinned anywhere in this repo.**

There's not a single `--model` in the code. The runner builds this command:

```
claude -p "<prompt>" --output-format stream-json --verbose
        --permission-mode acceptEdits
        --allowedTools mcp__azure-devops Read Glob Grep Task Write Edit …
        [--settings …] [--add-dir …]
```

Without `--model`, the CLI uses **the default model of the machine where the
backend runs**: whatever is configured in `~/.claude/settings.json` or chosen
via `/model` on that install. Changing the model for the three phases today
means changing the CLI's configuration, not touching the orchestrator.

And within each run:

| Step | Who runs it | Model |
|---|---|---|
| `analyze` — gathering and writing the analysis | the run's main agent | the CLI's default |
| `analyze` — reading relations and affected code | `Explore` / general-purpose subagents (via the `Task` tool) | inherited from the main agent |
| `design` — reading the analysis, studying the mirror, writing the change | main agent | the CLI's default |
| `implement` — the loop, diff review, and commits | main agent | the CLI's default |
| `implement` — each task in the plan | one subagent per task (via the `Task` tool), clean context | inherited from the main agent |

Subagents inherit the model of the agent that launches them unless the agent
type declares its own, and none of the ones the skills use do. In other
words: **the whole ticket, end to end, runs on a single model.**

### What is pinned, and it isn't the model

What changes from one phase to another isn't the model but the environment,
and that lives in four tables next to `PHASES` in `app.py`:

| Table | What it decides | `analyze` | `design` | `implement` |
|---|---|---|---|---|
| `PHASE_COMMANDS` | what gets launched | `/ticket-agent:analyze` | `/ticket-agent:plan` | `/ticket-agent:implement` |
| `PHASE_ALLOWED_TOOLS` | which extra tools | *(empty: read-only)* | `Bash(npx …openspec:*)` | `Bash` |
| `PHASE_DONE` | what state it leaves the ticket in | `analyzed` | `planned` | `implemented` |
| `PHASE_NOUN` | what the deliverable is called in the prompt | "the analysis" | "the plan" | "the implementation" |

Plus `settings_for()`, which only in `implement` injects the hook that denies
the push.

### If a per-phase model is ever wanted

It would be a fifth table `PHASE_MODEL` and two lines in `execute_run`:

```python
PHASE_MODEL = {"analyze": "opus", "design": "opus", "implement": "sonnet"}
...
cmd += ["--model", PHASE_MODEL[phase]]
```

It doesn't exist today, on purpose: there's no measurement showing one phase
needs something different from another, and the subscription bills the same
either way. Add it once there's a run that proves a cheaper model is enough
for `implement`, or that a better one changes `analyze`'s result.

### One rule that is non-negotiable

**Subscription, never an API key.** Programmatic execution uses the headless
CLI (`claude -p`), not the Agent SDK, and the runner removes
`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the subprocess environment
— there's a test that guarantees it. Without those variables, the only
credential available is the local `/login`'s.
