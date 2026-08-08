import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
BACKEND = TESTS.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    config = tmp_path / "config.json"
    config.write_text(
        '{"projects": [{"name": "Demo", "org": "DemoOrg", "project": "Demo", '
        f'"repoPath": "{(tmp_path / "repo").as_posix()}"}}]}}',
        encoding="utf-8",
    )
    (tmp_path / "repo").mkdir()
    monkeypatch.setenv("ORCH_CONFIG", str(config))
    sys.path.insert(0, str(BACKEND))
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module  # noqa: E402

    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c
