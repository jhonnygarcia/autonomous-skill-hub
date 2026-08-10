# Fase 2 — del análisis al plan de cambios: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el orquestador pueda lanzar una segunda fase que lee el análisis de un ticket y escribe un change de OpenSpec en el repo destino, sin tocar código de producto.

**Architecture:** una skill nueva `change-planning` hermana de `ticket-comprehension`, con su comando `/ticket-agent:plan`. El runner del orquestador deja de hardcodear el comando y lo deriva de la fase de la corrida. La UI gana un botón que solo aparece cuando el ticket ya tiene análisis.

**Tech Stack:** FastAPI + SQLite sin ORM (backend), Vite + React + Tailwind + shadcn (frontend), pytest, oxlint. La skill es markdown; el CLI `claude` la ejecuta headless.

**Spec:** `docs/superpowers/specs/2026-08-09-fase-2-plan-de-cambios-design.md`

## Global Constraints

- **Documentación y comentarios en español.** El repo es consistente en eso.
- **Tocar una skill obliga a subir `version` en `plugin.json`.** Esa versión es la clave de cache: `claude plugin update` no trae nada si no cambia. Esta entrega sube a **0.4.0**.
- **`claude plugin validate .` desde la raíz del repo debe pasar antes de commitear.**
- **Nunca `uvicorn --reload` en Windows**: deja hijos huérfanos reteniendo el 8000 y sirve código viejo sin avisar. Reiniciar a mano.
- **Suscripción, jamás API key.** El runner elimina `ANTHROPIC_API_KEY` y `ANTHROPIC_AUTH_TOKEN` del entorno del subproceso; hay un test que lo garantiza. No reintroducirlas.
- Comandos del backend desde `apps/orchestrator/backend/`: `.venv/Scripts/python -m pytest tests/ -v`.
- Comandos del frontend desde `apps/orchestrator/frontend/`: `npm run lint`, `npm run build`.

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `plugins/ticket-agent/skills/change-planning/SKILL.md` | **Crear.** El procedimiento de la Fase 2 completo |
| `plugins/ticket-agent/commands/plan.md` | **Crear.** Comando `/ticket-agent:plan <id>`, delega en la skill |
| `plugins/ticket-agent/.claude-plugin/plugin.json` | **Modificar.** `version` → `0.4.0` |
| `apps/orchestrator/backend/app.py` | **Modificar.** Mapa fase→comando, validación de fase, `allowedTools`, estado final |
| `apps/orchestrator/backend/tests/test_app.py` | **Modificar.** Cinco pruebas nuevas |
| `apps/orchestrator/frontend/src/api.ts` | **Modificar.** `run()` acepta fase |
| `apps/orchestrator/frontend/src/estado.ts` | **Modificar.** Etiqueta y color de `planned`; regla de cuándo se puede planificar |
| `apps/orchestrator/frontend/src/TicketDetail.tsx` | **Modificar.** Botón *Planificar* |
| `apps/orchestrator/frontend/src/App.tsx` | **Modificar.** Pasa la fase al `onRun` del detalle |

El backend va entero en `app.py` porque así está hecho el orquestador: un solo archivo con SQLite, rutas y runner. No se parte aquí.

---

### Task 1: Backend — la fase decide el comando

