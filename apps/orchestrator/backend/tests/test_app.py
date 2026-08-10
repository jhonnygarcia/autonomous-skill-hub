def test_db_tables_created(client):
    import app

    with app.db() as c:
        names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tickets", "runs"} <= names


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


def _use_fake_claude(monkeypatch, fail=False, plan_sello=None):
    fake = Path(__file__).parent / "fake_claude.py"
    monkeypatch.setenv("ORCH_CLAUDE_CMD", json.dumps([sys.executable, str(fake)]))
    monkeypatch.setenv("FAKE_FAIL", "1" if fail else "0")
    if plan_sello is None:
        monkeypatch.delenv("FAKE_PLAN_SELLO", raising=False)
    else:
        monkeypatch.setenv("FAKE_PLAN_SELLO", plan_sello)


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


def test_run_design_invoca_el_comando_plan(client, monkeypatch):
    """La fase decide el comando: design NO puede lanzar el analyze."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "/ticket-agent:plan 3323" in detail["log_tail"]
    assert "/ticket-agent:analyze" not in detail["log_tail"]
    assert detail["runs"][0]["phase"] == "design"


def test_run_design_deja_el_ticket_planned(client, monkeypatch):
    _use_fake_claude(monkeypatch, plan_sello="validado — la validación de OpenSpec pasó")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert client.get(f"/tickets/{tid}").json()["ticket"]["status"] == "planned"


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
    _use_fake_claude(monkeypatch)
    monkeypatch.setenv("FAKE_BIG", "1")
    tid = client.post("/tickets", json={"ado_id": 3322, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "analyzed"
    assert detail["runs"][0]["status"] == "success"
    entero = Path(detail["runs"][0]["log_path"]).read_text(encoding="utf-8")
    assert "ácido" * 20000 in entero          # llegó completa y sin partir un carácter
    assert "�" not in entero             # ningún carácter roto entre trozos


def test_run_error_state(client, monkeypatch):
    _use_fake_claude(monkeypatch, fail=True)
    tid = client.post("/tickets", json={"ado_id": 8, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "error"
    assert detail["runs"][0]["status"] == "error"


def test_design_sello_validado_deja_planned(client, monkeypatch):
    _use_fake_claude(monkeypatch, plan_sello="validado — la validación de OpenSpec pasó")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "planned"
    assert detail["runs"][0]["status"] == "success"


def test_design_sello_sin_validar_deja_planned(client, monkeypatch):
    _use_fake_claude(monkeypatch, plan_sello="sin-validar — dos intentos de validación fallaron")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "planned"
    assert detail["runs"][0]["status"] == "success"


def test_design_sello_no_escrito_deja_error(client, monkeypatch):
    """El spec exige `error` cuando falta el análisis o el CLI de OpenSpec no está
    disponible: la skill cierra con este sello en esos casos."""
    _use_fake_claude(monkeypatch, plan_sello="no-escrito — falta el análisis de la Fase 1")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "error"
    assert detail["runs"][0]["status"] == "error"


def test_design_sin_sello_se_trata_como_error(client, monkeypatch):
    """I2: `claude -p` sale con 0 aunque el agente se haya detenido sin hacer nada.
    Sin sello no hay forma de distinguir eso de un plan real, así que se trata como
    error aunque el proceso no haya fallado."""
    _use_fake_claude(monkeypatch)  # sin FAKE_PLAN_SELLO
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "error"
    assert detail["runs"][0]["status"] == "error"


def test_sello_no_se_exige_en_analyze(client, monkeypatch):
    """El contrato del sello es solo de la Fase 2: analyze no debe verse afectado."""
    _use_fake_claude(monkeypatch)  # sin FAKE_PLAN_SELLO
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "analyzed"
    assert detail["runs"][0]["status"] == "success"


def test_prompt_design_no_menciona_analisis(client, monkeypatch):
    """I6: el entregable de una corrida design es el plan, no el análisis — decirle
    "análisis" al agente ahí lo manda a re-trabajar el archivo equivocado."""
    _use_fake_claude(monkeypatch, plan_sello="validado — ok")
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
    _use_fake_claude(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-no-debe-llegar")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tampoco")
    tid = client.post("/tickets", json={"ado_id": 11, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["ticket"]["status"] == "analyzed"
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
