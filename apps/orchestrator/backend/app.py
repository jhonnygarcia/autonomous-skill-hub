import asyncio
import codecs
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ORCH_DB", BASE / "orchestrator.db"))
LOGS_DIR = Path(os.environ.get("ORCH_LOGS", BASE / "logs"))

# `test` used to be here and was removed on 2026-08-11: it isn't a phase, it's part of
# `implement`. Every task in the plan carries its own "Check" and the skill is required
# to run it, so run 3332 wrote 12 test files inside the implementation itself. A phase
# that never gets launched only takes up a slot in the timeline and promises something
# that never arrives.
PHASES = ["analyze", "design", "implement", "guards", "pr"]

# Declaring a phase doesn't mean implementing it. Only these three can be launched; the
# rest are in PHASES so the UI knows they exist, and they're rejected with 400.
PHASE_COMMANDS = {
    "analyze": "/ticket-agent:analyze",
    "design": "/ticket-agent:plan",
    "implement": "/ticket-agent:implement",
}
# What state a run that finishes well leaves the ticket in.
PHASE_DONE = {"analyze": "analyzed", "design": "planned", "implement": "implemented"}
# Bash is scoped per phase, not just per command: Phase 1 is read-only and doesn't carry
# Bash; Phase 2 needs to invoke the npm package `@fission-ai/openspec` (the CLI is NOT
# called `openspec`) for `init` and `validate`, and nothing else. The specifier has to
# match the start of the command literally or Claude blocks it, so both invocation
# forms are covered. A loose Bash in a client's repo is a different conversation — and
# that's exactly what happened when this list used to travel fixed for every phase.
PHASE_ALLOWED_TOOLS = {
    "analyze": [],
    "design": [
        "Bash(npx --yes @fission-ai/openspec@latest:*)",
        "Bash(npx @fission-ai/openspec:*)",
    ],
    # No specifier, on purpose: it's verified on a real run that `Bash(x:*)` enables
    # the tool and does not scope it. Pretending otherwise would be worse than not
    # setting it at all. Containment goes through `--settings` (see `settings_for`).
    "implement": ["Bash"],
}
# Noun for the deliverable, so the prompt doesn't call it "the analysis" to the agent
# when the phase is design (and vice versa).
PHASE_NOUN = {"analyze": "the analysis", "design": "the plan",
              "implement": "the implementation"}
# If someone adds a phase to one dict and not the others, today that's an uncaught
# KeyError inside a background task that leaves the run at `success` and the ticket
# unupdated.
assert PHASE_COMMANDS.keys() == PHASE_DONE.keys() == PHASE_ALLOWED_TOOLS.keys() == PHASE_NOUN.keys()

# Model and effort per phase, editable from Settings in the UI. They live in the
# `phase_config` table and nowhere else: empty means "whatever the CLI resolves in the
# destination repo", which is the default behavior for every phase.
# ponytail: global to the app, not per project nor per run.
EFFORTS = ("", "low", "medium", "high", "xhigh", "max")
# The model goes straight into the CLI's argv, so it can't start with `-`: that would be
# another flag. Accepts the aliases (`opus`, `sonnet`…) and the full ids.
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def phase_configs() -> dict[str, dict]:
    """The launchable phases with their configuration; whichever nobody touched come out empty."""
    with db() as c:
        rows = {r["phase"]: r for r in c.execute("SELECT * FROM phase_config")}
    return {f: {"model": rows[f]["model"] if f in rows else "",
                "effort": rows[f]["effort"] if f in rows else ""}
            for f in PHASE_COMMANDS}


HOOK_DENY_PUSH = Path(__file__).resolve().parent / "hooks" / "deny_push.py"


def settings_for(phase: str) -> list[str]:
    """`--settings` accepts an inline JSON, so the hook travels without a config file
    and without writing anything into the client's repo.

    It's branched per phase just like the tools: setting it everywhere would look the
    same today —the other phases don't have Bash— but it would go back to mixing "what
    this phase needs" with "what every phase drags along".
    """
    if phase != "implement":
        return []
    cfg = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f'"{sys.executable}" "{HOOK_DENY_PUSH}"'}]}]}}
    return ["--settings", json.dumps(cfg)]