**Files:**
- Modify: `apps/orchestrator/backend/app.py:16` (constante `PHASES`)
- Modify: `apps/orchestrator/backend/app.py:147-149` (`RunIn`)
- Modify: `apps/orchestrator/backend/app.py:289-347` (`execute_run`)
- Modify: `apps/orchestrator/backend/app.py:350-370` (`run_ticket`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `POST /tickets/{tid}/run` acepta `{"instructions": str|null, "phase": str}` con `phase` por defecto `"analyze"`. Devuelve `400` si la fase no es ejecutable. Constantes `PHASE_COMMANDS: dict[str,str]` y `PHASE_DONE: dict[str,str]`. La Tarea 2 consume el campo `phase` desde el frontend.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir en `tests/test_app.py`, justo después de `test_run_success_writes_log_and_states`:

```python
def test_run_design_invoca_el_comando_plan(client, monkeypatch):
    """La fase decide el comando: design NO puede lanzar el analyze."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    detail = client.get(f"/tickets/{tid}").json()
    assert "/ticket-agent:plan 3323" in detail["log_tail"]
    assert "/ticket-agent:analyze" not in detail["log_tail"]
    assert detail["runs"][0]["phase"] == "design"


def test_run_design_deja_el_ticket_planned(client, monkeypatch):
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    assert client.get(f"/tickets/{tid}").json()["ticket"]["status"] == "planned"


def test_fase_declarada_pero_no_ejecutable_da_400(client, monkeypatch):
    """implement está en PHASES pero no existe: se rechaza sin lanzar subproceso."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    r = client.post(f"/tickets/{tid}/run", json={"phase": "implement"})
    assert r.status_code == 400 and "implement" in r.json()["detail"]
    assert client.get(f"/tickets/{tid}").json()["runs"] == []


def test_run_sin_fase_sigue_siendo_analyze(client, monkeypatch):
    """Compatibilidad: quien ya llamaba sin fase no se entera del cambio."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3311, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    detail = client.get(f"/tickets/{tid}").json()
    assert detail["runs"][0]["phase"] == "analyze"
    assert "/ticket-agent:analyze 3311" in detail["log_tail"]


def test_bash_va_acotado_a_openspec(client, monkeypatch):
    """La Fase 2 necesita `npx openspec`; nada más. Bash suelto sería otra cosa."""
    _use_fake_claude(monkeypatch)
    tid = client.post("/tickets", json={"ado_id": 3323, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    log = client.get(f"/tickets/{tid}").json()["log_tail"]
    assert "Bash(npx openspec:*)" in log
    assert " Bash " not in log        # nunca Bash a secas
```

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "design or fase or acotado or sin_fase" -v`
Expected: FAIL. `test_run_design_invoca_el_comando_plan` falla porque el log trae `/ticket-agent:analyze`; `test_fase_declarada_pero_no_ejecutable_da_400` falla con `202` en vez de `400`.

- [ ] **Step 3: Añadir las constantes de fase**

Reemplazar la línea 16 de `app.py`:

```python
PHASES = ["analyze", "design", "implement", "test", "guards", "pr"]  # v1: solo analyze ejecutable
```

por:

```python
PHASES = ["analyze", "design", "implement", "test", "guards", "pr"]

# Declarar una fase no es implementarla. Solo estas dos se pueden lanzar; el resto
# están en PHASES para que la UI sepa que existen, y se rechazan con 400.
PHASE_COMMANDS = {
    "analyze": "/ticket-agent:analyze",
    "design": "/ticket-agent:plan",
}
# En qué deja al ticket una corrida que sale bien.
PHASE_DONE = {"analyze": "analyzed", "design": "planned"}
```

- [ ] **Step 4: Aceptar la fase en el cuerpo de la petición**

En `app.py`, reemplazar:

```python
class RunIn(BaseModel):
    instructions: str | None = None
```

por:

```python
class RunIn(BaseModel):
    instructions: str | None = None
    phase: str = "analyze"  # por defecto, para no romper a quien ya llamaba sin ella
```

- [ ] **Step 5: Derivar el comando y el estado final de la fase**

En `execute_run`, cambiar la firma:

```python
async def execute_run(run_id: int, ticket: dict, instructions: str | None):
```

por:

```python
async def execute_run(run_id: int, ticket: dict, instructions: str | None, phase: str):
```

Dentro, reemplazar:

```python
        prompt = f"/ticket-agent:analyze {ticket['ado_id']}"
```

por:

```python
        prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}"
```

Reemplazar la lista de `--allowedTools`:

```python
            "--allowedTools", "mcp__azure-devops", "Read", "Glob", "Grep", "Task", "Write", "Edit",
