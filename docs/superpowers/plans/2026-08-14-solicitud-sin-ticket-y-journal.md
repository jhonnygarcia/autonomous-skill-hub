# Solicitud sin ticket + journal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el pipeline arranque también desde una descripción libre del humano
(sin work item de Azure), con llave `R-`, funcionando por UI y con el plugin solo; y
un journal por ticket que registre corridas y hallazgos.

**Architecture:** Una fuente distinta para la etapa 1, no un pipeline nuevo: la
solicitud vive en `tickets.request` (BD) y el runner la proyecta a
`docs/tickets/<llave>-request.md` antes de `analyze`/`brief`; las skills se disparan
por la llave `R-`, no por el prompt (eso habilita el modo solo-plugin). Etapas 2 y 3
no cambian. El journal es `docs/tickets/<llave>-journal.md`: `## Corridas` lo escribe
el runner (determinista), `## Hallazgos` las skills; ninguna fase lo consume.

**Tech Stack:** FastAPI + SQLite sin ORM (backend), React + Vite + Tailwind
(frontend), skills en markdown (plugin). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-08-14-solicitud-sin-ticket-como-punto-de-entrada-design.md`

**Desviaciones del spec, decididas al planificar** (el código gana; el spec no se
reescribe retroactivamente):

1. **§4.1 pedía `ticket_out` devolviendo `str(ado_id)` para que la API no alterne
   tipos.** Eso rompe tres asserts existentes (`test_app.py:16,27,1139` comparan
   contra `int`), y el propio spec hizo criterio de aceptación (§5, §8) que los tests
   existentes queden verdes **sin tocarlos**. Resolución: `ado_id` viaja como está
   almacenado — `int` para Azure, `str` (`"R-7"`) para solicitudes; en TS el tipo es
   `number | string`. Todos los usos en la UI son de display (template strings) y
   funcionan con ambos.
2. **§9 listaba `repo-survey` entre las skills con instrucción de journal.** Un hijo
   del fan-out monta solo su repo y el scratch — no puede alcanzar el journal del repo
   primario. Sus hallazgos van en el survey mismo, y `analysis-consolidation` los
   traslada al journal (Task 5 cierra ese circuito).

## Global Constraints

- **Código y comentarios en inglés.** Strings prompt-facing (lo que lee el agente) en
  inglés; strings UI-facing (`HTTPException.detail`, textos de la UI) en español;
  literales de contrato (`HUELLA`, rutas `/modelos`, claves JSON como `fases`) no se
  traducen en ninguna dirección.
- **Los tests existentes quedan verdes sin editarlos.** Si un test existente falla, el
  cambio está mal, no el test (única excepción documentada: ninguna — la desviación 1
  existe precisamente para no tocarlos).
- **Cero dependencias nuevas** (npm y pip). Textarea nativo, sin componente de
  librería.
- **Tocar una skill exige bump de versión en DOS lugares**: `plugin.json` y el sello
  `by ticket-agent vX.Y.Z` de la plantilla de `ticket-comprehension/SKILL.md`. Este
  plan va a **v0.10.0** (Task 4 el sello, Task 5 el `plugin.json`).
- **Esta máquina: todo por PowerShell** (el bash local no tiene coreutils ni git). En
  PowerShell 5.1 no existe `&&`: encadenar con `;`.
- Backend tests: desde `apps/orchestrator/backend`,
  `.venv/Scripts/python -m pytest tests/test_app.py -v` (o `-k <nombre>`).
  Nunca `uvicorn --reload`.
- Frontend: desde `apps/orchestrator/frontend`, `npm run build` y `npm run lint`
  (baseline exacta: **dos warnings** de lint; ni uno más).
- Plugin: `claude plugin validate .` desde la raíz del repo debe pasar.
- Los tests nuevos deben fallar por la razón declarada antes de implementar (TDD), y
  cada uno debe poder responder «¿qué tendría que romperse para que falle?» — este
  proyecto lleva diez tests placebo encontrados; no agregues el undécimo.

---

## Estructura de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `apps/orchestrator/backend/app.py` | Tasks 1–3: columna `request`, creación XOR, llave `R-`, proyección del archivo, bloque de prompt, journal |
| `apps/orchestrator/backend/tests/test_app.py` | Tests de las Tasks 1–3, al final del archivo |
| `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md` | Task 4: rama de fuente `R-`, dos reglas nuevas, journal, sello |
| `plugins/ticket-agent/commands/analyze.md` | Task 4: aceptar `R-<clave>` y prosa |
| `plugins/ticket-agent/skills/ticket-brief/SKILL.md` | Task 5: rama de fuente + journal |
| `plugins/ticket-agent/commands/brief.md` | Task 5: aceptar `R-<clave>` |
| `plugins/ticket-agent/skills/{change-planning,change-implementation,analysis-consolidation,repo-survey}/SKILL.md` | Task 5: instrucción de journal (survey: variante) |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | Task 5: `0.9.1` → `0.10.0` |
| `apps/orchestrator/frontend/src/{api.ts,TicketList.tsx,App.tsx}` | Task 6: alternancia input/textarea, tipos |
| `CLAUDE.md`, `plugins/ticket-agent/README.md`, `docs/STATUS.md`, spec §9 | Task 7: mecanismo, checklist de instalación, estado |

---

### Task 1: Backend — la columna `request`, las dos formas de creación y la llave `R-`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — la tupla de `ALTER` en `init_db`
  (~línea 582), `class TicketIn` (~línea 653), `create_ticket` (~línea 764),
  `ticket_out` (~línea 978)
- Test: `apps/orchestrator/backend/tests/test_app.py` (agregar al final)

**Interfaces:**
- Consumes: `get_project`, `ticket_row`, `phases_for`, `ticket_out`, `now()` — todos
  existentes en `app.py`.
- Produces: `tickets.request TEXT` (columna); `POST /tickets` acepta
  `{ado_id:int, project}` **o** `{request:str, project}` (exactamente uno);
  `ticket_out` expone `origen: "ado"|"local"` (derivado, nunca almacenado); la llave
  de una solicitud es `ado_id == f"R-{id}"`. Tasks 2, 3 y 6 dependen de esto.

- [ ] **Step 1: Escribir los tests que fallan**

Al final de `tests/test_app.py` (los helpers `_use_fake_claude`, `_phase` y el
fixture `client` ya existen; `pytest` ya está importado):

```python
# --- Solicitud sin ticket: creación y llave (spec §3.1, §4.1, §4.2) ---


