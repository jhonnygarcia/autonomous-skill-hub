# Fase 2b — del plan al código — Plan de implementación

> **Ejecutado el 2026-08-10**, más la oleada de arreglos de la revisión final. Dos
> bloques de código que este documento muestra quedaron **desactualizados en ejecución**,
> y en los dos casos **manda el código**, no este plan:
>
> - **El regex del hook** (Tarea 3, `hooks/deny_push.py`). Aquí aparece con `\bgit\b…`,
>   que casa la subcadena en CUALQUIER posición: `git commit -m "... git push ..."` se
>   denegaba por mencionar la frase dentro del mensaje. El código añade un ancla de
>   inicio de comando (`_INICIO`: principio de cadena o tras `;`, `&`, `|`, salto de
>   línea, `(` o backtick, con `then`/`do`/`else` opcional dentro del ancla) a cada
>   alternativa.
> - **El helper `_app()` de los tests** (Tarea 1). Aquí solo mete `BACKEND_DIR` en
>   `sys.path`. Así, el primer import real de `app` dispara `init_db()` contra la **BD y
>   los logs reales** del backend. El código fija `ORCH_DB`/`ORCH_LOGS` a `tmp_path` y
>   saca `app` de `sys.modules` antes de importarlo, replicando el aislamiento del
>   fixture `client`; por eso recibe `(monkeypatch, tmp_path)`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una corrida de la fase `implement` ejecute el plan de OpenSpec de un
ticket —código escrito, comprobaciones corridas, commits por tarea en una rama— y deje
constancia verificable de qué quedó hecho y qué no.

**Architecture:** El runner gana tres pasos deterministas antes de lanzar el subproceso
(guarda de árbol limpio, creación de rama, `--settings` con un hook que deniega el push)
y una fase nueva en las cuatro tablas de `app.py`. La skill `change-implementation`
recorre `tasks.md`, delega cada tarea a un subagente, revisa su diff, commitea rutas
concretas y marca la casilla. El sello `HUELLA:` sigue siendo lo que decide el estado.

**Tech Stack:** Python 3 + FastAPI + SQLite sin ORM (backend), pytest, `git` por
`subprocess`, markdown para la skill, React+TS para el retoque de UI.

## Global Constraints

- **Suscripción, jamás API key.** El runner elimina `ANTHROPIC_API_KEY` y
  `ANTHROPIC_AUTH_TOKEN` del entorno del subproceso. No reintroducirlas.
- **Nunca `uvicorn --reload` en Windows**: deja hijos huérfanos reteniendo el 8000.
- **Tocar una skill obliga a subir `version` en `plugins/ticket-agent/.claude-plugin/plugin.json`.**
- **Documentación y comentarios en español.**
- **Bash va sin especificador en `implement`, a propósito.** Un `Bash(git:*)` fingiría
  una restricción que está verificado que no existe.
- **La guarda ignora los archivos sin trackear** (`??`). Es obligatorio: el repo
  principal siempre tiene `openspec/` y `docs/tickets/` sin trackear.
- Antes de dar por bueno un test, responder: **¿qué tendría que romperse para que este
  test fallara?** Si no hay respuesta concreta, el test no prueba nada.
