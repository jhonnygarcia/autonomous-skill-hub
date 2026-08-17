# Archivo de entregables con restauración — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada corrida deje una copia de lo que consumió (`entrada/`) y de lo que
produjo (`salida/`) en un directorio configurable, con `run.json`, y que el humano
pueda restaurar un entregable borrado del repo desde la UI.

**Architecture:** Una función `archive_run` en `app.py`, disparada dos veces por
`execute_run` (al lanzar y al cerrar), que copia rutas relativas al repo primario a
`<archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<ts>/{entrada,salida}/` y graba
`runs.archive_path`. Un endpoint `POST /tickets/{tid}/restaurar` copia la `salida/` de un
run de vuelta al repo — nunca sobreescribe árboles. `archive_dir` vive en una tabla
`settings` nueva (`GET/PUT /archivo`). Ninguna fase lee del archivo: es registro, nunca
insumo, igual que el journal.

**Tech Stack:** FastAPI + SQLite sin ORM (backend, `shutil` de la stdlib), React + Vite +
Tailwind (frontend). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-08-17-archivo-de-entregables-design.md`

**Desviación del spec, decidida al planificar:** el spec §2-D dice «resuelto por
`declared_file_or_none`». Esa función exige **archivo regular** (regla 3) y el
entregable de `design` es un directorio, así que no sirve tal cual. `copy_into` aplica
la misma regla 2 (resolver y exigir que caiga bajo `repo_path`) sobre archivo o árbol,
y nada más — el resto de reglas del visor son sobre *servir* un archivo, no sobre
copiarlo. Los tests 1 y 2 cubren ambas formas.

## Global Constraints

- **Precondición:** el árbol de trabajo tiene cambios sin commitear ajenos a este plan
  (`artifact_exists`, en `app.py`, `test_app.py` y `CLAUDE.md`). **Ese trabajo aterriza
  antes de la Task 1** — verificar `git status` limpio al empezar; si no lo está, parar
  y avisar. Este plan asume que `runs.artifact_exists` y `artifact_on_disk` existen.
- **Código y comentarios en inglés.** Strings **UI-facing** (`HTTPException` detail,
  notas de journal) en **español**. Rutas y JSON keys son literales de contrato: `/archivo`,
  `/restaurar`, `archive_path`, `entrada`, `salida`, `run.json` — no traducirlas.
- **Tests backend:** `cd apps/orchestrator/backend && .venv/Scripts/python -m pytest tests/ -v`.
  Cada test nuevo va en `tests/test_app.py`, usa el fixture `client` de `conftest.py`
  (repo primario en `tmp_path / "repo"`) y `_use_fake_claude(monkeypatch, stamp=...)`.
  **El fake no escribe archivos**: el test crea el entregable en disco antes de correr.
- **Frontend:** `cd apps/orchestrator/frontend && npm run build && npm run lint`. No hay
  tests de UI; build + lint son el check. Línea base: dos warnings en `badge.tsx` y
  `button.tsx`, ninguno más.
- **Nunca `uvicorn --reload`.** Para probar a mano, arrancar el backend después del
  último cambio a `app.py`.
- **Commits pequeños, uno por task**, con `Co-Authored-By` y `Claude-Session` como los
  anteriores de esta rama (`engine-agnostic`).
- **No tocar `declared_file`** (3 rondas de revisión adversarial); nada de este plan la
  modifica.

---

### Task 1: tabla `settings` y `GET/PUT /archivo`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — `init_db` (bloque `CREATE TABLE`, ~L690);
  nuevas funciones y rutas junto a `get_models`/`put_models` (~L811-850)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Produces: `setting(key: str) -> str` (vacío si no existe), `set_setting(key, value)`,
  `GET /archivo -> {"dir": str}`, `PUT /archivo {"dir": str} -> {"dir": str}`.

- [ ] **Step 1: test rojo**

```python
def test_archive_dir_setting_roundtrip_and_validation(client, tmp_path):
    """`archive_dir` lives in the DB and nowhere else; empty means off. A directory that
    doesn't exist is refused at save time, not discovered when the first run closes."""
    assert client.get("/archivo").json() == {"dir": ""}
    d = tmp_path / "archivo"
    d.mkdir()
    r = client.put("/archivo", json={"dir": d.as_posix()})
    assert r.status_code == 200 and r.json() == {"dir": d.as_posix()}
    assert client.get("/archivo").json() == {"dir": d.as_posix()}
    bad = client.put("/archivo", json={"dir": (tmp_path / "no-existe").as_posix()})
    assert bad.status_code == 400 and "no-existe" in bad.json()["detail"]
    # a bad save leaves the previous value alone
    assert client.get("/archivo").json() == {"dir": d.as_posix()}
    # empty switches it off
    assert client.put("/archivo", json={"dir": ""}).json() == {"dir": ""}
```

- [ ] **Step 2: correr y ver que falla**

`.venv/Scripts/python -m pytest tests/test_app.py::test_archive_dir_setting_roundtrip_and_validation -v`
→ FAIL: 404 en `/archivo`.

- [ ] **Step 3: implementar**

En `init_db`, dentro del `executescript` que crea las tablas, añadir después de
`phase_config`:

```sql
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

Junto a `phase_configs()` (~L229):

```python
def setting(key: str) -> str:
    """One row per knob, read at the moment it's needed (like `model_for`), never
    cached at startup: on Windows the backend isn't hot-reloaded."""
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else ""


def set_setting(key: str, value: str) -> None:
    with db() as c:
        c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
```

Junto a `get_models` (~L811):