def test_a_request_without_a_ticket_mints_a_prefixed_key(client):
    r = client.post("/tickets", json={
        "request": "Necesito un formulario que persista clientes\ncon validación",
        "project": "Demo"})
    assert r.status_code == 201
    t = r.json()
    # The prefix is load-bearing: without it, local request 7 and work item #7
    # write the same analysis file in the same repo.
    assert t["ado_id"] == f"R-{t['id']}"
    assert t["origen"] == "local"
    # Provisional title from the first non-empty line; the analysis overwrites it
    # later exactly like it does for ADO tickets.
    assert t["title"] == "Necesito un formulario que persista clientes"


def test_an_ado_ticket_still_reports_its_origin(client):
    t = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()
    assert t["ado_id"] == 3311        # int, exactly as before — see plan deviation 1
    assert t["origen"] == "ado"
    assert t["title"] is None


@pytest.mark.parametrize("body", [
    {"project": "Demo"},                                   # neither
    {"ado_id": 1, "request": "algo", "project": "Demo"},   # both
    {"request": "   \n  ", "project": "Demo"},             # blank counts as absent
])
def test_creation_demands_exactly_one_source(client, body):
    assert client.post("/tickets", json=body).status_code == 400
```

- [ ] **Step 2: Correr y verificar que fallan por la razón esperada**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "request_without_a_ticket or reports_its_origin or exactly_one_source" -v`
Expected: los tres FAIL — el primero con 422 (Pydantic rechaza el body sin `ado_id`),
`origen` KeyError en el segundo, y 422≠400 en el tercero.

- [ ] **Step 3: Implementar**

(a) En la tupla de `ALTER TABLE` de `init_db`, agregar al final:

```python
            # The free-text request that replaces the work item when there is one.
            # NULL for ADO tickets; its presence is what `origen` derives from.
            "ALTER TABLE tickets ADD COLUMN request TEXT",
```

(b) `TicketIn`:

```python
class TicketIn(BaseModel):
    # Exactly one of the two: an Azure work item id, or the free-text request that
    # replaces it. `create_ticket` enforces the XOR — the Spanish detail belongs in
    # the HTTPException the UI shows, not buried in a validator.
    ado_id: int | None = None
    request: str | None = None
    project: str
```

(c) `create_ticket` completo (reemplaza el actual):

```python
@app.post("/tickets", status_code=201)
def create_ticket(body: TicketIn):
    proj = get_project(body.project)
    if not proj:
        raise HTTPException(400, f"El proyecto '{body.project}' no está dado de alta")
    has_ado = body.ado_id is not None
    has_request = bool(body.request and body.request.strip())
    if has_ado == has_request:
        raise HTTPException(400, "Manda ado_id o request, y exactamente uno de los dos")
    ts = now()
    with db() as c:
        if has_ado:
            cur = c.execute(
                "INSERT INTO tickets(ado_id, org, project, repo_path, repo_label, extra_dirs, "
                "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (body.ado_id, proj["org"], proj["project"], proj["repo_path"],
                 proj["repo_label"], proj["extra_dirs"], ts, ts),
            )
        else:
            # Provisional title so the list doesn't show a bare key until the first
            # run; the analysis overwrites it later, same as for ADO tickets.
            title = next(ln.strip() for ln in body.request.splitlines() if ln.strip())[:80]
            cur = c.execute(
                "INSERT INTO tickets(ado_id, org, project, repo_path, repo_label, extra_dirs, "
                "created_at, updated_at, request, title) VALUES('',?,?,?,?,?,?,?,?,?)",
                (proj["org"], proj["project"], proj["repo_path"], proj["repo_label"],
                 proj["extra_dirs"], ts, ts, body.request, title),
            )
            # The key is minted from the row id: already unique, already monotonic —
            # a second counter would be a second thing to drift. The `R-` prefix keeps
            # local request 7 from colliding with work item #7 on disk and branches.
            # SQLite's INTEGER affinity stores 'R-7' as text untouched.
            c.execute("UPDATE tickets SET ado_id='R-'||id WHERE id=?", (cur.lastrowid,))
    t = ticket_row(cur.lastrowid)
    return ticket_out(t, phases_for(t, [], with_footprint=False))
```

(d) `ticket_out`:

```python
def ticket_out(t: sqlite3.Row, phases: list[dict]) -> dict:
    # `fases` travels here so every producer (POST /tickets, GET /tickets, and the
    # `.ticket` object inside GET /tickets/{tid}) agrees: the frontend's `Ticket` type
    # declares it required, and `json<T>()` never checks that at runtime.
    d = dict(t)
    # Derived, never stored: a stored copy could disagree with `request`.
    d["origen"] = "local" if d.get("request") else "ado"
    return {**d, "status": folded_status(phases), "fases": phases}
```