- Ruta del backend: `apps/orchestrator/backend/`. Tests con
  `.venv/Scripts/python -m pytest tests/ -v` desde ahí.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/hooks/deny_push.py` | **Nuevo.** Hook `PreToolUse`: decide si un comando Bash sale de la máquina |
| `backend/tests/test_deny_push.py` | **Nuevo.** Tabla de comandos denegados y permitidos |
| `backend/app.py` | Guarda, rama, tablas de fase, `settings_de`, cableado |
| `backend/tests/test_app.py` | Tests del runner (se extiende) |
| `plugins/ticket-agent/skills/change-implementation/SKILL.md` | **Nuevo.** El procedimiento |
| `plugins/ticket-agent/commands/implement.md` | **Nuevo.** El comando |
| `frontend/src/Timeline.tsx` | Mostrar la rama junto a la huella |

---

### Task 1: Verificar si un subagente hereda Bash y `--add-dir`

Es un spike, no código. **Gatea la forma de la Tarea 7**: si no hereda, el bucle con
subagente por tarea no es implementable y la skill se escribe lineal (enfoque A).

**Files:**
- Modify: `docs/superpowers/specs/2026-08-10-fase-2b-del-plan-al-codigo-design.md`
  (sección "Riesgos e incógnitas abiertas")

**Interfaces:**
- Produces: la decisión `HEREDA = sí | no`, que la Tarea 7 consume para elegir entre
  bucle con subagentes o bucle lineal.

- [ ] **Step 1: Lanzar el CLI real con los flags del runner**

Desde `D:/Companies/ProvidenceSolutions/ProvidenceTMSTenant`:

```bash
claude -p "Usa la herramienta Task para lanzar un subagente. El subagente debe ejecutar exactamente 'git status --porcelain' con cwd en D:/Companies/ProvidenceSolutions/ProvidenceTMS y devolverte su salida literal, y además leer el primer renglon de D:/Companies/ProvidenceSolutions/ProvidenceTMS/package.json. Reportame las dos cosas, y si alguna fue denegada dime el mensaje exacto de la denegacion." \
  --output-format stream-json --verbose \
  --permission-mode acceptEdits \
  --allowedTools mcp__azure-devops Read Glob Grep Task Write Edit Bash \
  --add-dir D:/Companies/ProvidenceSolutions/ProvidenceTMS \
  > /tmp/spike-subagente.log
```

(En Windows, redirigir a un archivo del scratchpad en vez de `/tmp`.)

- [ ] **Step 2: Leer el resultado en el log**

Buscar en el log: si aparece la salida de `git status` producida **dentro** de un
`Task`, hereda Bash. Si aparece el contenido de `package.json`, hereda el `--add-dir`.
Si aparece una denegación, copiar su texto literal.

Expected: una de las dos respuestas, sin ambigüedad. Si el agente principal ejecuta el
comando él mismo en vez de delegarlo, **el spike no vale**: repetir insistiendo en que
sea el subagente quien lo ejecute.

- [ ] **Step 3: Registrar la respuesta en el spec**

Sustituir el bullet "Herencia de permisos por los subagentes" de la sección "Riesgos e
incógnitas abiertas" por lo verificado, con la fecha y el fragmento de log que lo
prueba. Si la respuesta es "no hereda", añadir además una línea en "Decisiones"
anotando que la decisión 6 cae a la variante lineal y por qué.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-10-fase-2b-del-plan-al-codigo-design.md
git commit -m "docs(fase-2b): verificada la herencia de permisos por subagentes"
```

---

### Task 2: El hook que deniega el push

Independiente del resto: función pura, tabla de casos, sin tocar el runner.

**Files:**
- Create: `apps/orchestrator/backend/hooks/deny_push.py`
- Create: `apps/orchestrator/backend/tests/test_deny_push.py`

**Interfaces:**
- Produces: `debe_denegar(comando: str) -> bool` y `main() -> int` (código de salida
  del hook: `2` deniega, `0` deja pasar). La Tarea 5 consume la **ruta del archivo**,
  no estas funciones.

- [ ] **Step 1: Escribir el test que falla**

Crear `apps/orchestrator/backend/tests/test_deny_push.py`:

