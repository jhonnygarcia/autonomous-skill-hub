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
Los proyectos se dan de alta **desde la UI** (tarjeta *Proyectos*) y viven en la
BD. Por cada uno: `name` (etiqueta local), `org` y `project` de Azure DevOps,
`repoPath` (el repo primario — ahí corre el agente y ahí se escribe el análisis)
y, opcionalmente, `extraDirs`: repos hermanos que el ticket necesita **leer**
pero que están fuera del primario (p. ej. el backend, o la wiki clonada). Cada
`extraDir` se monta con `--add-dir`.

Las rutas se validan al guardar: si no existen, el alta falla con un 400 en vez
de reventar después dentro del subproceso.

## Arrancar
    # Backend
    cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/uvicorn app:app --port 8000

    # Frontend (otra terminal)
    cd frontend && npm install && npm run dev

Abre http://localhost:5173 — encola un ticket por ID, córrelo y sigue el log.

## Tests
    cd backend && .venv/Scripts/python -m pytest tests/ -v