- [ ] **Step 4: Correr los tests nuevos y verificar que pasan**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "request_without_a_ticket or reports_its_origin or exactly_one_source" -v`
Expected: 5 PASS (3 nombres, el tercero parametrizado ×3).

- [ ] **Step 5: Correr TODA la suite — los existentes no se tocan y quedan verdes**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: todo verde, cero tests existentes editados (`git diff --stat` no debe
mostrar borrados en `test_app.py`, solo líneas agregadas al final).

- [ ] **Step 6: Commit**

```powershell
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): una solicitud sin ticket se crea con llave R-<id>"
```

---

### Task 2: Backend — el runner proyecta la solicitud y el prompt la nombra

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — constantes junto a `BRIEF_REL`
  (~línea 462) y `execute_run` (~líneas 1199–1240)
- Test: `apps/orchestrator/backend/tests/test_app.py` (agregar al final)

**Interfaces:**
- Consumes: `tickets.request` y la llave `R-` de Task 1; `_spy_argv`, `_prompt_from`,
  `_git_init`, `_use_fake_claude` de los tests existentes.
- Produces: `REQUEST_FILE_REL = "docs/tickets/{ado_id}-request.md"` y
  `REQUEST_PROMPT` (constantes que Task 7 documenta); el archivo
  `docs/tickets/<llave>-request.md` reescrito desde la BD en cada corrida de
  `analyze`/`brief` (el contrato que las skills de Tasks 4–5 leen).

- [ ] **Step 1: Escribir los tests que fallan**

```python
# --- Solicitud sin ticket: el runner (spec §4.3) ---