```

por:

```python
            # Bash va acotado por comando: la Fase 2 necesita `npx openspec init` y
            # `validate`, y nada más. Un Bash suelto en el repo de un cliente es otra
            # conversación.
            "--allowedTools", "mcp__azure-devops", "Read", "Glob", "Grep", "Task", "Write", "Edit",
            "Bash(npx openspec:*)",
```

Y la última línea de la función:

```python
        set_ticket(ticket["id"], status="analyzed" if ok else "error")
```

por:

```python
        set_ticket(ticket["id"], status=PHASE_DONE[phase] if ok else "error")
```

- [ ] **Step 6: Validar la fase y propagarla al runner**

En `run_ticket`, insertar la validación justo después de comprobar que el ticket existe, y propagar la fase. La función queda así:

```python
@app.post("/tickets/{tid}/run", status_code=202)
def run_ticket(tid: int, body: RunIn, background: BackgroundTasks):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    if body.phase not in PHASE_COMMANDS:
        raise HTTPException(400, f"La fase '{body.phase}' no es ejecutable todavía")
    with db() as c:
        active = c.execute(
            "SELECT 1 FROM runs WHERE ticket_id=? AND status IN ('queued','running')", (tid,)
        ).fetchone()
    if active:
        raise HTTPException(409, "Este ticket ya tiene una corrida activa")
    with db() as c:
        cur = c.execute(
            "INSERT INTO runs(ticket_id, phase, instructions, status) VALUES(?,?,?,'queued')",
            (tid, body.phase, body.instructions),
        )
        run_id = cur.lastrowid
    set_ticket(tid, status="queued")
    background.add_task(execute_run, run_id, dict(t), body.instructions, body.phase)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
```

- [ ] **Step 7: Correr las pruebas nuevas y verificar que pasan**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "design or fase or acotado or sin_fase" -v`
Expected: PASS, 5 pruebas.

- [ ] **Step 8: Correr la suite entera y verificar que no se rompió nada**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: PASS, 24 pruebas (19 previas + 5 nuevas).

- [ ] **Step 9: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): la fase de la corrida decide qué comando se lanza"
```

---

### Task 2: Frontend — el botón Planificar

**Files:**
- Modify: `apps/orchestrator/frontend/src/api.ts:43-47` (`run`)
- Modify: `apps/orchestrator/frontend/src/estado.ts` (etiquetas y regla nueva)
- Modify: `apps/orchestrator/frontend/src/TicketDetail.tsx`
- Modify: `apps/orchestrator/frontend/src/App.tsx:102`

**Interfaces:**
- Consumes: de la Tarea 1, `POST /tickets/{id}/run` con `{instructions, phase}`.
- Produces: `api.run(id: number, instructions?: string, phase?: string)` y `puedePlanificar(t: Ticket): boolean` exportada desde `estado.ts`.

- [ ] **Step 1: `run()` acepta la fase**

En `src/api.ts`, reemplazar:

```ts
  run: (id: number, instructions?: string) =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null }),
    }).then(r => json<Run>(r)),
```

por:

```ts
  run: (id: number, instructions?: string, phase = "analyze") =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null, phase }),
    }).then(r => json<Run>(r)),
```

- [ ] **Step 2: Etiqueta de `planned` y regla de cuándo se puede planificar**

En `src/estado.ts`, añadir a los dos diccionarios:

```ts
const COLOR: Record<string, string> = {
  registrado: "bg-gray-100 text-gray-700",
  corriendo: "bg-blue-100 text-blue-800",
  analizado: "bg-green-100 text-green-800",
  planificado: "bg-violet-100 text-violet-800",
  error: "bg-red-100 text-red-800",
}
const LABEL: Record<string, string> = {
  queued: "registrado", running: "corriendo", analyzed: "analizado",
  planned: "planificado", error: "error",
}
```

Y añadir al final del archivo:

```ts
/** La Fase 2 lee el análisis de la Fase 1: sin análisis no hay nada que planificar.
 *  `planned` también vale — re-planificar es legítimo si cambió el análisis. */
