# Orquestador local de tickets — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App local en `apps/orchestrator/` que encola tickets de Azure DevOps por ID, corre el análisis del ticket-agent con Claude Code (suscripción local) sobre el repo del proyecto, y muestra workflow, historial de corridas y logs en una UI React.

**Architecture:** Backend FastAPI + SQLite (stdlib) que lanza `claude -p` como subproceso (headless, `--output-format stream-json`) con `cwd` en el repo destino; la salida se escribe a un log por corrida. Frontend Vite + React + TS + Tailwind v4 + shadcn/ui, una página con polling. Un ticket corre a la vez (lock global asyncio).

**Tech Stack:** Python 3.11+ · FastAPI · uvicorn · pytest · sqlite3 stdlib · Claude Code CLI (logueado) · Vite + React 18 + TypeScript · Tailwind v4 · shadcn/ui.

## Global Constraints

- **Ejecución con suscripción local vía CLI headless** (`claude -p`), NO el Agent SDK (requiere API key — desviación registrada en el spec).
- **Un ticket corre a la vez**: `asyncio.Lock` global; corridas extra quedan `queued`.
- **Sin secretos en archivos committeables.** `orchestrator.config.json` solo tiene nombres/rutas.
- El análisis vive en el repo del proyecto (`docs/tickets/<id>-analysis.md`); el orquestador guarda solo estado y logs.
- DB y logs no se commitean (`.gitignore`).
- Tests: pytest sobre la API con un **claude falso** (script Python vía `ORCH_CLAUDE_CMD`); el frontend se valida con `npm run build` + prueba manual.
- Entorno destino: Windows (rutas con `Path`, `shutil.which` para resolver `claude`).

## File Structure

```
apps/orchestrator/
├── orchestrator.config.json      # proyectos: name/org/project/repoPath (Task 1)
├── backend/
│   ├── requirements.txt          # (Task 1)
│   ├── app.py                    # FastAPI + DB + runner, un solo módulo (Tasks 1-3)
│   ├── logs/                     # <run_id>.log (gitignored)
│   └── tests/
│       ├── conftest.py           # (Task 1)
│       ├── fake_claude.py        # (Task 3)
│       └── test_app.py           # (Tasks 1-3)
└── frontend/                     # Vite + React + Tailwind + shadcn (Tasks 4-5)
```

---

### Task 1: Scaffold del backend, config y base de datos

**Files:**
- Create: `apps/orchestrator/orchestrator.config.json`
- Create: `apps/orchestrator/backend/requirements.txt`
- Create: `apps/orchestrator/backend/app.py` (config + DB; endpoints llegan en Task 2)
- Create: `apps/orchestrator/backend/tests/conftest.py`
- Create: `apps/orchestrator/backend/tests/test_app.py`
- Modify: `.gitignore` (raíz del repo; crear si no existe)

**Interfaces:**
- Produces: módulo `app` con `init_db()`, `db()`, `load_config()`, tablas `tickets` y `runs` — Tasks 2-3 los consumen. Env vars de override: `ORCH_DB`, `ORCH_LOGS`, `ORCH_CONFIG`, `ORCH_CLAUDE_CMD`.

- [x] **Step 1: Crear `orchestrator.config.json`**

```json
{
  "projects": [
    {
      "name": "ProvidenceTMS",
      "org": "ProvidenceSolutions",
      "project": "ProvidenceTMS",
      "repoPath": "D:/RUTA/AL/REPO/ProvidenceTMS"
    }
  ]
}
```

(Jhonny ajusta `repoPath` a la ruta real del clon del TMS.)

- [x] **Step 2: Crear `requirements.txt`**

```
fastapi
uvicorn[standard]
httpx
pytest
```

- [x] **Step 3: Crear `app.py` con config + DB**

```python
import asyncio
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ORCH_DB", BASE / "orchestrator.db"))
LOGS_DIR = Path(os.environ.get("ORCH_LOGS", BASE / "logs"))
CONFIG_PATH = Path(os.environ.get("ORCH_CONFIG", BASE.parent / "orchestrator.config.json"))

PHASES = ["analyze", "design", "implement", "test", "guards", "pr"]  # v1: solo analyze ejecutable


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_project(name: str) -> dict | None:
    return next((p for p in load_config()["projects"] if p["name"] == name), None)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ado_id INTEGER NOT NULL,
              org TEXT NOT NULL,
              project TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              current_phase TEXT NOT NULL DEFAULT 'analyze',
              status TEXT NOT NULL DEFAULT 'queued',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
              phase TEXT NOT NULL,
              instructions TEXT,
              status TEXT NOT NULL DEFAULT 'queued',
              log_path TEXT,
              started_at TEXT,
              finished_at TEXT
            );
            """
        )


app = FastAPI(title="ticket-orchestrator")
init_db()
```

