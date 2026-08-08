# Ticket Orchestrator

Cola local de tickets de Azure DevOps que corre el flujo del ticket-agent con tu
suscripción de Claude Code (CLI headless) sobre el repo de cada proyecto.

## Requisitos
- Python 3.11+, Node 20+
- Claude Code CLI logueado (`claude` en el PATH)
- Cada repo destino con el plugin ticket-agent instalado y configurado

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
