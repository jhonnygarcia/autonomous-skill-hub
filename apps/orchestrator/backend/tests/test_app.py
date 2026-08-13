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
    # a single list; the primary one is flagged, not in a separate field
    assert len(p["repos"]) == 2
    primary = [r for r in p["repos"] if r["primary"]]
    assert len(primary) == 1 and primary[0]["label"] == "front"
    assert all(Path(r["path"]).is_dir() for r in p["repos"])
    assert [r["label"] for r in p["repos"] if not r["primary"]] == ["backend"]


def test_project_crud_rejects_nonexistent_paths(client):
    bad = client.post("/projects", json={
        "name": "Roto", "org": "O", "project": "P",
        "repos": [{"path": "/no/existe", "primary": True}],
    })
    assert bad.status_code == 400 and "/no/existe" in bad.json()["detail"]
    assert client.post("/projects", json={
        "name": "Demo", "org": "O", "project": "P", "repos": _repos(client),
    }).status_code == 409


def test_project_requires_a_single_primary(client):
    repos = _repos(client)
    without_primary = client.post("/projects", json={
        "name": "Sin", "org": "O", "project": "P",
        "repos": [{**r, "primary": False} for r in repos],
    })
    assert without_primary.status_code == 400 and "principal" in without_primary.json()["detail"]

    two_primaries = client.post("/projects", json={
        "name": "Dos", "org": "O", "project": "P",
        "repos": [{**r, "primary": True} for r in repos],
    })
    assert two_primaries.status_code == 400 and "principal" in two_primaries.json()["detail"]

    empty = client.post("/projects", json={"name": "V", "org": "O", "project": "P", "repos": []})
    assert empty.status_code == 400 and "al menos un repo" in empty.json()["detail"]


def test_change_which_repo_is_primary(client):
    repos = _repos(client)
    flipped = [{**r, "primary": not r["primary"]} for r in repos]
    r = client.put("/projects/Demo", json={
        "name": "Demo", "org": "DemoOrg", "project": "Demo", "repos": flipped,
    })
    assert r.status_code == 200
    new_primary = [x for x in r.json()["repos"] if x["primary"]][0]
    assert new_primary["label"] == "backend"
    # and the ticket created now uses that repo as cwd
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == new_primary["path"]


def test_rename_project(client):
    repos = _repos(client)
    body = {"org": "DemoOrg", "project": "Demo", "repos": repos}
    # a ticket created earlier keeps its paths: it doesn't point at the catalog
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    before = client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"]

    r = client.put("/projects/Demo", json={"name": "Demo2", **body})
    assert r.status_code == 200 and r.json()["name"] == "Demo2"
    assert [p["name"] for p in client.get("/projects").json()] == ["Demo2"]
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == before

    # and the name is still unique
    client.post("/projects", json={"name": "Otro", **body})
    conflict = client.put("/projects/Otro", json={"name": "Demo2", **body})
    assert conflict.status_code == 409


def test_project_update_and_delete(client):
    primary_repos = [r for r in _repos(client) if r["primary"]]
    r = client.put("/projects/Demo", json={
        "name": "Demo", "org": "OtraOrg", "project": "Demo", "repos": primary_repos,
    })
    assert r.status_code == 200 and r.json()["org"] == "OtraOrg" and len(r.json()["repos"]) == 1
    assert client.delete("/projects/Demo").status_code == 204
    assert client.get("/projects").json() == []
    assert client.delete("/projects/Demo").status_code == 404


def test_ticket_inherits_extra_dirs_from_project(client):
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    t = client.get(f"/tickets/{tid}").json()["ticket"]
    assert len(json.loads(t["extra_dirs"])) == 1
    # the ticket keeps its own copy even if the project disappears from the catalog
    client.delete("/projects/Demo")
    assert client.get(f"/tickets/{tid}").json()["ticket"]["repo_path"] == t["repo_path"]


import json
import sys
from pathlib import Path


def _phase(client, tid, name):
    """By name, never by index. The phase list grew when the multi-repo route landed
    and every positional access broke at once — the tests always meant the name."""
    return next(f for f in client.get(f"/tickets/{tid}").json()["fases"]
                if f["fase"] == name)


def _use_fake_claude(monkeypatch, fail=False, stamp=None, skill_leak=False, no_session=False):
    fake = Path(__file__).parent / "fake_claude.py"
    monkeypatch.setenv("ORCH_CLAUDE_CMD", json.dumps([sys.executable, str(fake)]))
    monkeypatch.setenv("FAKE_FAIL", "1" if fail else "0")
    monkeypatch.setenv("FAKE_SKILL_LEAK", "1" if skill_leak else "0")
    monkeypatch.setenv("FAKE_NO_SESSION", "1" if no_session else "0")
    if stamp is None:
        monkeypatch.delenv("FAKE_HUELLA", raising=False)
    else:
        monkeypatch.setenv("FAKE_HUELLA", stamp)


