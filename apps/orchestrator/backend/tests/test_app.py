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
