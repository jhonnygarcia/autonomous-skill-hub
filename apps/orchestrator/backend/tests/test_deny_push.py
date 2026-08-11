"""The hook guards against accidents, not malice. Both sides matter: denying too little
lets a push slip through; denying too much breaks legitimate runs and is a nightmare to
diagnose."""
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hooks.deny_push import DENY_REASON, should_deny, main  # noqa: E402

DENIED = [
    "git push",
    "git push --force",
    "git push origin ticket-agent/3320",
    "git -C ../ProvidenceTMS push",
    "cd /tmp/x && git push",
    "git remote add otro https://ejemplo/x.git",
    "git remote set-url origin https://ejemplo/x.git",
    "gh pr create --fill",
    "az repos pr create --source-branch x",
    "if true; then git push; fi",      # `then` keyword after the `;` separator
    "for i in 1; do git push; done",   # `do` keyword after the `;` separator
    "`git push`",                      # the separator now includes the backtick
]

ALLOWED = [
    "git status --porcelain",
    "git commit -m 'push the button'",
    "git pushd",                       # doesn't exist, but starts the same
    "git push-notes",                  # the canary for a misplaced `\\b`
    "git remote -v",
    "git remote show origin",
    "npm run build",
    "dotnet build ProvidenceTMS/PTMS.API/PTMS.API.csproj -c Debug",
    'git commit -m "fix: prevent accidental git push in CI"',   # quoted "push"
    'echo "reminder: never git push to main" >> NOTES.md',      # not even git
    'git commit -m "then git push tomorrow"',  # canary: `then` isn't valid just anywhere
]


@pytest.mark.parametrize("cmd", DENIED)
def test_denies(cmd):
    assert should_deny(cmd) is True


@pytest.mark.parametrize("cmd", ALLOWED)
def test_lets_through(cmd):
    assert should_deny(cmd) is False


def _run_main(monkeypatch, payload):
    """Simulates stdin with `payload` (already-serialized JSON if it's a str; if not,
    it gets serialized) and runs `main()`, returning its exit code."""
    stdin_text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    return main()


def test_main_bash_event_forbidden(monkeypatch):
    event = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert _run_main(monkeypatch, event) == 2


def test_main_bash_event_allowed(monkeypatch):
    event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert _run_main(monkeypatch, event) == 0


def test_main_tool_name_other_than_bash(monkeypatch):
    event = {"tool_name": "Read", "tool_input": {"command": "git push"}}
    assert _run_main(monkeypatch, event) == 0


def test_main_unreadable_stdin(monkeypatch):
    assert _run_main(monkeypatch, "esto no es json") == 0


@pytest.mark.parametrize("payload", [
    None,
    42,
    [1, 2, 3],
    {"tool_name": "Bash", "tool_input": None},
    {"tool_name": "Bash", "tool_input": {"command": 123}},  # non-string `command`
])
def test_main_odd_shapes_fail_open(monkeypatch, payload):
    assert _run_main(monkeypatch, payload) == 0


def test_main_prints_reason_to_stderr_on_deny(monkeypatch, capsys):
    event = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    code = _run_main(monkeypatch, event)
    assert code == 2
    assert DENY_REASON in capsys.readouterr().err
