# Releases: downloading the app, and publishing one

Two audiences, one page. The first half is for whoever **downloads** the packaged
orchestrator; the second is for whoever **publishes** it.

**First, the thing worth being clear about: you probably don't need a release at
all.** The plugin — the part that actually reads tickets and writes code — installs
from the marketplace and downloads nothing:

    /plugin marketplace add jhonnygarcia/autonomous-skill-hub
    /plugin install ticket-agent@autonomous-skill-hub

See [INSTALL.md](INSTALL.md). Releases exist only for the **optional local app**: a
queue, a history and a button per stage over that same plugin.

---

# Part 1 · Running a release

## Download and run

1. Grab `orchestrator-vX.Y.Z.zip` from
   [Releases](https://github.com/jhonnygarcia/autonomous-skill-hub/releases).
2. Unzip it anywhere you like — it's self-contained and writes only inside its own
   folder.
3. Start it:

       run.cmd            # Windows: double-click, or from a terminal
       ./run.sh           # macOS / Linux

4. Open **http://localhost:8000**.

The first start creates a virtual environment and installs three Python packages,
which takes a few seconds; every start after that goes straight to the server. Stop
it with `Ctrl+C`.

## What's in the zip

    orchestrator/
      run.cmd  run.sh        the launcher
      backend/
        app.py               the whole server: API, runner, SQLite
        requirements.txt
        hooks/               the hook that denies push/PR during implement
      frontend/dist/         the built UI — no Node needed to run it
      README.md              the app's own documentation
      INSTALL.md  USAGE.md   plugin setup and day-to-day use
      LICENSE

No sources for the frontend, no `.venv`, no database, no logs: those appear next to
`app.py` the first time you run it.

## What it still needs on the machine

Packaging removes the build, not the prerequisites. The app's whole job is to drive
tools that live on your machine, so those have to be there:

| Needed | Why | Check |
|---|---|---|
| **Python 3.11+** | the zip ships the built UI, not an interpreter | `python --version` |
| **Claude Code CLI, logged in** | the app runs `claude -p`; it has no model of its own | `claude -p "say OK"` |
| **Node 20+ with `npx`** | the Azure DevOps MCP server and the OpenSpec CLI | `npx --version` |
| **An Azure DevOps credential** | `az login` or a PAT | [INSTALL.md, step 3](INSTALL.md#step-3--pick-how-it-authenticates) |
| **The plugin, in each target repo** | the app launches it; it doesn't contain it | `claude plugin list` |

That last row is the one people miss: **the release contains no agent.** Register a
project in the UI pointing at a repo with no `.claude/ticket-agent.json` and every
run fails — the UI can't tell, because the UI never had the authority. Configure the
repo first ([INSTALL.md, step 4](INSTALL.md#step-4--point-it-at-your-project)).

## Where it puts things

Everything the app owns lives inside the unzipped folder:

    backend/orchestrator.db    projects, tickets, runs
    backend/logs/<run_id>.log  one log per run
    backend/.venv/             created on first start

Everything the *agent* produces is written in your own repos — analyses, plans,
commits. Deleting the folder deletes the queue and its history, nothing else.

## Updating, and going back

Unzip the new version and copy `backend/orchestrator.db` over from the old folder to
keep your projects and history — or don't, and start clean. There's no installer and
no registry entry to leave behind; deleting the folder is a complete uninstall.

Nothing auto-updates. Watch
[Releases](https://github.com/jhonnygarcia/autonomous-skill-hub/releases) if you
care, or just re-download when something you want lands.

## When it doesn't start

| Symptom | What it is |
|---|---|
| "Python 3.11+ was not found" | Python isn't on the PATH. On Windows, reinstall ticking *Add to PATH* |
| the install step fails | no network access to PyPI — it needs it once, on first start |
| port 8000 is busy | something else holds it. `Get-NetTCPConnection -LocalPort 8000 -State Listen` (PowerShell) |
| the page loads but every run errors | the plugin isn't installed or configured **in the target repo** |
| `127.0.0.1:8000` refuses the connection | use `localhost` — see the app's README |

---

# Part 2 · Publishing a release

For the maintainer. The whole pipeline is
[`.github/workflows/release.yml`](.github/workflows/release.yml); this is when and
how to fire it.

## Cutting one

    git tag v0.9.1
    git push origin v0.9.1

That's it. Pushing a tag matching `v*` triggers the workflow, which:

1. builds the UI (`npm ci && npm run build`),
2. **runs the backend test suite** — a release that doesn't pass tests never gets
   published, which is the point of putting the tests there and not only locally,
3. assembles the zip in the layout above,
4. publishes it to Releases with auto-generated notes.

Failed build? Fix, then re-run from the Actions tab (`workflow_dispatch`) instead of
moving the tag. A tag that has already been public and then points somewhere else is
a tag nobody can trust.

## What the version number means

The tag is the **app's** version. The plugin has its own, in
`plugins/ticket-agent/.claude-plugin/plugin.json`, and it's a different thing on a
different clock: the plugin updates through the marketplace, without any release.
They happen to match today; nothing enforces it and nothing should.

Before tagging, check the plugin's own rule if you touched it: **bumping `version`
means bumping it in two places** — `plugin.json` and the `by ticket-agent vX.Y.Z`
stamp in the analysis and brief templates. A stamp that lies is worse than no stamp.

## The layout is load-bearing

The zip reproduces `backend/` and `frontend/dist/` as siblings because `app.py`
resolves the UI as `BASE.parent / "frontend" / "dist"`. Rearranging the zip without
touching that line ships a package that starts, serves the API, and answers `404` at
`/` — a failure that looks like a broken build and isn't.

Same reason the `/api` prefix is stripped by middleware in `app.py`: in development
Vite strips it, in a release nothing does. It's covered by
`test_api_prefix_is_stripped`, so it can't be deleted quietly.

## What's deliberately not there

- **No compiled binary.** A PyInstaller `.exe` would remove Python from the
  prerequisite list and add per-OS builds, antivirus false positives and opaque
  debugging — while Claude Code, Node and the Azure credential stay mandatory
  regardless. It buys the smallest item on the list at the highest price.
- **No gitflow branches.** One maintainer, one `main`, tags for releases. `develop`
  and `release/*` are coordination tools for a team that has to coordinate.
- **No auto-update.** The app runs your Claude session against your repos; it
  shouldn't rewrite itself behind your back.