def repos_text(phase: str, extras: list[dict], noun: str) -> str:
    """The prompt block that introduces the ticket's extra repos to the agent.

    Mounting them with `--add-dir` isn't enough: in run 3322 the agent had
    ProvidenceTMSTenant accessible, mentioned it 15 times and never opened it once. They
    have to be named to it, and the label is what tells it when to look there.

    It's branched per phase just like the tools and `settings_for`, for a reason that
    isn't cosmetic: design decision 4 says that in `implement` **every mounted repo of
    the ticket is writable**, and the `change-implementation` skill instructs the agent
    that, if the plan's map and the prompt disagree, it should follow the prompt. A
    single text that says "readable" and "written on the main one" is, in `implement`,
    the wrong instruction with top priority — and it leaves 3320 unimplemented, whose
    code lives entirely in an `extra_dir`.
    """
    if not extras:
        return ""
    listing = "; ".join(
        e["path"] + (f" — {e['label']}" if e["label"] else "") for e in extras)
    if phase == "implement":
        return (
            f"\n\nExtra repos mounted alongside the main one, and in this phase all of "
            f"them are writable: {listing}. The runner already prepared the working "
            "branch in each. Write the code in the repo the plan points to as the site "
            "of the change, not necessarily the main one, and commit in each repo "
            "whatever belongs to it."
        )
    return (
        f"\n\nExtra repos mounted and readable alongside the main one: {listing}. "
        "Read them when the ticket points to behavior that doesn't live in the main "
        f"repo; {noun} is still written in the main one."
    )