def test_a_request_run_projects_the_file_and_names_it(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    t = client.post("/tickets", json={"request": "Formulario de clientes",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={})
    req = tmp_path / "repo" / "docs" / "tickets" / f"{t['ado_id']}-request.md"
    assert req.read_text(encoding="utf-8") == "Formulario de clientes"
    prompt = _prompt_from(cap)
    # Run 3320 taught that what the prompt doesn't name, the agent invents: both the
    # file's name AND the negation of the work item have to travel.
    assert f"{t['ado_id']}-request.md" in prompt
    assert "does not exist and must not be searched for" in prompt


def test_an_ado_run_gets_no_request_block(client, monkeypatch, tmp_path):
    """The twin. Without it the block could travel in EVERY prompt and nobody would
    notice — and the negation would tell a real work item not to be read."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "must not be searched for" not in _prompt_from(cap)
    assert not (tmp_path / "repo" / "docs" / "tickets" / "3311-request.md").exists()


def test_the_request_file_is_rewritten_from_the_db(client, monkeypatch, tmp_path):
    """The DB is the source of truth; the file is a projection. An edited request
    must never leave a stale file behind."""
    _use_fake_claude(monkeypatch)
    t = client.post("/tickets", json={"request": "Texto original",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={})
    req = tmp_path / "repo" / "docs" / "tickets" / f"{t['ado_id']}-request.md"
    req.write_text("corrupto", encoding="utf-8")
    client.post(f"/tickets/{t['id']}/run", json={})
    assert req.read_text(encoding="utf-8") == "Texto original"


def test_brief_also_projects_the_request(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch)
    t = client.post("/tickets", json={"request": "Front y back",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={"phase": "brief"})
    assert (tmp_path / "repo" / "docs" / "tickets" / f"{t['ado_id']}-request.md").exists()


def test_design_does_not_write_the_request_file(client, monkeypatch, tmp_path):
    """Downstream phases consume the analysis, not the request; and the runner must
    not acquire the habit of writing into the repo near the clean-tree guard."""
    _use_fake_claude(monkeypatch)
    t = client.post("/tickets", json={"request": "Formulario",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={"phase": "design"})
    assert not (tmp_path / "repo" / "docs" / "tickets" / f"{t['ado_id']}-request.md").exists()


def test_a_request_run_keeps_the_mcp(client, monkeypatch):
    """Spec §4.3(b): the MCP stays — a request may cite real work items ("like bug
    #3271") and step 6 of the skill needs it. The prompt negation guards the main id."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    t = client.post("/tickets", json={"request": "como el bug 3271",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={})
    assert "mcp__azure-devops" in cap["argv"]


def test_implement_branches_on_the_request_key(client, monkeypatch, tmp_path):
    """`BRANCH_FMT` and `prepare_branch` must take the string key as-is."""
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/R-1-x/tasks.md")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    t = client.post("/tickets", json={"request": "Formulario",
                                      "project": "Demo"}).json()
    client.post(f"/tickets/{t['id']}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{t['id']}").json()["runs"][0]
    assert run["branch"] == f"ticket-agent/{t['ado_id']}"
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "request_run or rewritten_from_the_db or brief_also_projects or does_not_write_the_request or branches_on_the_request" -v`
Expected: FAIL los que esperan el archivo o el bloque (no existen aún); PASS pueden
salir ya `test_an_ado_run_gets_no_request_block`, `test_design_does_not_write…` y
`test_a_request_run_keeps_the_mcp` (protegen contra regresiones del propio Step 3) y
`test_implement_branches…` (el formato de rama ya acepta strings) — verificar que los
que fallan fallan por «archivo no existe» / «frase ausente», no por 500.

- [ ] **Step 3: Implementar**

(a) Constantes, junto a `BRIEF_REL` (prompt-facing → inglés):

```python
REQUEST_FILE_REL = "docs/tickets/{ado_id}-request.md"
# Both halves are load-bearing: run 3320 taught that what the prompt doesn't name,
# the agent invents — so the file is named AND the work item is negated.
REQUEST_PROMPT = (
    "\n\nThere is no Azure DevOps work item for this request: it does not exist and "
    "must not be searched for. The whole request is in `{path}`, written by the human "
    "who asked for it. Read it; it is the source, and the analysis cites it like any "
    "other document in the repo."
)
```

(b) En `execute_run`, después del bloque de `surveys` (tras la línea
`extras = normalize_dirs(...)`, ~1213) y ANTES de `prev = last_session(...)`:

```python
        if ticket.get("request") and phase in ("analyze", "brief"):
            # Projected from the DB on every launch so an edited request never leaves
            # a stale file behind. Only the two phases that read it: downstream phases
            # consume the analysis, and the runner shouldn't acquire the habit of
            # writing into the repo anywhere near the clean-tree guard's checks.
            req = Path(ticket["repo_path"]) / REQUEST_FILE_REL.format(ado_id=ticket["ado_id"])
            req.parent.mkdir(parents=True, exist_ok=True)
            req.write_text(ticket["request"], encoding="utf-8")
```

(c) En la rama fresh del prompt (el `else` de `if prev:`), después de la línea
`prompt += repos_text(...)` y antes del bloque de `surveys`:

```python
            if ticket.get("request") and phase in ("analyze", "brief"):
                prompt += REQUEST_PROMPT.format(
                    path=REQUEST_FILE_REL.format(ado_id=ticket["ado_id"]))
```

(La proyección corre también en resume — el archivo debe existir aunque la sesión
continúe; el bloque de prompt no, porque esa sesión ya lo recibió al nacer.)

- [ ] **Step 4: Correr los tests nuevos → PASS; luego toda la suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: todo verde.

- [ ] **Step 5: Commit**

```powershell
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): el runner proyecta la solicitud y el prompt niega el work item"
```

---

### Task 3: Backend — el journal por ticket

**Files:**
- Modify: `apps/orchestrator/backend/app.py` — constantes junto a `REQUEST_PROMPT`,
  función nueva `append_journal`, `execute_run` (inicio, tres early-returns y el
  cierre, ~líneas 1168–1354), `SURVEY_PROMPT`/armado de `child_prompt` (~1266)
- Test: `apps/orchestrator/backend/tests/test_app.py` (agregar al final)

**Interfaces:**
- Consumes: `seconds(start, end)` (existente, ~línea 781), `now()`, `split_reserve`,
  la variable local `branch` y `prev` de `execute_run`.
- Produces: `JOURNAL_REL = "docs/tickets/{ado_id}-journal.md"`, `JOURNAL_HEADER`,
  `JOURNAL_CLAIM` (frase que Tasks 4–5 citan textual en las skills:
  `"the runner keeps the `## Corridas` section"` / `"don't write a run line yourself"`),
  `append_journal(ticket, phase, state, detail, note, duration_s, branch, resumed_from)`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# --- Journal por ticket (spec §4.7) ---


def test_the_journal_gets_a_line_per_closed_run(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/9-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    _use_fake_claude(monkeypatch,
                     stamp="parcial — openspec/changes/9-x · falta decidir persistencia")
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    _use_fake_claude(monkeypatch)   # no stamp → the run closes as error/nada
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    text = (tmp_path / "repo" / "docs" / "tickets" / "9-journal.md").read_text(encoding="utf-8")
    corridas = text.split("## Hallazgos")[0]
    assert " · analyze · ok · docs/tickets/9-analysis.md" in corridas
    assert " · design · parcial · openspec/changes/9-x" in corridas
    assert "· reserva: falta decidir persistencia" in corridas
    assert " · design · nada · " in corridas    # error runs are exactly what a
    assert text.startswith("# Journal — 9")     # returning human wants to see


def test_the_journal_lines_stay_out_of_the_findings(client, monkeypatch, tmp_path):
    """The skills append findings at the END of the file; the runner has to insert
    its line BEFORE `## Hallazgos`, or every new run buries itself among findings.
    Mutation that must break this: replacing the insert with a plain append."""
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/9-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    j = tmp_path / "repo" / "docs" / "tickets" / "9-journal.md"
    j.write_text(j.read_text(encoding="utf-8") + "- hallazgo previo\n", encoding="utf-8")
    client.post(f"/tickets/{tid}/run", json={})
    corridas, hallazgos = j.read_text(encoding="utf-8").split("## Hallazgos")
    assert corridas.count(" · analyze · ") == 2
    assert "- hallazgo previo" in hallazgos


def test_the_orchestrated_prompt_claims_the_journal(client, monkeypatch):
    """Two possible writers of a run line (skill standalone, runner orchestrated).
    Without this phrase every orchestrated run would come out twice."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "don't write a run line yourself" in _prompt_from(cap)


def _spy_all_argv(monkeypatch):
    """Every spawn, in order — the fan-out launches several."""
    import asyncio
    calls = []
    original = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        calls.append(args)
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return calls


def test_the_survey_children_also_hear_the_claim(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    calls = _spy_all_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 41, "project": "Demo"}).json()["id"]
    _write_brief(tmp_path, 41)
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    child_prompts = [c[c.index("-p") + 1] for c in calls]
    assert child_prompts and all(
        "don't write a run line yourself" in p for p in child_prompts)


def test_the_journal_is_a_record_not_an_input(client, monkeypatch, tmp_path):
    """Deleting it must change nothing about a later phase: the analysis and the
    plan are the interfaces. If this ever fails, the journal became load-bearing."""
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/9-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    (tmp_path / "repo" / "docs" / "tickets" / "9-journal.md").unlink()
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert client.get(f"/tickets/{tid}").json()["runs"][0]["status"] == "success"
```

Nota sobre `_write_brief`: helper existente (~línea 694 de `test_app.py`); escribe el
brief con routing `SONDEAR: front, backend`, así que el fan-out lanza dos hijos.

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "journal or hear_the_claim" -v`
Expected: FAIL todos menos quizá `record_not_an_input` (que pasa vacuamente hasta que
el journal exista — su valor es de regresión permanente; déjalo escrito igual).

