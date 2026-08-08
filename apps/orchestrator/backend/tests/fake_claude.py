"""Sustituto de `claude -p` para tests: imprime sus args y respeta FAKE_FAIL."""
import os
import sys

print("FAKE-CLAUDE ARGS:", " ".join(sys.argv[1:]))
if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
    print("FAKE-CLAUDE SAW-API-KEY")
print('{"type":"assistant","text":"analizando..."}')
if os.environ.get("FAKE_FAIL") == "1":
    print("boom", file=sys.stderr)
    sys.exit(1)
print('{"type":"result","subtype":"success"}')
