# Avance por fases, huellas y timeline — Plan de implementación

> **Ejecutado el 2026-08-10** con `subagent-driven-development`, 8 tareas, 16 commits
> (`8eeb632..04afa60`) más la oleada de arreglos de la revisión final. Las casillas están
> marcadas; lo que se desvió del texto de abajo está anotado en `docs/STATUS.md`, sección
> "Lo aprendido". Dos correcciones que este documento arrastra y que el código **no**
> sigue: el `leer_huella` de la Tarea 2 tenía un `.strip("\n")` que trata su argumento
> como conjunto de caracteres, y la expresión de `rutas` de la Tarea 6 producía la ruta
> del directorio cuando la huella tenía un solo archivo dentro. Ambas se arreglaron en
> ejecución; el código manda sobre este plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Que cada corrida declare qué artefacto dejó, que el backend derive de esas
declaraciones el avance del ticket, y que la UI lo muestre como un recorrido de fases con
el artefacto legible dentro de la app.

**Architecture:** Las skills cierran con un sello `HUELLA: <ok|parcial|nada> — <ruta>`
que el runner ancla en la **última** coincidencia del log y persiste en dos columnas
nuevas de `runs`. `tickets.status` y `current_phase` dejan de ser fuente: el avance se
pliega de `runs` en cada lectura. El frontend gana un `Timeline.tsx` con una fila por
fase, su acción y su artefacto, servido por un endpoint de lectura con validación de
ruta en cuatro pasos.

**Tech Stack:** Python 3 + FastAPI + sqlite3 sin ORM (backend), pytest con
`tests/fake_claude.py` como doble del CLI; React 19 + TypeScript + Vite + Tailwind v4 +
shadcn (frontend), oxlint. Markdown para las skills del plugin.

## Global Constraints

- **Documentación, comentarios y textos de UI en español.** El repo es consistente en eso.
- **Ninguna dependencia nueva**, ni de npm ni de pip. El markdown se muestra en
  monoespaciada, sin renderizador.
- **Tocar una skill obliga a subir `version` en `plugins/ticket-agent/.claude-plugin/plugin.json`**
  a `0.5.0`. Esa versión es la clave de cache de `claude plugin update`.
- **El sello se ancla en la última coincidencia, jamás en la presencia.** El cuerpo de la
  skill viaja en el log (el `tool_result` de cargarla) y contiene los sellos literalmente.
- **`claude -p` sale con 0 aunque el agente no haya hecho nada.** El código de salida
  nunca decide por sí solo el estado de una corrida.
- **El visor de artefactos es de lectura y no se simplifica su validación**: declarada +
  `realpath` dentro de los repos del ticket + archivo regular + tope de 512 KB.
- Fases `implement`, `test`, `guards` y `pr` siguen declaradas y **no ejecutables**.
- Trabajamos directamente sobre `main`. No se crean ramas.
- Backend: correr siempre `uvicorn` **sin `--reload`** (deja huérfanos en Windows).

## Estructura de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md` | Cierra con `HUELLA:` apuntando al análisis | 1 |
| `plugins/ticket-agent/skills/change-planning/SKILL.md` | Cambia `PLAN:` por `HUELLA:` apuntando al change | 1 |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | `version` → `0.5.0` | 1 |
| `apps/orchestrator/backend/app.py` | Migración, lectura del sello, plegado, endpoint del visor | 2, 3, 4 |
| `apps/orchestrator/backend/tests/fake_claude.py` | Emite sellos `HUELLA:` y la fuga del cuerpo de la skill | 2 |
| `apps/orchestrator/backend/tests/test_app.py` | Todos los tests nuevos | 2, 3, 4 |
| `apps/orchestrator/frontend/src/api.ts` | Tipos `Fase`/`Huella`/`Artefacto` y la llamada al visor | 5 |
| `apps/orchestrator/frontend/src/estado.ts` | Etiquetas de fase, colores y la regla de habilitación | 5 |
| `apps/orchestrator/frontend/src/Timeline.tsx` | **Nuevo.** Una fila por fase, su acción y su artefacto | 6 |
| `apps/orchestrator/frontend/src/TicketDetail.tsx` | Cabecera adelgazada + Timeline + Log colapsado | 6, 7 |
| `apps/orchestrator/frontend/src/index.css` | Tokens de estado para el acabado visual | 8 |

---

### Task 1: El contrato de cierre en las dos skills

**Files:**
- Modify: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md` (añadir sección de cierre al final de `## 4. Cierre según autonomía`)
- Modify: `plugins/ticket-agent/skills/change-planning/SKILL.md:129-152` (§7 y "Manejo de errores")
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json:5`

**Interfaces:**
- Consumes: nada.
- Produces: el formato literal `HUELLA: <ok|parcial|nada> — <ruta o motivo>` que la Tarea 2
  parsea con la expresión regular `r"HUELLA: (ok|parcial|nada)\s*[—-]\s*(.+)"`.

- [x] **Step 1: Añadir el sello a `ticket-comprehension`**

En `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`, justo **después** del
bloque `## 4. Cierre según autonomía` y **antes** de `## Manejo de errores`, insertar:

```markdown
**Regla obligatoria de cierre.** La última línea de tu resumen —sin nada después— tiene
que ser exactamente este sello, seguido de la ruta del análisis relativa al repo
principal:

- `HUELLA: ok — docs/tickets/<id>-analysis.md` — el análisis está escrito y completo.
- `HUELLA: parcial — docs/tickets/<id>-analysis.md` — está escrito, pero con reservas
  (no pudiste leer el padre, faltan adjuntos, quedó "Información faltante" con peso).
  Explica la reserva en el resumen, no en la línea del sello.
- `HUELLA: nada — <motivo>` — no se escribió el archivo. El motivo va detrás del guion.

El orquestador lee esta línea para decidir si la corrida vale: el código de salida del
CLI no lo dice, porque sale en 0 aunque te hayas detenido sin escribir nada.
```

- [x] **Step 2: Cambiar el sello de `change-planning`**

En `plugins/ticket-agent/skills/change-planning/SKILL.md`, en la sección
`**Regla obligatoria de cierre.**` de §7, sustituir el párrafo introductorio y las tres
viñetas por:

```markdown
**Regla obligatoria de cierre.** La última línea del resumen —sin nada después— tiene
que ser exactamente uno de estos tres sellos, seguido de la ruta del change relativa al
repo principal (o del motivo, en el caso de `nada`). El orquestador lee esta línea para
decidir si la corrida vale: el código de salida del CLI no lo dice, porque sale en 0
aunque el agente se haya detenido sin escribir nada.

- `HUELLA: ok — openspec/changes/<id>-<slug>` — el change está escrito y
  `openspec validate --changes --no-interactive` pasó.
- `HUELLA: parcial — openspec/changes/<id>-<slug>` — el change se escribió pero la
  validación no pasó (dos intentos) o no llegó a correrse. Explica la reserva en el
  resumen.
- `HUELLA: nada — <motivo>` — no se llegó a escribir ningún change: falta el análisis,
  `npx` no está disponible, o `openspec init` falló.
```

- [x] **Step 3: Actualizar las cuatro referencias al sello viejo en "Manejo de errores"**

En el mismo archivo, en `## Manejo de errores`, sustituir cada mención:

| Antes | Después |
|---|---|
| `cierra con \`PLAN: no-escrito\`` (falta el análisis) | `cierra con \`HUELLA: nada — falta docs/tickets/<id>-analysis.md\`` |
| `cierra con \`PLAN: no-escrito\`` (`npx`/`openspec init`) | `cierra con \`HUELLA: nada — npx no disponible u openspec init falló\`` |
| `cierra con \`PLAN: validado\` o \`PLAN: sin-validar\` según haya pasado la validación` | `cierra con \`HUELLA: ok\` o \`HUELLA: parcial\` según haya pasado la validación` |
| `cierra con \`PLAN: sin-validar\`` (validate falla dos veces) | `cierra con \`HUELLA: parcial\`` |

- [x] **Step 4: Subir la versión del plugin**

En `plugins/ticket-agent/.claude-plugin/plugin.json`, cambiar `"version": "0.4.2"` por
`"version": "0.5.0"`.

- [x] **Step 5: Verificar que no queda ningún `PLAN:` en las skills y que el plugin valida**

```bash
cd D:/Companies/Jorge.Gutierrez/autonomous-skill-hub
grep -rn "PLAN:" plugins/ticket-agent/skills/   # esperado: sin resultados
grep -rn "HUELLA:" plugins/ticket-agent/skills/ # esperado: 3 en cada SKILL.md + las de errores
claude plugin validate .                        # esperado: OK
```

- [x] **Step 6: Commit**

```bash
git add plugins/ticket-agent
git commit -m "feat(ticket-agent): las dos skills cierran con el sello HUELLA (v0.5.0)"
```

---

### Task 2: Migración de `runs` y lectura del sello para toda fase

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (`init_db`, `execute_run`, nueva `leer_huella`)
- Modify: `apps/orchestrator/backend/tests/fake_claude.py`
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: el formato de sello de la Tarea 1.
- Produces:
  - `leer_huella(log_path: Path) -> tuple[str, str] | None` — `(estado, resto)` de la
    **última** coincidencia, o `None` si no hay ninguna. `estado` ∈ `{"ok","parcial","nada"}`.
  - Columnas `runs.artifact_state TEXT` y `runs.artifact_path TEXT`, rellenadas al cerrar
    cada corrida. Una corrida con `artifact_state IN ('ok','parcial')` tiene en
    `artifact_path` una **ruta relativa al `repo_path` del ticket**; con `'nada'`, un motivo.
  - La columna `tickets.current_phase` deja de existir.
  - Helper de test `_use_fake_claude(monkeypatch, fail=False, huella=None, skill_leak=False)`.

- [x] **Step 1: Enseñar a `fake_claude.py` a emitir el sello nuevo**

Sustituir en `apps/orchestrator/backend/tests/fake_claude.py` el bloque
`FAKE_SKILL_LEAK` y el bloque `sello` por:

```python
if os.environ.get("FAKE_SKILL_LEAK") == "1":
    # Imita el cuerpo de un SKILL.md colándose en el log (el tool_result de cargar la
    # skill): trae los tres sellos en prosa, ANTES del sello de cierre real, tal como
    # pasa en la corrida de verdad.
    cuerpo = (
        "## Cierre\n"
        "Termina siempre con una de estas tres líneas exactas:\n"
        "HUELLA: ok — docs/tickets/<id>-analysis.md\n"
        "HUELLA: parcial — docs/tickets/<id>-analysis.md\n"
        "HUELLA: nada — <motivo>\n"
    )
    print('{"type":"tool_result","text":' + json.dumps(cuerpo) + '}')
sello = os.environ.get("FAKE_HUELLA")
if sello:
    # Simula el sello de cierre obligatorio de las skills.
    print('{"type":"assistant","text":"resumen del cierre. HUELLA: ' + sello + '"}')
```

- [x] **Step 2: Adaptar el helper de tests**

En `apps/orchestrator/backend/tests/test_app.py`, sustituir `_use_fake_claude` por:

```python
def _use_fake_claude(monkeypatch, fail=False, huella=None, skill_leak=False):
    fake = Path(__file__).parent / "fake_claude.py"
    monkeypatch.setenv("ORCH_CLAUDE_CMD", json.dumps([sys.executable, str(fake)]))
    monkeypatch.setenv("FAKE_FAIL", "1" if fail else "0")
    monkeypatch.setenv("FAKE_SKILL_LEAK", "1" if skill_leak else "0")
    if huella is None:
        monkeypatch.delenv("FAKE_HUELLA", raising=False)
    else:
        monkeypatch.setenv("FAKE_HUELLA", huella)
```

- [x] **Step 3: Escribir los tests que fallan (los cuatro casos del sello, en ambas fases)**

Sustituir en `test_app.py` los siete tests que hoy hablan de `plan_sello`/`PLAN:`
(`test_run_design_deja_el_ticket_planned`, `test_design_sello_validado_deja_planned`,
`test_design_sello_sin_validar_deja_planned`, `test_design_sello_no_escrito_deja_error`,
`test_design_ignora_los_sellos_del_cuerpo_de_la_skill`,
`test_design_sin_sello_se_trata_como_error`, `test_sello_no_se_exige_en_analyze`) por:

```python
def test_huella_ok_deja_la_corrida_bien(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success"
    assert run["artifact_state"] == "ok"
    assert run["artifact_path"] == "docs/tickets/3323-analysis.md"


def test_huella_parcial_la_corrida_vale_y_conserva_la_reserva(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="parcial — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "parcial"


def test_huella_nada_deja_la_corrida_en_error(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="nada — falta el análisis de la Fase 1")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"
    assert "falta el análisis" in run["artifact_path"]


def test_sin_sello_la_corrida_es_error_en_cualquier_fase(client, monkeypatch):
    """`claude -p` sale con 0 aunque el agente se haya detenido sin hacer nada. Sin
    sello no hay forma de distinguir eso de una corrida real. Antes analyze estaba
    exento; ahora el contrato es de todas."""
    _use_fake_claude(monkeypatch)  # sin FAKE_HUELLA
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"
    assert "no declaró huella" in run["artifact_path"]


def test_el_sello_se_ancla_en_la_ultima_coincidencia(client, monkeypatch):
    """El tool_result de cargar el SKILL.md deja los tres sellos en prosa dentro del
    log, ANTES del cierre real. Comprobar presencia hace que la comprobación se
    encuentre a sí misma y dé por buena una corrida que cerró con `nada`."""
    _use_fake_claude(monkeypatch, skill_leak=True, huella="nada — falta el análisis")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"


def test_sello_legado_PLAN_se_sigue_entendiendo(client, monkeypatch):
    """Los logs de las corridas del 3323 se escribieron con `PLAN:`. Traducirlos evita
    que el historial existente aparezca como fallido el día que se mira el timeline."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    import app
    log = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["log_path"])
    log.write_text("bla\nPLAN: validado — todo bien\n", encoding="utf-8")
    assert app.leer_huella(log) == ("ok", "todo bien")
    log.write_text("PLAN: sin-validar — falló\n", encoding="utf-8")
    assert app.leer_huella(log)[0] == "parcial"
    log.write_text("PLAN: no-escrito — sin análisis\n", encoding="utf-8")
    assert app.leer_huella(log)[0] == "nada"


def test_current_phase_ya_no_existe(client):
    import app
    with app.db() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(tickets)")}
    assert "current_phase" not in cols
    assert {"artifact_state", "artifact_path"} <= {
        r["name"] for r in app.db().execute("PRAGMA table_info(runs)")}
```

Además, en `test_create_and_list_ticket` (línea 13) **quitar** `and t["current_phase"] == "analyze"`
del assert, que si no falla al desaparecer la columna.

- [x] **Step 4: Correr los tests y ver que fallan**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v -k "huella or sello or current_phase"
```
Esperado: FAIL — `KeyError: 'artifact_state'` y `AttributeError: module 'app' has no attribute 'leer_huella'`.

- [x] **Step 5: Añadir las columnas y borrar `current_phase`**

En `apps/orchestrator/backend/app.py`, dentro de `init_db`, ampliar la tupla del bucle
`for alter in (...)`:

```python
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
```

Y en el `CREATE TABLE IF NOT EXISTS tickets(...)` del `executescript`, **borrar** la línea
`current_phase TEXT NOT NULL DEFAULT 'analyze',`. En `CREATE TABLE IF NOT EXISTS runs(...)`,
añadir tras `log_path TEXT,`:

```sql
              artifact_state TEXT,
              artifact_path TEXT,
```

- [x] **Step 6: Escribir `leer_huella` y aplicarla a toda fase**

En `app.py`, sustituir la función `now()` por `now()` seguida de (es decir, insertar
justo después de `now()`):

```python
# El sello de cierre de las skills. Se acepta `PLAN:` como alias legado porque los logs
# de las corridas anteriores al contrato único se escribieron así.
SELLO = re.compile(r"(?:HUELLA|PLAN): (ok|parcial|nada|validado|sin-validar|no-escrito)\s*[—-]\s*(.+)")
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
    return LEGADO.get(estado, estado), resto.strip().strip('"').strip("\\n")
```

Y sustituir el bloque final de `execute_run` (hoy `if phase == "design" and ok: …` más las
dos últimas líneas) por:

```python
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
```

- [x] **Step 7: Dejar de escribir `tickets.status` como si fuera fuente**

`set_ticket` ya rellena `updated_at` solo, así que basta con quitarle el `status` a las
otras dos llamadas. En `execute_run`, cambiar `set_ticket(ticket["id"], status="running")`
por `set_ticket(ticket["id"])`. En `run_ticket`, cambiar `set_ticket(tid, status="queued")`
por `set_ticket(tid)`. Y añadir sobre `set_ticket` el comentario:

```python
def set_ticket(tid: int, **fields):
    """La columna `status` sigue en la tabla por las BDs viejas, pero ya no se escribe
    ni se lee: el estado del ticket se pliega de `runs` en `ticket_out`. Una segunda
    fuente es una fuente que algún día miente."""
```

- [x] **Step 8: Backfill de las corridas que ya existen**

Al final de `init_db`, dentro del mismo `with db() as c:`:

```python
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
```

`leer_huella` tiene que quedar **definida antes** de `init_db` en el archivo.

- [x] **Step 9: Correr toda la batería**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v
```
Esperado: PASS en todos. Los tests que hoy pasan (`test_bash_*`, `test_run_pasa_allowed_tools_y_add_dir`,
`test_run_strips_api_key_so_subscription_is_used`, `test_run_sobrevive_a_una_linea_gigante`)
comprueban el argv o el log, no el estado del ticket, así que no deberían tocarse — salvo
los que afirmen `status == "analyzed"`, que ahora exige sello: pásales
`huella="ok — docs/tickets/x.md"` en su `_use_fake_claude`.

- [x] **Step 10: Commit**

```bash
git add apps/orchestrator/backend
git commit -m "feat(orchestrator): runs guarda la huella declarada; el sello rige toda fase"
```

---

