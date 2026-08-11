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
# Cada alternativa exige que el verbo abra el comando: al principio de la cadena o
# justo tras un separador de shell (`;`, `&`, `|`, salto de línea, `(` o backtick).
# Sin este anclaje el regex casa la subcadena en cualquier punto, incluida dentro de
# texto entrecomillado — `git commit -m "... git push ..."` no es un push, es un
# mensaje. Tras el separador se admite, opcionalmente, una palabra clave de shell
# (`then`, `do`, `else`) — así `if true; then git push; fi` también abre comando. La
# palabra clave va DENTRO del ancla, no como alternativa suelta: si `then` pudiera
# aparecer en cualquier posición, `git commit -m "fix: then git push tomorrow"`
# volvería a denegarse por la misma vía que abrió el hallazgo del texto entrecomillado.
_INICIO = r"(?:^|[;&|\n(`])\s*(?:(?:then|do|else)\s+)?"
PROHIBIDO = re.compile(
    rf"{_INICIO}git\b{_OPCIONES}\s+push(?![-\w])"
    rf"|{_INICIO}git\b{_OPCIONES}\s+remote\s+(?:add|set-url)(?![-\w])"
    rf"|{_INICIO}gh\s+pr\s+create(?![-\w])"
    rf"|{_INICIO}az\s+repos\s+pr\s+create(?![-\w])"
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
    # El hook falla abierto: una forma de evento que no reconocemos (no es un objeto,
    # o `tool_input` no es un objeto) no es motivo para denegar ni para reventar.
    if not isinstance(evento, dict) or evento.get("tool_name") != "Bash":
        return 0
    entrada = evento.get("tool_input")
    if not isinstance(entrada, dict):
        return 0
    # `command` no-cadena (p. ej. un número) es una forma tan inesperada como
    # `tool_input: null`: el mismo defecto de fondo, sin motivo para reventar aquí.
    comando = entrada.get("command", "")
    if not isinstance(comando, str):
        return 0
    if debe_denegar(comando):
        print(MOTIVO, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