- [ ] **Step 3: Implementar**

(a) Constantes, junto a `REQUEST_PROMPT`:

```python
JOURNAL_REL = "docs/tickets/{ado_id}-journal.md"
JOURNAL_HEADER = "# Journal — {ado_id}\n\n## Corridas\n\n## Hallazgos\n"
# Prompt-facing. The skills know how to write their own run line — that is what makes
# the journal exist in plugin-only sessions. Orchestrated, this phrase claims the run
# line for the runner, whose line is richer (duration, branch, session); otherwise
# every run would come out twice. Findings stay the skill's either way.
JOURNAL_CLAIM = (
    "\n\nThe runner keeps the `## Corridas` section of the journal for this run; "
    "don't write a run line yourself. `## Hallazgos` is still yours."
)
```

(b) La función, junto a `stamp_stat`:

```python
def append_journal(ticket: dict, phase: str, state: str, detail: str,
                   note: str | None = None, duration_s: int | None = None,
                   branch: str | None = None, resumed_from: str | None = None) -> None:
    """One line per closed run — error runs included, with their reason: it's exactly
    what a returning human wants to see. Inserted at the end of `## Corridas`, i.e.
    right before `## Hallazgos`, so that section keeps growing at the end of the file
    where the skills append.

    A record, never an input: no phase reads this file (a test guards that), and a
    failure to write it must never take down the run bookkeeping around it.
    """
    p = Path(ticket["repo_path"]) / JOURNAL_REL.format(ado_id=ticket["ado_id"])
    try:
        text = p.read_text(encoding="utf-8") if p.exists() else \
            JOURNAL_HEADER.format(ado_id=ticket["ado_id"])
        mins, secs = divmod(duration_s or 0, 60)
        line = (f"{now()[:10]} · {phase} · {state} · {detail}"
                + (f" · {mins}m{secs:02d}s" if duration_s is not None else "")
                + (f" · rama {branch}" if branch else "")
                + (f" · ← resume de {resumed_from}" if resumed_from else "")
                + "\n"
                + (f"   · reserva: {note}\n" if note else ""))
        mark = "## Hallazgos"
        i = text.find(mark)
        text = text + line if i < 0 else text[:i] + line + text[i:]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    except OSError:
        pass  # ponytail: a record that can't be written is a lost line, not a lost run
```

(c) En `execute_run`:

- Al inicio, capturar el arranque para la duración:

  ```python
        started = now()
        set_run(run_id, status="running", log_path=str(log_path), started_at=started)
  ```

  (reemplaza el `started_at=now()` actual de la línea ~1168).

- En los TRES early-returns (fallo de `prepare_repos`, `NO_SURVEYS_REASON`,
  `NO_BRIEF_REASON`), una línea tras su `set_run(...)`, antes del `set_ticket`:

  ```python
                append_journal(ticket, phase, "nada", reason)
  ```

  (en los de surveys/brief el detalle es la constante:
  `append_journal(ticket, phase, "nada", NO_SURVEYS_REASON)` y
  `append_journal(ticket, phase, "nada", NO_BRIEF_REASON)`).

- En el cierre principal, después del `set_run(..., artifact_note=note)` (~línea
  1340) y antes del bloque del título:

  ```python
        append_journal(ticket, phase, state, path, note,
                       seconds(started, fin), branch, prev)
  ```

  donde `fin = now()` se captura en una variable justo antes del `set_run` del
  cierre (y ese `set_run` usa `finished_at=fin`), para que la línea y la BD digan
  el mismo instante.

(d) La frase del claim:

- En la rama fresh del prompt, al final (después de `adjustment_text`):
  `prompt += JOURNAL_CLAIM`. También en la rama resume:
  `prompt = (instructions or "") + RESUME_STAMP_REMINDER + JOURNAL_CLAIM` — una
  continuación también cierra una corrida, y el runner también la registra.
- En el armado de `child_prompt` del fan-out, después de `adjustment_text`:
  `child_prompt += JOURNAL_CLAIM`.

- [ ] **Step 4: Correr los tests nuevos → PASS; luego toda la suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: todo verde. Atención a los tests existentes de prompts
(`test_resume_does_not_resend_the_slash_command`, `test_analyze_prompt_keeps_extra_repos_readable`):
agregan asserts de contenido, no de igualdad exacta, así que el claim no los rompe —
si alguno falla, la causa es un assert de igualdad que hay que mirar, no silenciar.

- [ ] **Step 5: Mutación manual (no queda en la suite): verificar que el test de
  inserción muerde**

Cambiar temporalmente `text[:i] + line + text[i:]` por `text + line`, correr
`-k lines_stay_out_of_the_findings`, ver FAIL, revertir.

- [ ] **Step 6: Commit**

```powershell
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): journal por ticket - el runner registra cada corrida cerrada"
```

---

### Task 4: Plugin — `ticket-comprehension` y el comando `analyze`

**Files:**
- Modify: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`
- Modify: `plugins/ticket-agent/commands/analyze.md`

Sin test ejecutable: la verificación es por lectura y grep (una skill es markdown), y
`claude plugin validate .` como check estructural. La prueba real es la corrida en
vivo de STATUS (Task 7 la deja anotada como pendiente).