def adjustment_text(phase: str, noun: str, instructions: str | None) -> str:
    """The user's adjustment instructions, also per phase.

    In `analyze` and `design` the deliverable is ONE file and re-running means
    regenerating it. In `implement` there is no "the file" to regenerate: the
    deliverable is the code, and the only file the phase rewrites is `tasks.md`, which
    is the progress record — regenerating it would erase exactly what lets the run be
    resumed.
    """
    if not instructions:
        return ""
    if phase == "implement":
        return (
            f"\n\nUser's adjustment instructions for this run of {noun} "
            "(apply them to the tasks still pending; `tasks.md` is this phase's "
            "progress record: it gets checked off as you advance, it is not "
            f"regenerated and closed boxes are not reopened): {instructions}"
        )
    return (
        f"\n\nUser's adjustment instructions to rework {noun} "
        f"(apply them and regenerate the file): {instructions}"
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# The closing stamp for the skills. `PLAN:` is accepted as a legacy alias because logs
# from runs before the single contract were written that way. The actual log from
# `claude -p --output-format stream-json` isn't parsed as JSON here: the stamp travels
# nested inside `message.content[].text`, followed by `"`, `stop_reason`, `usage`,
# `session_id`, etc. on the same line. That's why the rest of the stamp stops at the
# first character that can't be part of its text — the quote or backslash that closes
# the JSON field — instead of greedily swallowing the rest of the line with `.+`. In a
# plain log without JSON (the legacy ones with `PLAN:`) there are no quotes or
# backslashes, so the behavior doesn't change: the capture reaches end of line just
# like before.
STAMP_RE = re.compile(r'(?:HUELLA|PLAN): (ok|parcial|nada|validado|sin-validar|no-escrito)\s*[—-]\s*([^"\\]+)')
LEGACY_STATES = {"validado": "ok", "sin-validar": "parcial", "no-escrito": "nada"}

# Separator between the path and the reserve in a `parcial` stamp: "HUELLA: parcial —
# <path> · <reserve>". Space, middle dot (U+00B7), space — that's what the two skills
# ask for in their closing rule.
RESERVE_SEP = " · "

NO_STAMP_REASON = "la corrida no declaró huella"
# The 5 historical runs from before this contract came out with status=success (the
# CLI exited 0) and no stamp: saying "failed" there would be lying about what happened.
LEGACY_NO_STAMP_REASON = "corrida anterior a este contrato: terminó bien, pero " + NO_STAMP_REASON


def split_reserve(state: str, rest: str) -> tuple[str, str | None]:
    """From a `parcial` stamp with a reserve, split the path (for `artifact_path`,
    which has to stay a clean path: it's the viewer's allowlist) from the reserve (for
    `artifact_note`). A `parcial` without ` · ` has no reserve and `rest` in full is the
    path, same as before this change."""
    if state == "parcial" and RESERVE_SEP in rest:
        path, note = rest.split(RESERVE_SEP, 1)
        return path.strip(), note.strip()
    return rest, None


def read_stamp(log_path: Path) -> tuple[str, str] | None:
    """`(state, path-or-reason)` from the LAST match in the log, or None if there is none.

    The LAST one, not just presence: the SKILL.md body travels in the log (the
    tool_result from loading it) and contains the three stamps literally, so checking
    for presence makes the check find itself and pass a run that actually closed with
    `nada`. This has already been paid for once."""
    if not log_path.exists():
        return None
    # ponytail: reads the whole file just to keep the tail; with MB-sized logs this
    # would need a seek from the end. Today they weigh KB.
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
    hits = STAMP_RE.findall(tail)
    if not hits:
        return None
    state, rest = hits[-1]
    return LEGACY_STATES.get(state, state), rest.strip()


def normalize_dirs(items: list) -> list[dict]:
    """Extra repos used to be a list of paths before carrying a label. Normalized on
    read so old rows don't break; they heal on the next save."""
    return [{"path": i, "label": ""} if isinstance(i, str)
            else {"path": i["path"], "label": i.get("label", "")} for i in items]


def project_out(row: sqlite3.Row) -> dict:
    """Outward a project has ONE list of repos, with one marked primary. Internally
    they're stored separately because the runner uses them differently: the primary one
    is the run's `cwd`, the rest travel as `--add-dir`."""
    repos = [{"path": row["repo_path"], "label": row["repo_label"], "primary": True}]
    repos += [{**d, "primary": False} for d in normalize_dirs(json.loads(row["extra_dirs"]))]
    return {"name": row["name"], "org": row["org"], "project": row["project"], "repos": repos}


def get_project(name: str) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()


def check_dirs(*paths: str) -> None:
    """Paths arrive from a form and end up as cwd and --add-dir of a subprocess: a typo
    here blows up inside the CLI with an unreadable error."""
    bad = [p for p in paths if not Path(p).is_dir()]
    if bad:
        raise HTTPException(400, "No existen o no son directorios: " + ", ".join(bad))


def is_dirty(repo: str) -> bool:
    """Is there uncommitted work that a `git switch -c` would carry along?

    `??` entries are ignored **on purpose**: the main repo always has `openspec/`,
    `docs/tickets/` and whatever `openspec init` left untracked — those are the agent's
    own artifacts. Requiring a pristine tree would make the phase permanently
    unlaunchable. What matters is what's tracked: that's genuinely the user's work.
    """
    # The directory is checked BEFORE invoking `git`, instead of wrapping the call in a
    # `try/except OSError`: that also caught a missing `git` on the PATH (the same
    # `FileNotFoundError`/`NotADirectoryError` on Windows) and disguised it as "not a
    # git repository" — a 409 that lies about the cause. A real invocation failure
    # (git not installed, etc.) has to propagate, not turn into a 409.
    if not Path(repo).is_dir():
        raise HTTPException(409, f"No es un repositorio git: {repo}")
    r = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No es un repositorio git: {repo}")
    return any(not ln.startswith("??") for ln in r.stdout.splitlines() if ln.strip())


def check_clean(repos: list[str]) -> None:
    bad = [r for r in repos if is_dirty(r)]
    if bad:
        raise HTTPException(409, "Hay cambios sin commitear en: " + ", ".join(bad)
                            + ". La fase implement commitea, y no debe llevarse por "
                              "delante tu trabajo a medias.")


BRANCH_FMT = "ticket-agent/{ado_id}"


def prepare_branch(repo: str, ado_id: int) -> str:
    """Creates the phase's branch, or switches to it if it already exists.

    The runner creates it, not the skill, for the same reason the stamp exists: a limit
    that depends on the agent obeying a markdown file isn't a limit. `refs/heads/` in
    the `rev-parse` so the branch isn't confused with a tag or a sha.
    """
    name = BRANCH_FMT.format(ado_id=ado_id)
    exists = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"],
                            cwd=repo, capture_output=True).returncode == 0
    cmd = ["git", "switch", "-q", name] if exists else ["git", "switch", "-q", "-c", name]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No se pudo preparar la rama en {repo}: {r.stderr.strip()}")
    return name