```python
class ArchiveIn(BaseModel):
    dir: str = ""


@app.get("/archivo")
def get_archive():
    return {"dir": setting("archive_dir")}


@app.put("/archivo")
def put_archive(body: ArchiveIn):
    """Empty switches the archive off. Anything else must be a directory that exists
    and can be written NOW: the alternative is finding out at the close of a run,
    where a failure is only a journal line."""
    d = body.dir.strip()
    if d:
        p = Path(d)
        if not p.is_dir():
            raise HTTPException(400, f"No es un directorio: {d}")
        try:
            probe = p / ".orch-probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError:
            raise HTTPException(400, f"No se puede escribir en: {d}")
    set_setting("archive_dir", d)
    return {"dir": d}
```

- [ ] **Step 4: verde**

Mismo comando → PASS. Y la suite completa: `.venv/Scripts/python -m pytest tests/ -q`.

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): archive_dir en settings, GET/PUT /archivo"
```

---

### Task 2: `archive_run` — snapshot de salida al cerrar, `run.json`, `archive_path`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — migración `ALTER TABLE runs ADD COLUMN
  archive_path TEXT`; helpers nuevos junto a `append_journal` (~L968); llamada en
  `execute_run` justo después de `append_journal(...)` del cierre principal (~L1710)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `setting("archive_dir")` (Task 1); `set_run`, `append_journal`, `now`.
- Produces:
  - `archive_folder(ticket: dict, run_id: int, phase: str, started: str) -> Path | None`
  - `copy_into(repo: Path, rel: str, dest: Path) -> tuple[int, str | None]`
    (archivos copiados, motivo de omisión o `None`)
  - `run_meta(ticket: dict, run_id: int) -> dict`
  - `archive_run(ticket: dict, run_id: int, phase: str, kind: str, rels: list[str],
    started: str) -> list[str]` (notas para el journal; vacío si todo bien)
  - `journal_note(ticket: dict, text: str) -> None` (una línea `   · <text>` antes de
    `## Hallazgos`)
  - columna `runs.archive_path`.

- [ ] **Step 1: tests rojos**

```python
def _archive_on(client, tmp_path):
    d = tmp_path / "archivo"
    d.mkdir()
    assert client.put("/archivo", json={"dir": d.as_posix()}).status_code == 200
    return d


def test_close_archives_the_declared_file_and_writes_run_json(client, monkeypatch, tmp_path):
    arch = _archive_on(client, tmp_path)
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "3323-analysis.md").write_text("análisis", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    folder = Path(run["archive_path"])
    # <archive>/<org>/<project>/<llave>/<run_id>-<fase>-<ts>/
    assert folder.parent == arch / "DemoOrg" / "Demo" / "3323"
    assert folder.name.startswith(f"{run['id']}-analyze-")
    assert (folder / "salida" / "docs" / "tickets" / "3323-analysis.md").read_text(encoding="utf-8") == "análisis"
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert meta["llave"] == 3323 and meta["phase"] == "analyze"
    assert meta["artifact_state"] == "ok" and meta["engine"] == "claude"
    # the journal copied into salida/ already carries THIS run's line
    journal = (folder / "salida" / "docs" / "tickets" / "3323-journal.md").read_text(encoding="utf-8")
    assert "· analyze · ok · docs/tickets/3323-analysis.md" in journal


def test_close_archives_a_declared_tree(client, monkeypatch, tmp_path):
    _archive_on(client, tmp_path)
    change = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    (change / "specs" / "pagos").mkdir(parents=True)
    (change / "proposal.md").write_text("p")
    (change / "specs" / "pagos" / "spec.md").write_text("s")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    folder = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["archive_path"])
    assert (folder / "salida" / "openspec" / "changes" / "3323-xpo" / "specs" / "pagos" / "spec.md").exists()
    assert (folder / "salida" / "openspec" / "changes" / "3323-xpo" / "proposal.md").exists()


def test_archive_off_copies_nothing(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "a.md").write_text("x")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success" and run["archive_path"] is None
    journal = (tmp_path / "repo" / "docs" / "tickets" / "1-journal.md").read_text(encoding="utf-8")
    assert "archivo:" not in journal


def test_archive_failure_does_not_touch_the_run(client, monkeypatch, tmp_path):
    """The deliverable exists in the repo; a copy that fails is a journal line."""
    arch = _archive_on(client, tmp_path)
    (tmp_path / "repo" / "a.md").write_text("x")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    # the directory disappears between the save and the close
    arch.rmdir()
    # …and a FILE takes its place, so mkdir fails with an OSError on every OS
    arch.write_text("no soy un directorio")
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "ok"
    journal = (tmp_path / "repo" / "docs" / "tickets" / "1-journal.md").read_text(encoding="utf-8")
    assert "· archivo: no copiado" in journal
```

- [ ] **Step 2: correr y ver que fallan**

`.venv/Scripts/python -m pytest tests/test_app.py -k "archives or archive_off or archive_failure" -v`
→ FAIL: `KeyError: 'archive_path'`.

- [ ] **Step 3: implementar**

Migración, al final de la tupla de `ALTER TABLE` en `init_db`:

```python
            # The snapshot folder this run wrote (`<archive_dir>/.../<run_id>-<phase>-<ts>`).
            # NULL = nothing archived — the archive was off, or the copy failed before
            # the folder existed. Read by the UI (restore button) and by `/restaurar`.
            "ALTER TABLE runs ADD COLUMN archive_path TEXT",
```

Helpers, después de `append_journal` (~L997):

