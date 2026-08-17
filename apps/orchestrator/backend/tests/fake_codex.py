"""Stand-in for `codex exec` in tests.

Deliberately NOT a copy of `fake_claude.py` with the names changed. It mimics the two
things that actually differ and that the runner has to get right, both verified against
codex-cli 0.147.0 on 2026-08-16:

- **the prompt arrives through stdin**, not in argv (`-` is the positional that says
  so), because a pack carries a whole SKILL.md and Windows caps a command line at 32 KB;
- **the session travels as `thread_id`**, not `session_id`.

A fake that shared the shape would pass while the runner mixed the two up.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


# Compact, exactly like the real binary: `{"type":"thread.started","thread_id":"..."}`
# with no spaces. A fake that pretty-printed would have "passed" a session regex that
# the real output never matches.
def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


print("FAKE-CODEX ARGS:", " ".join(sys.argv[1:]))
# Read whole: the runner writes the prompt and closes stdin, and a fake that didn't
# drain it would leave the real one's back-pressure untested.
prompt = sys.stdin.read() if not sys.stdin.isatty() else ""
print("FAKE-CODEX STDIN-BYTES:", len(prompt.encode("utf-8")))
print("FAKE-CODEX PROMPT:", json.dumps(prompt[:4000], ensure_ascii=False))

FAKE_SESSION = "01a00b64-d405-7e13-9dec-200800bb0f40"
if os.environ.get("FAKE_NO_SESSION") != "1":
    print(dumps({"type": "thread.started", "thread_id": FAKE_SESSION}))
if os.environ.get("OPENAI_API_KEY"):
    print("FAKE-CODEX SAW-API-KEY")
print(dumps({"type": "turn.started"}))
if os.environ.get("FAKE_FAIL") == "1":
    print("boom", file=sys.stderr)
    sys.exit(1)
stamp = os.environ.get("FAKE_HUELLA")
if stamp:
    # Nested inside JSON exactly like the real one: that nesting is why `STAMP_RE`
    # stops the path capture at a double quote, and it's what makes this test prove
    # the regex needs no per-engine variant.
    print(json.dumps({"type": "item.completed",
                      "item": {"type": "agent_message",
                               "text": f"cierre.\nHUELLA: {stamp}"}}, ensure_ascii=False))
print(dumps({"type": "turn.completed", "usage": {"output_tokens": 12}}))
