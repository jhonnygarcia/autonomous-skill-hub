# ticket-agent

Fully understands an Azure DevOps ticket — work item, relationships, attachments,
comments, wiki, and host-project rules — and produces a structured analysis in
`docs/tickets/<id>-analysis.md` (Phase 1, 100% read-only). A second phase turns
that analysis into an executable change plan, written as an OpenSpec change.

## Requirements

- Node.js 20+ with `npx` (Phase 2: downloads and runs `@fission-ai/openspec` over
  the network — without npm access, `init` and `validate` fail)
- Azure CLI with an active session: `az login`
- Claude Code with plugin support

## Installing in a project

1. `/plugin marketplace add <hub-url-or-path>`
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
     skill uses `project` for queries).
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

    /ticket-agent:plan 3311

Phase 2. Reads `docs/tickets/3311-analysis.md` (must exist; if not, asks you to run
Phase 1 first), studies the pattern in the code, and writes the OpenSpec change in
`openspec/changes/3311-<slug>/` (`proposal.md`, `tasks.md`, `design.md`,
`specs/<capability>/spec.md`), validated with the OpenSpec CLI.

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

Never stored in repo files. Authentication is resolved by the Azure CLI
(`az login`). Switching accounts = changing `ADO_ORG` + `ticket-agent.json` + the
az session.