```python
# A declared tree bigger than this is not copied: a stamp that got clipped to `docs`
# (see the backslash risk in STATUS.md) would otherwise archive the whole folder on
# every run. The run is untouched; the journal says what was skipped.
ARCHIVE_TREE_MAX_FILES = 200
ARCHIVE_TREE_MAX_BYTES = 20 * 1024 * 1024


def journal_note(ticket: dict, text: str) -> None:
    """One indented sub-line under the most recent run line — same shape as
    `· reserva:`. Inserted right before `## Hallazgos`, like the run lines."""
    p = Path(ticket["repo_path"]) / JOURNAL_REL.format(ado_id=ticket["ado_id"])
    try:
        body = p.read_text(encoding="utf-8", errors="replace") if p.exists() else \
            JOURNAL_HEADER.format(ado_id=ticket["ado_id"])
        line = f"   · {text}\n"
        i = body.find("## Hallazgos")
        body = body + line if i < 0 else body[:i] + line + body[i:]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    except OSError:
        pass  # ponytail: same policy as append_journal — a lost note, not a lost run


def _seg(value) -> str:
    """A path segment out of an org, a project or a key: anything not [\\w.-] → `_`."""
    return re.sub(r"[^\w.-]", "_", str(value)) or "_"


def archive_folder(ticket: dict, run_id: int, phase: str, started: str) -> Path | None:
    """`<archive_dir>/<org>/<project>/<llave>/<run_id>-<phase>-<YYYYMMDD-HHMM>`, or None
    when the archive is off. `org`/`project` are the ticket's own copies, so renaming
    the project moves nothing. The timestamp is the LAUNCH time, so entrada and salida
    of one run land in the same folder."""
    root = setting("archive_dir")
    if not root:
        return None
    ts = started[:16].replace("-", "").replace(":", "").replace("T", "-")  # 20260817-1530
    return (Path(root) / _seg(ticket["org"]) / _seg(ticket["project"])
            / _seg(ticket["ado_id"]) / f"{run_id}-{phase}-{ts}")


def copy_into(repo: Path, rel: str, dest: Path) -> tuple[int, str | None]:
    """Copy `repo/rel` (file or tree) to `dest/rel`, keeping the relative path.
    Returns (files copied, skip reason). Rule 2 of `declared_file` applies — the
    resolved source must fall under the repo — and nothing else: this copies, it
    doesn't serve. A source that doesn't exist copies nothing and says nothing."""
    root = repo.resolve()
    try:
        src = (root / rel).resolve()
    except (ValueError, OSError):
        return 0, None
    if not src.is_relative_to(root) or not src.exists():
        return 0, None
    target = dest / rel
    if src.is_dir():
        files = [x for x in src.rglob("*") if x.is_file()]
        size = sum(x.stat().st_size for x in files)
        if len(files) > ARCHIVE_TREE_MAX_FILES or size > ARCHIVE_TREE_MAX_BYTES:
            return 0, f"omitido — {rel}: {len(files)} archivos / {size // (1024 * 1024)} MB"
        shutil.copytree(src, target, dirs_exist_ok=True)
        return len(files), None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return 1, None


RUN_META_FIELDS = ("phase", "engine", "instructions", "resumed_from", "session_id",
                   "started_at", "finished_at", "status", "artifact_state",
                   "artifact_path", "artifact_note", "branch")


def run_meta(ticket: dict, run_id: int) -> dict:
    """What `run.json` holds: enough to read the folder without the DB (which has been
    wiped once). Human and forensic reading only — nothing in the orchestrator reads it."""
    with db() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    cfg = phase_configs().get(r["phase"], {}) if r else {}
    return {"ticket_id": ticket["id"], "llave": ticket["ado_id"], "org": ticket["org"],
            "project": ticket["project"], "repo_path": ticket["repo_path"],
            "extra_dirs": json.loads(ticket.get("extra_dirs") or "[]"),
            "run_id": run_id, "model": cfg.get("model", ""), "effort": cfg.get("effort", ""),
            **({k: r[k] for k in RUN_META_FIELDS} if r else {})}