export function puedePlanificar(t: Ticket): boolean {
  return t.status === "analyzed" || t.status === "planned"
}
```

- [ ] **Step 3: El botón en el detalle**

En `src/TicketDetail.tsx`, cambiar el import de `@/estado`:

```ts
import { bloqueo, colorCorrida, duracion, estado, puedePlanificar } from "@/estado"
```

cambiar la firma de `onRun`:

```ts
  onRun: (instructions?: string, phase?: string) => void
```

y añadir el botón dentro del `<div className="ml-auto flex gap-2">`, entre el de correr y el de borrar:

```tsx
          <Button size="sm" variant="secondary"
                  disabled={!!motivo || !puedePlanificar(t)}
                  title={motivo || (puedePlanificar(t) ? undefined
                                    : "Necesita un análisis: corre primero la Fase 1")}
                  onClick={() => onRun(undefined, "design")}>
            Planificar
          </Button>
```

- [ ] **Step 4: Pasar la fase desde App.tsx**

En `src/App.tsx`, reemplazar la línea 102:

```tsx
                        onRun={ins => act(() => api.run(detail.ticket.id, ins))}
```

por:

```tsx
                        onRun={(ins, phase) => act(() => api.run(detail.ticket.id, ins, phase))}
```

- [ ] **Step 5: Mostrar la fase en el historial de corridas**

Con dos fases lanzables, una lista donde todas las corridas se ven iguales deja de
poder leerse. En `src/TicketDetail.tsx`, dentro del `<li>` del historial, añadir la
fase justo después del badge de estado:

```tsx
              <Badge className={colorCorrida(r.status)}>{r.status}</Badge>
              <span className="text-xs text-gray-500">{r.phase}</span>
```

`r.phase` ya viene del backend y ya está en el tipo `Run` de `api.ts:5-8`: no hay que
tocar la API.

- [ ] **Step 6: Verificar tipos y lint**

Run: `npm run build && npm run lint`
Expected: ambos en verde. `npm run build` corre `tsc -b`, así que un `onRun` mal tipado sale aquí.

- [ ] **Step 7: Verificarlo en la UI**

Reiniciar el backend **sin `--reload`** (`.venv/Scripts/uvicorn app:app --port 8000`) y con `npm run dev` abrir un ticket. Comprobar:
- ticket en `queued` → *Planificar* deshabilitado, con el título explicando que falta el análisis;
- ticket en `analyzed` → habilitado;
- con una corrida activa en cualquier proyecto → deshabilitado, con el motivo del bloqueo.

- [ ] **Step 8: Commit**

```bash
git add apps/orchestrator/frontend/src
git commit -m "feat(orchestrator): botón Planificar, disponible solo con análisis hecho"
```

---

### Task 3: La skill `change-planning` y su comando

**Files:**
- Create: `plugins/ticket-agent/skills/change-planning/SKILL.md`
- Create: `plugins/ticket-agent/commands/plan.md`
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json` (`version` → `0.4.0`)

**Interfaces:**
- Consumes: de la Tarea 1, que el runner lance `/ticket-agent:plan <id>` para la fase `design`.
- Produces: el comando `/ticket-agent:plan`, que la Tarea 4 ejecuta de verdad.

- [ ] **Step 1: Crear el comando**

Crear `plugins/ticket-agent/commands/plan.md`:

```markdown
---
description: Convierte el análisis de un work item en un plan de cambios ejecutable, en formato OpenSpec
---

Planifica los cambios del ticket "$ARGUMENTS" de Azure DevOps.

Invoca la skill `ticket-agent:change-planning` y síguela al pie de la letra:
precondiciones (el análisis de la Fase 1 y la carpeta `openspec/`), lectura del
análisis, estudio del patrón en el código, escritura del change en
`openspec/changes/<id>-<slug>/`, validación con `npx openspec validate`, y cierre
según el nivel de autonomía configurado.

No escribas código de producto: el entregable de esta fase es el plan.

Si "$ARGUMENTS" está vacío o no es un número de work item, pide el ID y detente.
```

