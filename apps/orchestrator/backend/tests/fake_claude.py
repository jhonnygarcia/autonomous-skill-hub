"""Sustituto de `claude -p` para tests: imprime sus args y respeta FAKE_FAIL."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # el CLI real emite UTF-8; en Windows print usa cp1252

print("FAKE-CLAUDE ARGS:", " ".join(sys.argv[1:]))
if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
    print("FAKE-CLAUDE SAW-API-KEY")
print('{"type":"assistant","text":"analizando..."}')
if os.environ.get("FAKE_BIG") == "1":
    # Una sola línea por encima del límite de 64 KiB del lector de líneas de asyncio,
    # con acentos para que se note si un carácter se parte entre dos trozos.
    print('{"type":"assistant","text":"' + "ácido" * 20000 + '"}')
if os.environ.get("FAKE_FAIL") == "1":
    print("boom", file=sys.stderr)
    sys.exit(1)
sello = os.environ.get("FAKE_PLAN_SELLO")
if sello:
    # Simula el sello de cierre obligatorio de change-planning/SKILL.md §7.
    print('{"type":"assistant","text":"resumen del cierre. PLAN: ' + sello + '"}')
print('{"type":"result","subtype":"success"}')