def write_run_meta(folder: Path, ticket: dict, run_id: int) -> None:
    """Raises OSError like any write; callers decide what a lost run.json costs."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(
        json.dumps(run_meta(ticket, run_id), indent=2, ensure_ascii=False), encoding="utf-8")


def archive_run(ticket: dict, run_id: int, phase: str, kind: str, rels: list[str],
                started: str) -> list[str]:
    """Snapshot `rels` (relative to the primary repo) under `<folder>/<kind>/`, rewrite
    `run.json`, record `archive_path`. `kind` is `entrada` (what the phase is about to
    read) or `salida` (what it declared). Returns the notes the journal should carry —
    a skipped tree, a failed copy. Never raises: a record that can't be written is a
    lost line, not a lost run."""
    folder = archive_folder(ticket, run_id, phase, started)
    if not folder:
        return []
    notes = []
    try:
        (folder / kind).mkdir(parents=True, exist_ok=True)
        for rel in rels:
            _, skipped = copy_into(Path(ticket["repo_path"]), rel, folder / kind)
            if skipped:
                notes.append(f"archivo: {skipped}")
        write_run_meta(folder, ticket, run_id)
        set_run(run_id, archive_path=str(folder))
    except OSError as exc:
        notes.append(f"archivo: no copiado — {exc}")
    return notes
```

En `execute_run`, el cierre principal queda así (sustituir desde `append_journal(...)`
hasta antes del bloque `if phase == "analyze"`):

```python
        append_journal(ticket, phase, state, path, note,
                       seconds(started, fin), branch, prev)
        # AFTER the journal line, so the journal copied into salida/ already carries
        # this run. Only what closed with a footprint has a salida; the request and the
        # journal ride along because they're the two files a returning human reads
        # next to the deliverable.
        if state in ("ok", "parcial") and path:
            key = ticket["ado_id"]
            for n in archive_run(ticket, run_id, phase, "salida",
                                 [path, f"docs/tickets/{key}-request.md",
                                  f"docs/tickets/{key}-journal.md"], started):
                journal_note(ticket, n)
        # run.json is rewritten at close for EVERY outcome, `nada` included: the entrada
        # (Task 3) writes it with the run still `running`, and a folder that says so
        # forever would lie about a run that finished.
        folder = archive_folder(ticket, run_id, phase, started)
        if folder and folder.is_dir():
            try:
                write_run_meta(folder, ticket, run_id)
            except OSError:
                pass  # ponytail: same policy as the copies — a lost record, not a lost run
```

`llave` numérica: `_seg(3323)` → `"3323"`; `json.dumps` conserva el `int` en `run.json`
(el test lo compara con `3323`).

- [ ] **Step 4: verde**

Los cuatro tests → PASS. Suite completa en verde (`pytest tests/ -q`).

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): snapshot de salida por corrida, con run.json y archive_path"
```

---

### Task 3: snapshot de entrada al lanzar

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — `execute_run`, entre la proyección del
  request (~L1560-1567) y `prev = last_session(...)`; el `append_journal` del cierre
  gana las notas de entrada
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `archive_run` (Task 2).
- Produces: `entrada_rels(ticket: dict) -> list[str]`; `append_journal` gana un
  parámetro `extra: list[str] | None = None` (sub-líneas `   · <x>` tras la del run).

- [ ] **Step 1: tests rojos**

```python
def test_launch_archives_what_the_phase_will_read_including_human_edits(client, monkeypatch, tmp_path):
    """The seam between phases is the human ticking boxes in the .md. The salida of
    `analyze` has the box open; the entrada of `design` has it ticked — restoring the
    former would hand back the questions unanswered."""
    _archive_on(client, tmp_path)
    tickets = tmp_path / "repo" / "docs" / "tickets"
    tickets.mkdir(parents=True)
    analysis = tickets / "3323-analysis.md"
    analysis.write_text("## Decisiones para ti\n- [ ] **DECIDIR** usar cola\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    first = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["archive_path"])
    # the human answers
    analysis.write_text("## Decisiones para ti\n- [x] **DECIDIR** usar cola\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    (tmp_path / "repo" / "openspec" / "changes" / "3323-xpo").mkdir(parents=True)
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    second = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["archive_path"])
    assert "- [ ]" in (first / "salida" / "docs" / "tickets" / "3323-analysis.md").read_text(encoding="utf-8")
    assert "- [x]" in (second / "entrada" / "docs" / "tickets" / "3323-analysis.md").read_text(encoding="utf-8")
    # entrada also carries the journal as it was BEFORE this run's line
    assert (second / "entrada" / "docs" / "tickets" / "3323-journal.md").exists()


def test_run_with_no_stamp_still_has_entrada_and_run_json(client, monkeypatch, tmp_path):
    _archive_on(client, tmp_path)
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "1-request.md").write_text("pedido")
    _use_fake_claude(monkeypatch, stamp="nada — no pude")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    folder = Path(run["archive_path"])
    assert (folder / "entrada" / "docs" / "tickets" / "1-request.md").exists()
    assert not (folder / "salida").exists()
    assert json.loads((folder / "run.json").read_text(encoding="utf-8"))["artifact_state"] == "nada"


def test_entrada_includes_the_change_tree_a_previous_run_declared(client, monkeypatch, tmp_path):
    """`implement` ticks tasks.md inside the tree `design` declared: the entrada of an
    implement run is the plan as it stood before this run touched it."""
    _archive_on(client, tmp_path)
    change = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    change.mkdir(parents=True)
    (change / "tasks.md").write_text("- [ ] 1")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo/tasks.md")
    client.post(f"/tickets/{tid}/run", json={"phase": "analyze"})   # any later phase will do
    latest = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["archive_path"])
    assert (latest / "entrada" / "openspec" / "changes" / "3323-xpo" / "tasks.md").exists()
```

(El tercero usa `analyze` como «fase posterior» porque `implement` exige rama y árbol
limpio, que el fixture no monta; lo que se prueba es la regla «árbol declarado antes →
va en la entrada», no la fase.)

- [ ] **Step 2: correr y ver que fallan**

`pytest tests/test_app.py -k "entrada or no_stamp_still" -v` → FAIL.

- [ ] **Step 3: implementar**

Helper junto a `archive_run`:

```python
def entrada_rels(ticket: dict) -> list[str]:
    """What a phase is about to read: every `docs/tickets/<llave>-*` file (analysis,
    brief, request, journal — whichever exist) plus any tree a previous good run of
    this ticket declared (the OpenSpec change `implement` writes into)."""
    repo = Path(ticket["repo_path"])
    key = ticket["ado_id"]
    rels = [p.relative_to(repo).as_posix()
            for p in sorted((repo / "docs" / "tickets").glob(f"{key}-*")) if p.is_file()]
    with db() as c:
        declared = [r["artifact_path"] for r in c.execute(
            "SELECT DISTINCT artifact_path FROM runs WHERE ticket_id=? "
            "AND artifact_state IN ('ok','parcial') AND artifact_path IS NOT NULL",
            (ticket["id"],))]
    rels += [d for d in declared if d not in rels and (repo / d).is_dir()]
    return rels
```

`append_journal` gana `extra`:

```python
def append_journal(ticket: dict, phase: str, state: str, detail: str,
                   note: str | None = None, duration_s: int | None = None,
                   branch: str | None = None, resumed_from: str | None = None,
                   extra: list[str] | None = None) -> None:
    ...
        line = (...
                + (f"   · reserva: {note}\n" if note else "")
                + "".join(f"   · {x}\n" for x in (extra or [])))
```

En `execute_run`, justo antes de `prev = last_session(...)`:

```python
        # The entrada is what the phase is about to read, human edits included (the
        # ticked DECIDIR boxes live nowhere else). Taken AFTER the request projection
        # so it matches the disk the agent sees. Notes wait for the journal line.
        archive_notes = archive_run(ticket, run_id, phase, "entrada",
                                    entrada_rels(ticket), started)
```

Y en el cierre principal, `append_journal(...)` recibe `extra=archive_notes`; el bucle
de la salida (Task 2) sigue detrás con `journal_note`.

Los tres retornos tempranos anteriores (repo no preparado, sin surveys, sin brief) están
**antes** de este punto y no snapshotean nada — coherente con el spec §3.2.

- [ ] **Step 4: verde**

Los tres tests y la suite completa → PASS.

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): snapshot de entrada al lanzar — lo que la fase consume, con las respuestas del humano"
```

---

### Task 4: tope de tamaño para árboles declarados

**Files:**
- Modify: nada nuevo en `app.py` — `copy_into` (Task 2) ya lo aplica; esta task lo prueba
  y ajusta si hace falta
- Test: `apps/orchestrator/backend/tests/test_app.py`

- [ ] **Step 1: test rojo (o verde de una: entonces sigue al commit)**

```python
def test_a_declared_tree_over_the_cap_is_skipped_not_copied(client, monkeypatch, tmp_path):
    """A stamp clipped to `docs` would otherwise archive the whole folder every run."""
    _archive_on(client, tmp_path)
    monkeypatch.setattr("app.ARCHIVE_TREE_MAX_FILES", 3)
    docs = tmp_path / "repo" / "docs"
    docs.mkdir()
    for i in range(4):
        (docs / f"f{i}.md").write_text("x")
    _use_fake_claude(monkeypatch, stamp="ok — docs")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success"
    folder = Path(run["archive_path"])
    assert not (folder / "salida" / "docs" / "f0.md").exists()
    journal = (tmp_path / "repo" / "docs" / "tickets" / "1-journal.md").read_text(encoding="utf-8")
    # not "4 archivos": by close time `docs/` also holds `docs/tickets/1-journal.md`,
    # and the count is whatever the tree held when it was measured
    assert "· archivo: omitido — docs:" in journal
```

- [ ] **Step 2: correr**

`pytest tests/test_app.py::test_a_declared_tree_over_the_cap_is_skipped_not_copied -v`.
Si falla, la causa está en `copy_into` (Task 2) — corregir ahí, no aquí.

- [ ] **Step 3: commit**

```bash
git add apps/orchestrator/backend/tests/test_app.py apps/orchestrator/backend/app.py
git commit -m "test(orchestrator): un árbol declarado sobre el tope se omite y queda en el journal"
```

---

### Task 5: `POST /tickets/{tid}/restaurar` y «registro, nunca insumo»

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — ruta nueva junto a `run_ticket` (~L1726)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `runs.archive_path`, `append_journal`, `ticket_row`.
- Produces: `POST /tickets/{tid}/restaurar {"run_id": int, "overwrite": bool=false}
  -> {"restaurado": str, "archivos": int}`; `404` sin snapshot, `409` con run activo /
  destino presente.

- [ ] **Step 1: tests rojos**

```python
def _archived_analysis(client, monkeypatch, tmp_path, key=3323):
    """One good analyze run with the archive on; returns (tid, run_id, path on disk)."""
    _archive_on(client, tmp_path)
    p = tmp_path / "repo" / "docs" / "tickets" / f"{key}-analysis.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("versión uno", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp=f"ok — docs/tickets/{key}-analysis.md")
    tid = client.post("/tickets", json={"ado_id": key, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run_id = client.get(f"/tickets/{tid}").json()["runs"][0]["id"]
    return tid, run_id, p


def test_restore_puts_a_deleted_file_back_and_journals_it(client, monkeypatch, tmp_path):
    tid, run_id, p = _archived_analysis(client, monkeypatch, tmp_path)
    p.unlink()
    assert _phase(client, tid, "analyze")["huella"]["existe"] is False
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id})
    assert r.status_code == 200
    assert r.json() == {"restaurado": "docs/tickets/3323-analysis.md", "archivos": 1}
    assert p.read_text(encoding="utf-8") == "versión uno"
    assert _phase(client, tid, "analyze")["huella"]["existe"] is True
    journal = (tmp_path / "repo" / "docs" / "tickets" / "3323-journal.md").read_text(encoding="utf-8")
    assert f"· restaurar · ok · docs/tickets/3323-analysis.md" in journal
    assert f"desde run {run_id}" in journal


def test_restore_refuses_to_overwrite_a_file_unless_asked(client, monkeypatch, tmp_path):
    tid, run_id, p = _archived_analysis(client, monkeypatch, tmp_path)
    p.write_text("versión dos", encoding="utf-8")   # e.g. consolidate rewrote it
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id})
    assert r.status_code == 409 and "overwrite" in r.json()["detail"]
    assert p.read_text(encoding="utf-8") == "versión dos"
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id, "overwrite": True})
    assert r.status_code == 200
    assert p.read_text(encoding="utf-8") == "versión uno"


def test_restore_never_overwrites_a_tree(client, monkeypatch, tmp_path):
    """`implement` ticks tasks.md INSIDE the tree `design` declared. Putting the design
    snapshot back over it would untick real progress — so a tree only comes back when
    it's gone, `overwrite` or not."""
    _archive_on(client, tmp_path)
    change = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    change.mkdir(parents=True)
    (change / "tasks.md").write_text("- [ ] 1")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run_id = client.get(f"/tickets/{tid}").json()["runs"][0]["id"]
    (change / "tasks.md").write_text("- [x] 1")
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id, "overwrite": True})
    assert r.status_code == 409 and "árbol" in r.json()["detail"]
    assert (change / "tasks.md").read_text() == "- [x] 1"
    # gone → comes back whole
    shutil.rmtree(change)
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id})
    assert r.status_code == 200 and r.json()["archivos"] == 1
    assert (change / "tasks.md").read_text() == "- [ ] 1"


