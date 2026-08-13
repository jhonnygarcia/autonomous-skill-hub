# Autonomous Skill Hub

Personal marketplace of Claude Code plugins, plus a local app that drives them.
Each plugin packages real experience as skills, commands, agents and hooks,
installable in any project.

**Project status** (what's done, what's missing, decisions): [docs/STATUS.md](docs/STATUS.md)
**How it all fits together**, end to end: [docs/how-it-works.md](docs/how-it-works.md)

## The two things in this repo

| | What it is | Runs |
|---|---|---|
| [`plugins/ticket-agent/`](plugins/ticket-agent/) | A plugin, installable in **other** repos | In the target repo, never here |
| [`apps/orchestrator/`](apps/orchestrator/) | A local app (FastAPI + React) that queues tickets and launches the plugin against a target repo | Here, on ports 8000 and 5173 |

They're independent: the plugin works on its own from any Claude Code session.
The orchestrator only adds a queue, a history and buttons.

## ticket-agent: from a work item to commits

Three stages. Each one is its own run, and **you launch it** — nothing chains
itself, so there's a place to read, correct and decide between every two.

```
        ┌─ 1 repo ──►  analyze ─────────────────────────┐
Azure   │                                               ├──►  plan  ──►  implement
DevOps ─┤                                               │    OpenSpec    commits on
        └─ 2+ repos ─►  brief ──► survey ──► consolidate┘     change     a branch
                          │         │
                          │         └── ONE session rooted in EACH repo
                          └── decides which repos are worth surveying
```

**Why the second route exists.** `--add-dir` mounts another repo's *files*, but not
its `CLAUDE.md`, its hooks or its `.mcp.json`. A single session therefore writes
every repo under the *primary* repo's conventions — confidently, with nothing to
catch it. Only a session rooted in a repo loads that repo's rules.

Both routes end in the same `docs/tickets/<id>-analysis.md`, so the later stages
never learn which one ran. The multi-repo route adds one thing no single repo could
produce: a **contract table** collating what each repo expects from the others
against what each offers — which is where mismatched endpoints, duplicated work and
the same concept under two names show up.

**It stops on a branch with commits. No push, no PR.** You decide what goes out.

## The human in the loop

Each deliverable closes with a short, bounded `## Decisiones para ti` list, so
nobody has to read 8 KB hunting for the weak spots:

- `DECIDIR` carries a proposal. Unanswered, the next stage proceeds with it **and
  writes down that it did**.
- `BLOQUEA` has no defensible default, and stops the next stage.

You answer by editing the file and ticking the box — the same convention as
`tasks.md`. The orchestrator shows the count next to each phase.

Adjusting a phase also lets you choose **a fresh session or a continuation of the
previous one**. Only you know which fits: continuing saves the exploration when
you're *adding* scope; a fresh session keeps your correction from competing with
the reasoning behind the mistake when you're *correcting*.

## Install the plugin in a project

    /plugin marketplace add jhonnygarcia/autonomous-skill-hub
    /plugin install ticket-agent@autonomous-skill-hub

Then two files in the target repo, and a restart.

- **[INSTALL.md](INSTALL.md)** — prerequisites, the marketplace, the Azure credential
  (`az login` or a PAT), and the per-project configuration.
- **[USAGE.md](USAGE.md)** — each stage with examples, answering the open decisions,
  the multi-repo route, and every configuration key.
- **[RELEASE.md](RELEASE.md)** — the optional local app, packaged: download it, run
  it, and (for me) how a release gets published.

Updating an installed copy needs the marketplace suffix, and the plugin's `version`
must have changed — it's the cache key:

    claude plugin marketplace update autonomous-skill-hub
    claude plugin update ticket-agent@autonomous-skill-hub

## Run the orchestrator

Two processes, backend first — the frontend proxies `/api` to it. Details and the
port troubleshooting are in [CLAUDE.md](CLAUDE.md).

    cd apps/orchestrator/backend && .venv/Scripts/uvicorn app:app --port 8000
    cd apps/orchestrator/frontend && npm run dev

Then open **http://localhost:5173** (not `127.0.0.1` — see CLAUDE.md).

## Plugins

| Plugin | What it does | Status |
|---|---|---|
| [ticket-agent](plugins/ticket-agent/) | Azure DevOps ticket → analysis → OpenSpec plan → commits | All three stages, multi-repo |

## License

MIT — see [LICENSE](LICENSE). Install it, fork it, take the skills apart.

## Conventions for adding a plugin

1. Folder at `plugins/<name>/` with `.claude-plugin/plugin.json` (name, description, version).
2. Skills at `skills/<name>/SKILL.md`, commands at `commands/*.md` (auto-discovered).
3. Register the plugin in `.claude-plugin/marketplace.json`.
4. `claude plugin validate .` must pass before committing.
5. Designs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
6. **Touching anything the install copies means bumping `version`** — it's the cache
   key, and there are two places to bump: `plugin.json` and the `by ticket-agent
   vX.Y.Z` stamp in the analysis template.