def ticket_repos(t) -> list[str]:
    """The repos the ticket mounts: the primary one first, then the extras. That's the
    order they're checked and branched in, and it holds equally for a SQLite row and for
    the `dict` that travels to the background task."""
    return [t["repo_path"]] + [
        e["path"] for e in normalize_dirs(json.loads(t["extra_dirs"] or "[]"))]


def prepare_repos(repos: list[str], ado_id: int) -> str | None:
    """Clean-tree guard on ALL of them and, only if all pass, the branch on all of them.

    The two steps go in this order and not interleaved repo by repo: if one were
    checked and branched, then the next, a second dirty repo would leave the first one
    already switched to a branch with no run to explain it.

    All of them get branched, including ones the plan ends up not touching: the runner
    doesn't parse the plan, and a branch with no commits is noise that removes itself.
    """
    check_clean(repos)
    branch = None
    for r in repos:
        branch = prepare_branch(r, ado_id)
    return branch


def split_repos(repos: list) -> tuple:
    """Validates the list exactly as the UI sends it and splits it into (primary, rest)."""
    if not repos:
        raise HTTPException(400, "El proyecto necesita al menos un repo")
    primaries = [r for r in repos if r.primary]
    if len(primaries) != 1:
        raise HTTPException(400, "Marca exactamente un repo como principal")
    check_dirs(*[r.path for r in repos])
    return primaries[0], [r for r in repos if not r.primary]