- [x] **Step 4: Escribir el test de DB (falla aún: faltan endpoints, pero la DB debe funcionar)**

`tests/conftest.py`:

```python
import os
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
BACKEND = TESTS.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    config = tmp_path / "config.json"
    config.write_text(
        '{"projects": [{"name": "Demo", "org": "DemoOrg", "project": "Demo", '
        f'"repoPath": "{(tmp_path / "repo").as_posix()}"}}]}}',
        encoding="utf-8",
    )
    (tmp_path / "repo").mkdir()
    monkeypatch.setenv("ORCH_CONFIG", str(config))
    sys.path.insert(0, str(BACKEND))
    for mod in list(sys.modules):
        if mod == "app":
            del sys.modules[mod]
    import app as app_module  # noqa: E402

    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c
```

`tests/test_app.py` (primer test):

```python
def test_db_tables_created(client):
    import app

    with app.db() as c:
        names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tickets", "runs"} <= names
```

- [x] **Step 5: Correr el test**

Run: `cd apps/orchestrator/backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/python -m pytest tests/ -v`
Expected: PASS (1 test).

- [x] **Step 6: Actualizar `.gitignore` (raíz)**

```
apps/orchestrator/backend/.venv/
apps/orchestrator/backend/orchestrator.db
apps/orchestrator/backend/logs/
apps/orchestrator/frontend/node_modules/
apps/orchestrator/frontend/dist/
__pycache__/
```

- [x] **Step 7: Commit**

```bash
git add apps .gitignore
git commit -m "feat(orchestrator): scaffold backend con config y SQLite"
```

---

### Task 2: Endpoints CRUD de tickets

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (agregar endpoints)
- Modify: `apps/orchestrator/backend/tests/test_app.py` (agregar tests)

**Interfaces:**
- Consumes: `db()`, `get_project()`, `PHASES` de Task 1.
- Produces: `GET /projects` · `POST /tickets {ado_id, project}` → ticket · `GET /tickets` → lista · `GET /tickets/{id}` → `{ticket, runs, log_tail}` · `DELETE /tickets/{id}`. La Task 5 (UI) consume exactamente estas rutas.

- [x] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_app.py`:

```python
def test_create_and_list_ticket(client):
    r = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"})
    assert r.status_code == 201
    t = r.json()
    assert t["ado_id"] == 3311 and t["status"] == "queued" and t["current_phase"] == "analyze"
    assert client.get("/tickets").json()[0]["id"] == t["id"]


def test_create_ticket_unknown_project(client):
    assert client.post("/tickets", json={"ado_id": 1, "project": "Nope"}).status_code == 400


def test_get_ticket_detail_and_delete(client):
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["id"] == tid and detail["runs"] == [] and detail["log_tail"] == ""
    assert client.delete(f"/tickets/{tid}").status_code == 204
    assert client.get(f"/tickets/{tid}").status_code == 404


def test_projects_endpoint(client):
    assert client.get("/projects").json() == [{"name": "Demo", "org": "DemoOrg", "project": "Demo"}]
```

- [x] **Step 2: Correr y ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: FAIL (404 en las rutas nuevas).

- [x] **Step 3: Implementar los endpoints en `app.py`**

```python
class TicketIn(BaseModel):
    ado_id: int
    project: str


class RunIn(BaseModel):
    instructions: str | None = None


def ticket_row(tid: int) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()


@app.get("/projects")
def projects():
    return [{"name": p["name"], "org": p["org"], "project": p["project"]}
            for p in load_config()["projects"]]


@app.post("/tickets", status_code=201)
def create_ticket(body: TicketIn):
    proj = get_project(body.project)
    if not proj:
        raise HTTPException(400, f"Proyecto '{body.project}' no está en orchestrator.config.json")
    ts = now()
    with db() as c:
        cur = c.execute(
            "INSERT INTO tickets(ado_id, org, project, repo_path, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (body.ado_id, proj["org"], proj["project"], proj["repoPath"], ts, ts),
        )
    return dict(ticket_row(cur.lastrowid))


