# ticket-agent

From an Azure DevOps work item to commits on a branch, in three stages you launch
one at a time. Nothing chains itself: between every two there's a file on disk to
read, correct and decide on.

| Stage | Command | Produces |
|---|---|---|
| **1** understand | `/ticket-agent:analyze <id>` | `docs/tickets/<id>-analysis.md` — read-only |
| **2** plan | `/ticket-agent:plan <id>` | an OpenSpec change in `openspec/changes/<id>-<slug>/` |
| **3** implement | `/ticket-agent:implement <id>` | commits on `ticket-agent/<id>`, one per task |

A ticket that spans **several repos** takes a different route through stage 1 —
`brief` → `survey` → `consolidate`, one session rooted in each repo — because
`--add-dir` mounts another repo's files but not its rules. See
[When the ticket spans more than one repo](#when-the-ticket-spans-more-than-one-repo).
It ends in the same `<id>-analysis.md`, so stages 2 and 3 don't change.

**Stage 3 stops on a branch with commits: no push, no PR.** The `git log` is the
record; you decide what goes out.

## Requirements

The plugin installs none of these; it assumes them present.

- **Node.js 20+ with `npx` and network access.** Two separate uses: the MCP server
  itself (`npx -y @azure-devops/mcp`, downloaded on every start — without it there
  is no Phase 1 at all), and Phase 2's `@fission-ai/openspec` (note: the package is
  *not* called `openspec`). Neither is vendored anywhere.
- **A credential for Azure DevOps** — Azure CLI session (`az login`) by default, or
  a token. See "Credentials".
- **Git**, with `user.name`/`user.email` configured: Phase 2b commits per task.
- **Claude Code with plugin support**, and the hub added as a marketplace.

Not required: an `openspec/` folder in the target repo (Phase 2 runs `init` if it's
missing), and no Anthropic API key — execution runs on the CLI subscription.

Nothing checks these up front. A missing `npx` surfaces as
`HUELLA: nada — npx unavailable or openspec init failed`; a missing Azure
credential surfaces as "can't read the work item", which reads like a
misconfigured org and sends you looking in the wrong place. **Verify the
credential first** (see "Credentials").

## Installing in a project

Step by step, with the prerequisite checks and the usual failures:
[INSTALL.md](../../INSTALL.md); day-to-day use and the full configuration reference:
[USAGE.md](../../USAGE.md). The short version:

1. `/plugin marketplace add jhonnygarcia/autonomous-skill-hub`
2. `/plugin install ticket-agent@autonomous-skill-hub`
3. In the project, define the organization in `.claude/settings.json`:

       { "env": { "ADO_ORG": "ProvidenceSolutions" } }

4. Create `.claude/ticket-agent.json` (committable, no secrets):

       {
         "organization": "ProvidenceSolutions",
         "project": "ProvidenceTMS",
         "autonomy": "supervised",
         "subagent_model": "sonnet"
       }

   - `organization` must match `ADO_ORG` (the MCP connects using `ADO_ORG`; the
     skill uses `project` for queries). **Nothing validates that they match**: if
     they diverge, the MCP connects to one org while the skill queries a project
     from another, and the skill reports it as "MCP not connected".
   - `project` is the display name, with spaces and unescaped — the one in the work
     item URL, decoded. `.../CallRevu%20Development%20Lifecycle%20Management/...`
     goes in as `"CallRevu Development Lifecycle Management"`.
   - The org is the subdomain, and a legacy `<org>.visualstudio.com` account works:
     the MCP builds `https://dev.azure.com/<org>`, which is the same account under
     its modern alias. `https://cr360dev.visualstudio.com` → `"cr360dev"`.
   - `autonomy`: `supervised` or `autonomous`. In both cases the agent stops when
     each phase closes and presents its result to you — `autonomous` doesn't chain
     Phase 2 inside Phase 1 or vice versa; each phase is launched as its own run.
     Any other value is treated as `supervised`.
   - `subagent_model` (optional): which model Phase 2b uses to launch the
     subagents for each task. See "Model and effort".
5. Restart Claude Code so the MCP starts up with the configured organization.

## Usage

    /ticket-agent:analyze 3311

Produces `docs/tickets/3311-analysis.md` with: what the ticket asks for, explicit
and implicit acceptance criteria, ambiguities, context from related tickets,
reviewed attachments, applicable project rules, affected code, risks, and missing
information.

### When the ticket spans more than one repo

`analyze` runs in **one** session rooted in the main repo. That session loads the
main repo's `CLAUDE.md`, skills and hooks — and `--add-dir` mounts the other
repos' *files* but not their *configuration*. So the extra repos get analyzed
under the main repo's conventions, confidently, with nothing to catch it.

For those tickets, Phase 1 splits into three commands and one session per repo:

    /ticket-agent:brief 3311        # reads the work item, decides which repos to survey
    /ticket-agent:survey 3311       # one session rooted in EACH routed repo
    /ticket-agent:consolidate 3311  # merges them, with the contract between repos

`brief` writes `docs/tickets/3311-brief.md`, ending in a routing line you can
edit before launching the survey:

    SONDEAR: back, front

If the runner can't understand that line, it surveys **every** mounted repo. The
failure direction is always "one repo too many", never one too few.

`consolidate` produces the same `docs/tickets/3311-analysis.md` that `analyze`
would, so Phase 2 never learns which route ran — plus the table that no single
repo could write:

