import asyncio
import codecs
import json
import os
import re
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
# Bash va acotado por fase, no solo por comando: la Fase 1 es de solo lectura y no
# lleva Bash; la Fase 2 necesita invocar el paquete de npm `@fission-ai/openspec`
# (el CLI NO se llama `openspec`) para `init` y `validate`, y nada más. El
# especificador tiene que coincidir literalmente con el principio del comando o
# Claude lo bloquea, así que se cubren las dos formas de invocarlo. Un Bash suelto
# en el repo de un cliente es otra conversación — y fue justo lo que pasó cuando
# esta lista viajaba fija para todas las fases.
PHASE_ALLOWED_TOOLS = {
    "analyze": [],
    "design": [
        "Bash(npx --yes @fission-ai/openspec@latest:*)",
        "Bash(npx @fission-ai/openspec:*)",
    ],
}
# Sustantivo del entregable, para que el prompt no le diga "análisis" al agente
# cuando la fase es design (y viceversa).
PHASE_NOUN = {"analyze": "el análisis", "design": "el plan"}
# Si alguien añade una fase a un diccionario y no a los otros, hoy eso es un
# KeyError sin capturar dentro de un background task que deja la corrida en
# `success` y el ticket sin actualizar.
assert PHASE_COMMANDS.keys() == PHASE_DONE.keys() == PHASE_ALLOWED_TOOLS.keys() == PHASE_NOUN.keys()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# El sello de cierre de las skills. Se acepta `PLAN:` como alias legado porque los logs
# de las corridas anteriores al contrato único se escribieron así. El log real de
# `claude -p --output-format stream-json` no se parsea como JSON aquí: el sello viaja
# anidado en `message.content[].text`, seguido de `"`, `stop_reason`, `usage`,
# `session_id`, etc. en la misma línea. Por eso el resto del sello para en el primer
# carácter que no puede formar parte de su texto — la comilla o la barra invertida que
# cierran el campo JSON — en vez de tragarse voraz el resto de la línea con `.+`. En un
# log plano sin JSON (los legados con `PLAN:`) no hay comillas ni barras, así que el
# comportamiento no cambia: la captura llega hasta el fin de línea igual que antes.
SELLO = re.compile(r'(?:HUELLA|PLAN): (ok|parcial|nada|validado|sin-validar|no-escrito)\s*[—-]\s*([^"\\]+)')
LEGADO = {"validado": "ok", "sin-validar": "parcial", "no-escrito": "nada"}


def leer_huella(log_path: Path) -> tuple[str, str] | None:
    """`(estado, ruta-o-motivo)` de la ÚLTIMA coincidencia del log, o None si no hay.

    La ÚLTIMA, no la presencia: el cuerpo del SKILL.md viaja en el log (el tool_result
    de cargarlo) y contiene los tres sellos literalmente, así que comprobar presencia
    hace que la comprobación se encuentre a sí misma y dé por buena una corrida que
    cerró con `nada`. Ya se pagó una vez."""
    if not log_path.exists():
        return None
    # ponytail: se lee el archivo entero para quedarse con la cola; con logs de MB
    # tocaría un seek desde el final. Hoy pesan KB.
    cola = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    hits = SELLO.findall(cola)
    if not hits:
        return None
    estado, resto = hits[-1]
    return LEGADO.get(estado, estado), resto.strip()


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
              artifact_state TEXT,
              artifact_path TEXT,
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
            "ALTER TABLE runs ADD COLUMN artifact_state TEXT",
            "ALTER TABLE runs ADD COLUMN artifact_path TEXT",
            # Existía desde el primer commit, se inicializaba a 'analyze' y nada la
            # escribió jamás: un sitio previsto para esto que solo confundía. El avance
            # se calcula de `runs`.
            "ALTER TABLE tickets DROP COLUMN current_phase",
        ):
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass
        # Las corridas anteriores a este contrato tienen las columnas vacías y saldrían
        # como "no declaró huella" en el timeline. El sello está en su log: se lee una
        # vez, al migrar, en vez de en cada lectura.
        for r in c.execute(
            "SELECT id, log_path FROM runs WHERE artifact_state IS NULL AND log_path IS NOT NULL"
        ).fetchall():
            h = leer_huella(Path(r["log_path"]))
            if h:
                c.execute("UPDATE runs SET artifact_state=?, artifact_path=? WHERE id=?",
                          (h[0], h[1], r["id"]))


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
    t = ticket_row(cur.lastrowid)
    return ticket_out(t, fases_de(t, [], con_huella=False))


def segundos(desde: str | None, hasta: str | None) -> int | None:
    if not desde or not hasta:
        return None
    return int((datetime.fromisoformat(hasta) - datetime.fromisoformat(desde)).total_seconds())


def stat_huella(repo: str, rel: str) -> dict:
    """Tamaño y número de archivos de lo que la corrida declaró haber escrito. Una ruta
    declarada que no existe NO se oculta: se informa `existe: False`. Es la regla de oro
    de las skills aplicada al orquestador.

    Recursiva: un change de OpenSpec anida `specs/<capability>/spec.md`, así que mirar
    solo los hijos directos subrepresenta el entregable más común. `nombres` lleva la
    ruta relativa al directorio de la huella (no el basename) porque es exactamente la
    lista que la Tarea 4 usará como lista blanca del visor — "bajo el directorio
    declarado", no "hijo directo" — y siempre con `/`, también en Windows: ese valor
    viaja a la UI y de ahí al endpoint del visor, que trabaja con rutas POSIX."""
    p = Path(repo) / rel
    if not p.exists():
        return {"ruta": rel, "existe": False, "archivos": 0, "bytes": 0, "nombres": []}
    if p.is_dir():
        hijos = sorted(x for x in p.rglob("*") if x.is_file())
        nombres = [x.relative_to(p).as_posix() for x in hijos]
    else:
        hijos = [p]
        nombres = [p.name]
    return {"ruta": rel, "existe": True, "archivos": len(hijos),
            "bytes": sum(x.stat().st_size for x in hijos),
            # ponytail: 12 nombres bastan para el timeline; un change tiene 4.
            "nombres": nombres[:12]}