- [ ] **Step 2: Crear la skill**

Crear `plugins/ticket-agent/skills/change-planning/SKILL.md`:

````markdown
---
name: change-planning
description: Convierte el análisis de un ticket de Azure DevOps en un plan de cambios que otro agente pueda ejecutar - lee docs/tickets/<id>-analysis.md, estudia el patrón en el código y escribe un change de OpenSpec en el repo destino. Usar cuando se pida planificar, diseñar los cambios o preparar la implementación de un ticket ya analizado.
---

# Plan de cambios a partir de un análisis

Produce un plan que **otro agente pueda ejecutar sin volver a investigar**. No
escribas código de producto: el entregable es el change de OpenSpec.

Cuatro reglas de oro:

1. **Lo que no se pudo leer se reporta; jamás se rellena con suposiciones.**
2. **Toda cifra ajena al work item cita su fuente** — `archivo:línea`, commit o comando.
3. **Toda tarea cita el espejo del que se copia, con `archivo:línea`.** "Crear
   `XpoRateCall.cs`" sin decir de dónde se copia no es una tarea, es un deseo.
4. **Lo bloqueado se declara bloqueado, no se planifica alrededor.** Si algo no se
   puede hacer todavía, va a la sección de bloqueos con su motivo y su referencia —
   nunca como una tarea que parece ejecutable y no lo es.

## 1. Configuración

Lee `.claude/ticket-agent.json` del proyecto actual. Si no existe, detente y guía al
usuario para crearlo (plantilla en el README del plugin). Lee `autonomy`.

## 2. Precondiciones

1. **El análisis.** `docs/tickets/<id>-analysis.md` debe existir. Si no está,
   **detente** y dile al usuario que corra primero `/ticket-agent:analyze <id>`.
   No lo generes tú: son dos fases y esta es la segunda.
2. **OpenSpec.** Si no existe la carpeta `openspec/` en la raíz del repo, ejecuta
   `npx openspec init`. Si el comando no está disponible o falla, **detente** y
   repórtalo: sin el CLI no hay validación, y la validación es parte del entregable.

## 3. Lectura del análisis

Lee `docs/tickets/<id>-analysis.md` entero. De ahí salen el alcance, los criterios de
aceptación, el código afectado, las referencias citadas y lo que quedó bloqueado o
sin resolver.

**No vuelvas al MCP de Azure DevOps.** El análisis es la interfaz entre las dos
fases. Si le falta algo que necesitas, eso es un fallo de la Fase 1: regístralo en
"Información faltante" del plan diciendo que el análisis no lo trae, y sigue con lo
que sí puedas planificar.

## 4. Estudio del patrón

Abre los archivos que el análisis señala. Si el cambio consiste en replicar algo que
ya existe (otro carrier, otro proveedor, otro handler), **abre el ejemplo ya resuelto
y léelo**: es el espejo que citarán las tareas. Cada afirmación que hagas sobre el
código se comprueba abriéndolo, no se deduce del nombre del archivo.

Si el prompt te nombra repos adicionales montados con su etiqueta, entran en el
alcance de este paso.

## 5. Escritura del change

Escribe en `openspec/changes/<id>-<slug>/`:

- `<slug>`: el título del work item en kebab-case, sin puntuación, recortado a unas
  5 palabras. Ejemplo: el 3323 *"Carrier API V2 Migration - XPO"* →
  `openspec/changes/3323-carrier-api-v2-migration-xpo/`.

Cuatro archivos:

**`proposal.md`** — por qué, qué y con qué impacto. Cada cambio con la forma:

```markdown
**[Nombre del comportamiento o sección]**
- De: [estado actual]
- A: [estado futuro]
- Motivo: [por qué]
- Impacto: [rompe o no rompe, a quién afecta]
```

**`tasks.md`** — la checklist ejecutable. Cada tarea lleva destino, espejo con
líneas, y cómo se comprueba:

```markdown
- [ ] Crear `ruta/al/Destino.cs`
      Espejo: `ruta/al/Ejemplo.cs:1-140`
      Reusar: `ruta/a/lo/que/ya/existe.cs`
      Comprobación: [qué tiene que pasar para dar la tarea por buena]
```

Y una sección propia, de primer nivel, para lo que **no** se puede hacer:

```markdown
## Bloqueado

- **[Qué]** — [por qué no se puede todavía], según [referencia que lo respalda].
  Desbloquea: [qué haría falta].
```

**`design.md`** — las decisiones técnicas y sus alternativas descartadas. Si no hay
ninguna decisión que tomar, dilo en una línea en vez de rellenar.

**`specs/<capability>/spec.md`** — el estado futuro de la capacidad afectada.
`<capability>` es la **capacidad del sistema**, no el ticket: es la carpeta que
OpenSpec reutiliza entre cambios. Si ya existe una en `openspec/specs/` que encaje,
usa esa; no inventes una nueva por cada ticket.

## 6. Validación

Ejecuta `npx openspec validate`. Si falla, corrige y vuelve a validar. **A la segunda
validación fallida, para**: deja el change escrito y reporta qué no pasa. Un change
inválido que se puede revisar vale más que ninguno.

## 7. Cierre según autonomía

- `supervised`: resume en el chat qué se planificó, qué quedó bloqueado y qué falta;
  no toques el work item.
- `autonomous`: igual, y además señala explícitamente qué decisiones tomaste solo.

En ambos casos, la última línea del resumen dice dónde quedó el change.

## Manejo de errores

- Falta el análisis → detente y pide la Fase 1.
- `npx` no disponible o `openspec init` falla → detente y repórtalo.
- El análisis existe pero no trae el código afectado → planifica lo que puedas y
  registra el hueco señalando que viene de la Fase 1.
- No encuentras un espejo para una tarea → dilo en la tarea. Una tarea sin espejo es
  una tarea que el implementador tendrá que investigar, y eso hay que avisarlo.
````

- [ ] **Step 3: Subir la versión del plugin**

En `plugins/ticket-agent/.claude-plugin/plugin.json`, cambiar `"version": "0.3.0"` por `"version": "0.4.0"`.

Sin esto el cambio no llega al plugin instalado por más que se commitee: la versión es la clave de cache de `claude plugin update`.

- [ ] **Step 4: Validar el plugin**

Run: `claude plugin validate .` desde la raíz del repo.
Expected: sin errores. Si se queja del `name` de la skill, comprobar que la carpeta se llama igual que el `name` del frontmatter (`change-planning`).

- [ ] **Step 5: Commit**

```bash
git add plugins/ticket-agent
git commit -m "feat(ticket-agent): skill change-planning — del análisis al change de OpenSpec"
```

- [ ] **Step 6: Actualizar el plugin instalado**

Run: `claude plugin update ticket-agent@autonomous-skill-hub`
Expected: trae la 0.4.0. Comprobar con:

```bash
ls ~/.claude/plugins/cache/autonomous-skill-hub/ticket-agent/
diff ~/.claude/plugins/cache/autonomous-skill-hub/ticket-agent/0.4.0/skills/change-planning/SKILL.md \
     plugins/ticket-agent/skills/change-planning/SKILL.md
```

Expected: existe la carpeta `0.4.0` y el `diff` no imprime nada.

---

### Task 4: Validación de punta a punta sobre el 3323

Esta tarea no escribe código: ejerce lo construido y decide si la skill sirve. Es el equivalente a lo que se hizo con el 3322 en la Fase 1.

**Files:**
- Ninguno del hub. Escribe en `D:/Companies/ProvidenceSolutions/ProvidenceTMSTenant`.

**Interfaces:**
- Consumes: las tres tareas anteriores, ya commiteadas y con el plugin actualizado.
- Produces: el veredicto sobre si la skill necesita otro ajuste.