```python
"""El hook contiene accidentes, no malicia. Los dos lados importan: denegar de menos
deja escapar un push; denegar de más rompe corridas legítimas y se diagnostica fatal."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hooks.deny_push import debe_denegar  # noqa: E402

DENEGADOS = [
    "git push",
    "git push --force",
    "git push origin ticket-agent/3320",
    "git -C ../ProvidenceTMS push",
    "cd /tmp/x && git push",
    "git remote add otro https://ejemplo/x.git",
    "git remote set-url origin https://ejemplo/x.git",
    "gh pr create --fill",
    "az repos pr create --source-branch x",
]

PERMITIDOS = [
    "git status --porcelain",
    "git commit -m 'push the button'",
    "git pushd",                       # no existe, pero empieza igual
    "git push-notes",                  # el canario del `\\b` mal puesto
    "git remote -v",
    "git remote show origin",
    "npm run build",
    "dotnet build ProvidenceTMS/PTMS.API/PTMS.API.csproj -c Debug",
]


@pytest.mark.parametrize("cmd", DENEGADOS)
def test_deniega(cmd):
    assert debe_denegar(cmd) is True


@pytest.mark.parametrize("cmd", PERMITIDOS)
def test_deja_pasar(cmd):
    assert debe_denegar(cmd) is False
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `.venv/Scripts/python -m pytest tests/test_deny_push.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'hooks'`

- [ ] **Step 3: Escribir el hook**

Crear `apps/orchestrator/backend/hooks/__init__.py` vacío y
`apps/orchestrator/backend/hooks/deny_push.py`:

```python
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
```

- [ ] **Step 4: Correr el test para verlo pasar**

Run: `.venv/Scripts/python -m pytest tests/test_deny_push.py -v`
Expected: PASS, 17 casos.

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/hooks/ apps/orchestrator/backend/tests/test_deny_push.py
git commit -m "feat(orchestrator): hook que deniega push y PR en la fase implement"
```

---

### Task 3: Guarda de árbol limpio

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (junto a `check_dirs`, ~línea 129)
- Modify: `apps/orchestrator/backend/tests/test_app.py` (al final)

**Interfaces:**
- Produces: `sucio(repo: str) -> bool` y `check_limpios(repos: list[str]) -> None`
  (lanza `HTTPException(409)`). La Tarea 6 los llama desde `run_ticket`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `apps/orchestrator/backend/tests/test_app.py`:

```python
import subprocess

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _app():
    """`app` se importa DENTRO de cada test porque conftest lo saca de `sys.modules`
    para que relea `ORCH_DB`. Y el `sys.path` lo pone el fixture `client`, que estos
    tests no usan: sin esta línea pasarían o fallarían según el orden de ejecución."""
    sys.path.insert(0, str(BACKEND_DIR))
    import app
    return app


def _git_init(path):
    """Un repo con un commit: `git switch -c` necesita algo de donde colgar."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "seed.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=path, check=True)


def test_guarda_bloquea_un_trackeado_modificado(tmp_path):
    """Sin esto, `git switch -c` arrastra tu trabajo sin commitear a la rama del
    agente y el agente lo commitea como suyo."""
    app = _app()
    _git_init(tmp_path)
    (tmp_path / "seed.txt").write_text("v2\n", encoding="utf-8")
    assert app.sucio(str(tmp_path)) is True


def test_guarda_tolera_los_no_trackeados(tmp_path):
    """El caso que hace la fase lanzable: el repo principal SIEMPRE tiene
    `openspec/` y `docs/tickets/` sin trackear, que son artefactos del agente.
    Si este test falla, la fase implement es inlanzable para siempre."""
    app = _app()
    _git_init(tmp_path)
    (tmp_path / "openspec").mkdir()
    (tmp_path / "openspec" / "changes.md").write_text("x", encoding="utf-8")
    assert app.sucio(str(tmp_path)) is False


def test_guarda_ve_lo_que_esta_en_stage(tmp_path):
    app = _app()
    _git_init(tmp_path)
    (tmp_path / "nuevo.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "nuevo.txt"], cwd=tmp_path, check=True)
    assert app.sucio(str(tmp_path)) is True


def test_check_limpios_nombra_los_repos_sucios(tmp_path):
    app = _app()
    from fastapi import HTTPException
    limpio, sucio_ = tmp_path / "a", tmp_path / "b"
    limpio.mkdir(); sucio_.mkdir()
    _git_init(limpio); _git_init(sucio_)
    (sucio_ / "seed.txt").write_text("v2\n", encoding="utf-8")
    with pytest.raises(HTTPException) as e:
        app.check_limpios([str(limpio), str(sucio_)])
    assert e.value.status_code == 409
    assert str(sucio_) in e.value.detail
    assert str(limpio) not in e.value.detail


def test_un_directorio_que_no_es_git_da_409(tmp_path):
    app = _app()
    from fastapi import HTTPException
    (tmp_path / "pelado").mkdir()
    with pytest.raises(HTTPException) as e:
        app.check_limpios([str(tmp_path / "pelado")])
    assert e.value.status_code == 409
```

