# Autonomous Skill Hub

Personal marketplace of Claude Code plugins. Each plugin packages real
experience as skills, commands, agents and hooks, installable in any project.

**Project status** (what's done, what's missing, decisions): [docs/STATUS.md](docs/STATUS.md)

## Install in a project

    /plugin marketplace add <url-or-path-to-this-repo>
    /plugin install ticket-agent@autonomous-skill-hub

## Plugins

| Plugin | What it does | Status |
|---|---|---|
| [ticket-agent](plugins/ticket-agent/) | Understands Azure DevOps tickets → structured analysis | Phase 1 |

## Conventions for adding a plugin

1. Folder at `plugins/<name>/` with `.claude-plugin/plugin.json` (name, description, version).
2. Skills at `skills/<name>/SKILL.md`, commands at `commands/*.md` (auto-discovered).
3. Register the plugin in `.claude-plugin/marketplace.json`.
4. `claude plugin validate .` must pass before committing.
5. Designs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`.
