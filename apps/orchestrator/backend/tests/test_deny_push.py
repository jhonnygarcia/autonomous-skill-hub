"""El hook contiene accidentes, no malicia. Los dos lados importan: denegar de menos
deja escapar un push; denegar de más rompe corridas legítimas y se diagnostica fatal."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hooks.deny_push import debe_denegar  # noqa: E402

DENEGADOS = [
    "git push",
    "git push --force",
    "git push origin ticket-agent/3320",
    "git -C ../ProvidenceTMS push",
    "cd /tmp/x && git push",
    "git remote add otro https://ejemplo/x.git",
    "git remote set-url origin https://ejemplo/x.git",
    "gh pr create --fill",
    "az repos pr create --source-branch x",
]

PERMITIDOS = [
    "git status --porcelain",
    "git commit -m 'push the button'",
    "git pushd",                       # no existe, pero empieza igual
    "git push-notes",                  # el canario del `\\b` mal puesto
    "git remote -v",
    "git remote show origin",
    "npm run build",
    "dotnet build ProvidenceTMS/PTMS.API/PTMS.API.csproj -c Debug",
]


@pytest.mark.parametrize("cmd", DENEGADOS)
def test_deniega(cmd):
    assert debe_denegar(cmd) is True


@pytest.mark.parametrize("cmd", PERMITIDOS)
def test_deja_pasar(cmd):
    assert debe_denegar(cmd) is False