Añadir `import pytest` al principio del archivo si no está.

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k guarda -v`
Expected: FAIL con `AttributeError: module 'app' has no attribute 'sucio'`

- [ ] **Step 3: Implementar**

En `apps/orchestrator/backend/app.py`, justo después de `check_dirs`:

```python
def sucio(repo: str) -> bool:
    """¿Hay trabajo sin commitear que un `git switch -c` se llevaría por delante?

    Los `??` se ignoran **a propósito**: el repo principal siempre tiene `openspec/`,
    `docs/tickets/` y lo que dejó `openspec init` sin trackear — son artefactos del
    propio agente. Exigir un árbol virgen haría la fase inlanzable siempre. Lo que
    importa es lo trackeado: eso sí es trabajo del usuario.
    """
    r = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No es un repositorio git: {repo}")
    return any(not ln.startswith("??") for ln in r.stdout.splitlines() if ln.strip())


def check_limpios(repos: list[str]) -> None:
    malos = [r for r in repos if sucio(r)]
    if malos:
        raise HTTPException(409, "Hay cambios sin commitear en: " + ", ".join(malos)
                            + ". La fase implement commitea, y no debe llevarse por "
                              "delante tu trabajo a medias.")
```

Añadir `import subprocess` al bloque de imports de `app.py` si no está.

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "guarda or limpios or no_es_git" -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): guarda de arbol limpio que tolera lo no trackeado"
```

---

### Task 4: Preparación de rama y columna `branch`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (`init_db` ~línea 201, y junto a `check_limpios`)
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `RAMA_FMT: str`, `preparar_rama(repo: str, ado_id: int) -> str` (devuelve el
  nombre de la rama), y la columna `runs.branch`. La Tarea 6 los usa; la Tarea 8 lee la
  columna.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_app.py`:

```python
def test_preparar_rama_la_crea_y_se_situa_en_ella(tmp_path):
    app = _app()
    _git_init(tmp_path)
    nombre = app.preparar_rama(str(tmp_path), 3320)
    assert nombre == "ticket-agent/3320"
    actual = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path,
                            capture_output=True, text=True).stdout.strip()
    assert actual == "ticket-agent/3320"


def test_preparar_rama_dos_veces_no_falla(tmp_path):
    """Retomar una corrida parcial tiene que aterrizar en la MISMA rama. Con
    `switch -c` a secas, la segunda llamada peta con 'already exists'."""
    app = _app()
    _git_init(tmp_path)
    app.preparar_rama(str(tmp_path), 3320)
    subprocess.run(["git", "switch", "-q", "-"], cwd=tmp_path, check=True)
    assert app.preparar_rama(str(tmp_path), 3320) == "ticket-agent/3320"
    actual = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path,
                            capture_output=True, text=True).stdout.strip()
    assert actual == "ticket-agent/3320"
    ramas = subprocess.run(["git", "branch", "--list"], cwd=tmp_path,
                           capture_output=True, text=True).stdout
    assert ramas.count("ticket-agent/3320") == 1


