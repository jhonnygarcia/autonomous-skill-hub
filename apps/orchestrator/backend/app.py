import asyncio
import codecs
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

PHASES = ["analyze", "design", "implement", "test", "guards", "pr"]

# Declarar una fase no es implementarla. Solo estas dos se pueden lanzar; el resto
# están en PHASES para que la UI sepa que existen, y se rechazan con 400.
PHASE_COMMANDS = {
    "analyze": "/ticket-agent:analyze",
    "design": "/ticket-agent:plan",
}
# En qué deja al ticket una corrida que sale bien.
PHASE_DONE = {"analyze": "analyzed", "design": "planned"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_dirs(items: list) -> list[dict]:
    """Los repos extra fueron una lista de rutas antes de llevar etiqueta. Se
    normaliza al leer para que las filas viejas no rompan; sanan al siguiente guardado."""
    return [{"path": i, "label": ""} if isinstance(i, str)
            else {"path": i["path"], "label": i.get("label", "")} for i in items]


def project_out(row: sqlite3.Row) -> dict:
    """Hacia fuera un proyecto tiene UNA lista de repos, con uno marcado principal.
    Por dentro se guardan separados porque el runner los usa distinto: el principal
    es el `cwd` de la corrida, el resto viajan como `--add-dir`."""
    repos = [{"path": row["repo_path"], "label": row["repo_label"], "primary": True}]
    repos += [{**d, "primary": False} for d in norm_dirs(json.loads(row["extra_dirs"]))]
    return {"name": row["name"], "org": row["org"], "project": row["project"], "repos": repos}


def get_project(name: str) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()


def check_dirs(*paths: str) -> None:
    """Las rutas llegan de un formulario y terminan como cwd y --add-dir de un
    subproceso: un typo aquí revienta dentro del CLI con un error ilegible."""
    bad = [p for p in paths if not Path(p).is_dir()]
    if bad:
        raise HTTPException(400, "No existen o no son directorios: " + ", ".join(bad))


def split_repos(repos: list) -> tuple:
    """Valida la lista tal como la manda la UI y la parte en (principal, resto)."""
    if not repos:
        raise HTTPException(400, "El proyecto necesita al menos un repo")
    principales = [r for r in repos if r.primary]
    if len(principales) != 1:
        raise HTTPException(400, "Marca exactamente un repo como principal")
    check_dirs(*[r.path for r in repos])
    return principales[0], [r for r in repos if not r.primary]


def repos_columns(body) -> tuple:   # ProjectIn se define más abajo; sin anotación
    principal, resto = split_repos(body.repos)
    return (principal.path, principal.label,
            json.dumps([{"path": r.path, "label": r.label} for r in resto]))


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
            CREATE TABLE IF NOT EXISTS projects(
              name TEXT PRIMARY KEY,
              org TEXT NOT NULL,
              project TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              repo_label TEXT NOT NULL DEFAULT '',
              extra_dirs TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS tickets(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ado_id INTEGER NOT NULL,
              org TEXT NOT NULL,
              project TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              extra_dirs TEXT NOT NULL DEFAULT '[]',
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
        # BDs creadas antes de que existieran los repos extra. SQLite no tiene
        # ADD COLUMN IF NOT EXISTS, así que se intenta y se ignora si ya está.
        for alter in (
            "ALTER TABLE tickets ADD COLUMN extra_dirs TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE projects ADD COLUMN repo_label TEXT NOT NULL DEFAULT ''",
        ):
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass


app = FastAPI(title="ticket-orchestrator")
init_db()


class Repo(BaseModel):
    path: str
    label: str = ""       # "backend", "app de autenticación"… viaja al prompt del agente
    primary: bool = False  # exactamente uno: es el cwd y donde se escribe el análisis


class ProjectIn(BaseModel):
    name: str
    org: str
    project: str
    repos: list[Repo] = []


class TicketIn(BaseModel):
    ado_id: int
    project: str


class RunIn(BaseModel):
    instructions: str | None = None
    phase: str = "analyze"  # por defecto, para no romper a quien ya llamaba sin ella


def ticket_row(tid: int) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()


@app.get("/projects")
def list_projects():
    with db() as c:
        return [project_out(r) for r in c.execute("SELECT * FROM projects ORDER BY name")]


@app.post("/projects", status_code=201)
def create_project(body: ProjectIn):
    cols = repos_columns(body)
    with db() as c:
        if c.execute("SELECT 1 FROM projects WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(409, f"Ya existe un proyecto '{body.name}'")
        c.execute(
            "INSERT INTO projects(name, org, project, repo_path, repo_label, extra_dirs) "
            "VALUES(?,?,?,?,?,?)",
            (body.name, body.org, body.project, *cols),
        )
    return project_out(get_project(body.name))


@app.put("/projects/{name}")
def update_project(name: str, body: ProjectIn):
    # ponytail: reemplazo completo, sin PATCH parcial — el formulario manda todo.
    if not get_project(name):
        raise HTTPException(404)
    # Renombrar es seguro: los tickets copian los datos del proyecto al crearse, así
    # que ninguno apunta aquí. Solo hay que respetar que el nombre siga siendo único.
    if body.name != name and get_project(body.name):
        raise HTTPException(409, f"Ya existe un proyecto '{body.name}'")
    cols = repos_columns(body)
    with db() as c:
        c.execute(
            "UPDATE projects SET name=?, org=?, project=?, repo_path=?, repo_label=?, "
            "extra_dirs=? WHERE name=?",
            (body.name, body.org, body.project, *cols, name),
        )
    return project_out(get_project(body.name))


@app.delete("/projects/{name}", status_code=204)
def delete_project(name: str):
    # Seguro sin comprobar tickets: cada ticket guardó su propia copia al crearse.
    with db() as c:
        if not c.execute("DELETE FROM projects WHERE name=?", (name,)).rowcount:
            raise HTTPException(404)


@app.post("/tickets", status_code=201)
def create_ticket(body: TicketIn):
    proj = get_project(body.project)
    if not proj:
        raise HTTPException(400, f"El proyecto '{body.project}' no está dado de alta")
    ts = now()
    with db() as c:
        cur = c.execute(
            "INSERT INTO tickets(ado_id, org, project, repo_path, extra_dirs, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (body.ado_id, proj["org"], proj["project"], proj["repo_path"],
             proj["extra_dirs"], ts, ts),
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


@app.get("/runs/active")
def active_run():
    """La corrida en marcha, si la hay. El lock es global, así que la UI necesita esto
    para explicar por qué no puede lanzarse un ticket de OTRO proyecto."""
    with db() as c:
        r = c.execute(
            "SELECT r.id, r.ticket_id, r.started_at, t.ado_id, t.project "
            "FROM runs r JOIN tickets t ON t.id = r.ticket_id "
            "WHERE r.status IN ('queued','running') ORDER BY r.id LIMIT 1"
        ).fetchone()
    return dict(r) if r else None


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


async def execute_run(run_id: int, ticket: dict, instructions: str | None, phase: str):
    async with RUN_LOCK:  # ponytail: lock global, por-repo si algún día duele
        log_path = LOGS_DIR / f"{run_id}.log"
        set_run(run_id, status="running", log_path=str(log_path), started_at=now())
        set_ticket(ticket["id"], status="running")
        prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}"
        extras = norm_dirs(json.loads(ticket.get("extra_dirs") or "[]"))
        if extras:
            # Montarlos con --add-dir no basta: en la corrida del 3322 el agente tenía
            # ProvidenceTMSTenant accesible, lo mencionó 15 veces y no lo abrió ni una.
            # Hay que nombrárselos, y la etiqueta es lo que le dice cuándo mirar ahí.
            listado = "; ".join(
                e["path"] + (f" — {e['label']}" if e["label"] else "") for e in extras)
            prompt += (
                f"\n\nRepos adicionales montados y legibles además del principal: {listado}. "
                "Léelos cuando el ticket apunte a comportamiento que no vive en el repo "
                "principal; el análisis se sigue escribiendo en el principal."
            )
        if instructions:
            prompt += (
                "\n\nInstrucciones de ajuste del usuario para re-trabajar el análisis "
                f"(aplícalas y regenera el archivo): {instructions}"
            )
        cmd = claude_cmd() + [
            "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits",
            # En headless, acceptEdits NO auto-aprueba las tools del MCP: se
            # deniegan solas y el agente se queda sin poder leer el work item.
            # Bash va acotado por comando: la Fase 2 necesita invocar el paquete de
            # npm `@fission-ai/openspec` (el CLI NO se llama `openspec`) para `init`
            # y `validate`, y nada más. El especificador tiene que coincidir
            # literalmente con el principio del comando o Claude lo bloquea, así que
            # se cubren las dos formas de invocarlo. Un Bash suelto en el repo de un
            # cliente es otra conversación.
            "--allowedTools", "mcp__azure-devops", "Read", "Glob", "Grep", "Task", "Write", "Edit",
            "Bash(npx --yes @fission-ai/openspec@latest:*)", "Bash(npx @fission-ai/openspec:*)",
        ]
        for e in extras:
            cmd += ["--add-dir", e["path"]]
        # Garantiza que el CLI use la suscripción logueada, nunca facturación por API:
        # sin estas variables, la única credencial disponible es la del /login local.
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        ok = False
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                log.write(f"$ {' '.join(cmd)}\n\n")
                log.flush()
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=ticket["repo_path"],
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None
                # Por trozos, no por líneas: el lector de líneas de asyncio revienta con
                # "Separator is found, but chunk is longer than limit" a los 64 KiB, y el
                # stream-json los pasa en cuanto el agente escribe un archivo grande.
                # Pasó de verdad: una corrida buena del 3322 quedó marcada como error.
                # El decodificador incremental evita partir un carácter entre dos trozos.
                dec = codecs.getincrementaldecoder("utf-8")("replace")
                while chunk := await proc.stdout.read(65536):
                    log.write(dec.decode(chunk))
                    log.flush()
                log.write(dec.decode(b"", True))
                ok = (await proc.wait()) == 0
        except Exception as exc:  # el error queda en el log, jamás tumba el server
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[orchestrator] excepción: {exc}\n")
        set_run(run_id, status="success" if ok else "error", finished_at=now())
        set_ticket(ticket["id"], status=PHASE_DONE[phase] if ok else "error")


@app.post("/tickets/{tid}/run", status_code=202)
def run_ticket(tid: int, body: RunIn, background: BackgroundTasks):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    if body.phase not in PHASE_COMMANDS:
        raise HTTPException(400, f"La fase '{body.phase}' no es ejecutable todavía")
    with db() as c:
        active = c.execute(
            "SELECT 1 FROM runs WHERE ticket_id=? AND status IN ('queued','running')", (tid,)
        ).fetchone()
    if active:
        raise HTTPException(409, "Este ticket ya tiene una corrida activa")
    with db() as c:
        cur = c.execute(
            "INSERT INTO runs(ticket_id, phase, instructions, status) VALUES(?,?,?,'queued')",
            (tid, body.phase, body.instructions),
        )
        run_id = cur.lastrowid
    set_ticket(tid, status="queued")
    background.add_task(execute_run, run_id, dict(t), body.instructions, body.phase)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