@app.get("/tickets")
def list_tickets():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM tickets ORDER BY id DESC")]


@app.get("/tickets/{tid}")
def get_ticket(tid: int):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM runs WHERE ticket_id=? ORDER BY id DESC", (tid,))]
    tail = ""
    if runs and runs[0]["log_path"] and Path(runs[0]["log_path"]).exists():
        tail = Path(runs[0]["log_path"]).read_text(encoding="utf-8", errors="replace")[-8000:]
    return {"ticket": dict(t), "runs": runs, "log_tail": tail}


@app.delete("/tickets/{tid}", status_code=204)
def delete_ticket(tid: int):
    if not ticket_row(tid):
        raise HTTPException(404)
    with db() as c:
        for r in c.execute("SELECT log_path FROM runs WHERE ticket_id=?", (tid,)):
            if r["log_path"]:
                Path(r["log_path"]).unlink(missing_ok=True)
        c.execute("DELETE FROM tickets WHERE id=?", (tid,))
```

- [x] **Step 4: Correr los tests**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS (5 tests).

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/backend
git commit -m "feat(orchestrator): CRUD de tickets y endpoint de proyectos"
```

---

### Task 3: Runner headless de Claude Code y endpoint de corridas

**Files:**
- Modify: `apps/orchestrator/backend/app.py`
- Create: `apps/orchestrator/backend/tests/fake_claude.py`
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: tablas y endpoints previos; env `ORCH_CLAUDE_CMD` (JSON array con el prefijo del comando; default `["claude"]` resuelto con `shutil.which`).
- Produces: `POST /tickets/{id}/run {instructions?}` → 202 con el run creado; estados de run `queued→running→success|error`; ticket `running→analyzed|error`; log en `LOGS_DIR/<run_id>.log`. Re-trabajo = misma ruta con `instructions`.

- [x] **Step 1: Crear `tests/fake_claude.py`**

```python
"""Sustituto de `claude -p` para tests: imprime sus args y respeta FAKE_FAIL."""
import os
import sys

print("FAKE-CLAUDE ARGS:", " ".join(sys.argv[1:]))
print('{"type":"assistant","text":"analizando..."}')
if os.environ.get("FAKE_FAIL") == "1":
    print("boom", file=sys.stderr)
    sys.exit(1)
print('{"type":"result","subtype":"success"}')
```

- [x] **Step 2: Escribir los tests que fallan**

Agregar a `tests/test_app.py`:

```python
import json
import os
import sys
from pathlib import Path


def _use_fake_claude(monkeypatch, fail=False):
    fake = Path(__file__).parent / "fake_claude.py"
    monkeypatch.setenv("ORCH_CLAUDE_CMD", json.dumps([sys.executable, str(fake)]))
    monkeypatch.setenv("FAKE_FAIL", "1" if fail else "0")


def test_run_success_writes_log_and_states(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202
    detail = client.get(f"/tickets/{tid}").json()  # TestClient corre el background task antes
    assert detail["ticket"]["status"] == "analyzed"
    run = detail["runs"][0]
    assert run["status"] == "success" and run["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_run_error_state(client, monkeypatch):
    _use_fake_claude(monkeypatch, fail=True)
    tid = client.post("/tickets", json={"ado_id": 8, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "error"
    assert detail["runs"][0]["status"] == "error"


def test_rework_passes_instructions(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"instructions": "no consideraste el parent"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "no consideraste el parent" in detail["log_tail"]
    assert detail["runs"][0]["instructions"] == "no consideraste el parent"


def test_run_conflict_when_active(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 10, "project": "Demo"}).json()["id"]
    import app

    with app.db() as c:
        c.execute(
            "INSERT INTO runs(ticket_id, phase, status) VALUES(?, 'analyze', 'running')", (tid,)
        )
    assert client.post(f"/tickets/{tid}/run", json={}).status_code == 409
```

- [x] **Step 3: Correr y ver que fallan**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: FAIL (404 en `/run`).

- [x] **Step 4: Implementar el runner en `app.py`**