def test_runs_tiene_columna_branch(client):
    import app
    with app.db() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(runs)")]
    assert "branch" in cols
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "rama or branch" -v`
Expected: FAIL con `AttributeError: module 'app' has no attribute 'preparar_rama'`

- [ ] **Step 3: Implementar**

En `app.py`, después de `check_limpios`:

```python
RAMA_FMT = "ticket-agent/{ado_id}"


def preparar_rama(repo: str, ado_id: int) -> str:
    """Crea la rama de la fase, o se sitúa en ella si ya existe.

    La crea el runner y no la skill por el mismo motivo por el que existe el sello: un
    límite que depende de que el agente obedezca un markdown no es un límite.
    `refs/heads/` en el `rev-parse` para no confundir la rama con un tag o un sha.
    """
    nombre = RAMA_FMT.format(ado_id=ado_id)
    existe = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{nombre}"],
                            cwd=repo, capture_output=True).returncode == 0
    cmd = ["git", "switch", "-q", nombre] if existe else ["git", "switch", "-q", "-c", nombre]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No se pudo preparar la rama en {repo}: {r.stderr.strip()}")
    return nombre
```

Y en `init_db`, añadir a la tupla de `alter`:

```python
            # La rama que preparó el runner para una corrida de `implement`. Es el
            # único dato que la corrida produce y no cabe en `tasks.md`.
            "ALTER TABLE runs ADD COLUMN branch TEXT",
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "rama or branch" -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): rama por ticket, reentrante, y columna branch en runs"
```

---

### Task 5: La fase `implement` en las tablas, y `--settings` por fase

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (tablas ~línea 18-48; `execute_run` ~línea 519)
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `hooks/deny_push.py` de la Tarea 2 (solo su ruta).
- Produces: `settings_de(phase: str) -> list[str]` (los argumentos `--settings ...`, o
  lista vacía) y las cuatro entradas de `implement` en las tablas de fase.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_app.py`:

```python
def _espiar_argv(monkeypatch):
    """Sobre los argumentos REALES del subproceso, no sobre una subcadena del log."""
    import asyncio
    capturado = {}
    original = asyncio.create_subprocess_exec

    async def espia(*args, **kwargs):
        capturado["argv"] = args
        return await original(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", espia)
    return capturado


def test_implement_lleva_bash_pelado_y_settings(client, monkeypatch, tmp_path):
    import app
    _use_fake_claude(monkeypatch)
    cap = _espiar_argv(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    argv = cap["argv"]
    assert "Bash" in argv                      # pelado, no un especificador
    assert "--settings" in argv
    assert "deny_push.py" in argv[argv.index("--settings") + 1]


def test_analyze_no_lleva_settings_ni_bash(client, monkeypatch):
    """Que la lista no vuelva a viajar fija para todas las fases: fue justo lo que
    hizo que la Fase 1, declarada de solo lectura, acabara ejecutando shell."""
    _use_fake_claude(monkeypatch)
    cap = _espiar_argv(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    assert "--settings" not in cap["argv"]
    assert "Bash" not in cap["argv"]


def test_las_cuatro_tablas_incluyen_implement():
    import app
    for tabla in (app.PHASE_COMMANDS, app.PHASE_DONE,
                  app.PHASE_ALLOWED_TOOLS, app.PHASE_NOUN):
        assert "implement" in tabla
    assert app.PHASE_DONE["implement"] == "implemented"
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "implement or settings" -v`
Expected: FAIL — `implement` da 400 ("no es ejecutable todavía") y `KeyError`.

- [ ] **Step 3: Implementar**

En `app.py`, las cuatro tablas:

```python
PHASE_COMMANDS = {
    "analyze": "/ticket-agent:analyze",
    "design": "/ticket-agent:plan",
    "implement": "/ticket-agent:implement",
}
PHASE_DONE = {"analyze": "analyzed", "design": "planned", "implement": "implemented"}
PHASE_ALLOWED_TOOLS = {
    "analyze": [],
    "design": [
        "Bash(npx --yes @fission-ai/openspec@latest:*)",
        "Bash(npx @fission-ai/openspec:*)",
    ],
    # Sin especificador y a propósito: está verificado en corrida real que
    # `Bash(x:*)` habilita la herramienta y no la acota. Fingir lo contrario sería
    # peor que no ponerlo. La contención va por `--settings` (ver `settings_de`).
    "implement": ["Bash"],
}
PHASE_NOUN = {"analyze": "el análisis", "design": "el plan",
              "implement": "la implementación"}
```