def fases_de(t: sqlite3.Row, runs: list[dict], con_huella: bool = True) -> list[dict]:
    """El avance de una fase ES su corrida más reciente. `runs` llega ordenado por id DESC."""
    out = []
    for nombre in PHASES:
        if nombre not in PHASE_COMMANDS:
            out.append({"fase": nombre, "disponible": False})
            continue
        rs = [r for r in runs if r["phase"] == nombre]
        e = {"fase": nombre, "disponible": True, "corridas": len(rs),
             "fallidas": sum(1 for r in rs if r["status"] == "error")}
        if not rs:
            e["estado"] = "pendiente"
            out.append(e)
            continue
        u = rs[0]
        if u["status"] in ("queued", "running"):
            e["estado"] = "corriendo"
        elif u["status"] == "success" and u["artifact_state"] in ("ok", "parcial"):
            e["estado"] = u["artifact_state"]
        else:
            e["estado"] = "error"
        e["en"] = u["finished_at"] or u["started_at"]
        e["duracion_s"] = segundos(u["started_at"], u["finished_at"])
        if e["estado"] == "error":
            e["motivo"] = u["artifact_path"] or "la corrida falló sin declarar huella"
        elif e["estado"] in ("ok", "parcial") and u["artifact_path"] and con_huella:
            e["huella"] = stat_huella(t["repo_path"], u["artifact_path"])
        out.append(e)
    return out


def status_plegado(fases: list[dict]) -> str:
    """La etiqueta de la lista, plegada de las mismas fases que ve el detalle. Deja de
    depender de una columna que se sobrescribía a cada corrida."""
    if any(f.get("estado") == "corriendo" for f in fases):
        return "running"
    hechas = [f for f in fases if f.get("estado") in ("ok", "parcial")]
    if hechas:
        return PHASE_DONE[hechas[-1]["fase"]]
    if any(f.get("estado") == "error" for f in fases):
        return "error"
    return "queued"


def ticket_out(t: sqlite3.Row, fases: list[dict]) -> dict:
    return {**dict(t), "status": status_plegado(fases)}


@app.get("/tickets")
def list_tickets():
    with db() as c:
        ts = c.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        runs = [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC")]
    # ponytail: se traen todas las corridas de una y se agrupan en memoria; con miles
    # de tickets tocaría una consulta por ticket o un GROUP BY. Es una cola local.
    return [ticket_out(t, fases_de(t, [r for r in runs if r["ticket_id"] == t["id"]],
                                   con_huella=False)) for t in ts]


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
    fases = fases_de(t, runs)
    return {"ticket": ticket_out(t, fases), "fases": fases, "runs": runs, "log_tail": tail}


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
    """La columna `status` sigue en la tabla por las BDs viejas, pero ya no se escribe
    ni se lee: el estado del ticket se pliega de `runs` en `ticket_out`. Una segunda
    fuente es una fuente que algún día miente."""
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE tickets SET {cols} WHERE id=?", (*fields.values(), tid))


async def execute_run(run_id: int, ticket: dict, instructions: str | None, phase: str):
    async with RUN_LOCK:  # ponytail: lock global, por-repo si algún día duele
        log_path = LOGS_DIR / f"{run_id}.log"
        set_run(run_id, status="running", log_path=str(log_path), started_at=now())
        set_ticket(ticket["id"])
        prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}"
        noun = PHASE_NOUN[phase]
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
                f"principal; {noun} se sigue escribiendo en el principal."
            )
        if instructions:
            prompt += (
                f"\n\nInstrucciones de ajuste del usuario para re-trabajar {noun} "
                f"(aplícalas y regenera el archivo): {instructions}"
            )
        cmd = claude_cmd() + [
            "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits",
            # En headless, acceptEdits NO auto-aprueba las tools del MCP: se
            # deniegan solas y el agente se queda sin poder leer el work item.
            # El resto de tools por fase viene de PHASE_ALLOWED_TOOLS (ver arriba).
            "--allowedTools", "mcp__azure-devops", "Read", "Glob", "Grep", "Task", "Write", "Edit",
            *PHASE_ALLOWED_TOOLS[phase],
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
        # El código de salida no basta: `claude -p` sale con 0 aunque el agente se haya
        # detenido sin escribir nada. El sello de cierre de la skill es el único
        # contrato fiable, y ahora lo cumplen todas las fases.
        huella = leer_huella(log_path) if ok else None
        estado_h, resto = huella or ("nada", "la corrida no declaró huella")
        if estado_h == "nada":
            ok = False
        set_run(run_id, status="success" if ok else "error", finished_at=now(),
                artifact_state=estado_h, artifact_path=resto)
        set_ticket(ticket["id"])   # solo toca updated_at: el estado se calcula al leer


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
    set_ticket(tid)
    background.add_task(execute_run, run_id, dict(t), body.instructions, body.phase)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
