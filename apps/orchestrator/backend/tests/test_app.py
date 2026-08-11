import pytest


def test_db_tables_created(client):
    import app

    with app.db() as c:
        names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tickets", "runs"} <= names


def test_create_and_list_ticket(client):
    r = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"})
    assert r.status_code == 201
    t = r.json()
    assert t["ado_id"] == 3311 and t["status"] == "queued"
    assert client.get("/tickets").json()[0]["id"] == t["id"]


def test_create_ticket_unknown_project(client):
    assert client.post("/tickets", json={"ado_id": 1, "project": "Nope"}).status_code == 400


def test_get_ticket_detail_and_delete(client):
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["id"] == tid and detail["runs"] == [] and detail["log_tail"] == ""
    assert client.delete(f"/tickets/{tid}").status_code == 204
    assert client.get(f"/tickets/{tid}").status_code == 404


def _repos(client):
    return client.get("/projects").json()[0]["repos"]


def test_projects_endpoint(client):
    [p] = client.get("/projects").json()
    assert p["name"] == "Demo" and p["org"] == "DemoOrg" and p["project"] == "Demo"
    # una sola lista; el principal viene marcado, no en un campo aparte
    assert len(p["repos"]) == 2
    principal = [r for r in p["repos"] if r["primary"]]
    assert len(principal) == 1 and principal[0]["label"] == "front"
    assert all(Path(r["path"]).is_dir() for r in p["repos"])
    assert [r["label"] for r in p["repos"] if not r["primary"]] == ["backend"]


def test_project_crud_rejects_rutas_inexistentes(client):
    bad = client.post("/projects", json={
        "name": "Roto", "org": "O", "project": "P",
        "repos": [{"path": "/no/existe", "primary": True}],
    })
    assert bad.status_code == 400 and "/no/existe" in bad.json()["detail"]
    assert client.post("/projects", json={
        "name": "Demo", "org": "O", "project": "P", "repos": _repos(client),
    }).status_code == 409


def test_project_exige_un_unico_principal(client):
    repos = _repos(client)
    sin = client.post("/projects", json={
        "name": "Sin", "org": "O", "project": "P",
        "repos": [{**r, "primary": False} for r in repos],
    })
    assert sin.status_code == 400 and "principal" in sin.json()["detail"]

    dos = client.post("/projects", json={
        "name": "Dos", "org": "O", "project": "P",
        "repos": [{**r, "primary": True} for r in repos],
    })
    assert dos.status_code == 400 and "principal" in dos.json()["detail"]

    vacio = client.post("/projects", json={"name": "V", "org": "O", "project": "P", "repos": []})
    assert vacio.status_code == 400 and "al menos un repo" in vacio.json()["detail"]


def test_cambiar_cual_es_el_principal(client):
    repos = _repos(client)
    volteados = [{**r, "primary": not r["primary"]} for r in repos]
    r = client.put("/projects/Demo", json={
        "name": "Demo", "org": "DemoOrg", "project": "Demo", "repos": volteados,
    })
    assert r.status_code == 200
    nuevo = [x for x in r.json()["repos"] if x["primary"]][0]
    assert nuevo["label"] == "backend"
    # y el ticket que se cree ahora usa ese repo como cwd
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == nuevo["path"]


def test_renombrar_proyecto(client):
    repos = _repos(client)
    cuerpo = {"org": "DemoOrg", "project": "Demo", "repos": repos}
    # un ticket creado antes conserva sus rutas: no apunta al catálogo
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    antes = client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"]

    r = client.put("/projects/Demo", json={"name": "Demo2", **cuerpo})
    assert r.status_code == 200 and r.json()["name"] == "Demo2"
    assert [p["name"] for p in client.get("/projects").json()] == ["Demo2"]
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == antes

    # y el nombre sigue siendo único
    client.post("/projects", json={"name": "Otro", **cuerpo})
    choque = client.put("/projects/Otro", json={"name": "Demo2", **cuerpo})
    assert choque.status_code == 409


def test_project_update_y_delete(client):
    principal = [r for r in _repos(client) if r["primary"]]
    r = client.put("/projects/Demo", json={
        "name": "Demo", "org": "OtraOrg", "project": "Demo", "repos": principal,
    })
    assert r.status_code == 200 and r.json()["org"] == "OtraOrg" and len(r.json()["repos"]) == 1
    assert client.delete("/projects/Demo").status_code == 204
    assert client.get("/projects").json() == []
    assert client.delete("/projects/Demo").status_code == 404


def test_ticket_hereda_extra_dirs_del_proyecto(client):
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    t = client.get(f"/tickets/{tid}").json()["ticket"]
    assert len(json.loads(t["extra_dirs"])) == 1
    # el ticket conserva su copia aunque el proyecto desaparezca del catálogo
    client.delete("/projects/Demo")
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == t["repo_path"]


import json
import sys
from pathlib import Path