- [ ] **Step 1: Comprobar que el backend sirve el código actual**

El backend no recarga solo y ya ha servido código viejo tres veces. Comprobar que el proceso que escucha en el 8000 arrancó **después** de la última modificación de `app.py`:

```bash
powershell -NoProfile -Command "$c = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess; Get-CimInstance Win32_Process -Filter \"ProcessId=$c\" | Select-Object CreationDate,CommandLine | Format-List"
```

Expected: `CreationDate` posterior al `LastWriteTime` de `app.py`, y `CommandLine` **sin** `--reload`. Si no, matar el proceso y relanzar `.venv/Scripts/uvicorn app:app --port 8000`.

- [ ] **Step 2: Dar de alta el ticket 3323**

El 3323 es solo backend, así que el proyecto debe tener `ProvidenceTMSTenant` como repo **principal** — el análisis se escribe en el cwd de la corrida. Verificar en la UI (o en `GET /projects`) que es así antes de crear el ticket, y crearlo desde la UI.

Expected: el ticket queda en `queued` con `repo_path` = `.../ProvidenceTMSTenant`.

- [ ] **Step 3: Correr la Fase 1**

Su análisis no existe todavía. Desde la UI, botón *Correr análisis*.

Expected: estado `analyzed` y `docs/tickets/3323-analysis.md` escrito en `ProvidenceTMSTenant`. Comprobar que el análisis recogió el Feature padre **#3319** — ahí vive la Definition of Done y el inventario. Si no lo abrió, la Fase 2 no tendrá material y el fallo es de la Fase 1.

- [ ] **Step 4: Correr la Fase 2**

Botón *Planificar*.

Expected: estado `planned`, sin excepciones en el log.

- [ ] **Step 5: Los tres criterios de aceptación**

```bash
cd D:/Companies/ProvidenceSolutions/ProvidenceTMSTenant
npx openspec validate
ls openspec/changes/
```

1. `npx openspec validate` pasa.
2. Las tareas de `tasks.md` citan un espejo concreto con líneas — `AbfRateCall.cs:<líneas>` — y no "sigue el patrón de ABF".
3. **`GetDocs` aparece bajo `## Bloqueado`, no como tarea.** El hallazgo 4 del Feature #3319 dice que no existe ningún `UseV2(..., CarrierVerb.GetDocs)` en el gateway: el verbo no se puede migrar aunque el ticket lo pida.

El punto 3 es el examen. Mide lo mismo que midió leer de verdad `ProvidenceTMSTenant` en la Fase 1: si el agente admite un hueco o lo tapa.

- [ ] **Step 6: Contar lecturas del espejo en el log**

Igual que se hizo con el 3322, contar en el log de la corrida las invocaciones de `Read` sobre `PTMS.CarrierGateway/Carriers/Abf/`. Una skill que escribe "espejo: `AbfRateCall.cs:1-140`" **sin haber abierto el archivo** está inventando el número de líneas.

Expected: al menos una lectura por cada archivo espejo citado en `tasks.md`.

- [ ] **Step 7: Veredicto**

Si los tres criterios pasan, la Fase 2 queda aceptada con n=1 y hace falta un segundo ticket para confirmarla — lo aprendido en la Fase 1 fue justo eso.

Si falla el punto 3, el ajuste va en la regla de oro 4 de `SKILL.md`, y **hay que subir `version` a 0.4.1** y re-correr. Si falla el punto 2, el ajuste va en la sección 4 (estudio del patrón).

- [ ] **Step 8: Actualizar el estado del proyecto**

Actualizar `docs/STATUS.md`: la fila de la Fase 2 en el roadmap, la decisión de adoptar OpenSpec con su porqué, lo aprendido en esta corrida, y marcar los checkboxes de este plan. Actualizar también la sección "Cómo retomar en una sesión nueva".

```bash
git add docs/STATUS.md docs/superpowers/plans/2026-08-09-fase-2-plan-de-cambios.md
git commit -m "docs: Fase 2 validada sobre el 3323"
```