**Interfaces:**
- Consumes: el contrato de Task 2 (`docs/tickets/<id>-request.md` existe cuando el
  runner lanzó una solicitud) y la frase de `JOURNAL_CLAIM` de Task 3 (citada
  textual: «the runner keeps the `## Corridas` section»).
- Produces: la rama `R-` que Task 5 replica en `ticket-brief`; el sello `v0.10.0`.

- [ ] **Step 1: La rama de fuente en §2 (Recolección)**

Insertar al INICIO de la sección «## 2. Collection (all read-only)», antes del paso 1
actual:

```markdown
**Local request (`R-` key) — the source cut.** If the id starts with `R-`, there is
no work item: the whole request is `docs/tickets/<id>-request.md`, written by the
human who asked for it. If that file doesn't exist, stop and guide the user to
create it (same pattern as the missing `.claude/ticket-agent.json` in step 1).
Skip steps 1–4 below — there is no work item, no comments, no relations, no
attachments to read. Steps 5, 6 and 7 still apply in full: search the wiki with the
request's key terms, read every reference the request cites (a repo document by
path, a work item by id — "like bug #3271" is a citation), and absorb the host
project's rules. If the MCP is not connected, cited work items and the wiki go
under "Missing information" with that cause and the analysis **continues**: the
request file is the source; the MCP is supplementary here, not a precondition.
```

- [ ] **Step 2: Las dos reglas nuevas**

Después de las dos golden rules del encabezado, agregar:

```markdown
For a local request (`R-` key), two more rules, siblings of the golden ones:

3. **What the request doesn't say is not deduced in silence.** A work item went
   through refinement; a paragraph typed at 11pm did not. Every gap becomes a
   `- [ ] **DECIDIR**` with a proposal under "Decisiones para ti", or a
   `- [ ] **BLOQUEA**` when no default is defensible.
4. **Acceptance criteria are proposed, never invented.** A work item brings them; a
   request has none. Draft them and mark them as a proposal (`DECIDIR`) — never
   present them as given. A criterion presented as given reads with the same
   confidence as one that came from a refined work item, and nobody verifies it.
```

- [ ] **Step 3: La instrucción del journal**

Junto a la sección de cierre que define la `HUELLA` (~línea 190), agregar:

