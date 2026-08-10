"""Hook `PreToolUse` sobre Bash: deniega lo que sale de la máquina.

Contiene **accidentes, no malicia**: quien quisiera evadirlo tiene `bash -c` con la
cadena montada en una variable. Es un pestillo, no un blindaje, y su valor está en que
la acción irreversible deje de estar a un token de distancia.

Va en hook y no en `--disallowedTools` porque los especificadores casan prefijos
literales y `git -C ../otro push` se cuela por ahí.
"""
import json
import re
import sys

# `(?![-\w])` en vez de `\b` al final de cada verbo: `\b` casa entre `h` y `-`, así que
# `git push-notes` saldría denegado. Denegar de más rompe corridas legítimas.
# El grupo de opciones cubre `git -C <ruta> push` y `git --git-dir=x push`.
_OPCIONES = r"(?:\s+-{1,2}\S+(?:\s+\S+)?)*"
PROHIBIDO = re.compile(
    rf"\bgit\b{_OPCIONES}\s+push(?![-\w])"
    rf"|\bgit\b{_OPCIONES}\s+remote\s+(?:add|set-url)(?![-\w])"
    r"|\bgh\s+pr\s+create(?![-\w])"
    r"|\baz\s+repos\s+pr\s+create(?![-\w])"
)

MOTIVO = ("La Fase 2b para en rama con commits: nada de push ni de PR. "
          "No reintentes; registra la denegación y sigue con el plan.")


def debe_denegar(comando: str) -> bool:
    return PROHIBIDO.search(comando) is not None


def main() -> int:
    try:
        evento = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # sin evento legible no hay nada que denegar
    if evento.get("tool_name") != "Bash":
        return 0
    if debe_denegar(evento.get("tool_input", {}).get("command", "")):
        print(MOTIVO, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
