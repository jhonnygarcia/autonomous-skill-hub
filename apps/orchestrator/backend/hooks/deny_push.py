"""`PreToolUse` hook over Bash: denies what leaves the machine.

It guards against **accidents, not malice**: anyone who wanted to evade it has
`bash -c` with the string assembled in a variable. It's a latch, not armor, and its
value is that the irreversible action stops being one token away.

It's a hook and not `--disallowedTools` because specifiers match literal prefixes and
`git -C ../otro push` slips right through.
"""
import json
import re
import sys

# `(?![-\w])` instead of `\b` at the end of each verb: `\b` matches between `h` and
# `-`, so `git push-notes` would come out denied. Denying too much breaks legitimate
# runs. The options group covers `git -C <path> push` and `git --git-dir=x push`.
_OPTIONS = r"(?:\s+-{1,2}\S+(?:\s+\S+)?)*"
# Each alternative requires the verb to open the command: at the start of the string or
# right after a shell separator (`;`, `&`, `|`, newline, `(` or backtick). Without this
# anchor the regex matches the substring anywhere, including inside quoted text —
# `git commit -m "... git push ..."` isn't a push, it's a commit message. After the
# separator, a shell keyword is optionally allowed (`then`, `do`, `else`) — so
# `if true; then git push; fi` also opens a command. The keyword goes INSIDE the
# anchor, not as a loose alternative: if `then` could appear anywhere,
# `git commit -m "fix: then git push tomorrow"` would go back to being denied through
# the same path that opened the quoted-text finding.
_START = r"(?:^|[;&|\n(`])\s*(?:(?:then|do|else)\s+)?"
FORBIDDEN_RE = re.compile(
    rf"{_START}git\b{_OPTIONS}\s+push(?![-\w])"
    rf"|{_START}git\b{_OPTIONS}\s+remote\s+(?:add|set-url)(?![-\w])"
    rf"|{_START}gh\s+pr\s+create(?![-\w])"
    rf"|{_START}az\s+repos\s+pr\s+create(?![-\w])"
)

DENY_REASON = ("Phase 2b stops on a branch with commits: no push, no PR. "
               "Don't retry; log the denial and carry on with the plan.")


def should_deny(command: str) -> bool:
    return FORBIDDEN_RE.search(command) is not None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # no readable event, nothing to deny
    # The hook fails open: an event shape we don't recognize (not an object, or
    # `tool_input` not an object) isn't a reason to deny nor to crash.
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    # A non-string `command` (e.g. a number) is as unexpected a shape as
    # `tool_input: null`: the same underlying defect, no reason to crash here.
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return 0
    if should_deny(command):
        print(DENY_REASON, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
