"""Sustituto de `claude -p` para tests: imprime sus args y respeta FAKE_FAIL."""
import json
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
if os.environ.get("FAKE_SKILL_LEAK") == "1":
    # Imita el cuerpo de un SKILL.md colándose en el log (el tool_result de cargar la
    # skill): trae los tres sellos en prosa, ANTES del sello de cierre real, tal como
    # pasa en la corrida de verdad.
    cuerpo = (
        "## Cierre\n"
        "Termina siempre con una de estas tres líneas exactas:\n"
        "HUELLA: ok — docs/tickets/<id>-analysis.md\n"
        "HUELLA: parcial — docs/tickets/<id>-analysis.md\n"
        "HUELLA: nada — <motivo>\n"
    )
    print('{"type":"tool_result","text":' + json.dumps(cuerpo) + '}')
sello = os.environ.get("FAKE_HUELLA")
if sello:
    # Simula el sello de cierre obligatorio de las skills.
    print('{"type":"assistant","text":"resumen del cierre. HUELLA: ' + sello + '"}')
print('{"type":"result","subtype":"success"}')