def test_restore_refuses_while_a_run_is_active(client, monkeypatch, tmp_path):
    import app as app_module
    tid, run_id, p = _archived_analysis(client, monkeypatch, tmp_path)
    p.unlink()
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?, 'design', 'running')", (tid,))
    r = client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id})
    assert r.status_code == 409 and "activa" in r.json()["detail"]
    assert not p.exists()


def test_restore_404_when_the_run_has_no_snapshot(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "a.md").write_text("x")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")          # archive off
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run_id = client.get(f"/tickets/{tid}").json()["runs"][0]["id"]
    assert client.post(f"/tickets/{tid}/restaurar", json={"run_id": run_id}).status_code == 404
    assert client.post(f"/tickets/{tid}/restaurar", json={"run_id": 999}).status_code == 404


def test_deleting_the_archive_changes_nothing_about_the_next_run(client, monkeypatch, tmp_path):
    """A record, never an input: no phase reads from the archive."""
    _archive_on(client, tmp_path)
    (tmp_path / "repo" / "a.md").write_text("x")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    shutil.rmtree(tmp_path / "archivo")
    (tmp_path / "archivo").mkdir()
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "success"
    assert "/ticket-agent:plan 1" in detail["log_tail"]
```

`import shutil` al inicio de `test_app.py` si no está.

- [ ] **Step 2: correr y ver que fallan**

`pytest tests/test_app.py -k "restore or deleting_the_archive" -v` → FAIL: 404 en
`/restaurar` (los dos primeros asserts del test 404 pasarían por la razón equivocada —
por eso el resto tiene que fallar antes de implementar).

- [ ] **Step 3: implementar**

Junto a `run_ticket`:

```python
class RestoreIn(BaseModel):
    run_id: int
    overwrite: bool = False