### Task 3: El plegado — `fases` en el detalle y estado calculado en la lista

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (`get_ticket`, `list_tickets`, nuevas `stat_huella`, `fases_de`, `status_plegado`, `ticket_out`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `runs.artifact_state` / `runs.artifact_path` (Tarea 2).
- Produces:
  - `GET /tickets/{tid}` devuelve `{"ticket": …, "fases": [...], "runs": [...], "log_tail": …}`.
  - Cada entrada de `fases`: `{"fase": str, "disponible": bool}` y, si `disponible`:
    `"estado"` ∈ `{"pendiente","corriendo","ok","parcial","error"}`, `"corridas": int`,
    `"fallidas": int`, y opcionalmente `"en": str`, `"duracion_s": int`, `"motivo": str`,
    `"huella": {"ruta": str, "existe": bool, "archivos": int, "bytes": int, "nombres": [str]}`.
  - `ticket["status"]` sale calculado en detalle y en lista, con las mismas etiquetas de
    siempre (`queued|running|analyzed|planned|error`).

- [x] **Step 1: Escribir los tests que fallan**

Añadir al final de `apps/orchestrator/backend/tests/test_app.py`:

```python
def test_fases_sin_corridas(client):
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    fases = client.get(f"/tickets/{tid}").json()["fases"]
    assert [f["fase"] for f in fases] == ["analyze", "design", "implement", "test", "guards", "pr"]
    assert fases[0] == {"fase": "analyze", "disponible": True, "estado": "pendiente",
                        "corridas": 0, "fallidas": 0}
    # una fase no ejecutable no informa estado: no hay nada que informar
    assert fases[2] == {"fase": "implement", "disponible": False}
    assert client.get("/tickets").json()[0]["status"] == "queued"


def test_fases_con_una_corrida_por_fase(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "3323-analysis.md").write_text("x" * 500)
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok" and f["corridas"] == 1 and f["fallidas"] == 0
    assert f["huella"] == {"ruta": "docs/tickets/3323-analysis.md", "existe": True,
                           "archivos": 1, "bytes": 500,
                           "nombres": ["3323-analysis.md"]}
    assert isinstance(f["duracion_s"], int)
    # y el estado del ticket se pliega de ahí, sin leer ninguna columna
    assert client.get("/tickets").json()[0]["status"] == "analyzed"


def test_la_fase_toma_el_estado_de_su_corrida_mas_reciente(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "a.md").write_text("uno")
    _use_fake_claude(monkeypatch, huella="nada — se cayó")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    _use_fake_claude(monkeypatch, huella="ok — a.md")
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok" and f["corridas"] == 2 and f["fallidas"] == 1


def test_una_recorrida_del_analisis_no_borra_que_hay_plan(client, monkeypatch, tmp_path):
    """El defecto que mata este diseño: `tickets.status` se sobrescribía y el plan
    desaparecía del mundo al re-correr la Fase 1."""
    (tmp_path / "repo" / "a.md").write_text("uno")
    _use_fake_claude(monkeypatch, huella="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    client.post(f"/tickets/{tid}/run", json={})          # re-corre el análisis
    d = client.get(f"/tickets/{tid}").json()
    assert [f["estado"] for f in d["fases"][:2]] == ["ok", "ok"]
    assert d["ticket"]["status"] == "planned"
    assert client.get("/tickets").json()[0]["status"] == "planned"


def test_huella_de_un_directorio_cuenta_y_lista_sus_archivos(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    for n in ("proposal.md", "tasks.md", "design.md"):
        (d / n).write_text("abc")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    h = client.get(f"/tickets/{tid}").json()["fases"][1]["huella"]
    assert h["existe"] and h["archivos"] == 3 and h["bytes"] == 9
    assert sorted(h["nombres"]) == ["design.md", "proposal.md", "tasks.md"]


def test_ruta_declarada_que_no_existe_en_disco_no_se_oculta(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/fantasma.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok"                      # la fase conserva su estado
    assert f["huella"]["existe"] is False           # y la huella se delata
    assert f["huella"]["archivos"] == 0


def test_fase_en_error_lleva_el_motivo_del_sello(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="nada — falta el análisis de la Fase 1")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    f = client.get(f"/tickets/{tid}").json()["fases"][1]
    assert f["estado"] == "error" and "falta el análisis" in f["motivo"]
    assert "huella" not in f
```

- [x] **Step 2: Correr los tests y ver que fallan**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v -k "fases or plegado or recorrida or huella_de or declarada or motivo"
```
Esperado: FAIL con `KeyError: 'fases'`.

- [x] **Step 3: Escribir el plegado**

En `app.py`, insertar antes de `@app.get("/tickets")`:

```python
def segundos(desde: str | None, hasta: str | None) -> int | None:
    if not desde or not hasta:
        return None
    return int((datetime.fromisoformat(hasta) - datetime.fromisoformat(desde)).total_seconds())


def stat_huella(repo: str, rel: str) -> dict:
    """Tamaño y número de archivos de lo que la corrida declaró haber escrito. Una ruta
    declarada que no existe NO se oculta: se informa `existe: False`. Es la regla de oro
    de las skills aplicada al orquestador."""
    p = Path(repo) / rel
    if not p.exists():
        return {"ruta": rel, "existe": False, "archivos": 0, "bytes": 0, "nombres": []}
    hijos = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
    return {"ruta": rel, "existe": True, "archivos": len(hijos),
            "bytes": sum(x.stat().st_size for x in hijos),
            # ponytail: 12 nombres bastan para el timeline; un change tiene 4.
            "nombres": [x.name for x in hijos[:12]]}


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
```

- [x] **Step 4: Cablearlo en los dos endpoints**

Sustituir `list_tickets` y `get_ticket` por:

```python
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
```

- [x] **Step 5: Correr toda la batería**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v
```
Esperado: PASS.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend
git commit -m "feat(orchestrator): el avance se pliega de runs; tickets.status pasa a calcularse"
```

---

### Task 4: El visor de artefactos

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (nuevo endpoint al final)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `runs.artifact_path` con `artifact_state IN ('ok','parcial')` (Tarea 2).
- Produces: `GET /tickets/{tid}/artefacto?ruta=<relativa>` →
  `{"ruta": str, "texto": str, "bytes": int, "truncado": bool}`. Cualquier ruta que no
  pase las cuatro validaciones devuelve `400` **sin leer nada**.

- [x] **Step 1: Escribir los tests que fallan**

Añadir al final de `test_app.py`:

```python
TOPE = 512 * 1024


def _con_artefacto(client, monkeypatch, tmp_path, rel, contenido="hola"):
    destino = tmp_path / "repo" / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    _use_fake_claude(monkeypatch, huella=f"ok — {rel}")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    return tid


def test_artefacto_sirve_lo_declarado(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/3323-analysis.md", "# Análisis")
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "docs/tickets/3323-analysis.md"})
    assert r.status_code == 200
    assert r.json()["texto"] == "# Análisis" and r.json()["truncado"] is False


def test_artefacto_sirve_un_hijo_directo_de_un_directorio_declarado(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [x] uno", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    r = client.get(f"/tickets/{tid}/artefacto",
                   params={"ruta": "openspec/changes/3323-xpo/tasks.md"})
    assert r.status_code == 200 and r.json()["texto"] == "- [x] uno"


def test_artefacto_rechaza_ruta_no_declarada(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    (tmp_path / "repo" / "secreto.env").write_text("TOKEN=xxx", encoding="utf-8")
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "secreto.env"})
    assert r.status_code == 400


