"""El hook contiene accidentes, no malicia. Los dos lados importan: denegar de menos
deja escapar un push; denegar de más rompe corridas legítimas y se diagnostica fatal."""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hooks.deny_push import MOTIVO, debe_denegar, main  # noqa: E402

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
    "if true; then git push; fi",      # palabra clave `then` tras el separador `;`
    "for i in 1; do git push; done",   # palabra clave `do` tras el separador `;`
    "`git push`",                      # el separador ahora incluye el backtick
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
    'git commit -m "fix: prevent accidental git push in CI"',   # "push" entrecomillado
    'echo "reminder: never git push to main" >> NOTES.md',      # ni siquiera es git
    'git commit -m "then git push tomorrow"',  # canario: `then` no vale en cualquier sitio
]


@pytest.mark.parametrize("cmd", DENEGADOS)
def test_deniega(cmd):
    assert debe_denegar(cmd) is True


@pytest.mark.parametrize("cmd", PERMITIDOS)
def test_deja_pasar(cmd):
    assert debe_denegar(cmd) is False


def _correr_main(monkeypatch, payload):
    """Simula stdin con `payload` (JSON ya serializado si es str; si no, se serializa)
    y corre `main()`, devolviendo su código de salida."""
    entrada = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(entrada))
    return main()


def test_main_evento_bash_prohibido(monkeypatch):
    evento = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert _correr_main(monkeypatch, evento) == 2


def test_main_evento_bash_permitido(monkeypatch):
    evento = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert _correr_main(monkeypatch, evento) == 0


def test_main_tool_name_distinto_de_bash(monkeypatch):
    evento = {"tool_name": "Read", "tool_input": {"command": "git push"}}
    assert _correr_main(monkeypatch, evento) == 0


def test_main_stdin_ilegible(monkeypatch):
    assert _correr_main(monkeypatch, "esto no es json") == 0


@pytest.mark.parametrize("payload", [
    None,
    42,
    [1, 2, 3],
    {"tool_name": "Bash", "tool_input": None},
    {"tool_name": "Bash", "tool_input": {"command": 123}},  # `command` no-cadena
])
def test_main_formas_raras_fallan_abierto(monkeypatch, payload):
    assert _correr_main(monkeypatch, payload) == 0


def test_main_imprime_motivo_en_stderr_al_denegar(monkeypatch, capsys):
    evento = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    codigo = _correr_main(monkeypatch, evento)
    assert codigo == 2
    assert MOTIVO in capsys.readouterr().err