```markdown
**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Close
by appending one line to `## Corridas` — `<date> · analyze · <ok|parcial|nada> ·
<path>` — **unless the prompt says the runner keeps the `## Corridas` section**, in
which case the run line is the runner's and only `## Hallazgos` is yours.
```

- [ ] **Step 4: El sello de versión**

En la plantilla (~línea 86): `**Analyzed:** <date> by ticket-agent v0.9.1` →
`v0.10.0`.

- [ ] **Step 5: El comando `analyze.md`**

Reemplazar la última línea («If "$ARGUMENTS" is empty or not a work item number, ask
for the ID and stop.») por:

```markdown
If "$ARGUMENTS" is a work item number or an `R-` key (`R-7`, `R-form-clientes`),
analyze that id. If it is prose — a described need, not an id — derive a short
kebab-case slug from it, write the prose verbatim to
`docs/tickets/R-<slug>-request.md` (pick a different slug if that file already
exists; never overwrite), and continue as if you had been given `R-<slug>`. If
"$ARGUMENTS" is empty, ask for the ID or the request and stop.
```

- [ ] **Step 6: Verificar por grep y validador**

En PowerShell, desde la raíz:

```powershell
Select-String -Path plugins/ticket-agent/skills/ticket-comprehension/SKILL.md -Pattern "R- key","don't|runner keeps","v0.10.0"
claude plugin validate .
```

Expected: la rama, el journal y el sello presentes; `v0.9.1` ya no aparece en el
SKILL.md; el validador pasa.

- [ ] **Step 7: Commit**

```powershell
git add plugins/ticket-agent/skills/ticket-comprehension/SKILL.md plugins/ticket-agent/commands/analyze.md
git commit -m "feat(plugin): analyze entiende solicitudes R- (archivo o prosa) y alimenta el journal"
```

---

### Task 5: Plugin — las otras cinco skills, `brief` y la versión

**Files:**
- Modify: `plugins/ticket-agent/skills/ticket-brief/SKILL.md`
- Modify: `plugins/ticket-agent/commands/brief.md`
- Modify: `plugins/ticket-agent/skills/change-planning/SKILL.md`
- Modify: `plugins/ticket-agent/skills/change-implementation/SKILL.md`
- Modify: `plugins/ticket-agent/skills/analysis-consolidation/SKILL.md`
- Modify: `plugins/ticket-agent/skills/repo-survey/SKILL.md`
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: la rama de fuente de Task 4 (mismo texto, adaptado) y `JOURNAL_CLAIM`.
- Produces: plugin `v0.10.0` completo.

- [ ] **Step 1: `ticket-brief/SKILL.md` — la misma rama de fuente**

Insertar al inicio de su sección de recolección, completo:

```markdown
**Local request (`R-` key) — the source cut.** If the id starts with `R-`, there is
no work item: the whole request is `docs/tickets/<id>-request.md`, written by the
human who asked for it. If that file doesn't exist, stop and guide the user to
create it. Skip the work-item steps below — there is no work item, no comments, no
relations, no attachments to read; the brief quotes the request's own words where
the work item's description would go, and its acceptance criteria are proposals
(`DECIDIR`), never given. Wiki search, cited references and the host project's
rules still apply in full. If the MCP is not connected, cited work items and the
wiki go under "Missing information" with that cause and the brief **continues**:
the request file is the source; the MCP is supplementary here, not a precondition.
```

Y en su sección de cierre (junto a la `HUELLA`), el bloque de journal:

```markdown
**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Close
by appending one line to `## Corridas` — `<date> · brief · <ok|parcial|nada> ·
<path>` — **unless the prompt says the runner keeps the `## Corridas` section**, in
which case the run line is the runner's and only `## Hallazgos` is yours.
```

- [ ] **Step 2: `commands/brief.md`**

Reemplazar su última línea por:

```markdown
If "$ARGUMENTS" is empty, or is neither a work item number nor an `R-` key
(`R-7`, `R-form-clientes`), ask for the ID and stop.
```

(sin rama de prosa: el fan-out standalone es manual de todos modos, spec §4.6).

- [ ] **Step 3: journal en `change-planning` y `change-implementation`**

En la sección de cierre de cada una (junto a su `HUELLA`), completo y con su nombre
de fase:

```markdown
**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Close
by appending one line to `## Corridas` — `<date> · plan · <ok|parcial|nada> ·
<path>` — **unless the prompt says the runner keeps the `## Corridas` section**, in
which case the run line is the runner's and only `## Hallazgos` is yours.
```

(en `change-implementation`, la línea dice `implement` en lugar de `plan`), y una
frase extra solo en `change-implementation`:

```markdown
In this phase, findings that belong to a reviewed task go to `## Review notes` in
`tasks.md` as they do today; `## Hallazgos` in the journal is for what falls
outside the change entirely.
```

- [ ] **Step 4: `repo-survey` y `analysis-consolidation` — el circuito del fan-out**

En `repo-survey/SKILL.md` (NO el bloque estándar — un hijo no alcanza el journal):

```markdown
**Journal.** This session usually can't reach the primary repo's journal — a
fan-out child mounts only its own repo and the scratch. Findings outside the
survey's scope still matter: put them in the survey itself under a final
`## Hallazgos fuera de alcance` section. The consolidation reads every survey and
carries them to the journal.
```

En `analysis-consolidation/SKILL.md`, en su sección de cierre, completo:

```markdown
**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Carry
every `## Hallazgos fuera de alcance` entry from the surveys there too — the
children can't reach the journal; this session is the one that closes that loop.
Close by appending one line to `## Corridas` — `<date> · consolidate ·
<ok|parcial|nada> · <path>` — **unless the prompt says the runner keeps the
`## Corridas` section**, in which case the run line is the runner's and only
`## Hallazgos` is yours.
```

- [ ] **Step 5: `plugin.json`**: `"version": "0.9.1"` → `"0.10.0"`.

- [ ] **Step 6: Verificar**

```powershell
Select-String -Path plugins/ticket-agent/skills/*/SKILL.md -Pattern "## Hallazgos" | Measure-Object
claude plugin validate .
```

Expected: las seis skills mencionan el journal (cinco el bloque, `repo-survey` la
variante); el validador pasa; `Select-String -Path plugins/ticket-agent -Pattern "0.9.1" -Recurse`
no devuelve nada.

- [ ] **Step 7: Commit**

```powershell
git add plugins/ticket-agent
git commit -m "feat(plugin): brief acepta R-, todas las skills alimentan el journal, v0.10.0"
```

---

### Task 6: Frontend — la alternancia ticket/solicitud

**Files:**
- Modify: `apps/orchestrator/frontend/src/api.ts`
- Modify: `apps/orchestrator/frontend/src/TicketList.tsx`
- Modify: `apps/orchestrator/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `POST /tickets` con las dos formas (Task 1); `origen` en `Ticket`.
- Produces: `api.create(body: {ado_id?: number; request?: string}, project: string)`;
  `onAdd(body: {ado_id?: number; request?: string})`.

- [ ] **Step 1: `api.ts` — tipos y `create`**

```ts
export type Ticket = {
  id: number
  // number for Azure work items, the string key ("R-7") for local requests — the
  // backend returns each as stored, and every use here is display.
  ado_id: number | string
  origen: "ado" | "local"
  request: string | null
  org: string; project: string
  status: string; created_at: string; updated_at: string
  title: string | null   // its comment stays as-is
  fases: Phase[]         // its comment stays as-is
}
```

(los comentarios existentes de `title` y `fases` no se tocan; solo se insertan
`origen` y `request` y se ensancha el tipo de `ado_id`).

En `ActiveRun`, `ado_id: number | string`. Y `create`:

```ts
  create: (body: { ado_id?: number; request?: string }, project: string) =>
    fetch("/api/tickets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, project }),
    }).then(r => json<Ticket>(r)),
```

- [ ] **Step 2: `App.tsx` — el handler**

```ts
  const addTicket = (body: { ado_id?: number; request?: string }) =>
    project && act(() => api.create(body, project.name))
```

(la llamada `<TicketList ... onAdd={addTicket}` no cambia).

- [ ] **Step 3: `TicketList.tsx` — la alternancia**

Props: `onAdd: (body: { ado_id?: number; request?: string }) => void`. Estado y
handlers:

```tsx
  const [adoId, setAdoId] = useState("")
  const [request, setRequest] = useState("")
  const [mode, setMode] = useState<"ado" | "request">("ado")
  const add = () => { onAdd({ ado_id: Number(adoId) }); setAdoId("") }
  const addRequest = () => { onAdd({ request: request.trim() }); setRequest("") }
```

Reemplazar el contenido del `<div className="rounded-md border border-border p-3">`
del alta por:

```tsx
      <div className="rounded-md border border-border p-3">
        <div className="flex gap-1" role="tablist" aria-label="Origen del ticket">
          {([["ado", "Ticket de Azure"], ["request", "Solicitud directa"]] as const)
            .map(([k, label]) => (
              <Button key={k} size="sm" role="tab" aria-selected={mode === k}
                      variant={mode === k ? "secondary" : "ghost"}
                      onClick={() => setMode(k)}>
                {label}
              </Button>
            ))}
        </div>
        {mode === "ado" ? (
          <>
            <label htmlFor="ado-id" className="mt-3 block text-xs font-medium">
              ID del work item
            </label>
            {/* el Input + botón + línea de ayuda actuales, sin cambios */}
          </>
        ) : (
          <>
            <label htmlFor="request-text" className="mt-3 block text-xs font-medium">
              Qué necesitas
            </label>
            {/* Native textarea, mirroring the Input component's classes: the answer
                arrives while the decision is being made — the placeholder IS the
                cheapest quality lever this feature has (spec §4.5). */}
            <textarea id="request-text" rows={4} value={request}
                      onChange={e => setRequest(e.target.value)}
                      placeholder={"Qué necesitas, dónde vive hoy (pantalla, módulo, repo), por qué, y cómo sabrás que quedó bien."}
                      className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/50" />
            <div className="mt-2 flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                La primera línea será el título en la lista.
              </p>
              <Button onClick={addRequest} disabled={!request.trim()}>+ Añadir</Button>
            </div>
          </>
        )}
      </div>
