#!/usr/bin/env sh
# Starts the orchestrator: one process, http://localhost:8000
# First run creates the venv and installs; later runs skip straight to uvicorn.
set -e
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo "Creating the virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo
echo "  Orchestrator on http://localhost:8000    (Ctrl+C to stop)"
echo
exec .venv/bin/uvicorn app:app --port 8000