def test_artefacto_rechaza_travesia(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    for ruta in ("../../etc/passwd", "docs/../../fuera.md", "docs/tickets/../../../x"):
        assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": ruta}).status_code == 400


def test_artefacto_rechaza_ruta_absoluta_fuera_del_repo(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    fuera = tmp_path / "fuera.md"
    fuera.write_text("no", encoding="utf-8")
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": str(fuera)}).status_code == 400


def test_artefacto_rechaza_un_directorio(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("x", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": "openspec/changes/3323-xpo"}).status_code == 400


def test_artefacto_declarado_por_OTRO_ticket_no_vale(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    otro = client.post("/tickets", json={"ado_id": 9999, "project": "Demo"}).json()["id"]
    assert client.get(f"/tickets/{otro}/artefacto",
                      params={"ruta": "docs/tickets/a.md"}).status_code == 400


def test_artefacto_trunca_a_512kb(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "grande.md", "á" * TOPE)
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "grande.md"}).json()
    assert r["truncado"] is True and len(r["texto"]) <= TOPE
    assert "\ufffd" not in r["texto"]      # no se parte un carácter multibyte al cortar
```

- [x] **Step 2: Correr los tests y ver que fallan**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v -k artefacto
```
Esperado: FAIL con `404` (el endpoint no existe).

- [x] **Step 3: Escribir el endpoint**

Añadir al final de `app.py`:

```python
TOPE_ARTEFACTO = 512 * 1024


@app.get("/tickets/{tid}/artefacto")
def artefacto(tid: int, ruta: str):
    """Lee del disco a partir de un parámetro de la petición, así que la validación no se
    simplifica. No es un explorador de archivos: es "enséñame lo que ESTA corrida dijo
    que escribió". Tienen que cumplirse las cuatro."""
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        declaradas = [r["artifact_path"] for r in c.execute(
            "SELECT artifact_path FROM runs WHERE ticket_id=? AND artifact_path IS NOT NULL "
            "AND artifact_state IN ('ok','parcial')", (tid,))]

    # 1. Declarada por una corrida DE ESTE TICKET, o hija directa de un directorio declarado.
    pedida = PurePosixPath(ruta.replace("\\", "/"))
    if not any(pedida == PurePosixPath(d.replace("\\", "/"))
               or pedida.parent == PurePosixPath(d.replace("\\", "/")) for d in declaradas):
        raise HTTPException(400, "Esa ruta no la declaró ninguna corrida de este ticket")

    # 2. Resuelta con realpath, cae dentro del repo principal o de los extra del ticket.
    #    resolve() sigue enlaces, así que un symlink apuntando fuera muere aquí.
    raices = [Path(t["repo_path"]).resolve()]
    raices += [Path(d["path"]).resolve() for d in norm_dirs(json.loads(t["extra_dirs"] or "[]"))]
    real = (Path(t["repo_path"]) / ruta).resolve()
    if not any(real == r or r in real.parents for r in raices):
        raise HTTPException(400, "Esa ruta cae fuera de los repos del ticket")

    # 3. Archivo regular: ni directorio, ni dispositivo.
    if not real.is_file():
        raise HTTPException(400, "No es un archivo regular")

    # 4. Tope. El corte va en bytes, así que hay que retroceder hasta el último byte que
    #    NO sea de continuación (0b10xxxxxx): cortar a ciegas parte un carácter multibyte
    #    por la mitad y el visor pinta un rombo negro donde había una tilde.
    crudo = real.read_bytes()
    truncado = len(crudo) > TOPE_ARTEFACTO
    corte = TOPE_ARTEFACTO
    while truncado and corte > 0 and (crudo[corte] & 0xC0) == 0x80:
        corte -= 1
    texto = (crudo[:corte] if truncado else crudo).decode("utf-8", "replace")
    return {"ruta": ruta, "texto": texto, "bytes": len(crudo), "truncado": truncado}
```

Añadir `PurePosixPath` al import de `pathlib` en la cabecera:
`from pathlib import Path, PurePosixPath`. `codecs` sigue importado: lo usa `execute_run`.

- [x] **Step 4: Correr los tests**

```bash
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/ -v
```
Esperado: PASS en todos, incluidos los 8 de `artefacto`.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/backend
git commit -m "feat(orchestrator): visor de artefactos con validación de ruta en cuatro pasos"
```

---

### Task 5: Tipos y reglas en el frontend

**Files:**
- Modify: `apps/orchestrator/frontend/src/api.ts`
- Modify: `apps/orchestrator/frontend/src/estado.ts`
- Modify: `apps/orchestrator/frontend/src/TicketDetail.tsx:6,36-41` (solo para que compile)

**Interfaces:**
- Consumes: el JSON de las Tareas 3 y 4.
- Produces:
  - `type Fase`, `type Huella`, `type Artefacto` en `api.ts`; `api.artefacto(tid, ruta)`.
  - `FASE_LABEL: Record<string,string>`, `colorFase(estado)`, `iconoFase(estado)`,
    `puedeLanzar(fases, i, activo, ticketId): string` (devuelve el motivo del bloqueo, o
    `""` si se puede lanzar).
  - `puedePlanificar` **desaparece**.

- [x] **Step 1: Añadir los tipos y la llamada en `api.ts`**

Sustituir el bloque de tipos `Ticket`/`Run`/`TicketDetail` por:

```ts
export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  status: string; created_at: string; updated_at: string
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
  artifact_state: string | null; artifact_path: string | null
}
export type Huella = {
  ruta: string; existe: boolean; archivos: number; bytes: number; nombres: string[]
}
// `disponible: false` no lleva estado: una fase que no se puede lanzar no tiene nada
// que informar. El resto de campos solo aparecen si hubo alguna corrida.
export type Fase = {
  fase: string; disponible: boolean
  estado?: "pendiente" | "corriendo" | "ok" | "parcial" | "error"
  corridas?: number; fallidas?: number
  en?: string | null; duracion_s?: number | null; motivo?: string; huella?: Huella
}
export type Artefacto = { ruta: string; texto: string; bytes: number; truncado: boolean }
export type TicketDetail = { ticket: Ticket; fases: Fase[]; runs: Run[]; log_tail: string }
```

Y añadir al objeto `api`, tras `detail`:

```ts
  artefacto: (id: number, ruta: string) =>
    fetch(`/api/tickets/${id}/artefacto?ruta=${encodeURIComponent(ruta)}`)
      .then(r => json<Artefacto>(r)),
```

- [x] **Step 2: Sustituir `puedePlanificar` por la regla general en `estado.ts`**

Borrar la función `puedePlanificar` entera (líneas 44-51) y añadir en su lugar:

```ts
/** Las seis fases del pipeline, con el nombre que se le enseña al usuario. */
export const FASE_LABEL: Record<string, string> = {
  analyze: "Análisis", design: "Plan", implement: "Código",
  test: "Pruebas", guards: "Revisión", pr: "PR",
}

/** Qué se lee bajo la fila cuando la fase dejó algo. */
export const FASE_NOUN: Record<string, string> = {
  analyze: "análisis", design: "plan",
}

export function iconoFase(estado?: string): string {
  return estado === "ok" ? "✓" : estado === "parcial" ? "!" : estado === "error" ? "✕"
    : estado === "corriendo" ? "·" : "—"
}

export function colorFase(estado?: string): string {
  return estado === "ok" ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-700"
    : estado === "parcial" ? "border-amber-500/60 bg-amber-500/10 text-amber-700"
    : estado === "error" ? "border-red-500/60 bg-red-500/10 text-red-700"
    : estado === "corriendo" ? "border-blue-500/60 bg-blue-500/10 text-blue-700"
    : "border-border bg-muted text-muted-foreground"
}

/**
 * Motivo por el que NO se puede lanzar esta fase, o "" si sí se puede. Generaliza al
 * viejo `puedePlanificar`, cuya regla —"solo con análisis hecho"— era un caso particular
 * de esto: una fase se lanza si está disponible, no hay corrida activa, y la anterior
 * quedó en `ok` o `parcial`. La primera fase no tiene anterior, así que siempre se puede.
 */
export function puedeLanzar(
  fases: Fase[], i: number, activo: ActiveRun | null, ticketId: number,
): string {
  const f = fases[i]
  if (!f.disponible) return "esta fase todavía no existe"
  if (activo) {
    return activo.ticket_id === ticketId ? "esta corrida ya está en marcha"
      : `esperando a #${activo.ado_id} en ${activo.project}`
  }
  const previa = fases.slice(0, i).filter(p => p.disponible).pop()
  if (previa && previa.estado !== "ok" && previa.estado !== "parcial") {
    return `necesita ${FASE_LABEL[previa.fase]} en verde`
  }
  return ""
}

export function tamaño(bytes: number): string {
  return bytes < 1024 ? `${bytes} B`
    : bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function hora(iso?: string | null): string {
  return iso ? new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" }) : ""
}
```

Y ampliar el import de la primera línea del archivo:

```ts
import type { ActiveRun, Fase, Ticket } from "@/api"
```

- [x] **Step 3: Dejar `TicketDetail.tsx` compilando (arreglo mínimo, se rehace en la Tarea 6)**

En `apps/orchestrator/frontend/src/TicketDetail.tsx`, quitar `puedePlanificar` del import
de la línea 6 y sustituir el botón *Planificar* (líneas 35-41) por:

```tsx
          <Button size="sm" variant="secondary" disabled={!!motivo}
                  title={motivo || undefined}
                  onClick={() => onRun(undefined, "design")}>
            Planificar
          </Button>
```

- [x] **Step 4: Comprobar que compila y pasa el lint**

```bash
cd apps/orchestrator/frontend
npm run build
npm run lint
```
Esperado: ambos en verde, sin errores de tipos.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/frontend/src
git commit -m "feat(orchestrator-ui): tipos de fase y la regla general de habilitación"
```

---

### Task 6: El componente `Timeline`

**Files:**
- Create: `apps/orchestrator/frontend/src/Timeline.tsx`
- Modify: `apps/orchestrator/frontend/src/TicketDetail.tsx` (reescritura)

**Interfaces:**
- Consumes: `Fase`, `Artefacto`, `puedeLanzar`, `FASE_LABEL`, `colorFase`, `iconoFase`,
  `tamaño`, `hora` (Tarea 5); `api.artefacto` (Tarea 4).
- Produces: `<Timeline fases activo ticketId onRun />` donde
  `onRun: (fase: string, instructions?: string) => void`.

- [x] **Step 1: Crear `Timeline.tsx`**

```tsx
import { useState } from "react"
import { api, type ActiveRun, type Artefacto, type Fase } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { colorFase, FASE_LABEL, hora, iconoFase, puedeLanzar, tamaño } from "@/estado"

/**
 * El recorrido de fases del ticket: una fila por fase de PHASES, con su acción y el
 * artefacto que declaró haber dejado. Reemplaza a los botones de la cabecera — la acción
 * va donde está la información, el mismo principio que movió los repos a la cabecera del
 * proyecto. Las fases que aún no existen salen apagadas: el camino pendiente es contexto.
 */
export function Timeline({ fases, activo, ticketId, onRun }: {
  fases: Fase[]
  activo: ActiveRun | null
  ticketId: number
  onRun: (fase: string, instructions?: string) => void
}) {
  const [abierta, setAbierta] = useState<string | null>(null)   // caja de instrucciones
  const [instrucciones, setInstrucciones] = useState("")
  const [visor, setVisor] = useState<Artefacto | null>(null)
  const [cargando, setCargando] = useState<string | null>(null)
  const [errorVisor, setErrorVisor] = useState("")

  const ver = (ruta: string) => {
    if (visor?.ruta === ruta) return setVisor(null)     // segundo clic: cerrar
    setCargando(ruta); setErrorVisor("")
    api.artefacto(ticketId, ruta)
      .then(a => setVisor(a))
      .catch(e => { setVisor(null); setErrorVisor(String(e)) })
      .finally(() => setCargando(null))
  }

  return (
    <ol className="space-y-0">
      {fases.map((f, i) => {
        const motivo = puedeLanzar(fases, i, activo, ticketId)
        const h = f.huella
        const rutas = h?.existe
          ? (h.archivos === 1 && h.nombres[0] === h.ruta.split("/").pop()
              ? [h.ruta] : h.nombres.map(n => (h.archivos === 1 ? h.ruta : `${h.ruta}/${n}`)))
          : []
        const ultima = i === fases.length - 1
        return (
          <li key={f.fase} className="relative pl-8">
            {/* la línea que une las fases; no se dibuja bajo la última */}
            {!ultima && <span className="absolute left-[11px] top-7 bottom-0 w-px bg-border" />}
            <span className={`absolute left-0 top-2 flex h-6 w-6 items-center justify-center
                              rounded-full border text-[11px] font-semibold
                              ${colorFase(f.estado)}
                              ${f.estado === "corriendo" ? "animate-pulse" : ""}`}>
              {iconoFase(f.estado)}
            </span>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className={`text-sm font-medium ${f.disponible ? "" : "text-muted-foreground"}`}>
                {FASE_LABEL[f.fase] ?? f.fase}
              </span>
              {!f.disponible && (
                <span className="text-xs text-muted-foreground">no disponible aún</span>
              )}
              {f.disponible && f.estado === "pendiente" && (
                <span className="text-xs text-muted-foreground">sin corridas</span>
              )}
              {f.en && <span className="text-xs text-muted-foreground">{hora(f.en)}</span>}
              {f.duracion_s != null && (
                <span className="text-xs text-muted-foreground">
                  {f.duracion_s < 60 ? `${f.duracion_s}s`
                    : `${Math.floor(f.duracion_s / 60)}m${String(f.duracion_s % 60).padStart(2, "0")}s`}
                </span>
              )}
              {!!f.corridas && (
                <span className="text-xs text-muted-foreground">
                  {f.corridas} {f.corridas === 1 ? "corrida" : "corridas"}
                </span>
              )}
              {!!f.fallidas && (
                <span className="text-xs text-amber-600">⚠ {f.fallidas} falló</span>
              )}

              {f.disponible && (
                <div className="ml-auto flex gap-1">
                  <Button size="sm" variant={f.estado === "pendiente" ? "default" : "outline"}
                          disabled={!!motivo} title={motivo || undefined}
                          onClick={() => onRun(f.fase)}>
                    {f.corridas ? "Re-correr" : "Correr"}
                  </Button>
                  <Button size="sm" variant="ghost" disabled={!!motivo}
                          title={motivo || "Correr con instrucciones de ajuste"}
                          onClick={() => {
                            setAbierta(abierta === f.fase ? null : f.fase); setInstrucciones("")
                          }}>
                    ▾
                  </Button>
                </div>
              )}
            </div>

            {motivo && f.disponible && f.estado !== "corriendo" && (
              <p className="pb-2 text-xs text-muted-foreground">{motivo}</p>
            )}

            {f.estado === "error" && f.motivo && (
              <p className="pb-2 text-xs text-red-600">{f.motivo}</p>
            )}

            {h && (
              <div className="pb-2 text-xs">
                {h.existe ? (
                  <>
                    <span className="text-muted-foreground">⤷ </span>
                    <span className="font-mono">{h.ruta}</span>
                    <span className="text-muted-foreground">
                      {" · "}{h.archivos === 1 ? tamaño(h.bytes)
                        : `${h.archivos} archivos · ${tamaño(h.bytes)}`}
                    </span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {rutas.map(r => (
                        <button key={r} onClick={() => ver(r)}
                                className={`rounded border px-1.5 py-0.5 font-mono text-[11px]
                                            hover:bg-accent
                                            ${visor?.ruta === r ? "bg-accent" : ""}`}>
                          {cargando === r ? "…" : r.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <span className="text-amber-600">
                    ⤷ <span className="font-mono">{h.ruta}</span> · declarada y no encontrada
                  </span>
                )}
              </div>
            )}

            {abierta === f.fase && (
              <div className="pb-3">
                <Textarea rows={2} value={instrucciones}
                          placeholder={`Ajuste para ${FASE_LABEL[f.fase]}…`}
                          onChange={e => setInstrucciones(e.target.value)} />
                <Button size="sm" className="mt-2" disabled={!instrucciones || !!motivo}
                        onClick={() => {
                          onRun(f.fase, instrucciones); setInstrucciones(""); setAbierta(null)
                        }}>
                  Correr con este ajuste
                </Button>
              </div>
            )}

            {errorVisor && visor === null && rutas.length > 0 && (
              <p className="pb-2 text-xs text-red-600">{errorVisor}</p>
            )}

            {visor && rutas.includes(visor.ruta) && (
              <div className="mb-3 rounded-md border">
                <div className="flex items-center gap-2 border-b px-3 py-1.5 text-xs">
                  <span className="font-mono">{visor.ruta}</span>
                  <span className="text-muted-foreground">{tamaño(visor.bytes)}</span>
                  {visor.truncado && (
                    <span className="text-amber-600">truncado a 512 KB</span>
                  )}
                  <button className="ml-auto text-muted-foreground hover:underline"
                          onClick={() => setVisor(null)}>cerrar</button>
                </div>
                <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words
                                px-3 py-2 text-xs leading-relaxed">
                  {visor.texto}
                </pre>
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
```

- [x] **Step 2: Reescribir `TicketDetail.tsx`**

Sustituir el archivo entero por:

```tsx
import { useState } from "react"
import type { ActiveRun, TicketDetail as Detail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Timeline } from "@/Timeline"
import { bloqueo, colorCorrida, duracion, estado } from "@/estado"

export function TicketDetail({ detail, activo, projectName, onBack, onRun, onDelete }: {
  detail: Detail
  activo: ActiveRun | null
  projectName: string
  onBack: () => void
  onRun: (instructions?: string, phase?: string) => void
  onDelete: () => void
}) {
  const [verLog, setVerLog] = useState(false)
  const [verHistorial, setVerHistorial] = useState(false)
  const t = detail.ticket
  const { label, color } = estado(t, activo)
  const motivo = bloqueo(t, activo)

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-muted-foreground hover:underline">
        ← {projectName} / ticket #{t.ado_id}
      </button>

      {/* La cabecera se queda con el identificador, el estado y Borrar: las acciones de
          fase viven en su fila del timeline, junto a la información que las justifica. */}
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">#{t.ado_id}</h2>
        <Badge className={color}>{label}</Badge>
        <Button size="sm" variant="destructive" className="ml-auto" onClick={onDelete}>
          Borrar
        </Button>
      </div>
      {motivo && <p className="text-xs text-amber-700">{motivo}</p>}

      <Timeline fases={detail.fases} activo={activo} ticketId={t.id}
                onRun={(fase, ins) => onRun(ins, fase)} />

      <div>
        <button className="text-sm font-medium hover:underline"
                onClick={() => setVerHistorial(v => !v)}>
          {verHistorial ? "▾" : "▸"} Historial de corridas ({detail.runs.length})
        </button>
        {verHistorial && (
          <ul className="mt-2 space-y-1 text-sm">
            {detail.runs.map(r => (
              <li key={r.id} className="flex items-center gap-2">
                <Badge className={colorCorrida(r.status)}>{r.status}</Badge>
                <span className="text-xs text-muted-foreground">{r.phase}</span>
                <span className="text-muted-foreground">{r.started_at ?? "en cola"}</span>
                <span className="text-muted-foreground">{duracion(r.started_at, r.finished_at)}</span>
                {r.artifact_path && (
                  <span className="truncate font-mono text-xs text-muted-foreground"
                        title={r.artifact_path}>
                    {r.artifact_state}: {r.artifact_path}
                  </span>
                )}
                {r.instructions && (
                  <span className="truncate text-muted-foreground" title={r.instructions}>
                    ✎ {r.instructions}
                  </span>
                )}
              </li>
            ))}
            {detail.runs.length === 0 && (
              <li className="text-muted-foreground">Sin corridas aún.</li>
            )}
          </ul>
        )}
      </div>

      {/* El log se queda, colapsado: es la herramienta de diagnóstico cuando el timeline
          dice que algo falló, no lo primero que hay que leer. */}
      <div>
        <button className="text-sm font-medium hover:underline" onClick={() => setVerLog(v => !v)}>
          {verLog ? "▾" : "▸"} Log de la última corrida
        </button>
        {verLog && (
          <pre className="mt-2 max-h-[28rem] overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">
            {detail.log_tail || "(el log aparecerá cuando arranque la corrida)"}
          </pre>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Compilar, lint y comprobación manual**

```bash
cd apps/orchestrator/frontend
npm run build && npm run lint
```
Esperado: ambos en verde.

Luego, con el backend corriendo, abrir `http://localhost:5173`, entrar al ticket **3323**
y comprobar en pantalla:
- seis filas, con `Código`/`Pruebas`/`Revisión`/`PR` apagadas y sin botón;
- `Análisis` y `Plan` con su marca, su hora, su número de corridas y su ruta;
- pulsar un nombre de archivo abre el contenido debajo, y volver a pulsarlo lo cierra;
- `▾` abre la caja de ajuste **de esa fase**.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src
git commit -m "feat(orchestrator-ui): timeline de fases con visor de artefactos"
```

---

### Task 7: La lista de tickets deja de mentir

**Files:**
- Modify: `apps/orchestrator/frontend/src/TicketList.tsx:41-46`
- Modify: `apps/orchestrator/frontend/src/App.tsx:94-96`

**Interfaces:**
- Consumes: `ticket.status` ya plegado por el backend (Tarea 3).
- Produces: nada nuevo hacia otras tareas.

- [x] **Step 1: Que el botón de la lista diga la verdad**

El botón de la fila lanza siempre `analyze`, y su rótulo se decide con `t.status`. Ahora
que `status` es un plegado de todas las fases, `planned` haría que dijera "Correr" para
una fase ya corrida. Sustituir el bloque de botones (líneas 40-47) de
`TicketList.tsx` por:

```tsx
              <div className="ml-auto flex gap-1">
                <Button size="sm" variant="outline" disabled={!!motivo}
                        title={motivo || "Lanza la Fase 1; el resto se lanza desde el detalle"}
                        onClick={() => onRun(t.id)}>
                  {t.status === "queued" ? "Analizar" : "Re-analizar"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onOpen(t.id)}>Ver</Button>
              </div>
```

- [x] **Step 2: Compilar y lint**

```bash
cd apps/orchestrator/frontend
npm run build && npm run lint
```
Esperado: verde.

- [x] **Step 3: Comprobar en pantalla**

En la lista del proyecto, un ticket con plan hecho tiene que salir como **planificado**, y
seguir saliendo así después de re-correr el análisis — es el defecto que este diseño mata.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src
git commit -m "fix(orchestrator-ui): el botón de la lista nombra lo que realmente lanza"
```

---

### Task 8: Acabado visual

**Files:**
- Modify: `apps/orchestrator/frontend/src/index.css` (bloque `@layer base` al final)
- Modify: `apps/orchestrator/frontend/src/estado.ts` (paleta `COLOR`)
- Modify: `apps/orchestrator/frontend/src/ProjectHeader.tsx`
- Modify: `apps/orchestrator/frontend/src/App.tsx:66`

**Interfaces:**
- Consumes: los tokens de shadcn ya definidos en `index.css:51-118`.
- Produces: nada hacia otras tareas. Es acabado, no comportamiento.

**Por qué:** el archivo ya define una paleta completa en `oklch` con soporte de modo
oscuro, y los componentes la ignoran usando `gray-500`/`gray-100` a mano. El resultado es
que el tema existe y no se ve. Esta tarea hace que se vea; no añade dependencias ni
cambia ninguna regla de negocio.

- [x] **Step 1: Que las insignias de estado usen la paleta y no grises fijos**

En `estado.ts`, sustituir el objeto `COLOR` por:

```ts
const COLOR: Record<string, string> = {
  registrado: "border-border bg-muted text-muted-foreground",
  corriendo: "border-blue-500/50 bg-blue-500/10 text-blue-700",
  analizado: "border-emerald-500/50 bg-emerald-500/10 text-emerald-700",
  planificado: "border-violet-500/50 bg-violet-500/10 text-violet-700",
  error: "border-red-500/50 bg-red-500/10 text-red-700",
}
```

- [x] **Step 2: Dar aire y jerarquía al contenedor**

En `App.tsx`, sustituir la línea 66 por:

```tsx
    <div className="mx-auto flex w-full max-w-[92rem] gap-6 p-6">
```

- [x] **Step 3: Cambiar los grises fijos de `ProjectHeader` por tokens**

En `ProjectHeader.tsx`, sustituir `text-gray-500` → `text-muted-foreground`,
`text-gray-600` → `text-foreground/70`, `text-gray-700` → `text-foreground`,
`text-gray-400` → `text-muted-foreground/70`.

- [x] **Step 4: Un solo retoque tipográfico global**

Al final de `index.css`, dentro del `@layer base` existente, añadir dentro de la regla
`body`:

```css
  body {
    @apply bg-background text-foreground antialiased;
    font-feature-settings: "cv11", "ss01";
    }
```

- [x] **Step 5: Compilar, lint y mirar**

```bash
cd apps/orchestrator/frontend
npm run build && npm run lint
```
Esperado: verde. Luego recorrer la app: lista, detalle con timeline, ajustes.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/frontend/src
git commit -m "style(orchestrator-ui): la UI usa los tokens del tema en vez de grises fijos"
```

---

## Verificación final

- [x] `cd apps/orchestrator/backend && .venv/Scripts/python -m pytest tests/ -v` — todos verdes
- [x] `cd apps/orchestrator/frontend && npm run build && npm run lint` — verdes
- [x] `claude plugin validate .` desde la raíz del hub — OK
- [x] `grep -rn "current_phase\|puedePlanificar\|PLAN:" apps/ plugins/` — sin resultados
- [x] Reiniciar el backend **sin `--reload`** y comprobar que el proceso que escucha en el
      8000 arrancó **después** de la última modificación de `app.py`
- [x] Recorrer el ticket 3323 en la UI: seis fases, artefactos legibles, `▾` por fase
- [x] Actualizar `docs/STATUS.md` y marcar los checkboxes de este plan
