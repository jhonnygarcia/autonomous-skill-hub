@echo off
rem Starts the orchestrator: one process, http://localhost:8000
rem First run creates the venv and installs; later runs skip straight to uvicorn.
setlocal
cd /d "%~dp0backend"

if not exist ".venv" (
  echo Creating the virtual environment...
  python -m venv .venv || goto :nopython
  .venv\Scripts\pip install -q -r requirements.txt || goto :fail
)

echo.
echo   Orchestrator on http://localhost:8000    (Ctrl+C to stop)
echo.
rem Never --reload: on Windows the reloader orphans children holding the port.
.venv\Scripts\uvicorn app:app --port 8000
goto :eof

:nopython
echo.
echo   Python 3.11+ was not found in the PATH. Install it and run this again.
pause
goto :eof

:fail
echo.
echo   Could not install the dependencies. Is there network access?
pause