```python
RUN_LOCK = asyncio.Lock()


def claude_cmd() -> list[str]:
    raw = os.environ.get("ORCH_CLAUDE_CMD")
    if raw:
        return json.loads(raw)
    exe = shutil.which("claude")
    if not exe:
        raise HTTPException(500, "No se encontró el CLI 'claude' en el PATH")
    return [exe]


def set_run(run_id: int, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def set_ticket(tid: int, **fields):
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE tickets SET {cols} WHERE id=?", (*fields.values(), tid))


async def execute_run(run_id: int, ticket: dict, instructions: str | None):
    async with RUN_LOCK:  # ponytail: lock global; por-repo si algún día duele
        log_path = LOGS_DIR / f"{run_id}.log"
        set_run(run_id, status="running", log_path=str(log_path), started_at=now())
        set_ticket(ticket["id"], status="running")
        prompt = f"/ticket-agent:analyze {ticket['ado_id']}"
        if instructions:
            prompt += (
                "\n\nInstrucciones de ajuste del usuario para re-trabajar el análisis "
                f"(aplícalas y regenera el archivo): {instructions}"
            )
        cmd = claude_cmd() + [
            "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits",
        ]
        ok = False
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                log.write(f"$ {' '.join(cmd)}\n\n")
                log.flush()
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=ticket["repo_path"],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None
                async for line in proc.stdout:
                    log.write(line.decode("utf-8", errors="replace"))
                    log.flush()
                ok = (await proc.wait()) == 0
        except Exception as exc:  # el error queda en el log, jamás tumba el server
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[orchestrator] excepción: {exc}\n")
        set_run(run_id, status="success" if ok else "error", finished_at=now())
        set_ticket(ticket["id"], status="analyzed" if ok else "error")


@app.post("/tickets/{tid}/run", status_code=202)
def run_ticket(tid: int, body: RunIn, background: BackgroundTasks):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        active = c.execute(
            "SELECT 1 FROM runs WHERE ticket_id=? AND status IN ('queued','running')", (tid,)
        ).fetchone()
    if active:
        raise HTTPException(409, "Este ticket ya tiene una corrida activa")
    with db() as c:
        cur = c.execute(
            "INSERT INTO runs(ticket_id, phase, instructions, status) VALUES(?,?,?,'queued')",
            (tid, "analyze", body.instructions),
        )
    run_id = cur.lastrowid
    set_ticket(tid, status="queued")
    background.add_task(execute_run, run_id, dict(t), body.instructions)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
```

- [x] **Step 5: Correr los tests**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS (9 tests).

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend
git commit -m "feat(orchestrator): runner headless de Claude Code con lock, logs y re-trabajo"
```

---

### Task 4: Scaffold del frontend (Vite + Tailwind v4 + shadcn/ui)

**Files:**
- Create: `apps/orchestrator/frontend/` (generado por Vite) con `vite.config.ts` (proxy + Tailwind), `src/index.css`, alias `@/`.

**Interfaces:**
- Produces: proyecto React TS que compila con `npm run build`; proxy `/api` → `http://127.0.0.1:8000`; componentes shadcn `button card badge input textarea` disponibles. Task 5 escribe la UI encima.

- [x] **Step 1: Generar el proyecto y dependencias**

```bash
cd apps/orchestrator
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install tailwindcss @tailwindcss/vite
```

- [x] **Step 2: Configurar Vite (Tailwind + proxy + alias)** — reemplazar `vite.config.ts`:

```ts
import path from "node:path"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", rewrite: p => p.replace(/^\/api/, "") } } },
})
```

Reemplazar el contenido de `src/index.css` por:

```css
@import "tailwindcss";
```

En `tsconfig.json` y `tsconfig.app.json`, dentro de `compilerOptions`, agregar:

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

- [x] **Step 3: Inicializar shadcn/ui y componentes**

```bash
npx shadcn@latest init -d
npx shadcn@latest add button card badge input textarea
```

(`-d` acepta defaults; si pregunta el color base, elegir `neutral`.)

- [x] **Step 4: Verificar build**

Run: `npm run build`
Expected: build exitoso sin errores de TypeScript.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/frontend
git commit -m "feat(orchestrator): scaffold frontend Vite + Tailwind v4 + shadcn/ui"
```

---

### Task 5: UI del orquestador

**Files:**
- Create: `apps/orchestrator/frontend/src/api.ts`
- Modify: `apps/orchestrator/frontend/src/App.tsx` (reemplazo total)
- Delete: `apps/orchestrator/frontend/src/App.css`

**Interfaces:**
- Consumes: la API de Tasks 2-3 vía proxy `/api`; componentes shadcn de Task 4.
- Produces: página única — encolar (ID + proyecto), cola con stepper de 6 fases, detalle con historial/log/ajustar-y-recorrer/borrar, polling cada 3 s.

- [x] **Step 1: Crear `src/api.ts`**

```ts
export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  current_phase: string; status: string; created_at: string; updated_at: string
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
}
export type TicketDetail = { ticket: Ticket; runs: Run[]; log_tail: string }
export type Project = { name: string; org: string; project: string }

