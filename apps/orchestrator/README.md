# Ticket Orchestrator

Local queue of Azure DevOps tickets that runs the ticket-agent flow with your
Claude Code subscription (headless CLI) against each project's repo.

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

## Start
    # Backend
    cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000

    # Frontend (another terminal)
    cd frontend && npm install && npm run dev

Open http://localhost:5173 — queue a ticket by ID, run it and follow the log.

## Tests
    cd backend && .venv/Scripts/python -m pytest tests/ -v