def repos_columns(body) -> tuple:   # ProjectIn is defined further below; no annotation
    primary, rest = split_repos(body.repos)
    return (primary.path, primary.label,
            json.dumps([{"path": r.path, "label": r.label} for r in rest]))


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
            CREATE TABLE IF NOT EXISTS phase_config(
              phase TEXT PRIMARY KEY,
              model TEXT NOT NULL DEFAULT '',
              effort TEXT NOT NULL DEFAULT ''
            );
            """
        )
        # DBs created before extra repos existed. SQLite has no
        # ADD COLUMN IF NOT EXISTS, so it's attempted and ignored if it's already there.
        for alter in (
            "ALTER TABLE tickets ADD COLUMN extra_dirs TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE projects ADD COLUMN repo_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE runs ADD COLUMN artifact_state TEXT",
            "ALTER TABLE runs ADD COLUMN artifact_path TEXT",
            # The reserve of a `parcial` stamp (whatever follows ` · `), separate from
            # the path: `artifact_path` has to stay a clean path.
            "ALTER TABLE runs ADD COLUMN artifact_note TEXT",
            # The branch the runner prepared for an `implement` run. It's the only
            # piece of data the run produces that doesn't fit in `tasks.md`.
            "ALTER TABLE runs ADD COLUMN branch TEXT",
            # Existed since the first commit, was initialized to 'analyze' and nothing
            # ever wrote to it: a slot planned for this that only caused confusion.
            # Progress is computed from `runs`.
            "ALTER TABLE tickets DROP COLUMN current_phase",
        ):
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass
        # Runs from before this contract have empty columns and would show up as "no
        # stamp declared" in the timeline. Their stamp is in their log: it's read once,
        # at migration time, instead of on every read.
        for r in c.execute(
            "SELECT id, log_path FROM runs WHERE artifact_state IS NULL AND log_path IS NOT NULL"
        ).fetchall():
            h = read_stamp(Path(r["log_path"]))
            if h:
                path, note = split_reserve(*h)
                c.execute(
                    "UPDATE runs SET artifact_state=?, artifact_path=?, artifact_note=? WHERE id=?",
                    (h[0], path, note, r["id"]))


app = FastAPI(title="ticket-orchestrator")
init_db()


class Repo(BaseModel):
    path: str
    label: str = ""       # "backend", "app de autenticación"… travels to the agent's prompt
    primary: bool = False  # exactly one: it's the cwd and where the analysis is written


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
    phase: str = "analyze"  # default, so callers that don't pass it don't break


def ticket_row(tid: int) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()


class PhaseConfig(BaseModel):
    model: str = ""
    effort: str = ""


@app.get("/modelos")
def get_models():
    return phase_configs()


@app.put("/modelos")
def put_models(body: dict[str, PhaseConfig]):
    """Validates EVERYTHING before writing ANYTHING: a half-saved write would leave some
    phases with the new model and others with the old one, and nobody would know which."""
    for phase, cfg in body.items():
        if phase not in PHASE_COMMANDS:
            raise HTTPException(400, f"La fase '{phase}' no es ejecutable")
        if cfg.model and not MODEL_RE.match(cfg.model):
            raise HTTPException(400, f"Modelo inválido: '{cfg.model}'")
        if cfg.effort not in EFFORTS:
            raise HTTPException(
                400, f"Effort inválido: '{cfg.effort}' (usa {', '.join(EFFORTS[1:])})")
    with db() as c:
        for phase, cfg in body.items():
            c.execute(
                "INSERT INTO phase_config(phase, model, effort) VALUES(?,?,?) "
                "ON CONFLICT(phase) DO UPDATE SET model=excluded.model, effort=excluded.effort",
                (phase, cfg.model, cfg.effort))
    return phase_configs()


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
    # ponytail: full replace, no partial PATCH — the form sends everything.
    if not get_project(name):
        raise HTTPException(404)
    # Renaming is safe: tickets copy the project's data when they're created, so none
    # of them point here. All that matters is keeping the name unique.
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
    # Safe without checking tickets: each ticket saved its own copy when it was created.
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
    return ticket_out(t, phases_for(t, [], with_footprint=False))


def seconds(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    return int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def stamp_stat(repo: str, rel: str) -> dict:
    """Size and file count of what the run declared having written. A declared path
    that doesn't exist is NOT hidden: it's reported as `existe: False`. It's the golden
    rule of the skills applied to the orchestrator.

    Recursive: an OpenSpec change nests `specs/<capability>/spec.md`, so looking only at
    direct children would underrepresent the most common deliverable. `nombres` carries
    the path relative to the stamp's directory (not the basename) because it's exactly
    the list Task 4 will use as the viewer's allowlist — "under the declared
    directory", not "direct child" — and always with `/`, even on Windows: that value
    travels to the UI and from there to the viewer endpoint, which works with POSIX
    paths."""
    p = Path(repo) / rel
    if not p.exists():
        return {"ruta": rel, "existe": False, "archivos": 0, "bytes": 0, "nombres": []}
    if p.is_dir():
        children = sorted(x for x in p.rglob("*") if x.is_file())
        names = [x.relative_to(p).as_posix() for x in children]
    else:
        children = [p]
        names = [p.name]
    return {"ruta": rel, "existe": True, "archivos": len(children),
            "bytes": sum(x.stat().st_size for x in children),
            # ponytail: 12 names are enough for the timeline; a change has 4.
            "nombres": names[:12]}


def phases_for(t: sqlite3.Row, runs: list[dict], with_footprint: bool = True) -> list[dict]:
    """A phase's progress IS its most recent run. `runs` arrives ordered by id DESC."""
    out = []
    for name in PHASES:
        if name not in PHASE_COMMANDS:
            out.append({"fase": name, "disponible": False})
            continue
        rs = [r for r in runs if r["phase"] == name]
        e = {"fase": name, "disponible": True, "corridas": len(rs),
             "fallidas": sum(1 for r in rs if r["status"] == "error")}
        if not rs:
            e["estado"] = "pendiente"
            out.append(e)
            continue
        latest = rs[0]
        if latest["status"] in ("queued", "running"):
            e["estado"] = "corriendo"
        elif latest["status"] == "success" and latest["artifact_state"] in ("ok", "parcial"):
            e["estado"] = latest["artifact_state"]
        else:
            e["estado"] = "error"
        e["en"] = latest["finished_at"] or latest["started_at"]
        e["duracion_s"] = seconds(latest["started_at"], latest["finished_at"])
        if e["estado"] == "error":
            if latest["artifact_path"]:
                e["motivo"] = latest["artifact_path"]
            elif latest["status"] == "success":
                e["motivo"] = LEGACY_NO_STAMP_REASON
            else:
                e["motivo"] = NO_STAMP_REASON
        else:
            if e["estado"] == "parcial" and latest.get("artifact_note"):
                e["motivo"] = latest["artifact_note"]
            if e["estado"] in ("ok", "parcial") and latest["artifact_path"] and with_footprint:
                e["huella"] = stamp_stat(t["repo_path"], latest["artifact_path"])
        out.append(e)
    return out