| Qué | Lo espera | Lo ofrece | Veredicto |
|---|---|---|---|
| `GET /api/trends/export` | front | back | ✅ cuadra |
| campo `trendId` en la lista | front | — | ❌ hueco |

`analyze` stays available for multi-repo tickets: it's the fallback if the split
gets stuck, and the baseline to compare against. Both write the same file.

### The open decisions

The brief, the analysis and `design.md` close with `## Decisiones para ti` — a
short, bounded list of what needs a human, so you don't have to read 8 KB looking
for the weak spots:

    - [ ] **DECIDIR** — ¿el `trendId` lo expone el back o lo calcula el front?
          Propuesta: el back, sigue el patrón de `Controllers/Trends.cs:88`.
          Si no respondes, sigo con la propuesta.

    - [ ] **BLOQUEA** — el ticket no dice si el export respeta el filtro activo.

You answer by editing the file: tick the box, write underneath. Same convention
as `tasks.md`.

| Marker | Left unanswered |
|---|---|
| `DECIDIR` | The next phase proceeds with the proposal **and writes down that it did** |
| `BLOQUEA` | The next phase doesn't start |

`autonomy` in `.claude/ticket-agent.json` decides what an unanswered `DECIDIR`
does: `supervised` stops the next phase, `autonomous` proceeds and records it.
`BLOQUEA` stops in both.

    /ticket-agent:plan 3311

Phase 2. Reads `docs/tickets/3311-analysis.md` (must exist; if not, asks you to run
Phase 1 first), studies the pattern in the code, and writes the OpenSpec change in
`openspec/changes/3311-<slug>/` (`proposal.md`, `tasks.md`, `design.md`,
`specs/<capability>/spec.md`), validated with the OpenSpec CLI.

Each task in `tasks.md` names the test to write (`Test:`) and the command that runs
it (`Check:`) — separately, so Phase 3 can make the implementer write the test
first and watch it fail. What has no runnable test says so: `Check: manual — ...`.

    /ticket-agent:implement 3311

Phase 3, on the `ticket-agent/<id>` branch. Per task: an implementer subagent works
test-first, a second subagent reviews the diff with a clean context, the driving
agent re-runs the `Check` itself, and only then commits and checks the box. Findings
graded `minor`, and anything the plan explicitly ordered, never block — they're
appended to `tasks.md` under `## Review notes`. A task that fails twice stops the
run with `HUELLA: parcial` and the remaining boxes unchecked.

**It stops on a branch with commits: no push, no PR.** You decide when to push.

## Model and effort

A plugin cannot change the model of the session that runs it: neither skills nor
commands have a field for that. It's chosen from the outside, and each route
covers a different scope:

| What you want | How |
|---|---|
| This session, any phase | `/model opus` and `/effort high` before launching the command |
| Every session in a repo | `"model"` in the repo's `.claude/settings.json` |
| Phase 2b's subagents | `subagent_model` in `.claude/ticket-agent.json` |
| Per phase, without touching anything by hand | the hub's orchestrator: Settings → Model per phase |

`subagent_model` is the only knob the plugin applies by itself, and it only
reaches the subagents that Phase 2b launches per task — not the agent driving the
phase. Without it, subagents inherit the session's model, which is what you want
almost always; it's for the opposite case: dropping the model for the mechanical
work of tasks while the driving stays on the good one. `effort` has no
equivalent: it doesn't travel per invocation.

## Credentials

Default: **no token anywhere**. The MCP starts with `--authentication azcli` and
resolves the credential from the Azure CLI session. Switching accounts = changing
`ADO_ORG` + `ticket-agent.json` + the az session.

Check it before blaming the configuration — if the second command lists projects,
the MCP will connect:

    az account show
    az devops project list --org https://dev.azure.com/<org>

If the org lives in a different Entra tenant than your default one, `az login
--tenant <tenant-id>` is what fixes the `TF400813 ... is not authorized` error.

### Optional: a token instead of az login

`ADO_AUTH` overrides the authentication mode; unset, it stays `azcli`. Useful on a
machine with no Azure CLI, or for unattended runs.

| `ADO_AUTH` | Token variable | Format |
|---|---|---|
| *(unset)* / `azcli` | — | the `az login` session |
| `envvar` | `ADO_MCP_AUTH_TOKEN` | the PAT, plain |
| `pat` | `PERSONAL_ACCESS_TOKEN` | base64 of `email:pat` |
| `interactive` | — | opens a browser; **doesn't work headless** |

`envvar` is the one to use: one variable, plain PAT. The PAT needs at least Work
Items (read), Code (read), and Wiki (read) — plus Code (write) if Phase 2b is going
to push, which it doesn't.

**Where the two variables go is not the same place.** `ADO_AUTH` is safe to commit;
the token is not:

    // .claude/settings.json — committable
    { "env": { "ADO_ORG": "cr360dev", "ADO_AUTH": "envvar" } }

    // .claude/settings.local.json — gitignored, NEVER committed
    { "env": { "ADO_MCP_AUTH_TOKEN": "<pat>" } }

A real environment variable on the machine works just as well and keeps the secret
out of the repo entirely. A PAT in `settings.json` is a leaked credential the day
someone commits it — and PATs expire, so a run that worked yesterday and fails
today with 401 is the expiry, not the config.