Y, junto a ellas:

```python
HOOK_DENY_PUSH = Path(__file__).resolve().parent / "hooks" / "deny_push.py"


def settings_de(phase: str) -> list[str]:
    """`--settings` acepta un JSON en línea, así que el hook viaja sin archivo de
    configuración y sin escribir nada en el repo del cliente.

    Se ramifica por fase igual que las tools: ponerlo en todas daría igual hoy —las
    otras no tienen Bash— pero volvería a mezclar "lo que necesita esta fase" con "lo
    que arrastran todas".
    """
    if phase != "implement":
        return []
    cfg = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f'"{sys.executable}" "{HOOK_DENY_PUSH}"'}]}]}}
    return ["--settings", json.dumps(cfg)]
```

Añadir `import sys` si no está. En `execute_run`, dentro de la construcción de `cmd`,
después de `*PHASE_ALLOWED_TOOLS[phase],`:

```python
            *settings_de(phase),
```

- [ ] **Step 4: Correr los tests para verlos pasar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: PASS, toda la suite (los 66 anteriores incluidos).

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): fase implement con Bash y hook por --settings"
```

---

### Task 6: Cablear la guarda y la rama en `run_ticket`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (`run_ticket` ~línea 575)
- Modify: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `check_limpios` y `preparar_rama` (Tareas 3 y 4), `PHASE_COMMANDS` (Tarea 5).
- Produces: el `409` antes de encolar, y `runs.branch` poblada.

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_implement_con_repo_sucio_da_409_y_no_encola(client, monkeypatch, tmp_path):
    """El 409 llega ANTES de gastar un subproceso de 8 minutos."""
    import app
    _use_fake_claude(monkeypatch)
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    (tmp_path / "repo" / "seed.txt").write_text("v2\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 409
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_implement_guarda_la_rama_en_la_corrida(client, monkeypatch, tmp_path):
    _use_fake_claude(monkeypatch, huella="ok — openspec/changes/3320-x/tasks.md")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["branch"] == "ticket-agent/3320"


def test_analyze_no_exige_repo_limpio(client, monkeypatch):
    """La guarda es de `implement`. Si se aplicara a todas, la Fase 1 dejaría de
    poder correrse sobre un repo con trabajo a medias, que es lo normal."""
    _use_fake_claude(monkeypatch, huella="ok — docs/tickets/3311-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={})
    assert r.status_code == 202


def test_sello_parcial_de_implement_conserva_la_reserva(client, monkeypatch, tmp_path):
    """El contrato del sello ya existía, pero nadie lo había ejercitado con la fase
    nueva ni con una reserva de esta forma. Falla si el parseo se ata a las rutas de
    `docs/tickets/` o si la reserva se cuela dentro de `artifact_path`."""
    _use_fake_claude(
        monkeypatch,
        huella="parcial — openspec/changes/3320-x/tasks.md · 3/5 tareas, build en rojo")
    for d in ("repo", "backend-repo"):
        _git_init(tmp_path / d)
    tid = client.post("/tickets", json={"ado_id": 3320, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    run = client.get(f"/tickets/{tid}").json()["runs"][0]
    assert run["artifact_state"] == "parcial"
    assert run["artifact_path"] == "openspec/changes/3320-x/tasks.md"
    assert run["artifact_note"] == "3/5 tareas, build en rojo"
```

