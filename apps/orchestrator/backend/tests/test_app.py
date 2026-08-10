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


def test_current_phase_ya_no_existe(client):
    import app
    with app.db() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(tickets)")}
    assert "current_phase" not in cols
    assert {"artifact_state", "artifact_path"} <= {
        r["name"] for r in app.db().execute("PRAGMA table_info(runs)")}


def test_fase_declarada_pero_no_ejecutable_da_400(client, monkeypatch):
    """implement está en PHASES pero no existe: se rechaza sin lanzar subproceso."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 400 and "implement" in r.json()["detail"]
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
    otra cosa."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in log
    assert " Bash " not in log        # nunca Bash a secas


def test_bash_incluye_las_dos_formas_de_invocar_openspec_en_design(client, monkeypatch):
    """El especificador tiene que calzar literalmente con el principio del comando:
    hacen falta las dos formas (`npx --yes ...@latest` y `npx ...` a secas)."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in log
    assert "Bash(npx @fission-ai/openspec:*)" in log


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