const json = async <T,>(r: Response): Promise<T> => {
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? r.statusText)
  return r.status === 204 ? (undefined as T) : r.json()
}

export const api = {
  projects: () => fetch("/api/projects").then(r => json<Project[]>(r)),
  tickets: () => fetch("/api/tickets").then(r => json<Ticket[]>(r)),
  detail: (id: number) => fetch(`/api/tickets/${id}`).then(r => json<TicketDetail>(r)),
  create: (ado_id: number, project: string) =>
    fetch("/api/tickets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ado_id, project }),
    }).then(r => json<Ticket>(r)),
  run: (id: number, instructions?: string) =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null }),
    }).then(r => json<Run>(r)),
  remove: (id: number) => fetch(`/api/tickets/${id}`, { method: "DELETE" }).then(r => json<void>(r)),
}
```

- [x] **Step 2: Reemplazar `src/App.tsx`**

```tsx
import { useEffect, useState } from "react"
import { api, type Project, type Ticket, type TicketDetail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

const PHASES = [
  { key: "analyze", label: "Análisis" }, { key: "design", label: "Diseño" },
  { key: "implement", label: "Implementación" }, { key: "test", label: "Pruebas" },
  { key: "guards", label: "Guards" }, { key: "pr", label: "PR" },
]
const STATUS_COLOR: Record<string, string> = {
  queued: "bg-amber-100 text-amber-800", running: "bg-blue-100 text-blue-800",
  analyzed: "bg-green-100 text-green-800", error: "bg-red-100 text-red-800",
  success: "bg-green-100 text-green-800",
}

function Stepper({ ticket }: { ticket: Ticket }) {
  return (
    <div className="flex items-center gap-1 text-xs">
      {PHASES.map((p, i) => {
        const active = p.key === ticket.current_phase
        const done = active && ticket.status === "analyzed"
        const enabled = i === 0
        return (
          <div key={p.key} className="flex items-center gap-1">
            {i > 0 && <span className="text-gray-300">→</span>}
            <span className={
              done ? "rounded-full bg-green-600 px-2 py-0.5 text-white"
                : active ? "rounded-full bg-blue-600 px-2 py-0.5 text-white"
                : enabled ? "rounded-full bg-gray-200 px-2 py-0.5 text-gray-700"
                : "rounded-full bg-gray-100 px-2 py-0.5 text-gray-400"
            } title={enabled ? p.label : `${p.label} (próximamente)`}>
              {p.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [adoId, setAdoId] = useState("")
  const [project, setProject] = useState("")
  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [instructions, setInstructions] = useState("")
  const [error, setError] = useState("")

  const refresh = () => {
    api.tickets().then(setTickets).catch(e => setError(String(e)))
    if (selected != null) api.detail(selected).then(setDetail).catch(() => setDetail(null))
  }

  useEffect(() => {
    api.projects().then(ps => { setProjects(ps); if (ps[0]) setProject(ps[0].name) })
  }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [selected])

  const enqueue = async () => {
    setError("")
    try {
      const t = await api.create(Number(adoId), project)
      setAdoId(""); setSelected(t.id); refresh()
    } catch (e) { setError(String(e)) }
  }
  const act = (fn: () => Promise<unknown>) => fn().then(refresh).catch(e => setError(String(e)))

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">Ticket Orchestrator</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <CardHeader><CardTitle className="text-base">Encolar ticket</CardTitle></CardHeader>
        <CardContent className="flex gap-2">
          <Input className="w-32" placeholder="ID (ej. 3311)" value={adoId}
                 onChange={e => setAdoId(e.target.value)} />
          <select className="rounded-md border px-2 text-sm" value={project}
                  onChange={e => setProject(e.target.value)}>
            {projects.map(p => <option key={p.name}>{p.name}</option>)}
          </select>
          <Button onClick={enqueue} disabled={!adoId || !project}>Agregar</Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          {tickets.map(t => (
            <Card key={t.id} onClick={() => setSelected(t.id)}
                  className={`cursor-pointer ${selected === t.id ? "border-blue-500" : ""}`}>
              <CardContent className="space-y-2 pt-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">#{t.ado_id} · {t.project}</span>
                  <Badge className={STATUS_COLOR[t.status] ?? ""}>{t.status}</Badge>
                </div>
                <Stepper ticket={t} />
              </CardContent>
            </Card>
          ))}
          {tickets.length === 0 && <p className="text-sm text-gray-500">Sin tickets en cola.</p>}
        </div>

        {detail && (
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base">Ticket #{detail.ticket.ado_id}</CardTitle>
              <div className="flex gap-2">
                <Button size="sm" disabled={["queued", "running"].includes(detail.ticket.status)}
                        onClick={() => act(() => api.run(detail.ticket.id))}>
                  {detail.runs.length ? "Re-correr análisis" : "Correr análisis"}
                </Button>
                <Button size="sm" variant="destructive"
                        onClick={() => act(() => api.remove(detail.ticket.id)).then(() => setSelected(null))}>
                  Borrar
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="mb-1 text-sm font-medium">Ajustar y re-correr</p>
                <Textarea rows={2} placeholder="Describe el problema o ajuste…"
                          value={instructions} onChange={e => setInstructions(e.target.value)} />
                <Button size="sm" className="mt-2"
                        disabled={!instructions || ["queued", "running"].includes(detail.ticket.status)}
                        onClick={() => act(() => api.run(detail.ticket.id, instructions)).then(() => setInstructions(""))}>
                  Enviar ajuste
                </Button>
              </div>
              <div>
                <p className="mb-1 text-sm font-medium">Historial de corridas</p>
                <ul className="space-y-1 text-sm">
                  {detail.runs.map(r => (
                    <li key={r.id} className="flex items-center gap-2">
                      <Badge className={STATUS_COLOR[r.status] ?? ""}>{r.status}</Badge>
                      <span>{r.phase}</span>
                      <span className="text-gray-500">{r.started_at ?? "en cola"}</span>
                      {r.instructions && <span className="truncate text-gray-500" title={r.instructions}>✎ {r.instructions}</span>}
                    </li>
                  ))}
                  {detail.runs.length === 0 && <li className="text-gray-500">Sin corridas aún.</li>}
                </ul>
              </div>
              <div>
                <p className="mb-1 text-sm font-medium">Log</p>
                <pre className="max-h-64 overflow-auto rounded bg-gray-950 p-2 text-xs text-gray-100">
                  {detail.log_tail || "(vacío)"}
                </pre>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Limpiar restos del template**

Borrar `src/App.css` y quitar su import si `main.tsx` lo referencia (el template importa `./index.css`, que se queda).

- [x] **Step 4: Verificar build**

Run: `npm run build`
Expected: build exitoso.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/frontend
git commit -m "feat(orchestrator): UI de cola, workflow, historial y re-trabajo"
```

---

### Task 6: README, nota en el spec y aceptación end-to-end

**Files:**
- Create: `apps/orchestrator/README.md`
- Modify: `docs/superpowers/specs/2026-08-08-orchestrator-design.md` (nota de desviación: CLI headless en vez de Agent SDK)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: instrucciones de arranque y el criterio de aceptación real (ticket 3311).

- [x] **Step 1: Crear `apps/orchestrator/README.md`**

```markdown
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
```

- [x] **Step 2: Registrar la desviación en el spec**

En `docs/superpowers/specs/2026-08-08-orchestrator-design.md`, en la tabla de decisiones, cambiar la fila "Ejecución" a: `Claude Code CLI headless (claude -p) vía subprocess` con el porqué: `El Agent SDK requiere API key; el CLI usa la suscripción local ya logueada y carga los plugins del proyecto igual que el modo interactivo`. Añadir al final de la sección "Decisiones": "Desviación aprobada durante la implementación: se sustituye el Agent SDK por el CLI headless; el SDK queda como camino de mejora si se necesita control programático más fino."

- [ ] **Step 3: Aceptación end-to-end (manual, requiere a Jhonny)**

1. `orchestrator.config.json` con el `repoPath` real del TMS (plugin ticket-agent ya instalado ahí — Task 5 de la Fase 1).
2. Backend + frontend corriendo; encolar `3311`, "Correr análisis".
3. Verificar: log en vivo en la UI, ticket termina `analyzed`, y existe `docs/tickets/3311-analysis.md` en el repo TMS.
4. Probar "Ajustar y re-correr" con una instrucción real y verificar que el análisis se regenera.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/README.md docs
git commit -m "docs(orchestrator): README de arranque y desviación CLI headless en el spec"
```
