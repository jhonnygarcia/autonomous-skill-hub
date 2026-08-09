import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
BACKEND = TESTS.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCH_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ORCH_LOGS", str(tmp_path / "logs"))
    (tmp_path / "repo").mkdir()
    (tmp_path / "backend-repo").mkdir()
    sys.path.insert(0, str(BACKEND))
    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_module  # noqa: E402

    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        c.post("/projects", json={
            "name": "Demo", "org": "DemoOrg", "project": "Demo",
            "repos": [
                {"path": (tmp_path / "repo").as_posix(), "label": "front", "primary": True},
                {"path": (tmp_path / "backend-repo").as_posix(), "label": "backend"},
            ],
        })
        yield c