def folded_status(phases: list[dict]) -> str:
    """The list's label, folded from the same phases the detail view sees. Stops
    depending on a column that used to get overwritten on every run."""
    if any(f.get("estado") == "corriendo" for f in phases):
        return "running"
    done = [f for f in phases if f.get("estado") in ("ok", "parcial")]
    if done:
        return PHASE_DONE[done[-1]["fase"]]
    if any(f.get("estado") == "error" for f in phases):
        return "error"
    return "queued"


def ticket_out(t: sqlite3.Row, phases: list[dict]) -> dict:
    return {**dict(t), "status": folded_status(phases)}


@app.get("/tickets")
def list_tickets():
    with db() as c:
        ts = c.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        runs = [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC")]
    # ponytail: all runs are fetched at once and grouped in memory; with thousands of
    # tickets this would need a per-ticket query or a GROUP BY. It's a local queue.
    return [ticket_out(t, phases_for(t, [r for r in runs if r["ticket_id"] == t["id"]],
                                     with_footprint=False)) for t in ts]


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
    phases = phases_for(t, runs)
    return {"ticket": ticket_out(t, phases), "fases": phases, "runs": runs, "log_tail": tail}


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
    """The run currently in flight, if there is one. The lock is global, so the UI
    needs this to explain why it can't launch a ticket from ANOTHER project."""
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


def model_for(phase: str) -> list[str]:
    cfg = phase_configs()[phase]
    return ([*(["--model", cfg["model"]] if cfg["model"] else []),
             *(["--effort", cfg["effort"]] if cfg["effort"] else [])])


def set_run(run_id: int, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def set_ticket(tid: int, **fields):
    """The `status` column is still in the table for old DBs, but it's no longer
    written or read: the ticket's state is folded from `runs` in `ticket_out`. A second
    source is a source that will lie someday."""
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE tickets SET {cols} WHERE id=?", (*fields.values(), tid))


async def execute_run(run_id: int, ticket: dict, instructions: str | None, phase: str):
    async with RUN_LOCK:  # ponytail: global lock, could go per-repo if it ever hurts
        log_path = LOGS_DIR / f"{run_id}.log"
        set_run(run_id, status="running", log_path=str(log_path), started_at=now())
        set_ticket(ticket["id"])
        # Repo preparation goes HERE, under the lock and right before launching the
        # subprocess, and not only in the POST. The POST's still exists —it's the one
        # that gives the immediate 409 without spending anything— but it can't be the
        # authoritative one for two real reasons: (1) its active-run check filters by
        # `ticket_id`, so two different tickets over the SAME physical repo both pass it
        # and switch each other's branch while the first one's agent is working; (2)
        # between the POST and the launch up to half an hour can pass waiting for the
        # lock, and the user may have edited files in that gap.
        branch = None
        if phase == "implement":
            try:
                branch = prepare_repos(ticket_repos(ticket), ticket["ado_id"])
            except Exception as exc:
                # We're inside a background task: an exception here reaches nobody and
                # would leave the run stuck in `running` forever. It's closed as an
                # error with a readable reason, through the same path already used by a
                # run with no stamp (`artifact_state='nada'`, reason in `artifact_path`,
                # which is where `phases_for` pulls it from for the UI).
                reason = "no se pudo preparar el repositorio: " + str(
                    getattr(exc, "detail", None) or exc)
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write(f"[orchestrator] {reason}\n")
                set_run(run_id, status="error", finished_at=now(),
                        artifact_state="nada", artifact_path=reason)
                set_ticket(ticket["id"])
                return
            # The branch that gets saved is the one prepared under the lock, not one
            # the POST deduced before waiting.
            set_run(run_id, branch=branch)
        prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}"
        noun = PHASE_NOUN[phase]
        extras = normalize_dirs(json.loads(ticket.get("extra_dirs") or "[]"))
        prompt += repos_text(phase, extras, noun)
        prompt += adjustment_text(phase, noun, instructions)
        cmd = claude_cmd() + [
            "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits",
            # In headless mode, acceptEdits does NOT auto-approve MCP tools: they get
            # denied on their own and the agent is left unable to read the work item.
            # The rest of the tools per phase come from PHASE_ALLOWED_TOOLS (see above).
            "--allowedTools", "mcp__azure-devops", "Read", "Glob", "Grep", "Task", "Write", "Edit",
            *PHASE_ALLOWED_TOOLS[phase],
            *settings_for(phase),
            # Read at launch time, not at startup: changing the model in Settings has
            # to affect the next run without restarting the backend.
            *model_for(phase),
        ]
        for e in extras:
            cmd += ["--add-dir", e["path"]]
        # Guarantees the CLI uses the logged-in subscription, never API billing:
        # without these variables, the only credential available is the local /login one.
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
                # In chunks, not lines: asyncio's line reader blows up with "Separator
                # is found, but chunk is longer than limit" at 64 KiB, and stream-json
                # passes lines longer than that as soon as the agent writes a large
                # file. It really happened: a good run from 3322 ended up marked as an
                # error. The incremental decoder avoids splitting a character across
                # two chunks.
                dec = codecs.getincrementaldecoder("utf-8")("replace")
                while chunk := await proc.stdout.read(65536):
                    log.write(dec.decode(chunk))
                    log.flush()
                log.write(dec.decode(b"", True))
                ok = (await proc.wait()) == 0
        except Exception as exc:  # the error stays in the log, never brings down the server
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[orchestrator] excepción: {exc}\n")
        # The exit code isn't enough: `claude -p` exits 0 even if the agent stopped
        # without writing anything. The skill's closing stamp is the only reliable
        # contract, and now every phase honors it.
        stamp = read_stamp(log_path) if ok else None
        state, rest = stamp or ("nada", NO_STAMP_REASON)
        if state == "nada":
            ok = False
        path, note = split_reserve(state, rest)
        set_run(run_id, status="success" if ok else "error", finished_at=now(),
                artifact_state=state, artifact_path=path, artifact_note=note)
        set_ticket(ticket["id"])   # only touches updated_at: the state is computed on read


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
    if body.phase == "implement":
        # The guard, here: it's the one that returns the immediate 409 without spending
        # a subprocess or leaving a run queued, and the design calls for that property.
        # What does NOT happen here is switching branches: that occurs in `execute_run`,
        # under the lock (see there for why). This check is an early filter, not the
        # authoritative one.
        check_clean(ticket_repos(t))
    with db() as c:
        cur = c.execute(
            "INSERT INTO runs(ticket_id, phase, instructions, status) "
            "VALUES(?,?,?,'queued')",
            (tid, body.phase, body.instructions),
        )
        run_id = cur.lastrowid
    set_ticket(tid)
    background.add_task(execute_run, run_id, dict(t), body.instructions, body.phase)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())