@app.post("/tickets/{tid}/restaurar")
def restore_run(tid: int, body: RestoreIn):
    """Copies the salida/ of one run back to where the phases read it. A human act,
    never a phase's: the archive is a record, and this is the one door from it back
    into the repo. Files may be overwritten on request; trees never — `implement`
    ticks `tasks.md` inside the tree `design` declared, and putting the older tree back
    would untick real progress."""
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        r = c.execute("SELECT * FROM runs WHERE id=? AND ticket_id=?",
                      (body.run_id, tid)).fetchone()
        active = c.execute(
            "SELECT 1 FROM runs WHERE ticket_id=? AND status IN ('queued','running')",
            (tid,)).fetchone()
    if not r or not r["archive_path"] or r["artifact_state"] not in ("ok", "parcial"):
        raise HTTPException(404, "Esa corrida no dejó snapshot que restaurar")
    if active:
        raise HTTPException(409, "Este ticket tiene una corrida activa; restaura cuando termine")
    rel = r["artifact_path"]
    src = Path(r["archive_path"]) / "salida" / rel
    if not src.exists():
        raise HTTPException(404, f"El snapshot ya no está en disco: {src}")
    repo = Path(t["repo_path"]).resolve()
    dest = (repo / rel).resolve()
    if not dest.is_relative_to(repo):
        raise HTTPException(400, f"Ruta fuera del repo: {rel}")
    if src.is_dir():
        if dest.exists() and any(x.is_file() for x in dest.rglob("*")):
            raise HTTPException(
                409, f"Ya hay archivos en {rel}: un árbol nunca se sobreescribe. "
                     "Si de verdad quieres volver atrás, bórralo a mano y vuelve a restaurar")
        shutil.copytree(src, dest, dirs_exist_ok=True)
        n = sum(1 for x in src.rglob("*") if x.is_file())
    else:
        if dest.exists() and not body.overwrite:
            raise HTTPException(409, f"Ya existe {rel}; repite con overwrite para reemplazarlo")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        n = 1
    append_journal(dict(t), "restaurar", "ok", rel, note=f"desde run {r['id']}")
    return {"restaurado": rel, "archivos": n}
```

- [ ] **Step 4: verde**

Los seis tests y la suite completa → PASS.

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): POST /tickets/{tid}/restaurar — archivos con overwrite, árboles nunca"
```

---

### Task 6: frontend — `api.ts` y el campo de Settings

**Files:**
- Modify: `apps/orchestrator/frontend/src/api.ts` — tipo `Run`, tres llamadas nuevas
- Create: `apps/orchestrator/frontend/src/Archive.tsx`
- Modify: `apps/orchestrator/frontend/src/App.tsx:113` — render debajo de `<Models />`

**Interfaces:**
- Produces: `Run.archive_path: string | null`; `api.archive(): Promise<{dir: string}>`;
  `api.saveArchive(dir): Promise<{dir: string}>`;
  `api.restore(id, runId, overwrite=false): Promise<{restaurado: string; archivos: number}>`.

- [ ] **Step 1: `api.ts`**

En `Run`, después de `branch`:

```ts
  // The snapshot folder this run left, when the archive was on. `null` is the normal
  // case for every run before the archive existed and for runs with it switched off.
  archive_path: string | null
```

En `api`, después de `saveModels`:

```ts
  archive: () => fetch("/api/archivo").then(r => json<{ dir: string }>(r)),
  saveArchive: (dir: string) =>
    fetch("/api/archivo", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dir }),
    }).then(r => json<{ dir: string }>(r)),
  /** Puts a run's declared deliverable back into the repo from its snapshot. Files
   *  need `overwrite` when the destination exists; a tree is never overwritten. */
  restore: (id: number, runId: number, overwrite = false) =>
    fetch(`/api/tickets/${id}/restaurar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, overwrite }),
    }).then(r => json<{ restaurado: string; archivos: number }>(r)),
```

- [ ] **Step 2: `Archive.tsx`**

```tsx
import { useEffect, useState } from "react"
import { api } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

/** Where every run leaves its snapshot (entrada/, salida/, run.json). Empty = off.
 *  A human preference, not a deployment knob: it lives in the DB with the models. */
export function Archive() {
  const [dir, setDir] = useState("")
  const [saved, setSaved] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    api.archive().then(a => { setDir(a.dir); setSaved(a.dir) }).catch(e => setError(String(e)))
  }, [])

  const save = () => api.saveArchive(dir.trim())
    .then(a => { setDir(a.dir); setSaved(a.dir); setError("") })
    .catch(e => setError(String(e)))

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Archivo de entregables</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Cada corrida copia ahí lo que leyó (<code>entrada/</code>) y lo que escribió
          (<code>salida/</code>), con un <code>run.json</code>. Es un respaldo: ninguna
          fase lo lee. Si borran un entregable del repo, se restaura desde el ticket.
          Vacío = apagado.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Input aria-label="Directorio de archivo" value={dir} placeholder="D:/archivo-tickets"
                 onChange={e => setDir(e.target.value)} />
          <Button size="sm" onClick={save} disabled={dir.trim() === saved}>Guardar</Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: `App.tsx`**

Importar `Archive` y renderizarlo tras `<Models />` en la vista `settings`:

```tsx
import { Archive } from "@/Archive"
...
            <Models />
            <Archive />
```

- [ ] **Step 4: check**

`npm run build && npm run lint` → sin errores; los mismos dos warnings de siempre.
A mano: backend arriba, Settings → guardar un directorio real → recargar → sigue ahí;
guardar uno inexistente → error en rojo, el anterior se conserva.

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/frontend/src/api.ts apps/orchestrator/frontend/src/Archive.tsx apps/orchestrator/frontend/src/App.tsx
git commit -m "feat(ui): directorio de archivo en Settings"
```

---

### Task 7: frontend — Restaurar desde la timeline y desde el historial

**Files:**
- Modify: `apps/orchestrator/frontend/src/Timeline.tsx` — props (`onRestore`), rama
  `!h.existe` (~L241)
- Modify: `apps/orchestrator/frontend/src/TicketDetail.tsx` — props, lista de runs
  (~L60-80), diálogo de confirmación
- Modify: `apps/orchestrator/frontend/src/App.tsx:145` — pasar `onRestore`

**Interfaces:**
- Consumes: `api.restore`, `Run.archive_path` (Task 6), `ConfirmDialog`.
- Produces: `TicketDetail` prop `onRestore: (runId: number, overwrite: boolean) => Promise<void>`;
  `Timeline` prop `onRestore: (runId: number) => void`.

- [ ] **Step 1: `App.tsx`**

Donde se renderiza `TicketDetail` (junto a `onRun`), añadir:

```tsx
// NOT through `act`: that helper swallows the error into the global banner, and
// TicketDetail needs the 409 to decide whether to offer the overwrite dialog.
onRestore={(runId, overwrite) => api.restore(detail.ticket.id, runId, overwrite).then(() => refresh())}
```

(`refresh` es la misma función que `act` encadena en `App.tsx:77-80`.)

- [ ] **Step 2: `TicketDetail.tsx`**

Estado y handler:

```tsx
  const [confirmRestore, setConfirmRestore] = useState<number | null>(null)   // run id
  const [restoreError, setRestoreError] = useState("")

  const restore = (runId: number, overwrite = false) =>
    onRestore(runId, overwrite).then(() => setRestoreError("")).catch((e: Error) => {
      // The backend's 409 for a FILE says how to proceed; a tree's 409 doesn't, and
      // the dialog must not offer what the backend will refuse anyway.
      if (String(e.message).includes("overwrite")) setConfirmRestore(runId)
      else setRestoreError(String(e.message))
    })
```

En la lista de runs, después del `span` de `instructions`:

```tsx
                {r.archive_path && (r.artifact_state === "ok" || r.artifact_state === "parcial") && (
                  <Button size="sm" variant="ghost" className="ml-auto h-6 text-xs"
                          onClick={() => restore(r.id)} title={r.archive_path}>
                    Restaurar
                  </Button>
                )}
```

Debajo de la lista: `{restoreError && <p className="text-xs text-destructive">{restoreError}</p>}`.

Diálogo, junto al `ConfirmDialog` de borrado:

```tsx
      <ConfirmDialog open={confirmRestore !== null} title="El archivo ya existe"
                     body="Reemplazarlo con la versión del snapshot. La versión actual se pierde (salvo que otra corrida la haya archivado)."
                     confirmLabel="Reemplazar"
                     onConfirm={() => { const id = confirmRestore!; setConfirmRestore(null); restore(id, true) }}
                     onCancel={() => setConfirmRestore(null)} />