- [ ] **Step 2: Correr los tests para verlos fallar**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "409 or rama_en_la_corrida or no_exige" -v`
Expected: FAIL — hoy devuelve 202 y `branch` es `None`.

- [ ] **Step 3: Implementar**

En `run_ticket`, tras la comprobación de corrida activa y **antes** del `INSERT` en
`runs`:

```python
    rama = None
    if body.phase == "implement":
        # Los tres pasos deterministas del diseño, antes de gastar un subproceso.
        repos = [t["repo_path"]] + [e["path"] for e in
                                    norm_dirs(json.loads(t["extra_dirs"] or "[]"))]
        check_limpios(repos)
        for r in repos:
            # En todos, incluidos los que el plan acabe no tocando: el runner no
            # parsea el plan, y una rama sin commits es ruido que se borra solo.
            rama = preparar_rama(r, t["ado_id"])
```

Y en el `INSERT` de `runs`, añadir la columna `branch` con el valor `rama`.

- [ ] **Step 4: Correr toda la suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS, todos.

- [ ] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): implement exige arbol limpio y prepara la rama"
```

---

### Task 7: La skill `change-implementation` y su comando

**La forma del bucle la decide la Tarea 1.** Lo que sigue asume `HEREDA = sí`; si
salió que no, sustituir el paso 1 del bucle por "implementa la tarea tú mismo" y borrar
el paso 2, dejando el resto igual.

**Files:**
- Create: `plugins/ticket-agent/skills/change-implementation/SKILL.md`
- Create: `plugins/ticket-agent/commands/implement.md`
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json` (`version` → `0.6.0`)

**Interfaces:**
- Consumes: el `tasks.md` que produce `change-planning`; la rama que preparó la Tarea 6.
- Produces: el sello `HUELLA: <ok|parcial|nada> — <ruta a tasks.md>[ · <reserva>]`, que
  el runner ya sabe leer sin cambios.

- [ ] **Step 1: Escribir el comando**

Crear `plugins/ticket-agent/commands/implement.md`, copiando la forma de
`commands/plan.md` (delegar en la skill, sin lógica propia):

```markdown
---
description: Ejecuta el plan de cambios de un work item ya planificado, en una rama
---

Usa la skill `change-implementation` para ejecutar el plan del work item $ARGUMENTS.
```

- [ ] **Step 2: Escribir la skill**

Crear `plugins/ticket-agent/skills/change-implementation/SKILL.md`. El frontmatter y la
sección de cierre van **literales** —el sello es un contrato que el runner parsea con
una regex, así que un parafraseo lo rompe—:

```markdown
---
name: change-implementation
description: Ejecuta el plan de cambios de un ticket de Azure DevOps - lee openspec/changes/<id>-*/tasks.md, implementa cada tarea con un subagente, corre su comprobación, commitea por tarea en la rama del ticket y marca las casillas. Usar cuando se pida implementar, ejecutar el plan o escribir el código de un ticket ya planificado.
---
```

Y la última sección, exacta:

```markdown
## Cierre

Termina siempre con una de estas tres líneas, y que sea la **última** del mensaje:

    HUELLA: ok — openspec/changes/<id>-<slug>/tasks.md
    HUELLA: parcial — openspec/changes/<id>-<slug>/tasks.md · <reserva>
    HUELLA: nada — <motivo>

`ok` exige **las dos cosas**: todas las casillas marcadas y el build en verde. Si falta
cualquiera, es `parcial`, y la reserva dice qué: `3/5 tareas, build en rojo`.