def _use_fake_claude(monkeypatch, fail=False, huella=None, skill_leak=False):
    fake = Path(__file__).parent / "fake_claude.py"
    monkeypatch.setenv("ORCH_CLAUDE_CMD", json.dumps([sys.executable, str(fake)]))
    monkeypatch.setenv("FAKE_FAIL", "1" if fail else "0")
    monkeypatch.setenv("FAKE_SKILL_LEAK", "1" if skill_leak else "0")
    if huella is None:
        monkeypatch.delenv("FAKE_HUELLA", raising=False)
    else:
        monkeypatch.setenv("FAKE_HUELLA", huella)


def test_run_success_writes_log_and_states(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3311-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202
    detail = client.get(f"/tickets/{tid}").json()  # TestClient corre el background task antes
    run = detail["runs"][0]
    assert run["status"] == "success" and run["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_run_design_invoca_el_comando_plan(client, monkeypatch):
    """La fase decide el comando: design NO puede lanzar el analyze."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "/ticket-agent:plan 3323" in detail["log_tail"]
    assert "/ticket-agent:analyze" not in detail["log_tail"]
    assert detail["runs"][0]["phase"] == "design"


def test_huella_ok_deja_la_corrida_bien(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success"
    assert run["artifact_state"] == "ok"
    assert run["artifact_path"] == "docs/tickets/3323-analysis.md"


def test_huella_parcial_la_corrida_vale_y_conserva_la_reserva(client, monkeypatch):
    """La reserva de un `parcial` viaja EN el sello, tras ` · ` — no en el resumen. El
    runner la separa de la ruta: `artifact_path` se queda limpio (lista blanca del
    visor) y la reserva sale por `fases_de` como `motivo`, igual que ya hace `error`."""
    _use_fake_claude(
        monkeypatch,
        huella="parcial — openspec/changes/3323-xpo · openspec validate no pasó",
    )
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    run = detail["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "parcial"
    # la ruta queda limpia, sin la reserva colgando detrás
    assert run["artifact_path"] == "openspec/changes/3323-xpo"
    fase = detail["fases"][1]
    assert fase["estado"] == "parcial"
    assert fase["motivo"] == "openspec validate no pasó"


def test_huella_parcial_sin_reserva_sigue_funcionando(client, monkeypatch):
    """Un `parcial` sin ` · ` no tiene reserva: tiene que seguir funcionando igual que
    antes de este cambio, sin `motivo`."""
    _use_fake_claude(monkeypatch, huella="parcial — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    run = detail["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "parcial"
    assert run["artifact_path"] == "openspec/changes/3323-xpo"
    fase = detail["fases"][1]
    assert fase["estado"] == "parcial"
    assert "motivo" not in fase


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


def test_leer_huella_con_la_forma_real_del_stream_json(tmp_path):
    """El log real de `claude -p --output-format stream-json` no es una línea plana:
    el sello viaja anidado en `message.content[].text`, seguido en la misma línea por
    `stop_reason`, `usage`, `session_id`, `uuid` y más. Con `(.+)` voraz, `leer_huella`
    devolvía la ruta con toda esa cola pegada detrás — justo lo que la Fase de guardias
    (Tarea 4) usaría como ruta servible."""
    import app
    linea = (
        '{"type":"assistant","message":{"content":[{"type":"text",'
        '"text":"resumen. HUELLA: ok — docs/tickets/3323-analysis.md"}],'
        '"stop_reason":null},"session_id":"sess-1","uuid":"uuid-1",'
        '"timestamp":"2026-08-10T00:00:00Z","request_id":"req_1"}\n'
    )
    log = tmp_path / "run.log"
    log.write_text(linea, encoding="utf-8")
    assert app.leer_huella(log) == ("ok", "docs/tickets/3323-analysis.md")


def test_current_phase_ya_no_existe(tmp_path, monkeypatch):
    """Antes este test corría sobre una BD recién creada por el fixture `client`, cuyo
    `CREATE TABLE` nunca incluyó `current_phase`: pasaba sin ejecutar jamás el
    `ALTER TABLE ... DROP COLUMN` que decía proteger — placebo puro. Aquí se arma a
    mano una BD con el esquema VIEJO (con `current_phase`, sin `artifact_state` ni
    `artifact_path`) y se deja que `init_db` migre de verdad."""
    import sqlite3 as sq

    db_path = tmp_path / "vieja.db"
    conn = sq.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects(
          name TEXT PRIMARY KEY, org TEXT NOT NULL, project TEXT NOT NULL,
          repo_path TEXT NOT NULL, repo_label TEXT NOT NULL DEFAULT '',
          extra_dirs TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE tickets(
          id INTEGER PRIMARY KEY AUTOINCREMENT, ado_id INTEGER NOT NULL,
          org TEXT NOT NULL, project TEXT NOT NULL, repo_path TEXT NOT NULL,
          extra_dirs TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'queued',
          current_phase TEXT NOT NULL DEFAULT 'analyze',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE runs(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
          phase TEXT NOT NULL, instructions TEXT, status TEXT NOT NULL DEFAULT 'queued',
          log_path TEXT, started_at TEXT, finished_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORCH_DB", str(db_path))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    if "app" in sys.modules:
        del sys.modules["app"]
    import app  # ejecuta init_db() al importar, contra la BD vieja de arriba

    with app.db() as c:
        cols_tickets = {r["name"] for r in c.execute("PRAGMA table_info(tickets)")}
        cols_runs = {r["name"] for r in c.execute("PRAGMA table_info(runs)")}
    assert "current_phase" not in cols_tickets
    assert {"artifact_state", "artifact_path", "artifact_note"} <= cols_runs


def test_fase_declarada_pero_no_ejecutable_da_400(client, monkeypatch):
    """guards está en PHASES pero no existe: se rechaza sin lanzar subproceso."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "guards"})
    assert r.status_code == 400 and "guards" in r.json()["detail"]
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_run_sin_fase_sigue_siendo_analyze(client, monkeypatch):
    """Compatibilidad: quien ya llamaba sin fase no se entera del cambio."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_bash_va_acotado_a_openspec(client, monkeypatch):
    """La Fase 2 necesita invocar `@fission-ai/openspec`; nada más. Bash suelto sería
    otra cosa.

    Se comprueba sobre los argumentos REALES del subproceso, no sobre una subcadena
    del log: `assert " Bash " not in log` buscaba "Bash" rodeado de espacios por los
    dos lados, y un "Bash" pelado al FINAL de la lista de `--allowedTools` queda
    seguido de un salto de línea, no de un espacio — la comprobación no lo veía ahí."""
    _use_fake_claude(monkeypatch)
    import asyncio

    capturado = {}
    original = asyncio.create_subprocess_exec

    async def espia(*args, **kwargs):
        capturado["argv"] = args
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", espia)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in capturado["argv"]
    assert "Bash" not in capturado["argv"]       # nunca Bash a secas, como argumento exacto


def test_bash_incluye_las_dos_formas_de_invocar_openspec_en_design(client, monkeypatch):
    """El especificador tiene que calzar literalmente con el principio del comando:
    hacen falta las dos formas (`npx --yes ...@latest` y `npx ...` a secas)."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in log
    assert "Bash(npx @fission-ai/openspec:*)" in log


def _espiar_argv(monkeypatch):
    """Sobre los argumentos REALES del subproceso, no sobre una subcadena del log."""
    import asyncio
    capturado = {}
    original = asyncio.create_subprocess_exec

    async def espia(*args, **kwargs):
        capturado["argv"] = args
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", espia)
    return capturado


def test_implement_lleva_bash_pelado_y_settings(client, monkeypatch, tmp_path):
    import app
    _use_fake_claude(monkeypatch)
    cap = _espiar_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    argv = cap["argv"]
    assert "Bash" in argv                      # pelado, no un especificador
    assert "--settings" in argv
    assert "deny_push.py" in argv[argv.index("--settings") + 1]


def test_analyze_no_lleva_settings_ni_bash(client, monkeypatch):
    """Que la lista no vuelva a viajar fija para todas las fases: fue justo lo que
    hizo que la Fase 1, declarada de solo lectura, acabara ejecutando shell."""
    _use_fake_claude(monkeypatch)
    cap = _espiar_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "--settings" not in cap["argv"]
    assert "Bash" not in cap["argv"]


def test_las_cuatro_tablas_incluyen_implement():
    import app
    for tabla in (app.PHASE_COMMANDS, app.PHASE_DONE,
                  app.PHASE_ALLOWED_TOOLS, app.PHASE_NOUN):
        assert "implement" in tabla
    assert app.PHASE_DONE["implement"] == "implemented"


def test_bash_no_aparece_en_fase_analyze(client, monkeypatch):
    """C1: la Fase 1 es de solo lectura. Antes del fix, Bash viajaba en TODAS las
    corridas porque --allowedTools no miraba la fase; una corrida real de analyze
    llegó a ejecutar `ls`, `find` y `git remote -v` en el repo de un cliente."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash" not in log


def test_run_sobrevive_a_una_linea_gigante(client, monkeypatch):
    """El stream-json pasa de 64 KiB en una sola línea cuando el agente escribe un
    archivo grande. Leer por líneas reventaba ahí y marcaba `error` una corrida buena."""
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3322-analysis.md")
    monkeypatch.setenv("FAKE_BIG", "1")
    tid = client.post("/tickets", json={"ado_id": 3322, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "success"
    entero = Path(detail["runs"][0]["log_path"]).read_text(encoding="utf-8")
    assert "ácido" * 20000 in entero          # llegó completa y sin partir un carácter
    assert "�" not in entero             # ningún carácter roto entre trozos


def test_run_error_state(client, monkeypatch):
    _use_fake_claude(monkeypatch, fail=True)
    tid = client.post("/tickets", json={"ado_id": 8, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "error"


def test_prompt_design_no_menciona_analisis(client, monkeypatch):
    """I6: el entregable de una corrida design es el plan, no el análisis — decirle
    "análisis" al agente ahí lo manda a re-trabajar el archivo equivocado."""
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design", "instructions": "ajusta el alcance"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "análisis" not in log
    assert "el plan" in log


def test_rework_passes_instructions(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"instructions": "no consideraste el parent"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "no consideraste el parent" in detail["log_tail"]
    assert detail["runs"][0]["instructions"] == "no consideraste el parent"


def test_run_strips_api_key_so_subscription_is_used(client, monkeypatch):
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/11-analysis.md")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-no-debe-llegar")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tampoco")
    tid = client.post("/tickets", json={"ado_id": 11, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "success"
    assert "SAW-API-KEY" not in detail["log_tail"]


def test_runs_active(client):
    import os
    import sqlite3 as sq
    assert client.get("/runs/active").json() is None

    tid = client.post("/tickets", json={"ado_id": 3322, "project": "Demo"}).json()["id"]
    # Se inserta la corrida a mano: con TestClient el background task termina antes de
    # que vuelva la respuesta, así que no hay forma de observar una corrida "en vuelo".
    conn = sq.connect(os.environ["ORCH_DB"])
    conn.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'analyze','running')", (tid,))
    conn.commit()
    conn.close()

    a = client.get("/runs/active").json()
    assert a["ado_id"] == 3322 and a["project"] == "Demo" and a["ticket_id"] == tid


def test_run_pasa_allowed_tools_y_add_dir(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    # Sin --allowedTools, en headless las tools del MCP se auto-deniegan y el
    # agente se queda sin poder leer el work item.
    assert "--allowedTools mcp__azure-devops" in log
    # Los repos hermanos del proyecto viajan como --add-dir...
    assert "--add-dir" in log and "backend-repo" in log
    # ...y además se nombran en el prompt con su etiqueta: montarlos no basta para
    # que el agente los mire (lo comprobamos con Tenant en la corrida del 3322).
    assert "Repos adicionales montados" in log and "— backend" in log


def test_run_conflict_when_active(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 10, "project": "Demo"}).json()["id"]
    import app

    with app.db() as c:
        c.execute(
            "INSERT INTO runs(ticket_id, phase, status) VALUES(?, 'analyze', 'running')", (tid,)
        )
    assert client.post(f"/tickets/{tid}/run", json={}).status_code == 409


def test_fases_sin_corridas(client):
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    fases = client.get(f"/tickets/{tid}").json()["fases"]
    assert [f["fase"] for f in fases] == ["analyze", "design", "implement", "test", "guards", "pr"]
    assert fases[0] == {"fase": "analyze", "disponible": True, "estado": "pendiente",
                        "corridas": 0, "fallidas": 0}
    assert fases[2] == {"fase": "implement", "disponible": True, "estado": "pendiente",
                        "corridas": 0, "fallidas": 0}
    # una fase no ejecutable no informa estado: no hay nada que informar
    assert fases[3] == {"fase": "test", "disponible": False}
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


def test_huella_de_un_directorio_baja_a_subdirectorios(client, monkeypatch, tmp_path):
    """Un change de OpenSpec anida `specs/<capability>/spec.md`. Mirar solo los hijos
    directos deja ese archivo fuera de la cuenta, de los bytes y de `nombres` — justo el
    caso más común del entregable de `design`."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    (d / "specs" / "pagos").mkdir(parents=True)
    (d / "proposal.md").write_text("ab")
    (d / "tasks.md").write_text("cde")
    (d / "specs" / "pagos" / "spec.md").write_text("fghij")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    h = client.get(f"/tickets/{tid}").json()["fases"][1]["huella"]
    assert h["archivos"] == 3
    assert h["bytes"] == 2 + 3 + 5
    assert "specs/pagos/spec.md" in h["nombres"]


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


def test_corrida_historica_success_sin_huella_no_dice_que_fallo(client, monkeypatch):
    """Las 5 corridas históricas de antes de este contrato salieron con status=success
    (el CLI cerró en 0) y sin sello — no fallaron. `fases_de` las pinta como `error`
    porque no puede confiar en un artefacto sin declarar, pero el motivo no puede decir
    "falló" ahí: sería mentir sobre lo que de verdad pasó."""
    import os
    import sqlite3 as sq

    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    conn = sq.connect(os.environ["ORCH_DB"])
    conn.execute(
        "INSERT INTO runs(ticket_id, phase, status, started_at, finished_at) "
        "VALUES(?, 'analyze', 'success', '2026-01-01T00:00:00+00:00', "
        "'2026-01-01T00:01:00+00:00')",
        (tid,),
    )
    conn.commit()
    conn.close()
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "error"
    assert "falló" not in f["motivo"]
    assert "no declaró huella" in f["motivo"]
    assert "anterior a este contrato" in f["motivo"]


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


def test_artefacto_sirve_lo_declarado_por_una_corrida_parcial_con_reserva(
    client, monkeypatch, tmp_path
):
    """Regresión del hallazgo A: separar la reserva de la ruta en `artifact_path` no
    puede ensuciar la lista blanca del visor — un `parcial` con reserva se sigue
    sirviendo exactamente igual que uno sin ella."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "proposal.md").write_text("propuesta", encoding="utf-8")
    _use_fake_claude(
        monkeypatch,
        huella="parcial — openspec/changes/3323-xpo · openspec validate no pasó",
    )
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    r = client.get(f"/tickets/{tid}/artefacto",
                   params={"ruta": "openspec/changes/3323-xpo/proposal.md"})
    assert r.status_code == 200 and r.json()["texto"] == "propuesta"


def test_artefacto_sirve_un_hijo_directo_de_un_directorio_declarado(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] uno", encoding="utf-8")
    (d / "specs" / "pagos").mkdir(parents=True)
    (d / "specs" / "pagos" / "spec.md").write_text("# spec de pagos", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    r = client.get(f"/tickets/{tid}/artefacto",
                   params={"ruta": "openspec/changes/3323-xpo/tasks.md"})
    assert r.status_code == 200 and r.json()["texto"] == "- [ ] uno"
    # y un nieto: `stat_huella` cuenta recursivo, así que el visor tiene que admitirlo.
    r2 = client.get(f"/tickets/{tid}/artefacto",
                    params={"ruta": "openspec/changes/3323-xpo/specs/pagos/spec.md"})
    assert r2.status_code == 200 and r2.json()["texto"] == "# spec de pagos"


def test_artefacto_rechaza_ruta_no_declarada(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    (tmp_path / "repo" / "secreto.env").write_text("TOKEN=xxx", encoding="utf-8")
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "secreto.env"})
    assert r.status_code == 400


def test_artefacto_rechaza_travesia(client, monkeypatch, tmp_path):
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    for ruta in ("../../etc/passwd", "docs/../../fuera.md", "docs/tickets/../../../x"):
        assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": ruta}).status_code == 400


def test_artefacto_ruta_con_byte_nulo_da_400_no_500(client, monkeypatch, tmp_path):
    """`ruta` llega tal cual de la query string. Un byte nulo hace que `Path(...).resolve()`
    reviente con `ValueError` sin capturar — eso era un 500 en vez del 400 que le
    corresponde a una entrada inválida del cliente."""
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    import app

    try:
        app.artefacto(tid, "docs\x00tickets/a.md")
        assert False, "debía levantar HTTPException"
    except app.HTTPException as exc:
        assert exc.status_code == 400


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
    assert "�" not in r["texto"]      # no se parte un carácter multibyte al cortar


def test_artefacto_sirve_exactamente_512kb_sin_truncar(client, monkeypatch, tmp_path):
    """Frontera del tope: ni un byte de más entra en el corte, así que un archivo de
    exactamente TOPE bytes se sirve entero."""
    tid = _con_artefacto(client, monkeypatch, tmp_path, "justo.md", "x" * TOPE)
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "justo.md"}).json()
    assert r["truncado"] is False and r["bytes"] == TOPE and len(r["texto"]) == TOPE


def test_artefacto_rechaza_travesia_desde_directorio_declarado(client, monkeypatch, tmp_path):
    """CRÍTICO de la ronda 1: contra un directorio declarado (no un archivo), `..` sin
    normalizar dejaba fugarse a cualquier archivo del repo — verificado leyendo
    `secreto.env` fuera del change declarado. La regla 1 tiene que resolver la ruta
    ANTES de decidir si cae bajo lo declarado, igual que ya hacía la regla 2."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("x", encoding="utf-8")
    (tmp_path / "repo" / "secreto.env").write_text("DB_PASSWORD=superclave", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    posix = "openspec/changes/3323-xpo/../../../secreto.env"
    windows = "openspec\\changes\\3323-xpo\\..\\..\\..\\secreto.env"
    assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": posix}).status_code == 400
    assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": windows}).status_code == 400


def test_artefacto_artifact_path_vacio_no_es_comodin(client, monkeypatch, tmp_path):
    """IMPORTANTE de la ronda 1: un sello degenerado puede guardar `artifact_path=''`.
    `PurePosixPath('')` vale `.`, que "pertenece" a los `.parents` de cualquier ruta
    relativa — sin el filtro `!= ''` eso convierte la lista blanca en un comodín."""
    import os
    import sqlite3 as sq

    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    conn = sq.connect(os.environ["ORCH_DB"])
    conn.execute(
        "INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
        "VALUES(?, 'analyze', 'success', 'ok', '')", (tid,),
    )
    conn.commit()
    conn.close()
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artefacto_declarada_punto_no_es_comodin(client, monkeypatch, tmp_path):
    """RONDA 2: al pasar la regla 1 a rutas resueltas, `artifact_path='.'` resuelve a
    la raíz misma del repo, que sigue siendo un comodín aunque ya no sea `''`. La
    propiedad correcta es "estrictamente DENTRO de una raíz", no "distinto de ''"."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, huella="ok — .")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artefacto_declarada_doble_punto_no_es_comodin_y_alcanza_extra_dirs(
    client, monkeypatch, tmp_path
):
    """RONDA 2, el vector CRÍTICO verificado por el revisor: `artifact_path='..'`
    resuelve por encima del repo, y desde ahí `..` en la regla 2 vuelve a entrar tanto
    al repo principal como a los `extra_dirs` — cualquier archivo de cualquiera de los
    dos quedaba servible. `HUELLA: ok — ..` es alcanzable de verdad desde el sello de
    cierre de una skill degenerada."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    (tmp_path / "backend-repo" / "secreto-hermano.env").write_text("OTRO=1", encoding="utf-8")
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, huella="ok — ..")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": "../backend-repo/secreto-hermano.env"}).status_code == 400


def test_artefacto_declarada_dir_punto_punto_no_es_comodin(client, monkeypatch, tmp_path):
    """RONDA 2: `docs/..` resuelve a la raíz del repo igual que `.` — otra grafía para
    el mismo comodín, y la razón de que el arreglo tenga que ir por propiedad y no por
    lista de grafías prohibidas."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = _con_artefacto(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, huella="ok — docs/..")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artefacto_declarada_solo_espacios_no_es_comodin(client, monkeypatch, tmp_path):
    """RONDA 2: `leer_huella` hace `.strip()` sobre el sello, así que un `artifact_path`
    de solo espacios no puede llegar por el camino normal de una corrida — se simula
    insertando la fila directo, igual que el caso de `''` de la ronda 1."""
    import os
    import sqlite3 as sq

    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    conn = sq.connect(os.environ["ORCH_DB"])
    conn.execute(
        "INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
        "VALUES(?, 'analyze', 'success', 'ok', '   ')", (tid,),
    )
    conn.commit()
    conn.close()
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artefacto_directorio_de_primer_nivel_sigue_sirviendo(client, monkeypatch, tmp_path):
    """El filtro por propiedad de la ronda 2 no puede llevarse por delante el caso
    normal: una declarada legítima que sea un directorio de primer nivel del repo
    (aquí `docs`) sigue quedando estrictamente DENTRO de la raíz, así que sus hijos
    se siguen sirviendo."""
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "a.md").write_text("hola", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — docs")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "docs/tickets/a.md"})
    assert r.status_code == 200 and r.json()["texto"] == "hola"


def test_artefacto_travesia_que_vuelve_a_entrar_al_declarado_sirve(client, monkeypatch, tmp_path):
    """Una ruta con `..` no es sospechosa por tener `..`: lo que importa es dónde
    resuelve. Si vuelve a entrar al mismo directorio declarado, tiene que servirse
    igual que la forma directa — la regla 1 compara sobre `real`, ya resuelta."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] uno", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    ruta = "openspec/changes/3323-xpo/../3323-xpo/tasks.md"
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": ruta})
    assert r.status_code == 200 and r.json()["texto"] == "- [ ] uno"


def test_artefacto_declarada_dentro_de_un_extra_dir_sirve_su_hijo(client, monkeypatch, tmp_path):
    """Caso legítimo que no tenía cobertura propia: una declarada puede navegar fuera
    del `repo_path` hasta un `extra_dir` (son ambos raíces válidas del ticket), y su
    hijo se sigue sirviendo."""
    (tmp_path / "backend-repo" / "report.md").write_text("informe", encoding="utf-8")
    _use_fake_claude(monkeypatch, huella="ok — ../backend-repo/report.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "../backend-repo/report.md"})
    assert r.status_code == 200 and r.json()["texto"] == "informe"


def test_artefacto_extra_dir_ancestro_del_principal_no_reactiva_el_comodin(
    client, monkeypatch, tmp_path
):
    """RONDA 3: `any(rd != r and r in rd.parents for r in raices)` (ronda 2) funde dos
    preguntas — basta con que la declarada quede dentro de ALGUNA raíz, aunque SEA
    otra raíz. En un monorepo donde el `extra_dir` es ANCESTRO del `repo_path`
    (principal `Tenant/Web`, extra `Tenant`; `check_dirs` lo acepta porque solo mira
    `is_dir`), `.` resuelve al repo principal, que está estrictamente DENTRO del
    extra — y volvía a colar como huella, reactivando la vulnerabilidad original por
    configuración con el mismo disparador alcanzable (`HUELLA: ok — .`)."""
    (tmp_path / "Tenant" / "Web").mkdir(parents=True)
    (tmp_path / "Tenant" / "Api").mkdir(parents=True)
    (tmp_path / "Tenant" / "Web" / ".env").write_text("SECRETO=1", encoding="utf-8")
    (tmp_path / "Tenant" / "Api" / "appsettings.json").write_text(
        '{"ConnectionStrings": "secreta"}', encoding="utf-8")
    client.post("/projects", json={
        "name": "Anidado", "org": "O", "project": "P",
        "repos": [
            {"path": (tmp_path / "Tenant" / "Web").as_posix(), "label": "web", "primary": True},
            {"path": (tmp_path / "Tenant").as_posix(), "label": "tenant"},
        ],
    })
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Anidado"}).json()["id"]
    for huella in (".", "docs/..", ".."):
        _use_fake_claude(monkeypatch, huella=f"ok — {huella}")
        client.post(f"/tickets/{tid}/run", json={})
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": ".env"}).status_code == 400
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": "../Api/appsettings.json"}).status_code == 400


def test_artefacto_extra_dir_descendiente_del_principal_sigue_rechazando_comodin(
    client, monkeypatch, tmp_path
):
    """Dirección contraria del caso anidado: el `extra_dir` es DESCENDIENTE del
    `repo_path` (p. ej. un `vendor/` montado como repo aparte dentro del principal).
    `.` y `sub/..` siguen resolviendo a la raíz del repo principal, que sigue siendo
    una raíz — se descartan igual que en el caso plano."""
    (tmp_path / "repo2" / "vendor").mkdir(parents=True)
    (tmp_path / "repo2" / ".env").write_text("SECRETO=1", encoding="utf-8")
    client.post("/projects", json={
        "name": "Descendiente", "org": "O", "project": "P",
        "repos": [
            {"path": (tmp_path / "repo2").as_posix(), "label": "principal", "primary": True},
            {"path": (tmp_path / "repo2" / "vendor").as_posix(), "label": "vendor"},
        ],
    })
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Descendiente"}).json()["id"]
    for huella in (".", "vendor/.."):
        _use_fake_claude(monkeypatch, huella=f"ok — {huella}")
        client.post(f"/tickets/{tid}/run", json={})
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": ".env"}).status_code == 400


import subprocess

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _app(monkeypatch, tmp_path):
    """`app` se importa DENTRO de cada test porque conftest lo saca de `sys.modules`
    para que relea `ORCH_DB`. Estos tests no usan el fixture `client`, así que replican
    a mano su aislamiento (ver `test_current_phase_ya_no_existe`, línea ~312): sin fijar
    `ORCH_DB`/`ORCH_LOGS` y sin sacar `app` de `sys.modules`, un primer import real
    dispara `init_db()` contra la BD y los logs reales del backend — y lo que acaba en
    disco depende de qué test corrió primero."""
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "orch_test.db"))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    sys.path.insert(0, str(BACKEND_DIR))
    if "app" in sys.modules:
        del sys.modules["app"]
    import app
    return app


def _git_init(path):
    """Un repo con un commit: `git switch -c` necesita algo de donde colgar."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "seed.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)


def test_guarda_bloquea_un_trackeado_modificado(tmp_path, monkeypatch):
    """Sin esto, `git switch -c` arrastra tu trabajo sin commitear a la rama del
    agente y el agente lo commitea como suyo.

    El repo vive en un SUBdirectorio de `tmp_path`, nunca en `tmp_path` mismo: `_app`
    apunta `ORCH_DB`/`ORCH_LOGS` a `tmp_path`, y si el repo fuera `tmp_path` esa BD
    quedaría *dentro* del árbol bajo prueba — un `?? orch_test.db` parásito que
    `git status --porcelain` vería siempre, sin importar la lógica que el test dice
    ejercitar."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "seed.txt").write_text("v2\n", encoding="utf-8")
    assert app.sucio(str(repo)) is True


def test_guarda_tolera_los_no_trackeados(tmp_path, monkeypatch):
    """El caso que hace la fase lanzable: el repo principal SIEMPRE tiene
    `openspec/` y `docs/tickets/` sin trackear, que son artefactos del agente.
    Si este test falla, la fase implement es inlanzable para siempre."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "openspec").mkdir()
    (repo / "openspec" / "changes.md").write_text("x", encoding="utf-8")
    assert app.sucio(str(repo)) is False


def test_guarda_ve_lo_que_esta_en_stage(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "nuevo.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "nuevo.txt"], cwd=repo, check=True)
    assert app.sucio(str(repo)) is True


def test_check_limpios_nombra_los_repos_sucios(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    limpio, sucio_ = tmp_path / "a", tmp_path / "b"
    limpio.mkdir(); sucio_.mkdir()
    _git_init(limpio); _git_init(sucio_)
    (sucio_ / "seed.txt").write_text("v2\n", encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        app.check_limpios([str(limpio), str(sucio_)])
    assert e.value.status_code == 409
    assert str(sucio_) in e.value.detail
    assert str(limpio) not in e.value.detail


def test_un_directorio_que_no_es_git_da_409(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    (tmp_path / "pelado").mkdir()
    with pytest.raises(HTTPException) as e:
        app.check_limpios([str(tmp_path / "pelado")])
    assert e.value.status_code == 409


def test_preparar_rama_la_crea_y_se_situa_en_ella(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    nombre = app.preparar_rama(str(repo), 3320)
    assert nombre == "ticket-agent/3320"
    actual = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert actual == "ticket-agent/3320"


def test_preparar_rama_dos_veces_no_falla(tmp_path, monkeypatch):
    """Retomar una corrida parcial tiene que aterrizar en la MISMA rama. Con
    `switch -c` a secas, la segunda llamada peta con 'already exists'."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    app.preparar_rama(str(repo), 3320)
    subprocess.run(["git", "switch", "-q", "-"], cwd=repo, check=True)
    assert app.preparar_rama(str(repo), 3320) == "ticket-agent/3320"
    actual = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert actual == "ticket-agent/3320"
    ramas = subprocess.run(["git", "branch", "--list"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert ramas.count("ticket-agent/3320") == 1


def test_runs_tiene_columna_branch(client):
    import app
    with app.db() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(runs)")]
    assert "branch" in cols


def test_un_directorio_que_no_existe_da_409(tmp_path, monkeypatch):
    """No ya "no es un repo git": una ruta que ni siquiera está en disco. `sucio`
    comprueba `Path.is_dir()` antes de invocar `git`, así que esto da el mismo 409
    limpio sin necesidad de dejar que `subprocess.run` reviente con `cwd` inexistente."""
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        app.sucio(str(tmp_path / "no_existe"))
    assert e.value.status_code == 409


def test_git_ausente_no_se_disfraza_de_409(tmp_path, monkeypatch):
    """Un `git` ausente del PATH es un entorno mal configurado, no "no es un
    repositorio git": tiene que propagar, no convertirse en un 409 que miente sobre
    la causa. Se simula la ausencia parcheando `subprocess.run` (scoped por
    `monkeypatch`, revertido solo al terminar el test) en vez de tocar el PATH real
    de la sesión."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    def _sin_git(*args, **kwargs):
        raise FileNotFoundError("git no encontrado")

    monkeypatch.setattr(app.subprocess, "run", _sin_git)
    with pytest.raises(FileNotFoundError):
        app.sucio(str(repo))


def test_implement_con_repo_sucio_da_409_y_no_encola(client, monkeypatch, tmp_path):
    """El 409 llega ANTES de gastar un subproceso de 8 minutos."""
    import app
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    (tmp_path / "repo" / "seed.txt").write_text("v2\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 409
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_implement_guarda_la_rama_en_la_corrida(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3320-x/tasks.md")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"


def test_analyze_no_exige_repo_limpio(client, monkeypatch):
    """La guarda es de `implement`. Si se aplicara a todas, la Fase 1 dejaría de
    poder correrse sobre un repo con trabajo a medias, que es lo normal."""
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3311-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202


def test_sello_parcial_de_implement_conserva_la_reserva(client, monkeypatch, tmp_path):
    """El contrato del sello ya existía, pero nadie lo había ejercitado con la fase
    nueva ni con una reserva de esta forma. Falla si el parseo se ata a las rutas de
    `docs/tickets/` o si la reserva se cuela dentro de `artifact_path`."""
    _use_fake_claude(
        monkeypatch,
        huella="parcial — openspec/changes/3320-x/tasks.md · 3/5 tareas, build en rojo")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["artifact_state"] == "parcial"
    assert run["artifact_path"] == "openspec/changes/3320-x/tasks.md"
    assert run["artifact_note"] == "3/5 tareas, build en rojo"


def test_implement_con_segundo_repo_sucio_no_deja_el_primero_en_otra_rama(
    client, monkeypatch, tmp_path
):
    """El repo sucio es el SEGUNDO (`backend-repo`), con el principal limpio. Si la
    guarda se entremezclara con la creación de rama repo a repo (comprobar y ramificar
    uno, luego el siguiente), el principal ya habría pasado a `ticket-agent/<id>` antes
    de que la comprobación del segundo repo fallara. `test_implement_con_repo_sucio_
    da_409_y_no_encola` no distingue esto porque ensucia el repo principal — el primero
    de la lista — así que una implementación entremezclada falla en la misma primera
    iteración y ese test no la delata."""
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    original = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path / "repo",
        capture_output=True, text=True,
    ).stdout.strip()
    (tmp_path / "backend-repo" / "seed.txt").write_text("v2\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 409
    assert client.get(f"/tickets/{tid}").json()["runs"] == []
    actual = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path / "repo",
        capture_output=True, text=True,
    ).stdout.strip()
    assert actual == original


def test_implement_con_un_solo_repo_prepara_la_rama(client, monkeypatch, tmp_path):
    """El camino sin repos extra (`extra_dirs` vacío) no se ejercitaba nunca desde
    el endpoint: todos los tests anteriores de `implement` usan el proyecto `Demo`,
    que siempre trae un repo extra."""
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3320-x/tasks.md")
    solo = tmp_path / "solo-repo"
    solo.mkdir()
    _git_init(solo)
    client.post("/projects", json={
        "name": "Solo", "org": "O", "project": "P",
        "repos": [{"path": solo.as_posix(), "primary": True}],
    })
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Solo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 202
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"