ARTIFACT_CAP = 512 * 1024


@app.get("/tickets/{tid}/artefacto")
def artifact(tid: int, ruta: str):
    """Reads from disk starting from a request parameter, so validation can't be
    simplified. It's not a file explorer: it's "show me what THIS run said it wrote".
    All four conditions have to hold."""
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        declared = [r["artifact_path"] for r in c.execute(
            "SELECT artifact_path FROM runs WHERE ticket_id=? AND artifact_path IS NOT NULL "
            "AND artifact_path != '' AND artifact_state IN ('ok','parcial')", (tid,))]
            # ^ '' in addition to NULL as belt and suspenders — the real property that
            # discards wildcards lives further below, when building `real_declared`.

    # The ticket's roots: the main repo and the extras. Computed once and used
    # twice — to decide which declared paths count as a real footprint and,
    # further below, for rule 2.
    roots = [Path(t["repo_path"]).resolve()]
    roots += [Path(d["path"]).resolve() for d in normalize_dirs(json.loads(t["extra_dirs"] or "[]"))]

    # Resolved ONCE, BEFORE comparing anything: comparing over an unresolved
    # PurePosixPath (as rule 1 did before round 1 of the fixes) does NOT normalize
    # `..`, so "dir/../../../fuera" still had "dir" among its `.parents` and slipped
    # through as if it were a real descendant of a declared directory. Resolving first
    # closes that, the absolute/relative asymmetry, and Windows' case-insensitivity.
    #
    # `ruta` comes straight out of the query string: a null byte or an absurdly long
    # path makes `resolve()` blow up with `ValueError`/`OSError` uncaught, and without
    # catching it that was a 500 instead of the 400 that fits invalid client input.
    try:
        real = (Path(t["repo_path"]) / ruta).resolve()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, f"Ruta inválida: {exc}")

    # 1. Declared by a run OF THIS TICKET, or a file UNDER a declared directory — at
    #    any depth, not just a direct child: `stamp_stat` (Task 3) counts recursively
    #    because an OpenSpec change nests `specs/<capability>/spec.md`, and
    #    `huella.nombres` is exactly the allowlist the UI offers. Admitting only direct
    #    children would reject with 400 the very buttons the backend itself offered.
    #
    #    Filtering wildcards by SPELLING ('', '.', '..', 'docs/..', '   ') is a cat and
    #    mouse game: review round 2 found four more forms as soon as the comparison
    #    moved to resolved paths. The property that actually matters is different: a
    #    declared path only counts as a footprint if, ONCE RESOLVED, it lands STRICTLY
    #    inside some root of the ticket — it's neither the root itself (`..` resolves
    #    to the whole repo) nor above it. Whatever doesn't satisfy that isn't a
    #    footprint, it's a wildcard, and it's discarded here, before comparing against
    #    `real`.
    #
    #    Two questions, NOT one: `any(rd != r and r in rd.parents for r in roots)`
    #    (round 2) merged them into a single `any`, and with nested roots — an
    #    `extra_dir` that is an ANCESTOR of `repo_path`, the real monorepo case
    #    (primary `Tenant/src/Web`, extra `Tenant`; `check_dirs` accepts it without
    #    objection because it only checks `is_dir`) — it was enough for the declared
    #    path to land inside SOME root, even if THAT root was another root: `.`
    #    resolves to the primary repo, which sits strictly inside the extra, and it
    #    slipped through as a footprint again. First, whatever IS a root or sits ABOVE
    #    any of them gets discarded; only what survives that gets checked by
    #    containment. That order is what fixes the nested case: a declared path that
    #    resolves to the primary root gets discarded in the first step even if it's
    #    inside the extra.
    real_declared = []
    for d in declared:
        if not d:
            continue
        rd = (Path(t["repo_path"]) / d).resolve()
        if any(rd == r or rd in r.parents for r in roots):
            continue                      # it's a root, or contains one: wildcard, discard it
        if any(r in rd.parents for r in roots):
            real_declared.append(rd)  # strictly inside some root: valid
    if not any(real == d or d in real.parents for d in real_declared):
        raise HTTPException(400, "Esa ruta no la declaró ninguna corrida de este ticket")

    # 2. Falls inside the main repo or the ticket's extras. resolve() follows symlinks,
    #    so a symlink pointing outside dies here.
    if not any(real == r or r in real.parents for r in roots):
        raise HTTPException(400, "Esa ruta cae fuera de los repos del ticket")

    # 3. Regular file: neither a directory nor a device.
    if not real.is_file():
        raise HTTPException(400, "No es un archivo regular")

    # 4. Cap, without loading the whole file into memory: reads at most CAP+4 bytes
    #    instead of the whole file, to avoid paying a memory peak equal to the full
    #    artifact size just to serve 0.5 KB of it. The real size (for the `bytes`
    #    field) comes from `stat()`, not from what was read — and that's why
    #    `truncated` ALSO requires that the read buffer exceed the cap: if the file
    #    shrinks between the `stat()` and the `read()` (a run rewriting the artifact
    #    while the UI is looking at it), the cut index can't go past the buffer that
    #    was actually read and blow up with `IndexError`. Backing off to a byte that
    #    isn't a continuation byte (0b10xxxxxx) still stands: cutting blindly splits a
    #    multibyte character in half.
    size = real.stat().st_size
    with open(real, "rb") as fh:
        raw = fh.read(ARTIFACT_CAP + 4)
    truncated = size > ARTIFACT_CAP and len(raw) > ARTIFACT_CAP
    cut = ARTIFACT_CAP
    while truncated and cut > 0 and (raw[cut] & 0xC0) == 0x80:
        cut -= 1
    text = (raw[:cut] if truncated else raw).decode("utf-8", "replace")
    return {"ruta": ruta, "texto": text, "bytes": size, "truncado": truncated}
