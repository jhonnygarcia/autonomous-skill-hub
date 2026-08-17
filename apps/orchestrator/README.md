# Ticket Orchestrator

Local queue of Azure DevOps tickets that runs the ticket-agent flow with your
Claude Code subscription (headless CLI) against each project's repo.

## How you get it

**Not through `/plugin install`.** That installs plugins; this is an application, and
there's no marketplace for those. Two ways in:

**Download the release** — the packaged build, one process, nothing to compile.
Full instructions, including what it still needs on the machine and how to update:
[RELEASE.md](../../RELEASE.md). The short version:

1. Grab `orchestrator-vX.Y.Z.zip` from
   [Releases](https://github.com/jhonnygarcia/autonomous-skill-hub/releases).
2. Unzip it anywhere.
3. Run `run.cmd` (Windows) or `./run.sh` (macOS/Linux). First run creates the venv
   and installs three packages; later runs start straight away.
4. Open **http://localhost:8000**.

**Or clone the repo**, which is what you want if you're going to change the code:

    git clone https://github.com/jhonnygarcia/autonomous-skill-hub
    cd autonomous-skill-hub/apps/orchestrator

The zip still needs Python 3.11+ on the machine — it packages the built UI, not an
interpreter. It doesn't remove the other prerequisites either (Claude Code logged in,
Node with `npx`, an Azure credential): those are what the app *drives*, and no
packaging can make them optional.

The plugin and the app are independent. **The plugin doesn't need this** — it works
from any Claude Code session ([INSTALL.md](../../INSTALL.md),
[USAGE.md](../../USAGE.md)). This only adds a queue, a history, and buttons instead
of typing the commands. And it needs the plugin installed **in each target repo**
anyway: the app doesn't contain the agent, it launches it.

**What it is, so nobody deploys it by mistake:** one process on your own machine,
bound to localhost, no authentication, no users, SQLite in a file next to the code.
It runs `claude -p` with *your* logged-in session, so it can only ever work where
that session lives. Putting it on a shared server would hand everyone with the URL
your Claude subscription and write access to your repos. Run it locally.

## Requirements
- Python 3.11+, Node 20+
- Claude Code CLI logged in (`claude` in the PATH)
- Each target repo with the ticket-agent plugin installed and configured

## Subscription, not API key
The orchestrator runs `claude -p` (headless CLI), which authenticates with your
subscription session (Claude Code's `/login`) — it never uses `ANTHROPIC_API_KEY`
anywhere. On top of that, the runner **removes** `ANTHROPIC_API_KEY` and
`ANTHROPIC_AUTH_TOKEN` from the subprocess environment: even if they exist on
your machine for other projects, runs will never bill through the API.

To verify your session: `claude -p "say OK"` in a terminal without
`ANTHROPIC_API_KEY` set should respond without asking for credentials.

## Configure
Projects are registered **from the UI** (the *Projects* card) and live in the
DB. For each one: `name` (local label), Azure DevOps `org` and `project`,
`repoPath` (the primary repo — where the agent runs and where the analysis is
written) and, optionally, `extraDirs`: sibling repos the ticket needs to
**read** but that are outside the primary one (e.g. the backend, or the cloned
wiki). Each `extraDir` is mounted with `--add-dir`.

Paths are validated on save: if they don't exist, the registration fails with
a 400 instead of blowing up later inside the subprocess.

## Archive of deliverables

Off by default. Set a directory in Settings (the *Archive* card, `GET/PUT /archivo`)
and every run starts snapshotting what it consumed and what it produced — an empty
directory turns it back off.

Each run writes to
`<archive_dir>/<org>/<project>/<key>/<run_id>-<phase>-<YYYYMMDD-HHMM>/`:

- `entrada/` — taken at launch: every `docs/tickets/<key>-*` file, plus any directory
  a previous good run of this ticket declared (so the human's ticked `DECIDIR` boxes
  aren't lost even if nothing else changed).
- `salida/` — taken at close, after the journal line, so the copy already carries this
  run's entry: the deliverable the phase declared, the request file, and the journal.
- `run.json` — enough to identify the folder (ticket, run, phase, timestamp) if the
  database is ever wiped.

The deliverable is resolved against the primary repo **and** the ticket's extra
repos, in that order — the same roots the artifact viewer already checks — since a
phase can leave its output in a mounted repo instead of the primary one.

A tree above a fixed file/byte cap is skipped with a note in the journal instead of
being copied, and the copy stops counting the moment either cap is crossed rather
than walking the whole tree first — that's what keeps a `docs`-wide artifact from
archiving (and re-scanning) the whole folder on every run. A copy that fails is also
just a journal note: it never turns a successful run into an error.

Not every run with an `archive_path` can actually be restored in one click. A
fan-out `survey` archives its request and journal, but its declared "path" is a
scratch folder outside every repo, so its `salida/` never holds anything to put back.
And a deliverable that lives in a mounted repo, not the primary one, IS archived —
that's still a real backup — but restoring writes into `repo_path` only, so putting
it back through the one-click button would silently drop another repo's file into
the wrong repo. Each run carries a `restorable` flag, checked once at close against
which root the deliverable actually came from, and only a run with `restorable` set
offers a Restore button — `POST /tickets/{tid}/restaurar` itself refuses a non-
restorable run too, not just the button.

**Restoring is never automatic.** The archive is a record — nothing reads it to decide
anything, and a run started after the archive folder was deleted still produces its
own deliverable and its own stamp. The only way back is a human action: a *Restore*
button next to a run in the ticket's history, or on the timeline when the declared
artifact is missing from disk (`POST /tickets/{tid}/restaurar {run_id, overwrite}`).
It copies that run's `salida/` back into the repo, refuses while a run is active, and
never overwrites a directory — overwriting a single file needs `overwrite: true`. The
one refusal that's safe to retry that way (an existing file, no `overwrite`) comes
back tagged with a machine-readable code instead of prose, so the UI's retry can't be
tricked by a ticket whose own path happens to contain a word from the message.

## Start

From the release zip it's one command — `run.cmd` / `./run.sh` — and one URL,
http://localhost:8000, because the backend serves the built UI itself. The rest of
this section is **developing on the source**, where the UI is rebuilt on save.

Two processes, two terminals, **backend first** — the frontend proxies `/api` to it,
and a Vite started against a dead backend just serves a UI whose every request fails.
The `python -m venv` and `npm install` lines are first run only.

    # Backend — Windows
    cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000

    # Backend — macOS / Linux
    cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/uvicorn app:app --port 8000

    # Frontend (another terminal, either platform)
    cd frontend && npm install && npm run dev

Open **http://localhost:5173** — queue a ticket by ID, run it and follow the log.

Two things that will cost you an hour otherwise, both Windows-specific:

- **Use `localhost`, not `127.0.0.1`.** Vite binds to `::1` and uvicorn to
  `127.0.0.1`, so `http://127.0.0.1:5173` refuses the connection while `localhost`
  works. The dev proxy is fine either way — it reaches the backend server-side.
- **Never `uvicorn --reload`.** The reloader leaves orphaned children holding port
  8000, and the backend keeps serving stale code with no warning. When something
  behaves oddly, suspect the process before the code.

## Tests
    cd backend && .venv/Scripts/python -m pytest tests/ -v    # Windows
    cd backend && .venv/bin/python -m pytest tests/ -v        # macOS / Linux
