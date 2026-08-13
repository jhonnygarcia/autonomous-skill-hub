"""Stand-in for `claude -p` in tests: prints its args and honors FAKE_FAIL."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # the real CLI emits UTF-8; on Windows print uses cp1252

print("FAKE-CLAUDE ARGS:", " ".join(sys.argv[1:]))
if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
    print("FAKE-CLAUDE SAW-API-KEY")
if os.environ.get("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"):
    print("FAKE-CLAUDE SAW-EXTRA-CLAUDE-MD")
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