def test_run_success_writes_log_and_states(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3311-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202
    detail = client.get(f"/tickets/{tid}").json()  # TestClient runs the background task before
    run = detail["runs"][0]
    assert run["status"] == "success" and run["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_run_design_invokes_plan_command(client, monkeypatch):
    """The phase decides the command: design must NOT be able to launch analyze."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "/ticket-agent:plan 3323" in detail["log_tail"]
    assert "/ticket-agent:analyze" not in detail["log_tail"]
    assert detail["runs"][0]["phase"] == "design"


def test_stamp_ok_leaves_run_successful(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "success"
    assert run["artifact_state"] == "ok"
    assert run["artifact_path"] == "docs/tickets/3323-analysis.md"


def test_stamp_partial_run_counts_and_keeps_reserve(client, monkeypatch):
    """The reserve of a `parcial` travels WITHIN the stamp, after ` · ` — not in the
    summary. The runner splits it from the path: `artifact_path` stays clean (the
    viewer's whitelist) and the reserve comes out via `phases_for` as `motivo`, just
    like `error` already does."""
    _use_fake_claude(
        monkeypatch,
        stamp="parcial — openspec/changes/3323-xpo · openspec validate no pasó",
    )
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    run = detail["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "parcial"
    # the path stays clean, without the reserve hanging off the back
    assert run["artifact_path"] == "openspec/changes/3323-xpo"
    fase = _phase(client, tid, "design")
    assert fase["estado"] == "parcial"
    assert fase["motivo"] == "openspec validate no pasó"


def test_stamp_partial_without_reserve_still_works(client, monkeypatch):
    """A `parcial` without ` · ` has no reserve: it has to keep working the same as
    before this change, with no `motivo`."""
    _use_fake_claude(monkeypatch, stamp="parcial — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    run = detail["runs"][0]
    assert run["status"] == "success" and run["artifact_state"] == "parcial"
    assert run["artifact_path"] == "openspec/changes/3323-xpo"
    fase = _phase(client, tid, "design")
    assert fase["estado"] == "parcial"
    assert "motivo" not in fase


def test_stamp_nothing_leaves_run_in_error(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="nada — falta el análisis de la Fase 1")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"
    assert "falta el análisis" in run["artifact_path"]


def test_without_stamp_run_is_error_in_any_phase(client, monkeypatch):
    """`claude -p` exits 0 even when the agent stopped without doing anything. Without
    a stamp there's no way to tell that apart from a real run. Before, analyze was
    exempt; now the contract applies to all of them."""
    _use_fake_claude(monkeypatch)  # no FAKE_HUELLA
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"
    assert "no declaró huella" in run["artifact_path"]


def test_stamp_anchors_on_last_match(client, monkeypatch):
    """The tool_result of loading SKILL.md leaves the three stamps in prose inside the
    log, BEFORE the real closing one. Checking for mere presence makes the check find
    itself and wrongly approve a run that actually closed with `nada`."""
    _use_fake_claude(monkeypatch, skill_leak=True, stamp="nada — falta el análisis")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error" and run["artifact_state"] == "nada"


def test_legacy_PLAN_stamp_still_understood(client, monkeypatch):
    """The 3323 run logs were written with `PLAN:`. Translating them keeps existing
    history from showing up as failed the day the timeline is looked at."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    import app
    log = Path(client.get(f"/tickets/{tid}").json()["runs"][0]["log_path"])
    log.write_text("bla\nPLAN: validado — todo bien\n", encoding="utf-8")
    assert app.read_stamp(log) == ("ok", "todo bien")
    log.write_text("PLAN: sin-validar — falló\n", encoding="utf-8")
    assert app.read_stamp(log)[0] == "parcial"
    log.write_text("PLAN: no-escrito — sin análisis\n", encoding="utf-8")
    assert app.read_stamp(log)[0] == "nada"


def test_read_stamp_with_real_stream_json_shape(tmp_path):
    """The real log from `claude -p --output-format stream-json` is not a flat line:
    the stamp travels nested in `message.content[].text`, followed on the same line by
    `stop_reason`, `usage`, `session_id`, `uuid` and more. With a greedy `(.+)`,
    `read_stamp` used to return the path with all that trailer stuck behind it — exactly
    the string a caller would hand to `declared_file` to serve as the artifact's path."""
    import app
    line = (
        '{"type":"assistant","message":{"content":[{"type":"text",'
        '"text":"resumen. HUELLA: ok — docs/tickets/3323-analysis.md"}],'
        '"stop_reason":null},"session_id":"sess-1","uuid":"uuid-1",'
        '"timestamp":"2026-08-10T00:00:00Z","request_id":"req_1"}\n'
    )
    log = tmp_path / "run.log"
    log.write_text(line, encoding="utf-8")
    assert app.read_stamp(log) == ("ok", "docs/tickets/3323-analysis.md")


def test_current_phase_no_longer_exists(tmp_path, monkeypatch):
    """Before, this test ran against a DB freshly created by the `client` fixture,
    whose `CREATE TABLE` never included `current_phase`: it passed without ever
    running the `ALTER TABLE ... DROP COLUMN` it claimed to protect — pure placebo.
    Here a DB with the OLD schema is built by hand (with `current_phase`, without
    `artifact_state` or `artifact_path`) and `init_db` is left to migrate it for
    real."""
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
    assert "title" in cols_tickets
    assert {"artifact_state", "artifact_path", "artifact_note"} <= cols_runs


def test_declared_but_unlaunchable_phase_gives_400(client, monkeypatch):
    """A phase absent from PHASE_COMMANDS is rejected without spawning a
    subprocess. `guards` used to be declared in PHASES and unlaunchable; it is no
    longer declared at all, and the rejection is unchanged either way — what gates
    a run is the command table, not the declaration."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "guards"})
    assert r.status_code == 400 and "guards" in r.json()["detail"]
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_run_without_phase_defaults_to_analyze(client, monkeypatch):
    """Compatibility: whoever already called without a phase doesn't notice the
    change."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_bash_is_scoped_to_openspec(client, monkeypatch):
    """Phase 2 needs to invoke `@fission-ai/openspec`; nothing else. A bare Bash would
    be a different thing.

    Checked against the REAL subprocess arguments, not a substring of the log:
    `assert " Bash " not in log` looked for "Bash" surrounded by spaces on both
    sides, and a bare "Bash" at the END of the `--allowedTools` list is followed by a
    newline, not a space — the check didn't see it there."""
    _use_fake_claude(monkeypatch)
    import asyncio

    captured = {}
    original = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        captured["argv"] = args
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in captured["argv"]
    assert "Bash" not in captured["argv"]       # never a bare Bash, as an exact argument


def test_bash_includes_both_ways_to_invoke_openspec_in_design(client, monkeypatch):
    """The specifier has to match literally with the start of the command: both forms
    are needed (`npx --yes ...@latest` and bare `npx ...`)."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash(npx --yes @fission-ai/openspec@latest:*)" in log
    assert "Bash(npx @fission-ai/openspec:*)" in log


def _spy_argv(monkeypatch):
    """Against the REAL subprocess arguments, not a substring of the log."""
    import asyncio
    captured = {}
    original = asyncio.create_subprocess_exec

    async def spy(*args, **kwargs):
        captured["argv"] = args
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return captured


def test_implement_carries_bare_bash_and_settings(client, monkeypatch, tmp_path):
    """The hook isn't valid because it's mentioned, it's valid because of its shape:
    the `--settings` JSON is parsed and asserted on its structure.

    Looking for the substring `deny_push.py` in the argument let four mutations
    through that neuter the hook completely, verified one by one: `PreToolUse`→
    `PostToolUse` (it would run AFTER the push, with the `exit 2` already having
    nothing left to stop), a different `matcher` (it wouldn't fire on Bash), a
    different `type` (Claude doesn't execute it), and a script path that doesn't
    exist on disk."""
    import app
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    argv = cap["argv"]
    assert "Bash" in argv                      # bare, not a specifier
    assert "--settings" in argv

    cfg = json.loads(argv[argv.index("--settings") + 1])
    # BEFORE the push, or it isn't a containment: it's a chronicle.
    assert list(cfg["hooks"]) == ["PreToolUse"]
    [entry] = cfg["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Bash"          # the only tool that could push anything
    [hook] = entry["hooks"]
    assert hook["type"] == "command"
    # The command is `"<python>" "<script>"`: the last quoted string is the hook, and
    # it has to be a file that really exists — a `--settings` pointing at a script
    # that doesn't exist is a hook that never runs.
    hook_path = Path(hook["command"].split('"')[-2])
    assert hook_path.name == "deny_push.py" and hook_path.is_file()


def test_models_default_empty(client):
    """With nothing configured, every launchable phase comes out empty: the CLI
    resolves the model from the destination repo, which is how it worked before this
    existed."""
    m = client.get("/modelos").json()
    assert set(m) == {"analyze", "brief", "survey", "consolidate", "design", "implement"}
    assert all(v == {"model": "", "effort": ""} for v in m.values())


def test_model_and_effort_per_phase_reach_argv(client, monkeypatch):
    """What's configured in Settings has to show up in the subprocess argv; a phase
    left unconfigured carries no flags and keeps the repo's default."""
    _use_fake_claude(monkeypatch)
    client.put("/modelos", json={"analyze": {"model": "sonnet", "effort": "low"}})
    cap = _spy_argv(monkeypatch)

    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    argv = cap["argv"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--effort") + 1] == "low"

    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert "--model" not in cap["argv"] and "--effort" not in cap["argv"]


def test_models_are_read_at_launch_not_at_startup(client, monkeypatch):
    """Changing the model in Settings affects the next run without restarting the
    backend — which on Windows is exactly what can't be done live."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]

    client.post(f"/tickets/{tid}/run", json={})
    assert "--model" not in cap["argv"]

    client.put("/modelos", json={"analyze": {"model": "opus", "effort": ""}})
    client.post(f"/tickets/{tid}/run", json={})
    argv = cap["argv"]
    assert argv[argv.index("--model") + 1] == "opus"
    assert "--effort" not in argv       # vacío = no se pasa la bandera


@pytest.mark.parametrize("payload", [
    {"guards": {"model": "opus"}},           # fase no ejecutable: ni declarada ni con comando
    {"analyze": {"model": "--dangerously"}},  # se colaría como otra bandera del CLI
    {"analyze": {"model": "opus 5"}},
    {"analyze": {"effort": "altísimo"}},
])
def test_models_reject_garbage(client, payload):
    assert client.put("/modelos", json=payload).status_code == 400


def test_models_do_not_save_partially(client):
    """Validates everything before writing anything: if the second phase is invalid,
    the first one doesn't get saved either."""
    r = client.put("/modelos", json={"analyze": {"model": "opus"},
                                     "implement": {"effort": "turbo"}})
    assert r.status_code == 400
    assert client.get("/modelos").json()["analyze"]["model"] == ""


def test_analyze_carries_no_settings_or_bash(client, monkeypatch):
    """The list must not go back to traveling fixed for all phases: that's exactly
    what made Phase 1, declared read-only, end up running shell."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "--settings" not in cap["argv"]
    assert "Bash" not in cap["argv"]


def _prompt_from(cap):
    """The real `-p` of the subprocess, which is the only thing the agent gets to
    read."""
    argv = cap["argv"]
    return argv[argv.index("-p") + 1]


def test_implement_prompt_declares_extra_repos_writable(client, monkeypatch, tmp_path):
    """Design decision 4: in `implement` EVERY mounted repo of the ticket is writable.

    This isn't a wording nuance: the `change-implementation` skill (section 3) tells
    the agent to obey the prompt when the plan's map and the prompt differ, so a
    prompt that says "readable / writes go to the primary" is the wrong instruction
    with maximum priority — and 3320 has all its code in an `extra_dir`.
    """
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    prompt = _prompt_from(cap)
    assert "backend-repo" in prompt            # the extra is still named
    assert "writable" in prompt
    assert "readable" not in prompt
    assert "is still written in the main one" not in prompt


def test_analyze_prompt_keeps_extra_repos_readable(client, monkeypatch):
    """The other side of the branch. A test that only looked at `implement` would pass
    just the same with the writable text traveling in ALL phases — which is exactly
    the symmetric defect: Phase 1 is read-only."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    prompt = _prompt_from(cap)
    assert "backend-repo" in prompt
    assert "readable" in prompt
    assert "the analysis is still written in the main one" in prompt
    assert "writable" not in prompt


def test_run_captures_the_session_id(client, monkeypatch):
    """Without it there's no continuing a phase: `--resume` needs the id, and the only
    place it exists is the stream the runner is already reading."""
    from fake_claude import FAKE_SESSION
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}").json()["runs"][0]["session_id"] == FAKE_SESSION


def test_a_run_without_session_id_still_finishes(client, monkeypatch):
    """A missing id must not cost a good run. It only takes away the option to
    continue it — which is what `puede_continuar` reports."""
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/12-analysis.md", no_session=True)
    tid = client.post("/tickets", json={"ado_id": 12, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["session_id"] is None and run["status"] == "success"


def test_the_session_id_is_found_beyond_the_first_chunk(client, monkeypatch):
    """The stream is read in 64 KiB chunks. In a real run the id arrives in the first
    event, which makes "look at the first chunk and be done" the tempting shortcut —
    and it fails silently: the run comes out fine and simply can't be continued, with
    nothing saying why. Here the id is pushed past the first read.

    What this does NOT cover: the id landing astride two chunks. A pipe read can
    return short, so that boundary can't be placed deterministically from a test. The
    `carry` in the loop covers it without a test proving it, and that's stated
    where it lives."""
    from fake_claude import FAKE_SESSION
    _use_fake_claude(monkeypatch)
    monkeypatch.setenv("FAKE_SESSION_LATE", "1")
    tid = client.post("/tickets", json={"ado_id": 13, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}").json()["runs"][0]["session_id"] == FAKE_SESSION


def _solo_project(client, tmp_path):
    """A single-repo project: the one that keeps today's `analyze` route."""
    client.post("/projects", json={
        "name": "Solo", "org": "DemoOrg", "project": "Demo",
        "repos": [{"path": (tmp_path / "repo").as_posix(), "label": "front", "primary": True}],
    })


def test_the_four_tables_agree_on_the_new_phases():
    """A phase declared in one dict and missing from another is an uncaught KeyError
    inside a background task, leaving the run at `success` and the ticket untouched."""
    import app
    for table in (app.PHASE_COMMANDS, app.PHASE_DONE, app.PHASE_ALLOWED_TOOLS, app.PHASE_NOUN):
        for name in ("brief", "survey", "consolidate"):
            assert name in table
    # Only `consolidate` closes the analysis: an interrupted fan-out must not look
    # finished just because the brief went well.
    assert app.PHASE_DONE["brief"] != "analyzed"
    assert app.PHASE_DONE["consolidate"] == "analyzed"


def test_the_children_of_the_fan_out_carry_no_mcp(client, monkeypatch, tmp_path):
    """The survey runs rooted in a secondary repo with the brief inline in its prompt.
    Giving it MCP would mean that repo needs ADO_ORG, a token and its own
    ticket-agent.json — a second configuration to keep in sync, to fetch a work item
    it was already handed."""
    import app
    # `PHASE_ALLOWED_TOOLS` is not enough on its own: the MCP tool travels fixed in the
    # argv, so an empty list there doesn't remove it. This test found exactly that.
    assert "survey" not in app.PHASE_MCP and "consolidate" not in app.PHASE_MCP
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 30)
    tid = client.post("/tickets", json={"ado_id": 30, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    cap = _spy_argv(monkeypatch)
    client.post(f"/tickets/{tid}/run", json={"phase": "consolidate"})
    assert "mcp__azure-devops" not in list(cap["argv"])


def test_a_single_repo_ticket_keeps_the_analyze_route(client, tmp_path):
    """Nothing to fan out: offering `survey` there would be offering a fan-out with
    one repo in it."""
    _solo_project(client, tmp_path)
    tid = client.post("/tickets", json={"ado_id": 31, "project": "Solo"}).json()["id"]
    names = [f["fase"] for f in client.get(f"/tickets/{tid}").json()["fases"]]
    assert names == ["analyze", "design", "implement"]


def test_a_multi_repo_ticket_gets_the_fan_out_and_keeps_analyze(client):
    """`analyze` stays: it's the fallback if the fan-out gets stuck, and it's the
    baseline the whole design has to be measured against. Hiding what you're comparing
    to makes the comparison impossible — and both routes write the same file."""
    tid = client.post("/tickets", json={"ado_id": 32, "project": "Demo"}).json()["id"]
    names = [f["fase"] for f in client.get(f"/tickets/{tid}").json()["fases"]]
    assert names == ["analyze", "brief", "survey", "consolidate", "design", "implement"]


def test_a_phase_counts_the_decisions_it_left_open(client, monkeypatch, tmp_path):
    """Without the count nobody reads the `Decisiones para ti` sections: the only way
    to find them today is to open an 8 KB document and go hunting. A ticked box is an
    answered decision and must not keep asking."""
    (tmp_path / "repo" / "a.md").write_text(
        "# Analysis\n"
        "## Decisiones para ti\n"
        "- [ ] **DECIDIR** — ¿el back o el front?\n"
        "- [x] **DECIDIR** — ya respondida, no cuenta\n"
        "- [ ] **BLOQUEA** — el ticket no dice si respeta el filtro\n",
        encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 50, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert _phase(client, tid, "analyze")["decisiones"] == {"decidir": 1, "bloquea": 1}


def test_a_deliverable_without_decisions_says_nothing(client, monkeypatch, tmp_path):
    """Absence is not zero: a phase with nothing to decide must not paint a counter."""
    (tmp_path / "repo" / "a.md").write_text("# Analysis\nsin decisiones\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 51, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "decisiones" not in _phase(client, tid, "analyze")


def _write_brief(tmp_path, ado_id, routing="SONDEAR: front, backend"):
    d = tmp_path / "repo" / "docs" / "tickets"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ado_id}-brief.md").write_text(
        f"# Brief {ado_id}\n\nCriterio: exportar a Excel.\n\n{routing}\n", encoding="utf-8")


def test_the_brief_is_told_the_primary_repos_label(client, monkeypatch):
    """Found on run 3320 (2026-08-13): the prompt named the extras and left the agent to
    invent a name for the repo it was standing in. It wrote `SONDEAR: main, tms` when
    the label was `tenant`. The routing widened to every repo — the safe direction held
    — but the optimization was lost to a name nobody had told it."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 39, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "brief"})
    prompt = _prompt_from(cap)
    assert "`front`" in prompt and "backend" in prompt      # both labels, verbatim
    assert "SONDEAR" in prompt                              # and what they're for


def test_only_the_brief_gets_the_routing_labels(client, monkeypatch):
    """The other phases don't write a routing line, and a prompt that explains one is a
    prompt inviting a phase to produce something nobody reads."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 38, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "SONDEAR" not in _prompt_from(cap)


def test_survey_launches_one_child_per_routed_repo(client, monkeypatch, tmp_path):
    """One session rooted in each repo is the whole point: it's the only way its
    CLAUDE.md, its hooks and its `.mcp.json` are loaded at all."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 40)
    cwds = []
    import asyncio as aio
    original = aio.create_subprocess_exec

    async def spy(*args, **kwargs):
        cwds.append(kwargs.get("cwd"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(aio, "create_subprocess_exec", spy)
    tid = client.post("/tickets", json={"ado_id": 40, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    assert len(cwds) == 2
    assert {Path(c).name for c in cwds} == {"repo", "backend-repo"}


def test_survey_routing_narrows_the_children(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 41, routing="SONDEAR: backend")
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 41, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "survey: backend" in log and "survey: front" not in log
    assert cap["argv"][argv_index(cap, "-p") + 1].count("rooted in the repo") == 1


def argv_index(cap, flag):
    return list(cap["argv"]).index(flag)


def test_a_survey_child_mounts_only_the_scratch(client, monkeypatch, tmp_path):
    """The sibling repos are deliberately absent: mounting them would put the primary
    repo's rules back in front of the child, which is the very thing the fan-out
    exists to avoid. The scratch holds no `.claude/`, so it leaks no configuration."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 42, routing="SONDEAR: backend")
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 42, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    argv = list(cap["argv"])
    mounted = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
    assert len(mounted) == 1 and mounted[0].endswith(str(_last_run_id(client, tid)))
    assert not any("repo" == Path(m).name for m in mounted)


def _last_run_id(client, tid):
    return client.get(f"/tickets/{tid}").json()["runs"][0]["id"]


def test_a_survey_child_gets_the_brief_inline(client, monkeypatch, tmp_path):
    """The children carry no MCP: the work item is unreachable from there, so whatever
    the brief doesn't say does not exist for them."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 43, routing="SONDEAR: backend")
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 43, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    prompt = _prompt_from(cap)
    assert "Criterio: exportar a Excel." in prompt
    assert "mcp__azure-devops" not in list(cap["argv"])


def test_survey_without_a_brief_does_not_start(client, monkeypatch, tmp_path):
    """It doesn't generate the brief itself: they're two phases and this is the second.
    Same rule Phase 2 already applies to the analysis."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 44, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    f = _phase(client, tid, "survey")
    assert f["estado"] == "error" and "brief" in f["motivo"]


def test_a_failed_child_does_not_hide_behind_a_good_one(client, monkeypatch, tmp_path):
    """The most expensive failure in this system is an analysis that looks complete and
    isn't. Each child's verdict is read from ITS stretch of the log — reading the last
    stamp of the whole file would let one good survey vouch for a silent one.

    The discriminating case is the FIRST child stamping and the second not: reading the
    whole file would find the first one's stamp at the end of the second one's read and
    count a silent child as a success. Two children where the failure comes first, or
    where it exits non-zero, pass either way — the exit code carries them.
    """
    _use_fake_claude(monkeypatch)                       # no stamp by default
    _write_brief(tmp_path, 45)
    calls = {"n": 0}
    import asyncio as aio
    original = aio.create_subprocess_exec

    async def only_the_first_stamps(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            kwargs = {**kwargs, "env": {**kwargs["env"], "FAKE_HUELLA": "ok — survey.md"}}
        return await original(*args, **kwargs)

    monkeypatch.setattr(aio, "create_subprocess_exec", only_the_first_stamps)
    tid = client.post("/tickets", json={"ado_id": 45, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    f = _phase(client, tid, "survey")
    assert f["estado"] == "parcial"
    assert "falló backend" in client.get(f"/tickets/{tid}").json()["log_tail"]


def test_consolidate_can_reach_the_surveys(client, monkeypatch, tmp_path):
    """Found on run 3320 (2026-08-13): `consolidate` was launched with the surveys
    neither mounted nor named, so the only phase whose whole job is reading them
    couldn't. The scratch has no `.claude/`, so mounting it leaks no configuration."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 47)
    tid = client.post("/tickets", json={"ado_id": 47, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    cap = _spy_argv(monkeypatch)
    client.post(f"/tickets/{tid}/run", json={"phase": "consolidate"})
    argv = list(cap["argv"])
    mounted = [argv[i + 1] for i, a in enumerate(argv) if a == "--add-dir"]
    surveys = _phase(client, tid, "survey")["huella"]["ruta"]
    assert surveys in mounted                       # it can read them
    assert surveys in _prompt_from(cap)             # and it knows where they are
    assert "front, tenant" in _prompt_from(cap) or "front" in _prompt_from(cap)


def test_consolidate_without_surveys_does_not_start(client, monkeypatch, tmp_path):
    """Same rule the other phases already follow: it doesn't produce its own input."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 48, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "consolidate"})
    f = _phase(client, tid, "consolidate")
    assert f["estado"] == "error" and "survey" in f["motivo"]


def test_consolidate_is_told_which_repos_were_not_surveyed(client, monkeypatch, tmp_path):
    """The list of repos NOT surveyed is as much an input as the surveys: without it
    the consolidation can't write the line that stops the analysis from looking
    complete when it isn't — the most expensive failure in this system."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 49, routing="SONDEAR: backend")
    tid = client.post("/tickets", json={"ado_id": 49, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    cap = _spy_argv(monkeypatch)
    client.post(f"/tickets/{tid}/run", json={"phase": "consolidate"})
    assert "NOT surveyed: front" in _prompt_from(cap)


def test_a_fan_out_phase_cannot_be_continued(client, monkeypatch, tmp_path):
    """It drives several sessions and there's no single one to continue. Not recording
    any leaves `puede_continuar` false on its own, with no special case in the UI."""
    _use_fake_claude(monkeypatch, stamp="ok — survey.md")
    _write_brief(tmp_path, 46)
    tid = client.post("/tickets", json={"ado_id": 46, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "survey"})
    assert _phase(client, tid, "survey")["puede_continuar"] is False


def _run_twice(client, monkeypatch, ado_id, phase="analyze"):
    """First run leaves a session; the second one asks to continue it."""
    tid = client.post("/tickets", json={"ado_id": ado_id, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": phase})
    cap = _spy_argv(monkeypatch)
    client.post(f"/tickets/{tid}/run",
                json={"phase": phase, "instructions": "mira tambien el repo de auth",
                      "resume": True})
    return tid, cap


def test_resume_passes_the_session_and_forks_it(client, monkeypatch):
    """`--fork-session` isn't optional: without it the continuation reuses the id and
    the original run's transcript stops being reachable. With it, every row of `runs`
    keeps its own and the chain stays walkable."""
    from fake_claude import FAKE_SESSION
    _use_fake_claude(monkeypatch)
    tid, cap = _run_twice(client, monkeypatch, 20)
    argv = list(cap["argv"])
    assert argv[argv.index("--resume") + 1] == FAKE_SESSION
    assert "--fork-session" in argv
    assert client.get(f"/tickets/{tid}").json()["runs"][0]["resumed_from"] == FAKE_SESSION


def test_resume_does_not_resend_the_slash_command(client, monkeypatch):
    """The detail that would break the whole feature in silence. The session already
    ran the skill; resending the command restarts the procedure from step 1 — rereads
    the work item, reexplores, rewrites the deliverable — which is precisely what
    continuing was meant to avoid, and it can duplicate the output."""
    _use_fake_claude(monkeypatch)
    _, cap = _run_twice(client, monkeypatch, 21)
    prompt = _prompt_from(cap)
    assert "/ticket-agent:" not in prompt
    assert "mira tambien el repo de auth" in prompt
    # Already in its context; resending it just pays for the tokens again.
    assert "Extra repos mounted" not in prompt


def test_resume_still_demands_the_stamp(client, monkeypatch):
    """The runner requires the stamp on EVERY run. Without this reminder a good
    continuation closes with no stamp and gets marked as an error."""
    _use_fake_claude(monkeypatch)
    _, cap = _run_twice(client, monkeypatch, 22)
    assert "HUELLA" in _prompt_from(cap)


def test_resume_keeps_the_permission_flags(client, monkeypatch, tmp_path):
    """They're per-invocation permissions, not context. Dropping them on the
    continuation leaves the agent without write access to the extras and without its
    push guard, mid-conversation."""
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    _, cap = _run_twice(client, monkeypatch, 23, phase="implement")
    argv = list(cap["argv"])
    assert "--allowedTools" in argv and "Bash" in argv
    assert "--settings" in argv
    assert "--add-dir" in argv and any("backend-repo" in a for a in argv)


def test_resume_without_a_previous_session_runs_fresh(client, monkeypatch):
    """Never in silence: a continuation that quietly becomes a fresh run looks like
    the agent ignored the adjustment."""
    _use_fake_claude(monkeypatch, no_session=True)
    tid = client.post("/tickets", json={"ado_id": 24, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    cap = _spy_argv(monkeypatch)
    client.post(f"/tickets/{tid}/run", json={"instructions": "otra vuelta", "resume": True})
    argv = list(cap["argv"])
    assert "--resume" not in argv
    assert "/ticket-agent:analyze" in _prompt_from(cap)
    assert "sesión previa" in client.get(f"/tickets/{tid}").json()["log_tail"]


def test_a_phase_reports_whether_it_can_be_continued(client, monkeypatch):
    """What the UI disables the control with. Computed here, not in the client: it's
    the same condition that decides whether the resume applies or falls back to
    fresh, and two copies of it would drift."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 25, "project": "Demo"}).json()["id"]
    analyze = lambda: next(f for f in client.get(f"/tickets/{tid}").json()["fases"]
                           if f["fase"] == "analyze")
    assert analyze()["puede_continuar"] is False and analyze()["continuaciones"] == 0

    client.post(f"/tickets/{tid}/run", json={})
    assert analyze()["puede_continuar"] is True and analyze()["continuaciones"] == 0

    client.post(f"/tickets/{tid}/run", json={"instructions": "y esto", "resume": True})
    assert analyze()["continuaciones"] == 1
    client.post(f"/tickets/{tid}/run", json={"instructions": "y esto otro", "resume": True})
    assert analyze()["continuaciones"] == 2

    # A fresh run breaks the chain: the counter measures the CURRENT one, which is
    # what says how much context has piled up in the session now in play.
    client.post(f"/tickets/{tid}/run", json={})
    assert analyze()["continuaciones"] == 0


def test_implement_loads_the_rules_of_the_mounted_repos(client, monkeypatch, tmp_path):
    """`--add-dir` grants file access, not configuration discovery: it loads the added
    repo's skills and agents, but NOT its CLAUDE.md or `.claude/rules/`. Without this
    variable the agent writes the extra repo's code under the primary repo's
    conventions — confidently, and with nothing downstream to catch it.

    Only in `implement`, which is where obeying the other repo's rules while writing
    in it is what matters."""
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert "SAW-EXTRA-CLAUDE-MD" in client.get(f"/tickets/{tid}").json()["log_tail"]


def test_analyze_does_not_load_the_rules_of_the_mounted_repos(client, monkeypatch):
    """The other side of the branch, and it isn't symmetry for its own sake: in Phase 1
    the surveys put the other repos' rules into the analysis in writing. Loading them
    as configuration too would pay for the same thing twice, in every phase."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "SAW-EXTRA-CLAUDE-MD" not in client.get(f"/tickets/{tid}").json()["log_tail"]


def test_implement_without_extras_does_not_set_the_variable(client, monkeypatch, tmp_path):
    """A ticket with no mounted repos has nothing extra to load. Setting it anyway
    would work, but the log would stop explaining why the variable is there — and a
    variable nobody can justify is one nobody dares remove."""
    _use_fake_claude(monkeypatch)
    _git_init(tmp_path / "repo")
    client.post("/projects", json={
        "name": "Solo", "org": "DemoOrg", "project": "Demo",
        "repos": [{"path": (tmp_path / "repo").as_posix(), "label": "front", "primary": True}],
    })
    tid = client.post("/tickets", json={"ado_id": 3321, "project": "Solo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert "SAW-EXTRA-CLAUDE-MD" not in client.get(f"/tickets/{tid}").json()["log_tail"]


def test_adjustment_in_implement_does_not_ask_to_regenerate_the_file(client, monkeypatch, tmp_path):
    """In `implement` there's no "the file" to regenerate: the deliverable is the
    code, and the only file the phase rewrites is `tasks.md`, the progress log.
    Telling it to regenerate that is telling it to erase what lets the run be
    resumed."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run",
                json={"phase": "implement", "instructions": "usa el patrón del handler"})
    prompt = _prompt_from(cap)
    assert "usa el patrón del handler" in prompt
    assert "regenerate the file" not in prompt
    assert "tasks.md" in prompt


def test_adjustment_in_design_still_asks_to_regenerate_the_file(client, monkeypatch):
    """The other side: where the deliverable IS a file, re-running means regenerating
    it."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run",
                json={"phase": "design", "instructions": "acota el alcance"})
    prompt = _prompt_from(cap)
    assert "acota el alcance" in prompt
    assert "regenerate the file" in prompt


def test_the_four_tables_include_implement():
    import app
    for table in (app.PHASE_COMMANDS, app.PHASE_DONE,
                  app.PHASE_ALLOWED_TOOLS, app.PHASE_NOUN):
        assert "implement" in table
    assert app.PHASE_DONE["implement"] == "implemented"


def test_bash_does_not_appear_in_analyze_phase(client, monkeypatch):
    """C1: Phase 1 is read-only. Before the fix, Bash traveled in ALL runs because
    --allowedTools didn't look at the phase; a real analyze run went as far as
    running `ls`, `find` and `git remote -v` in a client's repo."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash" not in log


def test_run_survives_a_giant_line(client, monkeypatch):
    """The stream-json goes past 64 KiB in a single line when the agent writes a
    large file. Reading line by line used to blow up there and marked a good run as
    `error`."""
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3322-analysis.md")
    monkeypatch.setenv("FAKE_BIG", "1")
    tid = client.post("/tickets", json={"ado_id": 3322, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "success"
    whole = Path(detail["runs"][0]["log_path"]).read_text(encoding="utf-8")
    assert "ácido" * 20000 in whole          # arrived whole, no character split
    assert "�" not in whole              # no broken character between chunks


def test_run_error_state(client, monkeypatch):
    _use_fake_claude(monkeypatch, fail=True)
    tid = client.post("/tickets", json={"ado_id": 8, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["status"] == "error"


def test_design_prompt_does_not_mention_analysis(client, monkeypatch):
    """I6: the deliverable of a design run is the plan, not the analysis — telling
    the agent "the analysis" there sends it to rework the wrong file."""
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design", "instructions": "ajusta el alcance"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "the analysis" not in log
    assert "the plan" in log


def test_rework_passes_instructions(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 9, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"instructions": "no consideraste el parent"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "no consideraste el parent" in detail["log_tail"]
    assert detail["runs"][0]["instructions"] == "no consideraste el parent"


def test_run_strips_api_key_so_subscription_is_used(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/11-analysis.md")
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
    # The run is inserted by hand: with TestClient the background task finishes before
    # the response comes back, so there's no way to observe a run "in flight".
    conn = sq.connect(os.environ["ORCH_DB"])
    conn.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'analyze','running')", (tid,))
    conn.commit()
    conn.close()

    a = client.get("/runs/active").json()
    assert a["ado_id"] == 3322 and a["project"] == "Demo" and a["ticket_id"] == tid


def test_run_passes_allowed_tools_and_add_dir(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    # Without --allowedTools, in headless mode the MCP tools auto-deny and the agent
    # is left unable to read the work item.
    assert "--allowedTools mcp__azure-devops" in log
    # The project's sibling repos travel as --add-dir...
    assert "--add-dir" in log and "backend-repo" in log
    # ...and are also named in the prompt with their label: mounting them isn't
    # enough for the agent to look at them (verified with Tenant in the 3322 run).
    assert "Extra repos mounted" in log and "— backend" in log


def test_run_conflict_when_active(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 10, "project": "Demo"}).json()["id"]
    import app

    with app.db() as c:
        c.execute(
            "INSERT INTO runs(ticket_id, phase, status) VALUES(?, 'analyze', 'running')", (tid,)
        )
    assert client.post(f"/tickets/{tid}/run", json={}).status_code == 409


def test_phases_without_runs(client):
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    phases = client.get(f"/tickets/{tid}").json()["fases"]
    # `test` isn't there: tests are written inside `implement`, not in a phase of their own.
    # `Demo` mounts an extra repo, so it walks the fan-out route AND keeps `analyze`.
    assert [f["fase"] for f in phases] == [
        "analyze", "brief", "survey", "consolidate", "design", "implement"]
    # Exact shape, not a subset: the UI reads these keys and a phase that silently
    # grows one is a phase the client renders half-blind.
    for name in ("analyze", "implement"):
        assert _phase(client, tid, name) == {
            "fase": name, "disponible": True, "estado": "pendiente",
            "corridas": 0, "fallidas": 0,
            "puede_continuar": False, "continuaciones": 0}
    assert client.get("/tickets").json()[0]["status"] == "queued"


def test_the_ticket_list_carries_the_phases(client):
    """The three-dot stepper needs per-phase state, not just the folded status: `error`
    alone doesn't say which phase failed.

    Asserted against the detail view rather than against a literal list of phase names,
    so this test doesn't have to be rewritten every time `PHASES` changes — which it
    does in Task 9, two tasks from here. The footprint (the disk-reading part) stays
    off, which is what made the list cheap in the first place."""
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    expected = [f["fase"] for f in client.get(f"/tickets/{tid}").json()["fases"]]
    assert [f["fase"] for f in t["fases"]] == expected
    assert all("huella" not in f for f in t["fases"])


def test_fases_travels_on_all_three_ticket_producers(client):
    """`api.ts` declares `fases` required on `Ticket`, but `json<T>()` is an unchecked
    cast — the hand-written types are the frontend's only safety net, and only
    `GET /tickets` used to actually carry the field. `POST /tickets` and the `.ticket`
    object inside `GET /tickets/{tid}` have to agree, or the type is a lie told exactly
    at that boundary."""
    created = client.post("/tickets", json={"ado_id": 42, "project": "Demo"}).json()
    assert created["fases"] and created["fases"][0]["fase"] == "analyze"
    tid = created["id"]
    listed = next(t for t in client.get("/tickets").json() if t["id"] == tid)
    assert listed["fases"] == created["fases"]
    detail_ticket = client.get(f"/tickets/{tid}").json()["ticket"]
    assert detail_ticket["fases"] == created["fases"]
    # the detail view's OWN sibling `fases` key (read by `TicketDetail`, not by the
    # ticket stepper) stays exactly as it was — this is additive, not a move.
    assert client.get(f"/tickets/{tid}").json()["fases"] == created["fases"]


def test_phases_with_one_run_each(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "3323-analysis.md").write_text("x" * 500)
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3323-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok" and f["corridas"] == 1 and f["fallidas"] == 0
    assert f["huella"] == {"ruta": "docs/tickets/3323-analysis.md", "existe": True,
                           "archivos": 1, "bytes": 500,
                           "nombres": ["3323-analysis.md"]}
    assert isinstance(f["duracion_s"], int)
    # and the ticket's status folds from that, without reading any column
    assert client.get("/tickets").json()[0]["status"] == "analyzed"


def test_phase_takes_the_state_of_its_most_recent_run(client, monkeypatch, tmp_path):
    (tmp_path / "repo" / "a.md").write_text("uno")
    _use_fake_claude(monkeypatch, stamp="nada — se cayó")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok" and f["corridas"] == 2 and f["fallidas"] == 1


def test_a_rerun_of_analysis_does_not_erase_that_a_plan_exists(client, monkeypatch, tmp_path):
    """The defect that kills this design: `tickets.status` used to get overwritten
    and the plan vanished from the world when Phase 1 was re-run."""
    (tmp_path / "repo" / "a.md").write_text("uno")
    _use_fake_claude(monkeypatch, stamp="ok — a.md")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    client.post(f"/tickets/{tid}/run", json={})          # re-runs the analysis
    d = client.get(f"/tickets/{tid}").json()
    assert [_phase(client, tid, n)["estado"] for n in ("analyze", "design")] == ["ok", "ok"]
    assert d["ticket"]["status"] == "planned"
    assert client.get("/tickets").json()[0]["status"] == "planned"


def test_stamp_of_a_directory_counts_and_lists_its_files(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    for n in ("proposal.md", "tasks.md", "design.md"):
        (d / n).write_text("abc")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    h = _phase(client, tid, "design")["huella"]
    assert h["existe"] and h["archivos"] == 3 and h["bytes"] == 9
    assert sorted(h["nombres"]) == ["design.md", "proposal.md", "tasks.md"]


def test_stamp_of_a_directory_descends_into_subdirectories(client, monkeypatch, tmp_path):
    """An OpenSpec change nests `specs/<capability>/spec.md`. Looking only at direct
    children leaves that file out of the count, the bytes and `nombres` — exactly the
    most common shape of `design`'s deliverable."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    (d / "specs" / "pagos").mkdir(parents=True)
    (d / "proposal.md").write_text("ab")
    (d / "tasks.md").write_text("cde")
    (d / "specs" / "pagos" / "spec.md").write_text("fghij")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    h = _phase(client, tid, "design")["huella"]
    assert h["archivos"] == 3
    assert h["bytes"] == 2 + 3 + 5
    assert "specs/pagos/spec.md" in h["nombres"]


def test_declared_path_that_does_not_exist_on_disk_is_not_hidden(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/fantasma.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    f = client.get(f"/tickets/{tid}").json()["fases"][0]
    assert f["estado"] == "ok"                      # the phase keeps its state
    assert f["huella"]["existe"] is False           # and the stamp gives itself away
    assert f["huella"]["archivos"] == 0


def test_phase_in_error_carries_the_stamp_reason(client, monkeypatch):
    _use_fake_claude(monkeypatch, stamp="nada — falta el análisis de la Fase 1")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    f = _phase(client, tid, "design")
    assert f["estado"] == "error" and "falta el análisis" in f["motivo"]
    assert "huella" not in f


def test_historical_success_run_without_stamp_does_not_say_it_failed(client, monkeypatch):
    """The 5 historical runs from before this contract came out with status=success
    (the CLI exited 0) and no stamp — they didn't fail. `phases_for` paints them as
    `error` because it can't trust an undeclared artifact, but the reason can't say
    "falló" there: that would be lying about what really happened."""
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


CAP = 512 * 1024


def _with_artifact(client, monkeypatch, tmp_path, rel, content="hola"):
    destination = tmp_path / "repo" / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp=f"ok — {rel}")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    return tid


def test_artifact_serves_the_declared_path(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/3323-analysis.md", "# Análisis")
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "docs/tickets/3323-analysis.md"})
    assert r.status_code == 200
    assert r.json()["texto"] == "# Análisis" and r.json()["truncado"] is False


def test_artifact_serves_the_declared_path_from_a_partial_run_with_reserve(
    client, monkeypatch, tmp_path
):
    """Regression of finding A: splitting the reserve from the path in `artifact_path`
    must not dirty the viewer's whitelist — a `parcial` with a reserve keeps being
    served exactly like one without it."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "proposal.md").write_text("propuesta", encoding="utf-8")
    _use_fake_claude(
        monkeypatch,
        stamp="parcial — openspec/changes/3323-xpo · openspec validate no pasó",
    )
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    r = client.get(f"/tickets/{tid}/artefacto",
                   params={"ruta": "openspec/changes/3323-xpo/proposal.md"})
    assert r.status_code == 200 and r.json()["texto"] == "propuesta"


def test_artifact_serves_a_direct_child_of_a_declared_directory(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] uno", encoding="utf-8")
    (d / "specs" / "pagos").mkdir(parents=True)
    (d / "specs" / "pagos" / "spec.md").write_text("# spec de pagos", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    r = client.get(f"/tickets/{tid}/artefacto",
                   params={"ruta": "openspec/changes/3323-xpo/tasks.md"})
    assert r.status_code == 200 and r.json()["texto"] == "- [ ] uno"
    # and a grandchild: `stamp_stat` counts recursively, so the viewer has to allow it.
    r2 = client.get(f"/tickets/{tid}/artefacto",
                    params={"ruta": "openspec/changes/3323-xpo/specs/pagos/spec.md"})
    assert r2.status_code == 200 and r2.json()["texto"] == "# spec de pagos"


def test_artifact_rejects_undeclared_path(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    (tmp_path / "repo" / "secreto.env").write_text("TOKEN=xxx", encoding="utf-8")
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "secreto.env"})
    assert r.status_code == 400


def test_artifact_rejects_traversal(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    for path_ in ("../../etc/passwd", "docs/../../fuera.md", "docs/tickets/../../../x"):
        assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": path_}).status_code == 400


def test_artifact_path_with_null_byte_gives_400_not_500(client, monkeypatch, tmp_path):
    """`ruta` arrives as-is from the query string. A null byte makes
    `Path(...).resolve()` blow up with an uncaught `ValueError` — that was a 500
    instead of the 400 that an invalid client input deserves."""
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    import app

    try:
        app.artifact(tid, "docs\x00tickets/a.md")
        assert False, "should have raised HTTPException"
    except app.HTTPException as exc:
        assert exc.status_code == 400


def test_artifact_rejects_absolute_path_outside_repo(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    outside = tmp_path / "fuera.md"
    outside.write_text("no", encoding="utf-8")
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": str(outside)}).status_code == 400


def test_artifact_rejects_a_directory(client, monkeypatch, tmp_path):
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("x", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": "openspec/changes/3323-xpo"}).status_code == 400


def test_artifact_declared_by_another_ticket_is_invalid(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/tickets/a.md")
    other = client.post("/tickets", json={"ado_id": 9999, "project": "Demo"}).json()["id"]
    assert client.get(f"/tickets/{other}/artefacto",
                      params={"ruta": "docs/tickets/a.md"}).status_code == 400


def test_artifact_truncates_at_512kb(client, monkeypatch, tmp_path):
    tid = _with_artifact(client, monkeypatch, tmp_path, "grande.md", "á" * CAP)
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "grande.md"}).json()
    assert r["truncado"] is True and len(r["texto"]) <= CAP
    assert "�" not in r["texto"]      # no multibyte character split at the cut


def test_artifact_serves_exactly_512kb_without_truncating(client, monkeypatch, tmp_path):
    """Boundary of the cap: not one byte extra enters the cut, so a file of exactly
    CAP bytes is served whole."""
    tid = _with_artifact(client, monkeypatch, tmp_path, "justo.md", "x" * CAP)
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "justo.md"}).json()
    assert r["truncado"] is False and r["bytes"] == CAP and len(r["texto"]) == CAP


def test_artifact_rejects_traversal_from_declared_directory(client, monkeypatch, tmp_path):
    """CRITICAL from round 1: against a declared directory (not a file), an
    unnormalized `..` let it escape to any file in the repo — verified by reading
    `secreto.env` outside the declared change. Rule 1 has to resolve the path
    BEFORE deciding whether it falls under the declared path, just like rule 2
    already did."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("x", encoding="utf-8")
    (tmp_path / "repo" / "secreto.env").write_text("DB_PASSWORD=superclave", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    posix = "openspec/changes/3323-xpo/../../../secreto.env"
    windows = "openspec\\changes\\3323-xpo\\..\\..\\..\\secreto.env"
    assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": posix}).status_code == 400
    assert client.get(f"/tickets/{tid}/artefacto", params={"ruta": windows}).status_code == 400


def test_artifact_empty_artifact_path_is_not_a_wildcard(client, monkeypatch, tmp_path):
    """IMPORTANT from round 1: a degenerate stamp can save `artifact_path=''`.
    `PurePosixPath('')` equals `.`, which "belongs" to the `.parents` of any relative
    path — without the `!= ''` filter that turns the whitelist into a wildcard."""
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


def test_artifact_declared_dot_is_not_a_wildcard(client, monkeypatch, tmp_path):
    """ROUND 2: once rule 1 moves to resolved paths, `artifact_path='.'` resolves to
    the repo's own root, which is still a wildcard even though it's no longer `''`.
    The correct property is "strictly INSIDE a root", not "different from ''"."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, stamp="ok — .")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artifact_declared_dotdot_is_not_a_wildcard_and_reaches_extra_dirs(
    client, monkeypatch, tmp_path
):
    """ROUND 2, the CRITICAL vector verified by the reviewer: `artifact_path='..'`
    resolves above the repo, and from there `..` in rule 2 goes back into both the
    primary repo and the `extra_dirs` — any file in either one was servable.
    `HUELLA: ok — ..` is genuinely reachable from a degenerate skill's closing
    stamp."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    (tmp_path / "backend-repo" / "secreto-hermano.env").write_text("OTRO=1", encoding="utf-8")
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, stamp="ok — ..")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": "../backend-repo/secreto-hermano.env"}).status_code == 400


def test_artifact_declared_dir_dotdot_is_not_a_wildcard(client, monkeypatch, tmp_path):
    """ROUND 2: `docs/..` resolves to the repo root just like `.` — another spelling
    of the same wildcard, and the reason the fix has to go by property, not by a list
    of forbidden spellings."""
    (tmp_path / "repo" / ".env").write_text("SECRETO=1", encoding="utf-8")
    tid = _with_artifact(client, monkeypatch, tmp_path, "docs/a.md")
    _use_fake_claude(monkeypatch, stamp="ok — docs/..")
    client.post(f"/tickets/{tid}/run", json={})
    assert client.get(f"/tickets/{tid}/artefacto",
                      params={"ruta": ".env"}).status_code == 400


def test_artifact_declared_whitespace_only_is_not_a_wildcard(client, monkeypatch, tmp_path):
    """ROUND 2: `read_stamp` does `.strip()` on the stamp, so a whitespace-only
    `artifact_path` can't arrive through the normal run path — simulated by
    inserting the row directly, just like the `''` case from round 1."""
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


def test_artifact_top_level_directory_still_serves(client, monkeypatch, tmp_path):
    """The property filter from round 2 can't sweep away the normal case: a
    legitimate declared path that is a top-level directory of the repo (here `docs`)
    still ends up strictly INSIDE the root, so its children keep being served."""
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "a.md").write_text("hola", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "docs/tickets/a.md"})
    assert r.status_code == 200 and r.json()["texto"] == "hola"


def test_artifact_traversal_that_reenters_declared_path_serves(client, monkeypatch, tmp_path):
    """A path with `..` isn't suspicious for having `..`: what matters is where it
    resolves. If it re-enters the same declared directory, it has to be served just
    like the direct form — rule 1 compares against `real`, already resolved."""
    d = tmp_path / "repo" / "openspec" / "changes" / "3323-xpo"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] uno", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3323-xpo")
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    path_ = "openspec/changes/3323-xpo/../3323-xpo/tasks.md"
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": path_})
    assert r.status_code == 200 and r.json()["texto"] == "- [ ] uno"


def test_artifact_declared_inside_an_extra_dir_serves_its_child(client, monkeypatch, tmp_path):
    """A legitimate case with no coverage of its own: a declared path can navigate
    outside the `repo_path` into an `extra_dir` (both are valid roots of the
    ticket), and its child keeps being served."""
    (tmp_path / "backend-repo" / "report.md").write_text("informe", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — ../backend-repo/report.md")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    r = client.get(f"/tickets/{tid}/artefacto", params={"ruta": "../backend-repo/report.md"})
    assert r.status_code == 200 and r.json()["texto"] == "informe"


def test_artifact_extra_dir_ancestor_of_primary_does_not_reactivate_wildcard(
    client, monkeypatch, tmp_path
):
    """ROUND 3: `any(rd != r and r in rd.parents for r in raices)` (round 2) fuses
    two questions — it's enough for the declared path to fall inside SOME root, even
    if it IS another root. In a monorepo where the `extra_dir` is an ANCESTOR of the
    `repo_path` (primary `Tenant/Web`, extra `Tenant`; `check_dirs` accepts it
    because it only looks at `is_dir`), `.` resolves to the primary repo, which is
    strictly INSIDE the extra — and it slipped back in as a stamp, reactivating the
    original vulnerability through configuration with the same reachable trigger
    (`HUELLA: ok — .`)."""
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
    for stamp in (".", "docs/..", ".."):
        _use_fake_claude(monkeypatch, stamp=f"ok — {stamp}")
        client.post(f"/tickets/{tid}/run", json={})
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": ".env"}).status_code == 400
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": "../Api/appsettings.json"}).status_code == 400


def test_artifact_extra_dir_descendant_of_primary_still_rejects_wildcard(
    client, monkeypatch, tmp_path
):
    """Opposite direction of the nested case: the `extra_dir` is a DESCENDANT of the
    `repo_path` (e.g. a `vendor/` mounted as a separate repo inside the primary one).
    `.` and `sub/..` still resolve to the primary repo's root, which is still a root
    — discarded just like in the flat case."""
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
    for stamp in (".", "vendor/.."):
        _use_fake_claude(monkeypatch, stamp=f"ok — {stamp}")
        client.post(f"/tickets/{tid}/run", json={})
        assert client.get(f"/tickets/{tid}/artefacto",
                          params={"ruta": ".env"}).status_code == 400


import subprocess

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _app(monkeypatch, tmp_path):
    """`app` is imported INSIDE each test because conftest pulls it out of
    `sys.modules` so it rereads `ORCH_DB`. These tests don't use the `client`
    fixture, so they replicate its isolation by hand (see
    `test_current_phase_no_longer_exists`, line ~312): without fixing
    `ORCH_DB`/`ORCH_LOGS` and without pulling `app` out of `sys.modules`, a first
    real import fires `init_db()` against the backend's real DB and logs — and what
    ends up on disk depends on which test ran first."""
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "orch_test.db"))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    sys.path.insert(0, str(BACKEND_DIR))
    if "app" in sys.modules:
        del sys.modules["app"]
    import app
    return app


def _git_init(path):
    """A repo with one commit: `git switch -c` needs something to hang off of."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "seed.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)


def test_guard_blocks_a_modified_tracked_file(tmp_path, monkeypatch):
    """Without this, `git switch -c` drags your uncommitted work onto the agent's
    branch and the agent commits it as its own.

    The repo lives in a SUBdirectory of `tmp_path`, never in `tmp_path` itself: `_app`
    points `ORCH_DB`/`ORCH_LOGS` at `tmp_path`, and if the repo were `tmp_path` that DB
    would end up *inside* the tree under test — a parasitic `?? orch_test.db` that
    `git status --porcelain` would always see, regardless of the logic the test claims
    to exercise."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "seed.txt").write_text("v2\n", encoding="utf-8")
    assert app.is_dirty(str(repo)) is True


def test_guard_tolerates_untracked_files(tmp_path, monkeypatch):
    """The case that makes the phase launchable: the primary repo ALWAYS has
    untracked `openspec/` and `docs/tickets/`, which are the agent's artifacts.
    If this test fails, the implement phase is unlaunchable forever."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "openspec").mkdir()
    (repo / "openspec" / "changes.md").write_text("x", encoding="utf-8")
    assert app.is_dirty(str(repo)) is False


def test_guard_sees_what_is_staged(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    (repo / "nuevo.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "nuevo.txt"], cwd=repo, check=True)
    assert app.is_dirty(str(repo)) is True


def test_check_clean_names_the_dirty_repos(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    clean, dirty_ = tmp_path / "a", tmp_path / "b"
    clean.mkdir(); dirty_.mkdir()
    _git_init(clean); _git_init(dirty_)
    (dirty_ / "seed.txt").write_text("v2\n", encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        app.check_clean([str(clean), str(dirty_)])
    assert e.value.status_code == 409
    assert str(dirty_) in e.value.detail
    assert str(clean) not in e.value.detail


def test_a_directory_that_is_not_git_gives_409(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    (tmp_path / "pelado").mkdir()
    with pytest.raises(HTTPException) as e:
        app.check_clean([str(tmp_path / "pelado")])
    assert e.value.status_code == 409


def test_prepare_branch_creates_it_and_switches_to_it(tmp_path, monkeypatch):
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    name = app.prepare_branch(str(repo), 3320)
    assert name == "ticket-agent/3320"
    current = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert current == "ticket-agent/3320"


def test_prepare_branch_twice_does_not_fail(tmp_path, monkeypatch):
    """Resuming a partial run has to land on the SAME branch. With a bare
    `switch -c`, the second call blows up with 'already exists'."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    app.prepare_branch(str(repo), 3320)
    subprocess.run(["git", "switch", "-q", "-"], cwd=repo, check=True)
    assert app.prepare_branch(str(repo), 3320) == "ticket-agent/3320"
    current = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert current == "ticket-agent/3320"
    branches = subprocess.run(["git", "branch", "--list"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert branches.count("ticket-agent/3320") == 1


def test_prepare_branch_does_not_confuse_a_tag_with_the_branch(tmp_path, monkeypatch):
    """The `rev-parse` carries `refs/heads/` on purpose. Without that prefix —
    `rev-parse --verify -q ticket-agent/3320`— a same-named TAG resolves just as
    well as a branch, the runner thinks the branch already exists and does
    `git switch <tag>`, which git rejects ("a branch is expected"): the phase
    becomes unlaunchable with a 409.

    A same-named branch and tag are the only thing that tells the two cases apart;
    with only branches around, removing `refs/heads/` leaves the whole suite green."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    subprocess.run(["git", "tag", "ticket-agent/3320"], cwd=repo, check=True)
    assert app.prepare_branch(str(repo), 3320) == "ticket-agent/3320"
    current = subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert current == "ticket-agent/3320"


def test_runs_has_branch_column(client):
    import app
    with app.db() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(runs)")]
    assert "branch" in cols


def _fake_analyze(client, monkeypatch, tmp_path, contenido: str):
    """Runs a fake `analyze` that writes `contenido` at docs/tickets/1-analysis.md and
    closes with the stamp pointing at it. Returns the ticket id."""
    import app as app_module

    dest = tmp_path / "repo" / "docs" / "tickets"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "1-analysis.md").write_text(contenido, encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','docs/tickets/1-analysis.md')", (tid,))
    t = app_module.ticket_row(tid)
    titulo = app_module.read_title(t, "docs/tickets/1-analysis.md")
    if titulo:
        app_module.set_ticket(tid, title=titulo)
    return tid


def test_title_comes_from_the_first_heading(client, monkeypatch, tmp_path):
    tid = _fake_analyze(client, monkeypatch, tmp_path,
                        "por ticket-agent v0.7.1\n\n# Carrier API V2 Migration - Dayton\n\ntexto\n")
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] == "Carrier API V2 Migration - Dayton"


def test_analysis_without_heading_leaves_title_empty(client, monkeypatch, tmp_path):
    """Soft contract: the skill's template writes the `# `, but no plugin test protects
    it. Without a heading the list falls back to `#<ado_id>` — it must never blow up."""
    tid = _fake_analyze(client, monkeypatch, tmp_path, "sin encabezado ninguno\n")
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] is None


def test_the_runner_stores_the_title_after_a_real_analyze_run(client, monkeypatch, tmp_path):
    """Drives the WIRING, not the gate.

    The three tests above call `read_title` directly, which proves the function works and
    not that `execute_run` ever calls it. A test that reimplements the runner's logic in
    order to check the runner is the exact shape of placebo this project has already
    found five times — it passes because of its own setup. This one goes through
    `POST /tickets/{tid}/run` with the fake CLI and reads the result off `GET /tickets`.
    """
    dest = tmp_path / "repo" / "docs" / "tickets"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "40-analysis.md").write_text(
        "por ticket-agent v0.7.1\n\n# Carrier API V2 Migration - Dayton\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/40-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 40, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] == "Carrier API V2 Migration - Dayton"


def test_only_analyze_stores_a_title(client, monkeypatch, tmp_path):
    """The hook is gated on the phase. A `design` run that declares a markdown file with
    a heading must not stamp the plan's title onto the ticket."""
    dest = tmp_path / "repo" / "docs"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "plan.md").write_text("# El plan, no el ticket\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/plan.md")
    tid = client.post("/tickets", json={"ado_id": 41, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] is None


def test_title_is_not_a_second_door_to_disk(client, tmp_path):
    """A stamp declaring a traversal must not let `read_title` read outside the repo."""
    import app as app_module

    (tmp_path / "secreto.md").write_text("# secreto\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 2, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','../secreto.md')", (tid,))
    t = app_module.ticket_row(tid)
    assert app_module.read_title(t, "../secreto.md") is None


def test_a_directory_that_does_not_exist_gives_409(tmp_path, monkeypatch):
    """Not "not a git repo" anymore: a path that isn't even on disk. `is_dirty`
    checks `Path.is_dir()` before invoking `git`, so this gives the same clean 409
    without needing to let `subprocess.run` blow up with a nonexistent `cwd`."""
    app = _app(monkeypatch, tmp_path)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        app.is_dirty(str(tmp_path / "no_existe"))
    assert e.value.status_code == 409


def test_missing_git_is_not_disguised_as_409(tmp_path, monkeypatch):
    """A `git` missing from PATH is a misconfigured environment, not "not a git
    repository": it has to propagate, not turn into a 409 that lies about the
    cause. The absence is simulated by patching `subprocess.run` (scoped by
    `monkeypatch`, reverted only when the test ends) instead of touching the
    session's real PATH."""
    app = _app(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    def _no_git(*args, **kwargs):
        raise FileNotFoundError("git no encontrado")

    monkeypatch.setattr(app.subprocess, "run", _no_git)
    with pytest.raises(FileNotFoundError):
        app.is_dirty(str(repo))


def test_implement_with_dirty_repo_gives_409_and_does_not_queue(client, monkeypatch, tmp_path):
    """The 409 arrives BEFORE spending an 8-minute subprocess."""
    import app
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    (tmp_path / "repo" / "seed.txt").write_text("v2\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 409
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_implement_saves_the_branch_on_the_run(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3320-x/tasks.md")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"


def test_analyze_does_not_require_clean_repo(client, monkeypatch):
    """The guard belongs to `implement`. If it applied to all phases, Phase 1 would
    no longer be able to run over a repo with half-finished work, which is normal."""
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3311-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202


def test_implement_partial_stamp_keeps_the_reserve(client, monkeypatch, tmp_path):
    """The stamp contract already existed, but nobody had exercised it with the new
    phase or with a reserve of this shape. Fails if the parsing is tied to
    `docs/tickets/` paths or if the reserve leaks into `artifact_path`."""
    _use_fake_claude(
        monkeypatch,
        stamp="parcial — openspec/changes/3320-x/tasks.md · 3/5 tareas, build en rojo")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["artifact_state"] == "parcial"
    assert run["artifact_path"] == "openspec/changes/3320-x/tasks.md"
    assert run["artifact_note"] == "3/5 tareas, build en rojo"


def test_implement_with_second_repo_dirty_does_not_leave_the_first_on_another_branch(
    client, monkeypatch, tmp_path
):
    """The dirty repo is the SECOND one (`backend-repo`), with the primary clean. If
    the guard got entangled with branching repo by repo (check and branch one, then
    the next), the primary would already have moved to `ticket-agent/<id>` before the
    second repo's check failed.
    `test_implement_with_dirty_repo_gives_409_and_does_not_queue` doesn't catch this
    because it dirties the primary repo — the first one in the list — so an
    interleaved implementation fails on that very first iteration and that test
    doesn't expose it."""
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
    current = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path / "repo",
        capture_output=True, text=True,
    ).stdout.strip()
    assert current == original


def test_implement_with_a_single_repo_prepares_the_branch(client, monkeypatch, tmp_path):
    """The path with no extra repos (empty `extra_dirs`) was never exercised from the
    endpoint: every earlier `implement` test uses the `Demo` project, which always
    brings an extra repo."""
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3320-x/tasks.md")
    single_repo = tmp_path / "solo-repo"
    single_repo.mkdir()
    _git_init(single_repo)
    client.post("/projects", json={
        "name": "Solo", "org": "O", "project": "P",
        "repos": [{"path": single_repo.as_posix(), "primary": True}],
    })
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Solo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 202
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"


def _queue_without_running(monkeypatch):
    """Leaves the run queued without executing it and returns a `run_now()` that
    executes it for real, whenever the test wants.

    `TestClient` runs background tasks INSIDE `client.post(...)`, so without this
    there's no gap to slip into between "the POST passed the guard" and "the run
    starts" — which is exactly the gap these two tests exercise. `run_ticket`
    resolves `execute_run` as a module global at call time, so substituting it
    works."""
    import app
    import asyncio
    pending = []
    real = app.execute_run
    monkeypatch.setattr(app, "execute_run", lambda *a: pending.append(a))
    return lambda: asyncio.run(real(*pending[0]))


def test_a_tree_that_gets_dirty_after_the_post_never_launches_the_subprocess(
    client, monkeypatch, tmp_path
):
    """The POST's guard is evaluated when queuing, but the run can start much later,
    waiting for the lock. If the user edits files in that gap — or if another ticket
    over the SAME physical repo slipped past the guard, which filters by `ticket_id`—
    the agent would start over a tree that's no longer the validated one and commit
    someone else's work as its own. Fails if the late check disappears from
    `execute_run`: the subprocess would launch anyway."""
    _use_fake_claude(monkeypatch)
    cap = _spy_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    run_now = _queue_without_running(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 202          # with a clean tree, the POST queues

    # The user edits while the run waits for the lock.
    (tmp_path / "repo" / "seed.txt").write_text("v2\n", encoding="utf-8")
    run_now()

    assert "argv" not in cap             # the CLI was never launched
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["status"] == "error"
    assert run["branch"] is None         # branch wasn't changed either
    assert (tmp_path / "repo").as_posix() in run["artifact_path"]
    # and the phase reports it with a readable reason, not "no declaró huella"
    phase = [f for f in client.get(f"/tickets/{tid}").json()["fases"]
            if f["fase"] == "implement"][0]
    assert phase["estado"] == "error" and "sin commitear" in phase["motivo"]
    # the repo stays where it was: the run didn't move it before giving up
    current = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path / "repo",
                            capture_output=True, text=True).stdout.strip()
    assert current != "ticket-agent/3320"


def test_the_run_branch_is_the_one_prepared_under_the_lock(
    client, monkeypatch, tmp_path
):
    """The same late path, but succeeding. The row ends up with the correct branch
    and state even though the POST didn't prepare anything: fails if `execute_run`
    stops branching or stops writing `branch`, and also if the branch went back to
    coming out of the POST (here the run is queued and the POST already returned
    `branch=None`)."""
    _use_fake_claude(monkeypatch, stamp="ok — openspec/changes/3320-x/tasks.md")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    run_now = _queue_without_running(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    queued = client.post(f"/tickets/{tid}/run", json={"phase": "implement"}).json()
    assert queued["branch"] is None      # the POST no longer branches

    run_now()

    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"
    assert run["status"] == "success"
    for d in ("repo", "backend-repo"):   # BOTH repos, not just the primary
        current = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path / d,
                                capture_output=True, text=True).stdout.strip()
        assert current == "ticket-agent/3320"


def test_delete_mid_run_does_not_crash_the_title_hook(client, monkeypatch, tmp_path):
    """`DELETE /tickets/{tid}` has no guard against an in-flight run. A ticket deleted
    while `analyze` is still running must not crash the background task's title hook:
    `declared_file` does `t["id"]` unconditionally, and a `None` row from a ticket
    deleted mid-run used to reach it uncaught, inside a background task nobody is
    watching."""
    (tmp_path / "repo" / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "repo" / "docs" / "tickets" / "3311-analysis.md").write_text(
        "# Titulo\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/3311-analysis.md")
    run_now = _queue_without_running(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})

    # The ticket (and, via the FK cascade, its queued run) disappears before the run
    # actually executes — exactly the gap `execute_run` waits in for the lock.
    assert client.delete(f"/tickets/{tid}").status_code == 204

    run_now()  # must not raise


def test_existing_path_is_valid(client, tmp_path):
    r = client.post("/rutas/validar", json={"ruta": (tmp_path / "repo").as_posix()})
    assert r.status_code == 200
    assert r.json() == {"existe": True}


def test_nonexistent_path_is_invalid(client, tmp_path):
    r = client.post("/rutas/validar", json={"ruta": (tmp_path / "no-existe").as_posix()})
    assert r.json() == {"existe": False}


def test_a_file_is_not_a_repo(client, tmp_path):
    f = tmp_path / "archivo.txt"
    f.write_text("x", encoding="utf-8")
    r = client.post("/rutas/validar", json={"ruta": f.as_posix()})
    assert r.json() == {"existe": False}


def test_absurd_path_does_not_blow_up(client):
    """A null byte makes `Path.is_dir()` raise instead of returning False. The form
    sends whatever the user pasted, so this reaches the endpoint for real."""
    r = client.post("/rutas/validar", json={"ruta": "x\x00y"})
    assert r.status_code == 200
    assert r.json() == {"existe": False}


def test_declared_file_or_none_rejects_what_the_endpoint_rejects(client, tmp_path, monkeypatch):
    """The internal consumers (`read_title`, `task_progress`) must not get a second,
    laxer door to disk. Same ticket, same declared path, same verdict — the only
    difference is `None` instead of a 400."""
    import app as app_module

    (tmp_path / "repo" / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / "docs" / "a.md").write_text("# hola", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")

    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','docs')", (tid,))
    t = app_module.ticket_row(tid)

    # declared and inside: resolves
    assert app_module.declared_file_or_none(t, "docs/a.md") is not None
    # traversal out of the repo: None, not an exception and not a Path
    assert app_module.declared_file_or_none(t, "docs/../../secreto.txt") is None
    # not declared by any run of this ticket
    assert app_module.declared_file_or_none(t, "otro.md") is None
    # a directory is not a servable file
    assert app_module.declared_file_or_none(t, "docs") is None


def _with_plan(client, tmp_path, tasks_md: str | None, ado_id: int = 30,
               trailing_slash: bool = False):
    """A ticket with a `design` run that declared a change directory, and an `implement`
    run in flight. Returns the ticket id."""
    import app as app_module

    change = tmp_path / "repo" / "openspec" / "changes" / f"{ado_id}-x"
    change.mkdir(parents=True, exist_ok=True)
    if tasks_md is not None:
        (change / "tasks.md").write_text(tasks_md, encoding="utf-8")
    rel = f"openspec/changes/{ado_id}-x" + ("/" if trailing_slash else "")
    tid = client.post("/tickets", json={"ado_id": ado_id, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'design','success','ok',?)", (tid, rel))
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    return tid


def _implement(client, tid):
    return next(f for f in client.get(f"/tickets/{tid}").json()["fases"]
                if f["fase"] == "implement")


def test_progress_counts_the_boxes(client, tmp_path):
    md = "## 1\n- [x] a\n- [x] b\n  - [x] c\n- [ ] d\n- [ ] e\n"
    tid = _with_plan(client, tmp_path, md)
    assert _implement(client, tid)["progreso"] == {"hechas": 3, "total": 5}


def test_no_tasks_md_means_no_bar(client, tmp_path):
    tid = _with_plan(client, tmp_path, None, ado_id=31)
    assert _implement(client, tid).get("progreso") is None


def test_tasks_md_without_boxes_means_no_bar(client, tmp_path):
    tid = _with_plan(client, tmp_path, "solo prosa, ninguna casilla\n", ado_id=32)
    assert _implement(client, tid).get("progreso") is None


def test_no_design_run_means_no_bar(client):
    import app as app_module
    tid = client.post("/tickets", json={"ado_id": 33, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    assert _implement(client, tid).get("progreso") is None


def test_an_unreadable_tasks_md_means_no_bar(client, tmp_path, monkeypatch):
    """The counter runs WHILE `implement` is writing that same file — it is polled every
    three seconds during a run that took 83 minutes in production. That is a real TOCTOU
    window between `declared_file_or_none`'s `is_file()` and the `read_text()` two lines
    later, not a device-file curiosity. Without this test, deleting the `try/except`
    outright reddens nothing."""
    tid = _with_plan(client, tmp_path, "- [x] a\n- [ ] b\n", ado_id=35)
    real_read = Path.read_text

    def boom(self, *a, **k):
        if self.name == "tasks.md":
            raise OSError("el agente lo estaba reescribiendo")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", boom)
    assert _implement(client, tid).get("progreso") is None


def test_a_declared_path_with_a_trailing_slash_still_counts(client, tmp_path, monkeypatch):
    """The stamp is written by an agent obeying a markdown file, so the declared
    directory may or may not carry its trailing slash. `rstrip("/")` covers both — but
    `pathlib` quietly collapses a doubled internal slash on its own by the time it
    resolves, so asserting only the end-to-end `progreso` result passes even with the
    strip removed. This pins the exact string `task_progress` hands to
    `declared_file_or_none`, which the strip actually controls."""
    import app as app_module

    seen = {}
    real_check = app_module.declared_file_or_none

    def spy(t, ruta):
        seen["ruta"] = ruta
        return real_check(t, ruta)

    monkeypatch.setattr(app_module, "declared_file_or_none", spy)
    tid = _with_plan(client, tmp_path, "- [x] a\n- [ ] b\n", ado_id=36, trailing_slash=True)
    assert _implement(client, tid)["progreso"] == {"hechas": 1, "total": 2}
    assert seen["ruta"] == "openspec/changes/36-x/tasks.md"


def test_progress_is_not_a_second_door_to_disk(client, tmp_path):
    """A `design` stamp that declares a traversal must not let the counter read a
    `tasks.md` outside the ticket's repos."""
    import app as app_module

    fuera = tmp_path / "fuera"
    fuera.mkdir(exist_ok=True)
    (fuera / "tasks.md").write_text("- [x] a\n- [ ] b\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 34, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'design','success','ok','../fuera')", (tid,))
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    assert _implement(client, tid).get("progreso") is None
