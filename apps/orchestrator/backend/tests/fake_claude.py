"""Stand-in for `claude -p` in tests: prints its args and honors FAKE_FAIL."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # the real CLI emits UTF-8; on Windows print uses cp1252

print("FAKE-CLAUDE ARGS:", " ".join(sys.argv[1:]))
# The real CLI emits it from the very first event and keeps it stable for the whole
# run (checked in logs/1.log). Emitted by default so every test exercises the capture;
# FAKE_NO_SESSION covers the opposite case, where the runner must not break.
FAKE_SESSION = "40cb0029-f2da-41da-a306-01c6bba77163"
_session_line = '{"type":"system","subtype":"init","session_id":"' + FAKE_SESSION + '"}'
if os.environ.get("FAKE_NO_SESSION") == "1":
    _session_line = None
elif os.environ.get("FAKE_SESSION_LATE") == "1":
    # Pushes the id past the first 64 KiB read, so it lands in a later chunk. Catches
    # an implementation that only inspects the first chunk — the tempting shortcut,
    # since in a real run the id does arrive in the first event.
    print('{"type":"assistant","text":"' + "relleno" * 12000 + '"}')
else:
    print(_session_line)
    _session_line = None
if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
    print("FAKE-CLAUDE SAW-API-KEY")
if os.environ.get("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"):
    print("FAKE-CLAUDE SAW-EXTRA-CLAUDE-MD")
if _session_line:          # FAKE_SESSION_LATE: after the padding, in a later chunk
    print(_session_line)
print('{"type":"assistant","text":"analizando..."}')
if os.environ.get("FAKE_BIG") == "1":
    # A single line above the 64 KiB limit of asyncio's line reader, with accented
    # characters so it's noticeable if one gets split across two chunks.
    print('{"type":"assistant","text":"' + "ácido" * 20000 + '"}')
if os.environ.get("FAKE_FAIL") == "1":
    print("boom", file=sys.stderr)
    sys.exit(1)
if os.environ.get("FAKE_SKILL_LEAK") == "1":
    # Mimics a SKILL.md body leaking into the log (the tool_result from loading the
    # skill): it carries the three stamps in prose, BEFORE the real closing stamp,
    # exactly as happens on a real run.
    body = (
        "## Cierre\n"
        "Termina siempre con una de estas tres líneas exactas:\n"
        "HUELLA: ok — docs/tickets/<id>-analysis.md\n"
        "HUELLA: parcial — docs/tickets/<id>-analysis.md\n"
        "HUELLA: nada — <motivo>\n"
    )
    # ensure_ascii=False: that's how the real (Node) CLI dumps stream-json — without
    # escaping the em dash to `—`. With json.dumps' default escaping, the three stamps
    # in this prose never matched the regex and the anchoring test passed without
    # exercising anything (`hits` had a single element: the real stamp).
    print('{"type":"tool_result","text":' + json.dumps(body, ensure_ascii=False) + '}')
stamp = os.environ.get("FAKE_HUELLA")
if stamp:
    # Simulates the skills' mandatory closing stamp.
    print('{"type":"assistant","text":"resumen del cierre. HUELLA: ' + stamp + '"}')
print('{"type":"result","subtype":"success"}')