```

El `add()` del modo ADO y su input numérico (con su filtro `\D` y su Enter) quedan
como están. `#{t.ado_id}` renderiza `#R-7` sin tocarlo; no se agrega badge de origen.

- [ ] **Step 4: Verificar**

Run (desde `apps/orchestrator/frontend`): `npm run build; npm run lint`
Expected: build verde; lint en su baseline exacta de dos warnings. Verificación
manual por lectura: `Select-String -Path src/*.tsx -Pattern "Number\(adoId\)"`
devuelve solo el handler del modo ADO.

- [ ] **Step 5: Commit**

```powershell
git add apps/orchestrator/frontend/src/api.ts apps/orchestrator/frontend/src/TicketList.tsx apps/orchestrator/frontend/src/App.tsx
git commit -m "feat(ui): alta por solicitud directa junto al ticket de Azure"
```

---

### Task 7: Documentación — el mecanismo, el checklist y el estado

**Files:**
- Modify: `CLAUDE.md` (sección Architecture, cerca del párrafo «The ticket copies…»)
- Modify: `plugins/ticket-agent/README.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/superpowers/specs/2026-08-14-solicitud-sin-ticket-como-punto-de-entrada-design.md`
  (solo la nota de §9 sobre `repo-survey` — desviación 2 del encabezado)

**Interfaces:**
- Consumes: todo lo anterior, ya commiteado.
- Produces: nada que otro task consuma; es el cierre.

- [ ] **Step 1: `CLAUDE.md` — el mecanismo** (en inglés; la regla de los dos
  archivos: el README es el checklist, aquí va el porqué). Agregar un párrafo tras el
  del ticket que copia datos del proyecto, cubriendo: las dos formas de
  `POST /tickets` y el XOR; la llave `R-<rowid>` acuñada del id de fila y el reparto
  del espacio de nombres con los slugs del modo standalone; que `origen` es derivado
  de `request` y por qué no hay columna; la proyección del `-request.md` solo en
  `analyze`/`brief` y por qué (la BD es la fuente, el archivo la proyección
  reescrita); que el MCP se queda y la negación viaja en el prompt
  (`REQUEST_PROMPT`); el journal (`## Corridas` del runner con inserción antes de
  `## Hallazgos`, `JOURNAL_CLAIM` reclamándolo, y la regla «registro, nunca insumo»
  con su test); y la desviación de tipos de `ado_id` (int o str según origen).

- [ ] **Step 2: `plugins/ticket-agent/README.md` — el checklist** (para el dev de
  fuera): cómo usar una solicitud sin orquestador — escribir
  `docs/tickets/R-<slug>-request.md` y correr `/ticket-agent:analyze R-<slug>`, o
  directamente `/ticket-agent:analyze <prosa>`; que los slugs son del humano y los
  números del orquestador; qué es el journal y qué sección es de quién; y que con
  solicitud el MCP es opcional (sin él, lo citado cae en Missing information).

- [ ] **Step 3: `docs/STATUS.md`** — entrada de sesión nueva (fecha 2026-08-14):
  qué se construyó (las dos formas de entrada, el journal, v0.10.0, conteo de tests
  backend resultante), la desviación 1 del plan, y en pendientes inmediatos:
  «primera corrida real de una solicitud vaga por la ruta de fan-out — mide si el
  análisis sale con DECIDIR honestos o con alcance inventado (spec §6)» y «probar el
  modo solo-plugin de punta a punta en un repo real».

- [ ] **Step 4: La nota en el spec** — en §9, la fila de las cuatro skills: anotar
  que `repo-survey` recibió la variante (hallazgos en el survey; la consolidación
  los traslada), con «decidido al planificar» y la razón (un hijo no monta el repo
  primario).

- [ ] **Step 5: Verificación final completa**

```powershell
cd apps/orchestrator/backend; .venv/Scripts/python -m pytest tests/ -v; cd ../frontend; npm run build; npm run lint; cd ../../..; claude plugin validate .
```

Expected: todo verde, baseline de lint intacta, validador ok.

- [ ] **Step 6: Commit**

```powershell
git add CLAUDE.md plugins/ticket-agent/README.md docs/STATUS.md docs/superpowers/specs/2026-08-14-solicitud-sin-ticket-como-punto-de-entrada-design.md
git commit -m "docs: solicitud sin ticket y journal - mecanismo, checklist y estado"
```