La ruta va con barras normales (`/`), nunca invertidas. La reserva va **solo** en la
línea del sello, tras ` · `; el resto de la explicación va en el resumen, no aquí.
```

El cuerpo lleva estas secciones, con el contenido de la sección "La skill
`change-implementation`" y "Reglas de oro" del spec:

1. **Configuración**: leer `.claude/ticket-agent.json`, sacar `autonomy`.
2. **Precondiciones**: buscar `openspec/changes/<id>-*/tasks.md`; si no hay → parar y
   cerrar con `HUELLA: nada — falta el plan de <id>`; si hay más de uno → parar y
   preguntar cuál; comprobar que la rama actual es `ticket-agent/<id>`.
3. **Lectura**: `tasks.md` entero, más `design.md` y `proposal.md`.
4. **Bucle** por cada tarea sin marcar, en orden: subagente en contexto limpio con el
   texto literal de la tarea → ejecuta y corre su "Comprobación" → devuelve archivos
   tocados, resultado y desviaciones → el agente principal revisa el diff de esas rutas
   → commit de esas rutas con mensaje `<id> tarea N: <asunto>` → marcar `- [x]`.
5. **Parada**: si una tarea falla dos veces, **el bucle para**; no se salta ni se
   continúa. Sellar `parcial`.
6. **Cierre**: build de cada repo tocado (verde es condición para `ok`), sello, y en
   `supervised` resumen en el chat.
7. **Reglas de oro**, las cinco del spec, literales:
   1. Commitea rutas concretas. Nunca `git add -A` ni `git add .`.
   2. Un commit por tarea, con su número y su asunto.
   3. La comprobación de la tarea se ejecuta, no se declara.
   4. Una tarea que falla dos veces detiene el plan.
   5. No se reintenta lo que el hook deniega.
8. **Cierre**, el bloque literal de arriba.

- [ ] **Step 3: Subir la versión del plugin**

En `plugins/ticket-agent/.claude-plugin/plugin.json`, `version` → `"0.6.0"`. Sin esto,
`claude plugin update` no trae nada y la prueba sale falsa.

- [ ] **Step 4: Validar y aplicar**

```bash
claude plugin validate .
claude plugin update ticket-agent@autonomous-skill-hub
```
Expected: `Validation passed` y `updated from 0.5.2 to 0.6.0`.

- [ ] **Step 5: Commit**

```bash
git add plugins/ticket-agent
git commit -m "feat(ticket-agent): skill change-implementation para la fase 2b"
```

---

### Task 8: Mostrar la rama en el timeline

**Files:**
- Modify: `apps/orchestrator/frontend/src/Timeline.tsx`

**Interfaces:**
- Consumes: `runs[].branch` (Tarea 4) vía `GET /tickets/{id}`.

- [ ] **Step 1: Comprobar que el campo llega**

Run: `curl -s localhost:8000/tickets/3 | python -m json.tool | grep branch`
Expected: la clave existe (valor `null` en las corridas viejas).

- [ ] **Step 2: Pintarla junto a la huella**

En la fila de la fase, donde hoy se muestra `artifact_path`, añadir la rama cuando
exista, con el mismo tratamiento tipográfico que la ruta del artefacto (fuente mono,
tamaño menor). Debe desaparecer sin hueco cuando es `null` — la mayoría de las corridas
no tienen rama.

- [ ] **Step 3: Verificar build y lint**

```bash
npm run build
npm run lint
```
Expected: ambos verdes.

- [ ] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src/Timeline.tsx
git commit -m "feat(orchestrator-ui): la rama de la corrida junto a su huella"
```

---

## Cierre del hito

Cuando las ocho tareas estén hechas, la prueba de fuego es **el 3320**: 5 tareas, un
solo repo, y ese repo es un `extra_dir` — así que la primera corrida real ejercita de
inmediato la decisión de multi-repo escribible.

Comprobar, como se hizo con el 3322 y el 3323:

- El sello en el log, anclado en la **última** coincidencia.
- `tasks.md` con las casillas marcadas, servido por el visor dentro de la app.
- `git log` de `ProvidenceTMS` en la rama `ticket-agent/3320`: un commit por tarea, y
  **ningún commit que arrastre `openspec/`, `docs/tickets/` o `.claude/`**.
- Que el hook haya denegado algo, o que no haya hecho falta. Las dos cosas son
  información; lo que no vale es no saberlo.

Actualizar `docs/STATUS.md` con el resultado y marcar las casillas de este plan.