```

Pasar a `Timeline`: `onRestore={runId => restore(runId)}`.

- [ ] **Step 3: `Timeline.tsx`**

Prop nueva `onRestore: (runId: number) => void`. En el `map`, junto a `branch`:

```tsx
        // The most recent good run of this phase that left a snapshot: what the
        // Restore shortcut puts back when the deliverable is gone. Older snapshots are
        // reachable from the run history.
        const restorable = runs.find(r => r.phase === f.fase && r.archive_path
          && (r.artifact_state === "ok" || r.artifact_state === "parcial")) ?? null
```

En la rama `!h.existe` (el `span` ámbar «no se encontró en disco»), envolver y añadir:

```tsx
                    <span className="flex flex-wrap items-center gap-2 text-amber-600 dark:text-amber-500">
                      <span>
                        Artefacto declarado en{" "}
                        <span className="font-mono">{h.ruta}</span>, no se encontró en disco
                      </span>
                      {restorable && (
                        <Button size="sm" variant="outline" className="h-6 text-xs"
                                onClick={() => onRestore(restorable.id)}>
                          Restaurar desde el archivo
                        </Button>
                      )}
                    </span>
```

- [ ] **Step 4: check**

`npm run build && npm run lint` → limpio. A mano, con el archivo encendido: correr
`analyze` sobre un ticket de prueba, borrar el análisis del repo, ver el aviso ámbar con
el botón, restaurar, ver la huella verde de nuevo y la línea `restaurar · ok` en el
journal. Sobreescribir un archivo existente pasa por el diálogo; sobre un árbol el
error se muestra y no hay diálogo.

- [ ] **Step 5: commit**

```bash
git add apps/orchestrator/frontend/src/Timeline.tsx apps/orchestrator/frontend/src/TicketDetail.tsx apps/orchestrator/frontend/src/App.tsx
git commit -m "feat(ui): restaurar un entregable desde la timeline o el historial de corridas"
```

---

### Task 8: documentación

**Files:**
- Modify: `CLAUDE.md` — sección Orchestrator, tras el párrafo del journal
- Modify: `docs/STATUS.md` — decisión 21 (marcar el primer punto como hecho), pendiente
  «copiar el análisis antes del fan-out» (tachar), sesión nueva
- Modify: `apps/orchestrator/README.md` — configurar el archivo, qué hay en cada carpeta,
  restaurar es manual
- Modify: `docs/superpowers/plans/2026-08-17-archivo-de-entregables.md` — checkboxes

- [ ] **Step 1: `CLAUDE.md`**

Añadir después del párrafo «The journal is written after every run…»:

```markdown
**Every run leaves a snapshot, and no phase ever reads it.** With `archive_dir` set
(Settings → `GET/PUT /archivo`, table `settings`, read at snapshot time like
`model_for`), `archive_run` copies to
`<archive_dir>/<org>/<project>/<llave>/<run_id>-<fase>-<YYYYMMDD-HHMM>/`: `entrada/`
at launch (every `docs/tickets/<llave>-*` file plus any tree a previous good run
declared — the human's ticked `DECIDIR` boxes live nowhere else), `salida/` at close
(the declared path, request and journal, taken **after** the journal line so the copy
carries this run), and `run.json` (enough to read the folder after a DB wipe). Trees
over `ARCHIVE_TREE_MAX_FILES`/`_BYTES` are skipped with a journal line — a stamp
clipped to `docs` would otherwise archive the folder every run. A failed copy is a
journal line, never an error run. `runs.archive_path` is the folder; NULL means
nothing archived. **A record, never an input**: a test guards that deleting the
archive changes nothing about the next run. The one door back is
`POST /tickets/{tid}/restaurar {run_id, overwrite}`: it copies that run's `salida/`
to the repo, refuses while a run is active, needs `overwrite` for an existing file,
and **never overwrites a tree** — `implement` ticks `tasks.md` inside the tree `design`
declared, and putting the older tree back would untick real progress. It journals
itself as `restaurar · ok`.
```

- [ ] **Step 2: `STATUS.md`**

- En la decisión 21, primer punto: prefijar `**Hecho el 2026-08-17** —`.
- En «Immediate pending items», tachar «The next two-repo ticket: copy the analysis
  before running the fan-out» con `~~…~~ — **superseded 2026-08-17**: every run snapshots
  its entrada/salida when the archive is on; the pre-fan-out copy is automatic`.
- Sesión nueva (`## Undécima sesión — 2026-08-17`): qué se construyó (dos disparadores,
  restaurar, `run.json`, tope), cuántos tests (contar), y la nota de que **no** corrió
  contra un ticket real todavía.

- [ ] **Step 3: README del orquestador**

Sección «Archivo de entregables»: cómo encenderlo, la estructura de carpetas, qué es
`run.json`, y que restaurar es un botón en el ticket (o el `POST`) — nunca automático.

- [ ] **Step 4: tildar este plan y commit**

```bash
git add CLAUDE.md docs/STATUS.md apps/orchestrator/README.md docs/superpowers/plans/2026-08-17-archivo-de-entregables.md
git commit -m "docs: el archivo de entregables — mecanismo en CLAUDE.md, cierre en STATUS.md"
```

---

## Verificación final (antes de dar por cerrado)

- `pytest tests/ -q` verde, contando los 15 tests nuevos del spec §5 (mapa: §5.1→T2,
  §5.2→T2, §5.3→T3, §5.4→T2, §5.5→T2, §5.6→T2, §5.7→T3, §5.8→T4, §5.9→T5, §5.10→T5,
  §5.11→T5, §5.12→T5, §5.13→T5, §5.14→T5, §5.15→T1).
- `npm run build && npm run lint` limpio.
- Una pasada a mano con el archivo encendido contra `ProvidenceTMSTenant` (el conejillo
  de indias): un `analyze`, borrar el análisis, restaurar desde la UI.
