# Ticket Orchestrator

Cola local de tickets de Azure DevOps que corre el flujo del ticket-agent con tu
suscripción de Claude Code (CLI headless) sobre el repo de cada proyecto.

## Requisitos
- Python 3.11+, Node 20+
- Claude Code CLI logueado (`claude` en el PATH)
- Cada repo destino con el plugin ticket-agent instalado y configurado

## Suscripción, no API key
El orquestador corre `claude -p` (CLI headless), que se autentica con la sesión
de tu suscripción (el `/login` de Claude Code) — no usa `ANTHROPIC_API_KEY` en
ninguna parte. Además, el runner **elimina** `ANTHROPIC_API_KEY` y
`ANTHROPIC_AUTH_TOKEN` del entorno del subproceso: aunque existan en tu máquina
por otros proyectos, las corridas jamás facturarán por API.

Para verificar tu sesión: `claude -p "di OK"` en una terminal sin
`ANTHROPIC_API_KEY` definida debe responder sin pedir credenciales.

## Configurar
Edita `orchestrator.config.json` con tus proyectos: `name`, `org`, `project`
y `repoPath` (ruta local del clon).

## Arrancar
    # Backend
    cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000

    # Frontend (otra terminal)
    cd frontend && npm install && npm run dev

Abre http://localhost:5173 — encola un ticket por ID, córrelo y sigue el log.

## Tests
    cd backend && .venv/Scripts/python -m pytest tests/ -v
