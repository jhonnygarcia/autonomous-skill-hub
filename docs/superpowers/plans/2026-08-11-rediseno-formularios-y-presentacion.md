# Rediseño de formularios y presentación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la UI del orchestrator conteste cuando el usuario decide —rutas validadas al salir del campo, botones que dicen por qué no, borrados que preguntan, corridas largas que muestran avance— sin agregar una sola dependencia.

**Architecture:** Backend FastAPI de un archivo (`app.py`, SQLite sin ORM); frontend React+Vite con vistas conmutadas por `useState`, sin router. El formulario de proyecto se muda de un bloque expandido dentro de una `Card` a una vista dedicada. Dos endpoints nuevos y dos columnas/campos nuevos en payloads existentes. El guardián de rutas del visor de artefactos se extrae a función para que el título del ticket y el contador de progreso lo reusen.

**Tech Stack:** Python 3 + FastAPI + SQLite + pytest. React 19 + TypeScript + Vite + Tailwind + shadcn (button, card, badge, input, textarea — no se agrega ninguno más). oxlint.

**Spec:** `docs/superpowers/specs/2026-08-11-rediseno-formularios-y-presentacion-design.md`

## Global Constraints

- **Cero dependencias nuevas.** Ni `sonner`, ni `dropdown-menu`, ni `alert-dialog`, ni `react-hook-form`, ni `zod`, ni componentes nuevos de shadcn, ni framework de tests de frontend. `package.json` y `requirements.txt` no se tocan.
- **Idioma** (regla del `CLAUDE.md`): código, comentarios y docstrings en **inglés**; textos que lee el usuario en el navegador (labels, `HTTPException(detail=...)`, mensajes de error) en **español**. Los literales de contrato (`HUELLA`, `/modelos`, `/artefacto?ruta=`, claves JSON como `fases`) no se traducen en ninguna dirección.
- **No se toca:** `STAMP_RE`, `split_reserve`, `read_stamp`, `deny_push.py`, `settings_for`, `prepare_branch`, `prepare_repos`, `check_clean`, `RUN_LOCK`, `Models.tsx`.
- **El frontend no tiene tests.** No hay vitest ni jest y no se agregan (violaría la restricción de dependencias). Las tareas de frontend cierran con `npm run build` + `npm run lint` verdes y una verificación manual concreta y descrita.
- **El backend no se arranca con `--reload`** en Windows: deja procesos huérfanos reteniendo el puerto 8000 y sirve código viejo sin avisar. Reiniciar a mano y confirmar que el proceso arrancó después del último cambio a `app.py`.
- **Cada test de backend se verifica mutando el código.** Un test que sigue verde después de romper a propósito lo que dice proteger es un placebo; este proyecto ya encontró nueve.
- **Comandos:** backend desde `apps/orchestrator/backend/`: `.venv/Scripts/python -m pytest tests/ -v`. Frontend desde `apps/orchestrator/frontend/`: `npm run build`, `npm run lint`.

---

# Fase 1 — Proyectos

## Task 1: Endpoint `POST /rutas/validar`

**Files:**
- Modify: `apps/orchestrator/backend/app.py:236-241` (`check_dirs`), y agregar el endpoint junto a los otros de proyectos (después de `delete_project`, `app.py:524-529`)
- Test: `apps/orchestrator/backend/tests/test_app.py` (agregar al final)

**Interfaces:**
- Consumes: nada.
- Produces: `is_repo_dir(path: str) -> bool` y la ruta `POST /rutas/validar` con cuerpo `{"ruta": str}` que devuelve `{"existe": bool}`. La Task 4 la consume desde el frontend.

- [x] **Step 1: Write the failing tests**

Agregar al final de `tests/test_app.py`:

```python
def test_existing_path_is_valid(client, tmp_path):
    r = client.post("/rutas/validar", json={"ruta": (tmp_path / "repo").as_posix()})
    assert r.status_code == 200
    assert r.json() == {"existe": True}


def test_nonexistent_path_is_invalid(client, tmp_path):
    r = client.post("/rutas/validar", json={"ruta": (tmp_path / "no-existe").as_posix()})
    assert r.json() == {"existe": False}


def test_a_file_is_not_a_repo(client, tmp_path):
    f = tmp_path / "archivo.txt"
    f.write_text("x", encoding="utf-8")
    r = client.post("/rutas/validar", json={"ruta": f.as_posix()})
    assert r.json() == {"existe": False}


def test_absurd_path_does_not_blow_up(client):
    """A null byte makes `Path.is_dir()` raise instead of returning False. The form
    sends whatever the user pasted, so this reaches the endpoint for real."""
    r = client.post("/rutas/validar", json={"ruta": "x\x00y"})
    assert r.status_code == 200
    assert r.json() == {"existe": False}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k path -v`
Expected: los cuatro FAIL con `404 != 200` (la ruta no existe todavía).

- [x] **Step 3: Write the implementation**

Reemplazar `check_dirs` (`app.py:236-241`) por:

```python
def is_repo_dir(path: str) -> bool:
    """Whether a path from a form points at a real directory.

    `is_dir()` raises instead of returning False on a null byte or an absurdly long
    path, and this value comes straight from a text field the user pasted into.
    """
    try:
        return Path(path).is_dir()
    except (ValueError, OSError):
        return False


def check_dirs(*paths: str) -> None:
    """Paths arrive from a form and end up as cwd and --add-dir of a subprocess: a typo
    here blows up inside the CLI with an unreadable error."""
    bad = [p for p in paths if not is_repo_dir(p)]
    if bad:
        raise HTTPException(400, "No existen o no son directorios: " + ", ".join(bad))
```

Agregar el modelo junto a los otros `BaseModel` (después de `ProjectIn`, `app.py:432-436`):

```python
class RutaIn(BaseModel):
    ruta: str
```

Y el endpoint después de `delete_project` (`app.py:529`):

```python
@app.post("/rutas/validar")
def validar_ruta(body: RutaIn):
    """The same check `check_dirs` does, exposed on its own so the project form can
    answer at blur time instead of at save time.

    It does NOT replace `check_dirs`: saving keeps validating, and that one stays the
    authoritative check. This endpoint is a courtesy, so a failure here never blocks a
    save — see the frontend's `catch` in `ProjectForm`.
    """
    return {"existe": is_repo_dir(body.ruta)}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: los 4 nuevos PASS y los existentes siguen PASS (`check_dirs` cambió de cuerpo pero no de contrato).

- [x] **Step 5: Verify the tests aren't placebos (mutation)**

Cambiar temporalmente `is_repo_dir` a `return True`.
Run: `.venv/Scripts/python -m pytest tests/test_app.py -k path -v`
Expected: `test_nonexistent_path_is_invalid`, `test_a_file_is_not_a_repo` y `test_absurd_path_does_not_blow_up` en **rojo**. Si alguno sigue verde, el test no prueba nada. Revertir la mutación.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(backend): la ruta se puede validar sin guardar el proyecto"
```

---

## Task 2: `ConfirmDialog` sobre `<dialog>` nativo

**Files:**
- Create: `apps/orchestrator/frontend/src/ConfirmDialog.tsx`

**Interfaces:**
- Consumes: `@/components/ui/button`.
- Produces: `<ConfirmDialog open title body? confirmLabel? onConfirm onCancel />`. Lo consumen la Task 4 (descartar cambios), la Task 5 (borrar proyecto) y la Task 8 (borrar ticket).

- [x] **Step 1: Write the component**

```tsx
import { useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"

/**
 * Confirmation on top of the native `<dialog>`.
 *
 * shadcn's `alert-dialog` is not installed on purpose: `showModal()` already gives a
 * focus trap, Escape to close, `::backdrop` and `inert` on the rest of the page — all
 * of which Radix reimplements for browsers this app never runs in. It's a local Vite
 * app; the platform feature is the correct answer here, not the shortcut.
 *
 * React state is the single source of truth: the dialog's own `cancel` event (Escape)
 * is prevented and routed back through `onCancel`, so the element never closes behind
 * the state's back.
 */
export function ConfirmDialog({
  open, title, body, confirmLabel = "Borrar", onConfirm, onCancel,
}: {
  open: boolean
  title: string
  body?: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onCancel={e => { e.preventDefault(); onCancel() }}
      className="max-w-sm rounded-lg border border-border bg-background p-0
                 text-foreground backdrop:bg-black/40"
    >
      <div className="space-y-3 p-4">
        <p className="text-sm font-semibold">{title}</p>
        {body && <p className="text-sm text-muted-foreground">{body}</p>}
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onCancel}>Cancelar</Button>
          <Button size="sm" variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  )
}
```

- [x] **Step 2: Verify build and lint**

Run desde `apps/orchestrator/frontend/`: `npm run build && npm run lint`
Expected: ambos verdes. El componente todavía no lo usa nadie — eso es esperado en este paso.

- [x] **Step 3: Commit**

```bash
git add apps/orchestrator/frontend/src/ConfirmDialog.tsx
git commit -m "feat(ui): confirmacion sobre <dialog> nativo, sin traer Radix"
```

---

## Task 3: `RepoTable` extraída de `ProjectHeader`

**Files:**
- Create: `apps/orchestrator/frontend/src/RepoTable.tsx`
- Modify: `apps/orchestrator/frontend/src/ProjectHeader.tsx:17-37`

**Interfaces:**
- Consumes: el tipo `Repo` de `@/api`.
- Produces: `<RepoTable repos={Repo[]} />`. La consume la Task 5 (lista de proyectos).

- [x] **Step 1: Create the component**

```tsx
import type { Repo } from "@/api"

/**
 * The repo table that used to live inside `ProjectHeader`.
 *
 * It gets extracted because the project list needs the same one: today that
 * information travels in a `title=` attribute, which only appears on hover and is
 * therefore undiscoverable — the third rule of the spec.
 */
export function RepoTable({ repos }: { repos: Repo[] }) {
  // primary first: that's where the agent runs and where it writes
  const sorted = [...repos].sort((a, b) => Number(b.primary) - Number(a.primary))
  return (
    <table className="text-xs">
      <tbody>
        {sorted.map(r => (
          <tr key={r.path}>
            <td className="pr-3 align-top text-muted-foreground">
              {r.label || "sin descripción"}
              {r.primary && <span className="ml-1 text-muted-foreground/70">· principal</span>}
            </td>
            <td className="font-mono text-foreground">{r.path}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

- [x] **Step 2: Use it from `ProjectHeader`**

Reemplazar `ProjectHeader.tsx` completo por:

```tsx
import type { Project } from "@/api"
import { RepoTable } from "@/RepoTable"

/**
 * The repos the agent will mount need to be in view RIGHT WHERE launching a
 * ticket is decided — not hidden in the form where they were configured.
 */
export function ProjectHeader({ project }: { project: Project }) {
  return (
    <div className="space-y-2">
      <div>
        <h2 className="text-xl font-semibold">{project.name}</h2>
        <p className="text-sm text-muted-foreground">{project.org}/{project.project}</p>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-foreground/70">Repos que verá el agente</p>
        <RepoTable repos={project.repos} />
        {project.repos.length === 1 && (
          <p className="mt-1 text-xs text-muted-foreground/70">
            Solo un repo. Se añaden más al editar el proyecto.
          </p>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Verify build, lint and the screen**

Run: `npm run build && npm run lint`
Expected: verdes.

Verificación manual: con el backend corriendo, abrir `http://localhost:5173`, elegir un proyecto y confirmar que la tabla de repos del header se ve **exactamente igual que antes** (etiqueta a la izquierda, ruta monoespaciada a la derecha, `· principal` en el primero). Es una extracción, no un rediseño: cualquier diferencia visual es un error.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src/RepoTable.tsx apps/orchestrator/frontend/src/ProjectHeader.tsx
git commit -m "refactor(ui): la tabla de repos sale de ProjectHeader para poder reusarse"
```

---

## Task 4: `ProjectForm`, la vista dedicada

**Files:**
- Create: `apps/orchestrator/frontend/src/ProjectForm.tsx`
- Modify: `apps/orchestrator/frontend/src/api.ts:47-79` (agregar `validatePath`)

**Interfaces:**
- Consumes: `api.saveProject`, `api.validatePath` (nuevo), `ConfirmDialog` (Task 2), `Button`, `Input`.
- Produces: `<ProjectForm initial={Project | null} onSaved={(name: string) => void} onCancel={() => void} />`. La consume la Task 5 desde `App.tsx`. Los helpers `newProject()` y `validate()` quedan **locales del módulo**: nadie fuera del archivo los usa, y exportarlos dispara `react/only-export-components` en oxlint, que sube la línea base de warnings sin comprar nada.

- [x] **Step 1: Add `validatePath` to the API client**

En `api.ts`, dentro del objeto `api`, después de `removeProject` (línea 55):

```ts
  /** Does this path exist on disk? A courtesy for the form: saving validates again,
   *  and that one is the authoritative check. */
  validatePath: (ruta: string) =>
    fetch("/api/rutas/validar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ruta }),
    }).then(r => json<{ existe: boolean }>(r)).then(x => x.existe),
```

- [x] **Step 2: Write the component**

```tsx
import { useEffect, useRef, useState } from "react"
import { api, type Project, type Repo } from "@/api"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Input } from "@/components/ui/input"

const EMPTY: Project = {
  name: "", org: "", project: "",
  repos: [{ path: "", label: "", primary: true }],
}

// Module-local, both of them: nothing outside this file uses them, and exporting a
// non-component alongside a component trips oxlint's `react/only-export-components`.
const newProject = (): Project => ({ ...EMPTY, repos: [{ ...EMPTY.repos[0] }] })

/**
 * What's missing, per field. Replaces the four-condition `disabled` that named none of
 * them: the button stays alive and pressing it paints what's missing.
 */
function validate(f: Project): Record<string, string> {
  const e: Record<string, string> = {}
  if (!f.name.trim()) e.name = "Ponle un nombre al proyecto."
  if (!f.org.trim()) e.org = "Falta la organización de Azure DevOps."
  if (!f.project.trim()) e.project = "Falta el proyecto de Azure DevOps."
  if (!f.repos.some(r => r.path.trim())) e.repos = "Necesitas al menos un repo con su ruta."
  // Blank rows get dropped on save. If the one marked primary is among them, the payload
  // arrives with no primary at all: the backend answers 400 (`split_repos`) with a banner
  // that doesn't say which row to fix — a round trip to learn something the form already
  // knows. Reachable by filling the second row and forgetting to move the radio.
  else if (!f.repos.some(r => r.primary && r.path.trim())) {
    e.repos = "El repo marcado como principal necesita su ruta."
  }
  return e
}

function Field({ id, label, hint, error, children }: {
  id: string; label: string; hint?: string; error?: string; children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className="text-xs font-medium">{label}</label>
      {hint && <span className="ml-1 text-xs text-muted-foreground">{hint}</span>}
      <div className="mt-1">{children}</div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  )
}

export function ProjectForm({ initial, onSaved, onCancel, onDirtyChange }: {
  /** `null` = creating. Otherwise, the project as it is saved. */
  initial: Project | null
  onSaved: (name: string) => void
  onCancel: () => void
  /** Reported upward so the sidebar can route its navigation through the same
   *  confirmation this component already uses for Cancelar and Escape. Without it,
   *  clicking another project unmounts the form and discards what was typed — the
   *  guard exists, and the navigation walks around it. */
  onDirtyChange?: (dirty: boolean) => void
}) {
  const original = initial?.name ?? null
  const [form, setForm] = useState<Project>(
    initial ? { ...initial, repos: initial.repos.map(r => ({ ...r })) } : newProject())
  const [errors, setErrors] = useState<Record<string, string>>({})
  // path → exists. Keyed by the string and not by the row index on purpose: removing a
  // row would otherwise shift every verdict below it onto the wrong path.
  const [paths, setPaths] = useState<Record<string, boolean>>({})
  const [actionError, setActionError] = useState("")
  const [confirmLeave, setConfirmLeave] = useState(false)
  const snapshot = useRef(JSON.stringify(initial ?? newProject()))

  const dirty = JSON.stringify(form) !== snapshot.current
  const patch = (fn: (rs: Repo[]) => Repo[]) => setForm(f => ({ ...f, repos: fn(f.repos) }))

  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  // Clears the flag when the form goes away, so a stale `true` can't make the next
  // navigation prompt about changes that no longer exist. Its own effect and not a
  // cleanup on the one above: that one re-runs on every `dirty` change, and clearing
  // there would blink the flag off and on.
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange])

  /** On blur, not debounced while typing: a path gets pasted whole, and validating
   *  mid-word produces a run of reds that mean nothing. */
  const checkPath = (ruta: string) => {
    const v = ruta.trim()
    if (!v || v in paths) return
    api.validatePath(v)
      .then(existe => setPaths(p => ({ ...p, [v]: existe })))
      // No mark and no block: the save validates again and that is the authoritative
      // check. A courtesy endpoint being down must not stop the user from saving.
      .catch(() => {})
  }

  const save = () => {
    const e = validate(form)
    setErrors(e)
    if (Object.keys(e).length) {
      // `campo-repos` sits on the PRIMARY row's path input, not on the wrapping <div>:
      // both `repos` errors are about that row, and a <div> without tabindex silently
      // refuses focus, which made this a no-op for the most reachable failure.
      document.getElementById(`campo-${Object.keys(e)[0]}`)?.focus()
      return
    }
    setActionError("")
    // blank rows are dropped here; the backend rejects paths that don't exist
    api.saveProject({ ...form, repos: form.repos.filter(r => r.path.trim()) }, original)
      .then(p => onSaved(p.name))
      .catch(err => setActionError(String(err)))
  }

  const leave = () => (dirty ? setConfirmLeave(true) : onCancel())

  return (
    <div className="space-y-4">
      <button onClick={leave}
              className="rounded text-sm text-muted-foreground hover:text-foreground
                         hover:underline focus-visible:outline-none focus-visible:ring-2
                         focus-visible:ring-ring/50">
        ← Proyectos {original ? `/ ${original}` : "/ nuevo"}
      </button>

      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">
          {original ? "Editar proyecto" : "Nuevo proyecto"}
        </h2>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={leave}>Cancelar</Button>
          <Button size="sm" onClick={save}>Guardar</Button>
        </div>
      </div>

      {actionError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40
                        bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <span className="flex-1">{actionError}</span>
          <button onClick={() => setActionError("")} aria-label="Descartar el error"
                  className="rounded px-1 focus-visible:outline-none focus-visible:ring-2
                             focus-visible:ring-ring/50">✕</button>
        </div>
      )}

      <Field id="campo-name" label="Nombre del proyecto" error={errors.name}
             hint="como quieras llamarlo tú; puedes cambiarlo">
        <Input id="campo-name" placeholder="p. ej. TMS" value={form.name}
               onChange={e => setForm({ ...form, name: e.target.value })} />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field id="campo-org" label="Organización de Azure DevOps" error={errors.org}>
          <Input id="campo-org" placeholder="ProvidenceSolutions" value={form.org}
                 onChange={e => setForm({ ...form, org: e.target.value })} />
        </Field>
        <Field id="campo-project" label="Proyecto de Azure DevOps" error={errors.project}
               hint="donde viven los tickets">
          <Input id="campo-project" placeholder="ProvidenceTMS" value={form.project}
                 onChange={e => setForm({ ...form, project: e.target.value })} />
        </Field>
      </div>

      <div>
        <p className="text-xs font-medium">Repos que verá el agente</p>
        <p className="mb-3 text-xs text-muted-foreground">
          El marcado como <strong>principal</strong> es donde corre el agente y donde se
          escribe el análisis; los demás los lee. La descripción viaja al prompt y es lo
          que le dice cuándo mirar en cada uno.
        </p>

        <div className="space-y-4">
          {form.repos.map((r, i) => {
            const key = r.path.trim()
            // `undefined` = not visited yet. Absence is not a verdict.
            const exists = key in paths ? paths[key] : undefined
            return (
              <div key={i} className="rounded-md border border-border p-3">
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input type="radio" name="principal" checked={r.primary}
                           onChange={() => patch(rs => rs.map((x, j) => ({ ...x, primary: j === i })))} />
                    {r.primary ? <strong>principal</strong> : <span className="text-muted-foreground">principal</span>}
                  </label>
                  {exists === true && <span className="text-xs text-emerald-600 dark:text-emerald-500">✓ existe</span>}
                  {exists === false && <span className="text-xs text-destructive">✗ no existe</span>}
                  <Button size="sm" variant="ghost" className="ml-auto"
                          disabled={form.repos.length === 1}
                          onClick={() => patch(rs => {
                            const remaining = rs.filter((_, j) => j !== i)
                            // if the primary one leaves, the first one left takes over
                            return remaining.some(x => x.primary)
                              ? remaining
                              : remaining.map((x, j) => ({ ...x, primary: j === 0 }))
                          })}>
                    ✕ quitar
                  </Button>
                </div>

                <Input className="mt-2 font-mono" placeholder="D:/ruta/al/repo" value={r.path}
                       id={r.primary ? "campo-repos" : undefined}
                       aria-label="Ruta del repo"
                       onBlur={e => checkPath(e.target.value)}
                       onChange={e => patch(rs =>
                         rs.map((x, j) => j === i ? { ...x, path: e.target.value } : x))} />
                {exists === false && (
                  <p className="mt-1 text-xs text-destructive">
                    ⚠ No encontré esa carpeta en disco.
                  </p>
                )}

                <Input className="mt-2" placeholder="frontend, backend, app de auth…"
                       aria-label="Descripción del repo" value={r.label}
                       onChange={e => patch(rs =>
                         rs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
              </div>
            )
          })}
        </div>
        {errors.repos && <p className="mt-1 text-xs text-destructive">{errors.repos}</p>}

        <Button size="sm" variant="outline" className="mt-2"
                onClick={() => patch(rs => [...rs, { path: "", label: "", primary: false }])}>
          + Agregar repo
        </Button>
      </div>

      <ConfirmDialog open={confirmLeave} title="Hay cambios sin guardar."
                     body="Si sales ahora se pierden." confirmLabel="Descartar"
                     onConfirm={() => { setConfirmLeave(false); onCancel() }}
                     onCancel={() => setConfirmLeave(false)} />
    </div>
  )
}
```

- [x] **Step 3: Verify build and lint**

Run: `npm run build && npm run lint`
Expected: verdes. Todavía no está enganchado a `App.tsx` — eso es la Task 5.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src/ProjectForm.tsx apps/orchestrator/frontend/src/api.ts
git commit -m "feat(ui): el formulario de proyecto contesta al salir de cada campo"
```

---

## Task 5: Enganchar la vista, dejar `Projects` como lista

**Files:**
- Modify: `apps/orchestrator/frontend/src/App.tsx` (completo)
- Modify: `apps/orchestrator/frontend/src/Projects.tsx` (completo)
- Modify: `apps/orchestrator/frontend/src/Sidebar.tsx:31`

**Interfaces:**
- Consumes: `ProjectForm` (Task 4), `ConfirmDialog` (Task 2), `RepoTable` (Task 3).
- Produces: la vista `{ kind: "projectForm"; name: string | null }` en el `View` union de `App.tsx`.

- [x] **Step 1: Rewrite `Projects.tsx` as a list only**

```tsx
import { useState } from "react"
import { api, type Project } from "@/api"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/ConfirmDialog"
import { RepoTable } from "@/RepoTable"

export function Projects({ projects, onEdit, onNew, onChange }: {
  projects: Project[]
  onEdit: (name: string) => void
  onNew: () => void
  onChange: () => void
}) {
  const [toDelete, setToDelete] = useState<string | null>(null)
  const [error, setError] = useState("")

  const remove = (name: string) => {
    setToDelete(null)
    api.removeProject(name).then(onChange).catch(e => setError(String(e)))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">Proyectos</h2>
        <Button size="sm" className="ml-auto" onClick={onNew}>+ Nuevo proyecto</Button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40
                        bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <span className="flex-1">{error}</span>
          <button onClick={() => setError("")} aria-label="Descartar el error"
                  className="rounded px-1 focus-visible:outline-none focus-visible:ring-2
                             focus-visible:ring-ring/50">✕</button>
        </div>
      )}

      {projects.map(p => (
        <div key={p.name} className="rounded-md border border-border p-3">
          <div className="flex items-center gap-2">
            <span className="font-medium">{p.name}</span>
            <div className="ml-auto flex items-center gap-3">
              <Button size="sm" variant="outline" onClick={() => onEdit(p.name)}>Editar</Button>
              {/* Separated from `Editar` and muted: it used to sit right next to it,
                  same size and same weight, and it executed on the first click. */}
              <Button size="sm" variant="ghost" className="text-muted-foreground"
                      onClick={() => setToDelete(p.name)}>
                Borrar
              </Button>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">{p.org}/{p.project}</p>
          {/* The repos used to live in a `title=`: visible only on hover, and therefore
              undiscoverable. */}
          <div className="mt-2"><RepoTable repos={p.repos} /></div>
        </div>
      ))}

      {projects.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Sin proyectos. Agrega uno para poder encolar tickets.
        </p>
      )}

      <ConfirmDialog open={!!toDelete} title={`¿Borrar el proyecto "${toDelete}"?`}
                     body="Los tickets ya creados no se rompen: cada uno guardó su propia
                           copia de los datos. Pero no vas a poder encolar nuevos."
                     onConfirm={() => toDelete && remove(toDelete)}
                     onCancel={() => setToDelete(null)} />
    </div>
  )
}
```

- [x] **Step 2: Rewrite `App.tsx`**

```tsx
import { useEffect, useState } from "react"
import { api, type ActiveRun, type Project, type Ticket, type TicketDetail as Detail } from "@/api"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Models } from "@/Models"
import { ProjectForm } from "@/ProjectForm"
import { ProjectHeader } from "@/ProjectHeader"
import { Projects } from "@/Projects"
import { Sidebar } from "@/Sidebar"
import { TicketDetail } from "@/TicketDetail"
import { TicketList } from "@/TicketList"

// Four views switched by hand. No router: it's a single-user local app and
// `react-router` would be a dependency for nothing.
type View =
  | { kind: "project" }
  | { kind: "ticket"; id: number }
  | { kind: "settings" }
  // `name: null` = creating. The form used to be a block expanded inside the settings
  // card, which is why `+ Nuevo` had to jump to another view and open it via a prop.
  | { kind: "projectForm"; name: string | null }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [view, setView] = useState<View>({ kind: "project" })
  // User-initiated actions and the project load land here. What does NOT is the 3-second
  // poll: it retries on its own, and a banner for a transient blip is noise that trains
  // you to ignore the banner. Loading the projects is different — it runs on mount and
  // after saving, and failing silently there leaves an empty app with no explanation.
  const [error, setError] = useState("")
  // The project form reports whether it has unsaved changes, and a navigation requested
  // while it does is held here until the user confirms. The form guards its own Cancelar
  // and Escape; without this the sidebar routes around that guard and discards what was
  // typed — same situation, three ways out, and only two of them used to ask.
  const [formDirty, setFormDirty] = useState(false)
  const [pendingNav, setPendingNav] = useState<(() => void) | null>(null)

  const navigate = (go: () => void) => {
    if (view.kind === "projectForm" && formDirty) setPendingNav(() => go)
    else go()
  }

  // `select` is sent by the form after saving, so a rename doesn't change the
  // active project out from under it (the old name is no longer in the list).
  const refreshProjects = (select?: string) =>
    api.projects().then(ps => {
      setProjects(ps)
      setCurrent(c => {
        const wanted = select ?? c
        return ps.some(p => p.name === wanted) ? wanted : (ps[0]?.name ?? null)
      })
    }).catch(e => setError(String(e)))

  const refresh = () => {
    api.tickets().then(setTickets).catch(() => {})
    api.activeRun().then(setActiveRun).catch(() => {})
    if (view.kind === "ticket") api.detail(view.id).then(setDetail).catch(() => setDetail(null))
  }

  useEffect(() => { refreshProjects() }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.kind, view.kind === "ticket" ? view.id : null])

  const project = projects.find(p => p.name === current) ?? null
  // The ticket stores the ADO project, not the catalog key.
  // ponytail: today they match; if they ever diverge, tickets need a `project_key`.
  const myTickets = project ? tickets.filter(t => t.project === project.project) : []

  const act = (fn: () => Promise<unknown>) => {
    setError("")
    return fn().then(refresh).catch(e => setError(String(e)))
  }

  const addTicket = (adoId: number) =>
    project && act(() => api.create(adoId, project.name))

  const open = (id: number) => { setDetail(null); setView({ kind: "ticket", id }) }
  const back = () => { setDetail(null); setView({ kind: "project" }) }
  const editing = view.kind === "projectForm" ? view.name : null

  return (
    <div className="mx-auto flex w-full max-w-[92rem] gap-6 p-6">
      <Sidebar projects={projects} current={current}
               settings={view.kind === "settings" || view.kind === "projectForm"}
               onSelect={n => navigate(() => { setCurrent(n); back() })}
               onSettings={() => navigate(() => setView({ kind: "settings" }))} />

      <main className="min-w-0 flex-1 space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40
                          bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="flex-1">{error}</span>
            <button onClick={() => setError("")} aria-label="Descartar el error"
                    className="rounded px-1 focus-visible:outline-none focus-visible:ring-2
                               focus-visible:ring-ring/50">✕</button>
          </div>
        )}

        {view.kind === "settings" && (
          <>
            <Projects projects={projects}
                      onEdit={name => setView({ kind: "projectForm", name })}
                      onNew={() => setView({ kind: "projectForm", name: null })}
                      onChange={() => refreshProjects()} />
            <Models />
          </>
        )}

        {view.kind === "projectForm" && (
          <ProjectForm initial={projects.find(p => p.name === editing) ?? null}
                       onDirtyChange={setFormDirty}
                       onSaved={name => { refreshProjects(name); setView({ kind: "settings" }) }}
                       onCancel={() => setView({ kind: "settings" })} />
        )}

        {(view.kind === "project" || view.kind === "ticket") && !project && (
          <p className="text-sm text-muted-foreground">
            Aún no hay proyectos.{" "}
            <button className="underline" onClick={() => setView({ kind: "projectForm", name: null })}>
              Agrega uno
            </button>{" "}
            para poder encolar tickets.
          </p>
        )}

        {view.kind === "project" && project && (
          <>
            <ProjectHeader project={project} />
            <TicketList tickets={myTickets} activeRun={activeRun} onAdd={addTicket} onOpen={open}
                        onRun={id => act(() => api.run(id))} />
          </>
        )}

        {view.kind === "ticket" && project && detail && (
          <TicketDetail detail={detail} activeRun={activeRun} projectName={project.name}
                        onBack={back}
                        onRun={(ins, phase) => act(() => api.run(detail.ticket.id, ins, phase))}
                        onDelete={() => { act(() => api.remove(detail.ticket.id)); back() }} />
        )}
      </main>

      {/* Same wording and same component the form uses for Cancelar and Escape: leaving
          by a third route shouldn't feel like a different question. */}
      <ConfirmDialog open={!!pendingNav} title="Hay cambios sin guardar."
                     body="Si sales ahora se pierden." confirmLabel="Descartar"
                     onConfirm={() => { const go = pendingNav; setPendingNav(null); go?.() }}
                     onCancel={() => setPendingNav(null)} />
    </div>
  )
}
```

- [x] **Step 3: Drop `+ Nuevo` from the sidebar**

En `Sidebar.tsx`, borrar la línea 31 (`<Button size="sm" variant="outline" className="mt-1" onClick={onNew}>+ Nuevo</Button>`), quitar `onNew` de las props y de su tipo. El botón de crear vive ahora donde está la lista: dos botones para lo mismo, en dos pantallas distintas, era el salto que nadie entendía.

- [x] **Step 4: Verify build, lint and the whole flow**

Run: `npm run build && npm run lint`
Expected: verdes, y **cero referencias sobrantes** a `startNew` o a la prop `onNew` (el compilador de TypeScript las cazaría).

Verificación manual, con backend y frontend corriendo — los seis casos:
1. Ajustes → `+ Nuevo proyecto` abre la vista dedicada con el título "Nuevo proyecto".
2. Escribir una ruta que **no** existe y salir del campo (Tab) pinta `✗ no existe` y el aviso.
3. Corregirla por una que sí existe y salir del campo pinta `✓ existe`.
4. Apretar `Guardar` con el nombre vacío marca el campo en rojo, lo enfoca, y **no** navega.
5. Editar un proyecto, cambiar algo y apretar `Cancelar` abre el diálogo; `Escape` lo cierra sin salir.
6. `Borrar` en la lista abre el diálogo; confirmar borra el proyecto y la lista se refresca.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/frontend/src/App.tsx apps/orchestrator/frontend/src/Projects.tsx apps/orchestrator/frontend/src/Sidebar.tsx
git commit -m "feat(ui): el formulario de proyecto vive en su propia vista"
```

---

# Fase 2 — Tickets

## Task 6: Extraer el guardián de rutas a `declared_file`

> **La tarea más delicada del plan.** El código que se mueve costó **tres rondas** de revisión adversarial y 638 vectores de path traversal, y cada ronda cerró un agujero que había abierto la anterior. La regla es **mover, no reescribir**: mismo cuerpo, mismo orden de comprobaciones, mismos mensajes, mismos comentarios. Si al terminar el diff muestra una condición reformulada "para que se lea mejor", está mal hecho.

**Files:**
- Modify: `apps/orchestrator/backend/app.py:859-960` (el handler `artifact`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `normalize_dirs`, `ticket_row`, `db`.
- Produces: `declared_file(t: sqlite3.Row, ruta: str) -> Path` (lanza `HTTPException(400)`) y `declared_file_or_none(t: sqlite3.Row, ruta: str) -> Path | None`. Las consumen la Task 7 (`read_title`) y la Task 10 (`task_progress`).

- [x] **Step 1: Write the failing test for the new function**

Agregar al final de `tests/test_app.py`:

```python
def test_declared_file_or_none_rejects_what_the_endpoint_rejects(client, tmp_path, monkeypatch):
    """The internal consumers (`read_title`, `task_progress`) must not get a second,
    laxer door to disk. Same ticket, same declared path, same verdict — the only
    difference is `None` instead of a 400."""
    import app as app_module

    (tmp_path / "repo" / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / "docs" / "a.md").write_text("# hola", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")

    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','docs')", (tid,))
    t = app_module.ticket_row(tid)

    # declared and inside: resolves
    assert app_module.declared_file_or_none(t, "docs/a.md") is not None
    # traversal out of the repo: None, not an exception and not a Path
    assert app_module.declared_file_or_none(t, "docs/../../secreto.txt") is None
    # not declared by any run of this ticket
    assert app_module.declared_file_or_none(t, "otro.md") is None
    # a directory is not a servable file
    assert app_module.declared_file_or_none(t, "docs") is None
```

- [x] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k declared_file_or_none -v`
Expected: FAIL con `AttributeError: module 'app' has no attribute 'declared_file_or_none'`.

- [x] **Step 3: Move the guard out of the handler**

Cortar de `artifact` (`app.py:867-940`) las reglas 1, 2 y 3 —desde el `with db() as c:` que arma `declared` hasta el `raise HTTPException(400, "No es un archivo regular")`— y pegarlas **tal cual, con todos sus comentarios**, dentro de esta función nueva, colocada justo antes de `ARTIFACT_CAP` (`app.py:856`):

```python
def declared_file(t: sqlite3.Row, ruta: str) -> Path:
    """Resolves `ruta` against the ticket's main repo and enforces the three rules that
    make a path servable: declared by a run OF THIS ticket (or under a declared
    directory, at any depth), inside the ticket's repos, and a regular file.

    Extracted from `GET /tickets/{tid}/artefacto`, where it lived inline, because the
    ticket's title and the task-progress counter need the same check from outside the
    endpoint. **Moved, not rewritten**: same body, same order of checks, same messages.
    That code took three rounds of adversarial review and 638 vectors, and each round
    closed a hole the previous one had opened.

    The cap and the read stay in the endpoint: those are about serving a file, not about
    deciding whether it may be read.

    **`t` must be a row from `ticket_row`.** The extraction moved the ticket's scope out
    of a path parameter and onto the caller's row: the declared-paths query is filtered
    by `t["id"]`. A caller handing over a hand-built or partial mapping gets a `KeyError`
    if the column is missing, or — silently, which is worse — a query scoped to the wrong
    ticket if the `id` doesn't match the ticket whose files are being served.
    """
    # <<< aquí van, sin tocar, las líneas 867-940 originales, terminando en `return real`
```

Y agregar, inmediatamente después:

```python
def declared_file_or_none(t: sqlite3.Row, ruta: str) -> Path | None:
    """The same check for internal consumers, which want `None` and not a 400.

    A separate door to disk is exactly what must NOT exist here: this is a wrapper, so
    a fix to `declared_file` reaches every caller at once.
    """
    try:
        return declared_file(t, ruta)
    except HTTPException:
        return None
```

El handler queda:

```python
@app.get("/tickets/{tid}/artefacto")
def artifact(tid: int, ruta: str):
    """Reads from disk starting from a request parameter, so validation can't be
    simplified. It's not a file explorer: it's "show me what THIS run said it wrote"."""
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    real = declared_file(t, ruta)

    # Cap, without loading the whole file into memory: reads at most CAP+4 bytes
    # <<< el resto del comentario y del cuerpo original (líneas 942-960), sin cambios
```

- [x] **Step 4: Run the FULL suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: los existentes PASS —**incluida toda la batería de path traversal, que sigue corriendo contra el endpoint**— más el nuevo. Un test de traversal que se volvió rojo significa que la extracción cambió el comportamiento: revertir y volver a mover, sin reformular.

- [x] **Step 5: Verify it isn't a placebo (mutation)**

Cambiar temporalmente el cuerpo de `declared_file` por `return (Path(t["repo_path"]) / ruta).resolve()`.
Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: **rojo** tanto en los tests de traversal del endpoint como en `test_declared_file_or_none_rejects_what_the_endpoint_rejects`. Si el endpoint se pone rojo pero el test nuevo no, el test nuevo no está ejerciendo la función. Revertir la mutación.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "refactor(backend): el guardian de rutas sale del handler, movido sin reescribir"
```

---

## Task 7: El título del ticket, leído del análisis

**Files:**
- Modify: `apps/orchestrator/backend/app.py:388-403` (migraciones), `app.py:818-820` (cierre de `execute_run`), y agregar `read_title` cerca de `stamp_stat` (`app.py:555`)
- Modify: `apps/orchestrator/frontend/src/api.ts:1-4` (tipo `Ticket`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `declared_file_or_none` (Task 6), `ticket_row`, `set_ticket`.
- Produces: `read_title(t: sqlite3.Row, rel: str) -> str | None`, la columna `tickets.title`, y el campo `title: string | null` en el payload de `GET /tickets` y `GET /tickets/{id}`. Lo consume la Task 8.

- [x] **Step 1: Write the failing tests**

```python
def _fake_analyze(client, monkeypatch, tmp_path, contenido: str):
    """Runs a fake `analyze` that writes `contenido` at docs/tickets/1-analysis.md and
    closes with the stamp pointing at it. Returns the ticket id."""
    import app as app_module

    dest = tmp_path / "repo" / "docs" / "tickets"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "1-analysis.md").write_text(contenido, encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 1, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','docs/tickets/1-analysis.md')", (tid,))
    t = app_module.ticket_row(tid)
    titulo = app_module.read_title(t, "docs/tickets/1-analysis.md")
    if titulo:
        app_module.set_ticket(tid, title=titulo)
    return tid


def test_title_comes_from_the_first_heading(client, monkeypatch, tmp_path):
    tid = _fake_analyze(client, monkeypatch, tmp_path,
                        "por ticket-agent v0.7.1\n\n# Carrier API V2 Migration - Dayton\n\ntexto\n")
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] == "Carrier API V2 Migration - Dayton"


def test_analysis_without_heading_leaves_title_empty(client, monkeypatch, tmp_path):
    """Soft contract: the skill's template writes the `# `, but no plugin test protects
    it. Without a heading the list falls back to `#<ado_id>` — it must never blow up."""
    tid = _fake_analyze(client, monkeypatch, tmp_path, "sin encabezado ninguno\n")
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] is None


def test_the_runner_stores_the_title_after_a_real_analyze_run(client, monkeypatch, tmp_path):
    """Drives the WIRING, not the gate.

    The three tests above call `read_title` directly, which proves the function works and
    not that `execute_run` ever calls it. A test that reimplements the runner's logic in
    order to check the runner is the exact shape of placebo this project has already
    found five times — it passes because of its own setup. This one goes through
    `POST /tickets/{tid}/run` with the fake CLI and reads the result off `GET /tickets`.
    """
    dest = tmp_path / "repo" / "docs" / "tickets"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "40-analysis.md").write_text(
        "por ticket-agent v0.7.1\n\n# Carrier API V2 Migration - Dayton\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/tickets/40-analysis.md")
    tid = client.post("/tickets", json={"ado_id": 40, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={})
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] == "Carrier API V2 Migration - Dayton"


def test_only_analyze_stores_a_title(client, monkeypatch, tmp_path):
    """The hook is gated on the phase. A `design` run that declares a markdown file with
    a heading must not stamp the plan's title onto the ticket."""
    dest = tmp_path / "repo" / "docs"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "plan.md").write_text("# El plan, no el ticket\n", encoding="utf-8")
    _use_fake_claude(monkeypatch, stamp="ok — docs/plan.md")
    tid = client.post("/tickets", json={"ado_id": 41, "project": "Demo"}).json()["id"]
    client.post(f"/tickets/{tid}/run", json={"phase": "design"})
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    assert t["title"] is None


def test_title_is_not_a_second_door_to_disk(client, tmp_path):
    """A stamp declaring a traversal must not let `read_title` read outside the repo."""
    import app as app_module

    (tmp_path / "secreto.md").write_text("# secreto\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 2, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'analyze','success','ok','../secreto.md')", (tid,))
    t = app_module.ticket_row(tid)
    assert app_module.read_title(t, "../secreto.md") is None
```

- [x] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k title -v`
Expected: FAIL con `AttributeError: module 'app' has no attribute 'read_title'`.

- [x] **Step 3: Add the column, the reader, and the write in the runner**

En `init_db`, agregar a la tupla de `ALTER` (después de la línea 398, `ADD COLUMN branch`):

```python
            # The ticket's title, read from the analysis when `analyze` closes well.
            # It doesn't come from Azure DevOps: the backend has no ADO credentials —
            # the MCP only lives inside the agent's subprocess — and giving it some
            # would mean building a second authentication path to save a typo.
            "ALTER TABLE tickets ADD COLUMN title TEXT",
```

Agregar `read_title` justo después de `stamp_stat` (`app.py:579`):

```python
def read_title(t: sqlite3.Row, rel: str) -> str | None:
    """The analysis's first `# ` heading, or None.

    Soft contract: the skill's template writes that heading, but no plugin test protects
    it, so every failure path returns None and the UI falls back to `#<ado_id>`.

    Goes through `declared_file_or_none`, not straight to disk: a stamp that declares a
    traversal must not become a second, laxer door.
    """
    p = declared_file_or_none(t, rel)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            # The heading is at the top; a 28 KB analysis isn't read whole for a title.
            for _ in range(50):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("# "):
                    return line[2:].strip()[:200] or None
    except OSError:
        return None
    return None
```

En `execute_run`, después del `set_run(...)` final (`app.py:818-819`) y antes del `set_ticket` (línea 820):

```python
        # The title travels with the analysis, so it only gets read when that phase
        # closes with a footprint. `title` is only written when one is found: a re-run
        # that comes out worse must not erase the title the previous one left.
        if phase == "analyze" and state in ("ok", "parcial"):
            title = read_title(ticket_row(ticket["id"]), path)
            if title:
                set_ticket(ticket["id"], title=title)
```

En `api.ts`, el tipo `Ticket`:

```ts
export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  status: string; created_at: string; updated_at: string
  /** Read from the analysis when `analyze` closes well. `null` before that: we don't
   *  know what the ticket is about yet, and saying so is honest. */
  title: string | null
}
```

`ticket_out` devuelve `{**dict(t), ...}`, así que el campo viaja solo en cuanto existe la columna: no hay que tocar `GET /tickets` ni `GET /tickets/{id}`.

- [x] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: los tres nuevos PASS y los anteriores siguen PASS.

- [x] **Step 5: Verify they aren't placebos (mutation)**

Dos mutaciones, una por riesgo:

1. En `read_title`, cambiar `p = declared_file_or_none(t, rel)` por `p = Path(t["repo_path"]) / rel`.
   Expected: `test_title_is_not_a_second_door_to_disk` en **rojo**.
2. En `read_title`, cambiar `if line.startswith("# ")` por `if True`.
   Expected: `test_analysis_without_heading_leaves_title_empty` en **rojo**.
3. En `execute_run`, borrar el gancho entero (las cuatro líneas del
   `if phase == "analyze" and state in ("ok", "parcial")`).
   Expected: `test_the_runner_stores_the_title_after_a_real_analyze_run` en **rojo**,
   y los tres tests que llaman a `read_title` directamente **en verde** — que es
   justamente por lo que hacía falta el cuarto.
4. En ese mismo gancho, cambiar la condición a solo `state in ("ok", "parcial")`,
   quitando la comprobación de fase.
   Expected: `test_only_analyze_stores_a_title` en **rojo**.

Si alguna deja todo verde, ese test no prueba nada. Revertir las cuatro.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py apps/orchestrator/frontend/src/api.ts
git commit -m "feat(backend): el titulo del ticket sale del analisis, no de Azure DevOps"
```

---

## Task 8: La lista de tickets — título, ayuda del id y stepper

**Files:**
- Modify: `apps/orchestrator/backend/app.py:638-646` (`list_tickets` incluye `fases`)
- Modify: `apps/orchestrator/frontend/src/api.ts` (tipo `Ticket`)
- Modify: `apps/orchestrator/frontend/src/TicketList.tsx` (completo)
- Modify: `apps/orchestrator/frontend/src/TicketDetail.tsx:41-43` (confirmación de borrado)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `Phase` y `PHASE_LABEL`, `ConfirmDialog` (Task 2), `title` (Task 7).
- Produces: `fases: Phase[]` en cada elemento de `GET /tickets`.

- [x] **Step 1: Write the failing test for `fases` in the list**

```python
def test_the_ticket_list_carries_the_phases(client):
    """The three-dot stepper needs per-phase state, not just the folded status: `error`
    alone doesn't say which phase failed.

    Asserted against the detail view rather than against a literal list of phase names,
    so this test doesn't have to be rewritten every time `PHASES` changes — which it
    does in Task 9, two tasks from here. The footprint (the disk-reading part) stays
    off, which is what made the list cheap in the first place."""
    tid = client.post("/tickets", json={"ado_id": 7, "project": "Demo"}).json()["id"]
    t = next(x for x in client.get("/tickets").json() if x["id"] == tid)
    expected = [f["fase"] for f in client.get(f"/tickets/{tid}").json()["fases"]]
    assert [f["fase"] for f in t["fases"]] == expected
    assert all("huella" not in f for f in t["fases"])
```

- [x] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k lista_de_tickets_trae -v`
Expected: FAIL con `KeyError: 'fases'`.

- [x] **Step 3: Include `fases` in the list payload**

Reemplazar el `return` de `list_tickets` (`app.py:645-646`):

```python
    out = []
    for t in ts:
        # The footprint stays off: it's the part that touches disk, and the list doesn't
        # show artifacts. The phases themselves are cheap and the stepper needs them —
        # the folded `status` says `error` without saying which phase failed.
        ph = phases_for(t, [r for r in runs if r["ticket_id"] == t["id"]], with_footprint=False)
        out.append({**ticket_out(t, ph), "fases": ph})
    return out
```

En `api.ts`, agregar al tipo `Ticket`: `fases: Phase[]` (mover la declaración de `Ticket` debajo de `Phase`, o declarar `Phase` antes — TypeScript resuelve los tipos sin importar el orden, así que basta con agregar el campo).

- [x] **Step 4: Rewrite `TicketList.tsx`**

```tsx
import { useState } from "react"
import type { ActiveRun, Phase, Ticket } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { blockReason, PHASE_LABEL, ticketStatus } from "@/status"

const DOT: Record<string, string> = {
  ok: "bg-emerald-500",
  parcial: "bg-amber-500",
  error: "bg-red-500",
  corriendo: "bg-blue-500 animate-pulse",
  pendiente: "bg-muted-foreground/25",
}

/**
 * Three dots, one per launchable phase.
 *
 * It was removed in the 2026-08-09 redesign for showing six phases with five dimmed on
 * every row, and `STATUS.md` left it written that it comes back once phases 2-4 really
 * exist. They do, and with `guards`/`pr` gone there are exactly three.
 *
 * `role="img"` with one composed name — NOT `aria-hidden`, and not a label per dot. The
 * badge beside it cannot stand in for these: `folded_status` collapses every phase into
 * a single word, so it says "error" and never which phase failed. That detail lives only
 * in the dots, and hiding them would leave it available on hover and nowhere else. One
 * name because it reads as one graphic; three names would be thirty stops in a list of
 * ten tickets. `role="img"` also makes the subtree presentational, so the per-dot
 * `title`s stay for the mouse without being announced twice.
 */
function Stepper({ fases }: { fases: Phase[] }) {
  const shown = fases.filter(f => f.disponible)
  const label = (f: Phase) => `${PHASE_LABEL[f.fase] ?? f.fase}: ${f.estado ?? "pendiente"}`
  return (
    <span className="flex items-center" role="img" aria-label={shown.map(label).join(" · ")}>
      {shown.map((f, i) => (
        <span key={f.fase} className="flex items-center">
          {i > 0 && <span aria-hidden className="h-px w-3 bg-border" />}
          <span title={label(f)}
                className={`h-2 w-2 rounded-full ${DOT[f.estado ?? "pendiente"]}`} />
        </span>
      ))}
    </span>
  )
}

export function TicketList({ tickets, activeRun, onAdd, onOpen, onRun }: {
  tickets: Ticket[]
  activeRun: ActiveRun | null
  onAdd: (adoId: number) => void
  onOpen: (id: number) => void
  onRun: (id: number) => void
}) {
  const [adoId, setAdoId] = useState("")
  const add = () => { onAdd(Number(adoId)); setAdoId("") }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border p-3">
        <label htmlFor="ado-id" className="text-xs font-medium">ID del work item</label>
        <div className="mt-1 flex gap-2">
          <Input id="ado-id" className="w-40" placeholder="3332" value={adoId}
                 onChange={e => setAdoId(e.target.value.replace(/\D/g, ""))}
                 onKeyDown={e => e.key === "Enter" && adoId && add()} />
          <Button onClick={add} disabled={!adoId}>+ Añadir</Button>
        </div>
        {/* The number is not validated against Azure DevOps on purpose: the backend has
            no ADO credentials. Saying where it comes from costs a line and does the
            same job. */}
        <p className="mt-2 text-xs text-muted-foreground">
          El número del final de la URL en Azure DevOps:{" "}
          <span className="font-mono">…/_workitems/edit/<strong>3332</strong></span>
        </p>
      </div>

      <div className="divide-y rounded-md border">
        {tickets.map(t => {
          const { label, color } = ticketStatus(t, activeRun)
          const reason = blockReason(t, activeRun)
          return (
            <div key={t.id} className="px-3 py-2 transition-colors hover:bg-muted/40">
              <div className="flex items-center gap-2">
                <button className="rounded text-sm font-medium hover:underline
                                   focus-visible:outline-none focus-visible:ring-2
                                   focus-visible:ring-ring/50"
                        onClick={() => onOpen(t.id)}>
                  #{t.ado_id}
                </button>
                {/* No title before the analysis runs: we don't know what it is yet. */}
                {t.title && (
                  <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground"
                        title={t.title}>
                    {t.title}
                  </span>
                )}
                <div className={`flex gap-1 ${t.title ? "" : "ml-auto"}`}>
                  <Button size="sm" variant="outline" disabled={!!reason}
                          title={reason || "Lanza la Fase 1; el resto se lanza desde el detalle"}
                          onClick={() => onRun(t.id)}>
                    {t.status === "queued" ? "Analizar" : "Re-analizar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onOpen(t.id)}>Ver</Button>
                </div>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Stepper fases={t.fases} />
                <Badge className={color}>{label}</Badge>
                {reason && activeRun?.ticket_id !== t.id && (
                  <span className="text-xs text-muted-foreground">{reason}</span>
                )}
              </div>
            </div>
          )
        })}
        {tickets.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            Sin tickets en este proyecto. Escribe un id arriba para añadir el primero.
          </p>
        )}
      </div>
    </div>
  )
}
```

- [x] **Step 5: Confirm before deleting a ticket**

En `TicketDetail.tsx`, agregar el import (`useState` ya está importado en la línea 1):

```tsx
import { ConfirmDialog } from "@/ConfirmDialog"
```

Agregar el estado junto a `showLog` y `showHistory` (`TicketDetail.tsx:22-23`), y reemplazar el botón (`TicketDetail.tsx:41-43`):

```tsx
  const [confirmDelete, setConfirmDelete] = useState(false)
```

```tsx
        <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground"
                onClick={() => setConfirmDelete(true)}>
          Borrar
        </Button>
```

Y al final del `<div className="space-y-4">`, antes de cerrarlo:

```tsx
      <ConfirmDialog open={confirmDelete} title={`¿Borrar el ticket #${t.ado_id}?`}
                     body="Se borran sus corridas y sus logs. Los artefactos que el
                           agente escribió en el repo se quedan donde están."
                     onConfirm={() => { setConfirmDelete(false); onDelete() }}
                     onCancel={() => setConfirmDelete(false)} />
```

- [x] **Step 6: Run backend tests, build and lint**

Run: `.venv/Scripts/python -m pytest tests/ -v` → todos PASS.
Run: `npm run build && npm run lint` → verdes.

Verificación manual: un ticket sin analizar muestra `#3332` y tres puntos grises; después de una corrida `ok` de análisis muestra el título y el primer punto verde. `Borrar` en el detalle abre el diálogo.

- [x] **Step 7: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py apps/orchestrator/frontend/src
git commit -m "feat(ui): el ticket dice de que se trata y por donde va"
```

---

# Fase 3 — Timeline

## Task 9: Sacar `guards` y `pr`

**Files:**
- Modify: `apps/orchestrator/backend/app.py:20-25` (`PHASES` y su comentario)
- Modify: `apps/orchestrator/frontend/src/status.ts:58-64` (`PHASE_LABEL`)
- Modify: `apps/orchestrator/backend/tests/test_app.py:702` y `:708`

**Interfaces:**
- Consumes: nada.
- Produces: `PHASES == list(PHASE_COMMANDS)`. La Task 8 depende de esto para su aserción de tres fases.

- [x] **Step 1: Update the two assertions that expect five phases**

En `tests/test_app.py`, línea 702:

```python
    assert [f["fase"] for f in phases] == ["analyze", "design", "implement"]
```

Y borrar la línea 708 entera (`assert phases[3] == {"fase": "guards", "disponible": False}`), que afirmaba justamente lo que deja de existir.

Los otros tres usos de `guards` (líneas 329-334 y 478) **siguen valiendo tal cual**: comprueban que una fase que no está en `PHASE_COMMANDS` se rechaza con 400, y eso no cambia — `guards` deja de estar declarada, pero sigue sin ser lanzable.

- [x] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k phase -v`
Expected: FAIL en la línea 702, que sigue recibiendo cinco fases.

- [x] **Step 3: Remove the two phases**

En `app.py`, reemplazar el comentario y la constante (`app.py:20-25`):

```python
# Declaring a phase and being able to launch it are two different things, and a phase
# declared without a command is a broken promise taking up a slot in the timeline. `test`
# went first on 2026-08-11 (it isn't a phase, it's part of `implement`), and `guards` and
# `pr` follow it: they were in this list from the start and never gained a command, so the
# UI painted two rows out of five that never did anything. They come back when they exist.
PHASES = ["analyze", "design", "implement"]
```

En `status.ts` (`app` frontend), reemplazar `PHASE_LABEL` (`status.ts:58-64`):

```ts
/** The pipeline's phases, with the name shown to the user.
 *  `test` disappeared on 2026-08-11 (tests are written inside `implement`), and
 *  `guards`/`pr` on the same date for the opposite reason: they never existed. */
export const PHASE_LABEL: Record<string, string> = {
  analyze: "Análisis", design: "Plan", implement: "Código",
}
```

**No se toca** la rama `if name not in PHASE_COMMANDS` de `phases_for` (`app.py:586-588`) ni el `if (!f.disponible)` de `canRunPhase` (`status.ts:104`). Quedan sin alcanzar hoy, y son el mecanismo que hace que declarar una fase futura no reviente. Borrarlos ahorraría dos líneas y costaría el próximo `guards`.

- [x] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: todos PASS. Prestar atención a cualquier test que contase fases indirectamente.

Run: `npm run build && npm run lint` → verdes.

- [x] **Step 5: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py apps/orchestrator/frontend/src/status.ts
git commit -m "refactor: guards y pr salen del timeline hasta que existan"
```

---

## Task 10: `progreso` — contar casillas de `tasks.md`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (agregar `task_progress` después de `stamp_stat`, y engancharlo en `phases_for`, `app.py:612-616`)
- Modify: `apps/orchestrator/frontend/src/api.ts:18-23` (tipo `Phase`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `declared_file_or_none` (Task 6).
- Produces: `task_progress(t, runs) -> dict | None` y el campo `progreso?: {hechas: number; total: number} | null` en la entrada de la fase `implement` de `GET /tickets/{id}`. Lo consume la Task 11.

- [x] **Step 1: Write the failing tests**

```python
def _with_plan(client, tmp_path, tasks_md: str | None, ado_id: int = 30,
               trailing_slash: bool = False):
    """A ticket with a `design` run that declared a change directory, and an `implement`
    run in flight. Returns the ticket id."""
    import app as app_module

    change = tmp_path / "repo" / "openspec" / "changes" / f"{ado_id}-x"
    change.mkdir(parents=True, exist_ok=True)
    if tasks_md is not None:
        (change / "tasks.md").write_text(tasks_md, encoding="utf-8")
    rel = f"openspec/changes/{ado_id}-x" + ("/" if trailing_slash else "")
    tid = client.post("/tickets", json={"ado_id": ado_id, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'design','success','ok',?)", (tid, rel))
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    return tid


def _implement(client, tid):
    return next(f for f in client.get(f"/tickets/{tid}").json()["fases"]
                if f["fase"] == "implement")


def test_progress_counts_the_boxes(client, tmp_path):
    md = "## 1\n- [x] a\n- [x] b\n  - [x] c\n- [ ] d\n- [ ] e\n"
    tid = _with_plan(client, tmp_path, md)
    assert _implement(client, tid)["progreso"] == {"hechas": 3, "total": 5}


def test_no_tasks_md_means_no_bar(client, tmp_path):
    tid = _with_plan(client, tmp_path, None, ado_id=31)
    assert _implement(client, tid).get("progreso") is None


def test_tasks_md_without_boxes_means_no_bar(client, tmp_path):
    tid = _with_plan(client, tmp_path, "solo prosa, ninguna casilla\n", ado_id=32)
    assert _implement(client, tid).get("progreso") is None


def test_no_design_run_means_no_bar(client):
    import app as app_module
    tid = client.post("/tickets", json={"ado_id": 33, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    assert _implement(client, tid).get("progreso") is None


def test_an_unreadable_tasks_md_means_no_bar(client, tmp_path, monkeypatch):
    """The counter runs WHILE `implement` is writing that same file — it is polled every
    three seconds during a run that took 83 minutes in production. That is a real TOCTOU
    window between `declared_file_or_none`'s `is_file()` and the `read_text()` two lines
    later, not a device-file curiosity. Without this test, deleting the `try/except`
    outright reddens nothing."""
    tid = _with_plan(client, tmp_path, "- [x] a\n- [ ] b\n", ado_id=35)
    real_read = Path.read_text

    def boom(self, *a, **k):
        if self.name == "tasks.md":
            raise OSError("el agente lo estaba reescribiendo")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", boom)
    assert _implement(client, tid).get("progreso") is None


def test_a_declared_path_with_a_trailing_slash_still_counts(client, tmp_path):
    """The stamp is written by an agent obeying a markdown file, so the declared
    directory may or may not carry its trailing slash. `rstrip("/")` covers both and
    nothing proved it did.

    CORRECCIÓN (encontrada al mutar, ver commit 6041491): la aserción end-to-end de
    abajo **es un placebo por sí sola**. `pathlib` colapsa los separadores repetidos al
    construir el `Path`, antes de `resolve()`, así que `Path("a//b")` y `Path("a/b")`
    son el mismo objeto: quitando el `.rstrip("/")` el fichero se resuelve igual y el
    test sigue verde. El único nivel donde la mutación es observable es la cadena que
    `task_progress` entrega a `declared_file_or_none`, ANTES de que se normalice. El
    test implementado espía ese argumento y afirma que no lleva la barra doble; ver el
    código real en `tests/test_app.py`, que manda sobre este bloque."""
    tid = _with_plan(client, tmp_path, "- [x] a\n- [ ] b\n", ado_id=36, trailing_slash=True)
    assert _implement(client, tid)["progreso"] == {"hechas": 1, "total": 2}


def test_progress_is_not_a_second_door_to_disk(client, tmp_path):
    """A `design` stamp that declares a traversal must not let the counter read a
    `tasks.md` outside the ticket's repos."""
    import app as app_module

    fuera = tmp_path / "fuera"
    fuera.mkdir(exist_ok=True)
    (fuera / "tasks.md").write_text("- [x] a\n- [ ] b\n", encoding="utf-8")
    tid = client.post("/tickets", json={"ado_id": 34, "project": "Demo"}).json()["id"]
    with app_module.db() as c:
        c.execute("INSERT INTO runs(ticket_id, phase, status, artifact_state, artifact_path) "
                  "VALUES(?,'design','success','ok','../fuera')", (tid,))
        c.execute("INSERT INTO runs(ticket_id, phase, status) VALUES(?,'implement','running')",
                  (tid,))
    assert _implement(client, tid).get("progreso") is None
```

- [x] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -k "progress or bar" -v`
Expected: `test_progress_counts_the_boxes` FAIL con `KeyError: 'progreso'`; los otros pasan por accidente (el campo no existe, así que `.get()` da `None`). Eso está bien: son redes para la implementación, no la prueba de que falta.

- [x] **Step 3: Implement `task_progress` and hook it in**

Agregar después de `stamp_stat` (`app.py:579`):

```python
# A checked box in `tasks.md`. The Phase 2b skill checks them off as it advances, so
# counting lines is the whole mechanism — no stream-json parsing, which is a CLI format
# that would have to be maintained when it changes.
DONE_BOX = re.compile(r"^\s*- \[x\]", re.MULTILINE | re.IGNORECASE)
OPEN_BOX = re.compile(r"^\s*- \[ \]", re.MULTILINE)


def task_progress(t: sqlite3.Row, runs: list[dict]) -> dict | None:
    """`{hechas, total}` for a running `implement`, or None.

    Answers the question you actually have at minute 50 of an 83-minute run —how much is
    left— instead of "is it still alive". It's an estimate, not a truth: a big task
    counts the same as a small one, which is why the UI shows the count and never a
    percentage of time.

    None as soon as anything doesn't add up: no `design` run with a footprint, no
    `tasks.md`, no boxes. Then the UI shows the stopwatch it showed before.
    """
    design = next((r for r in runs
                   if r["phase"] == "design"
                   and r["artifact_state"] in ("ok", "parcial")
                   and r["artifact_path"]), None)
    if not design:
        return None
    # Same path guard as the viewer: this is a path declared by a run of THIS ticket, and
    # it goes through the predicate that took three rounds and 638 vectors.
    p = declared_file_or_none(t, design["artifact_path"].rstrip("/") + "/tasks.md")
    if not p:
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hechas = len(DONE_BOX.findall(text))
    total = hechas + len(OPEN_BOX.findall(text))
    return {"hechas": hechas, "total": total} if total else None
```

En `phases_for`, dentro del `else` que ya existe (`app.py:612-616`), agregar antes del `if e["estado"] == "parcial"`:

```python
            # Only while running, and only in the detail view: it's a disk read, and the
            # list turns the footprint off for exactly that reason. Once finished, "19 of
            # 19" says nothing the green check doesn't.
            if with_footprint and name == "implement" and e["estado"] == "corriendo":
                e["progreso"] = task_progress(t, runs)
```

En `api.ts`, el tipo `Phase`:

```ts
export type Phase = {
  fase: string; disponible: boolean
  estado?: "pendiente" | "corriendo" | "ok" | "parcial" | "error"
  corridas?: number; fallidas?: number
  en?: string | null; duracion_s?: number | null; motivo?: string; huella?: Footprint
  /** Only on `implement` and only while running. An estimate: a big task weighs the
   *  same as a small one, so it's shown as a count and never as a percentage. */
  progreso?: { hechas: number; total: number } | null
}
```

- [x] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/ -v`
Expected: los cinco nuevos PASS, los anteriores siguen PASS.

- [x] **Step 5: Verify they aren't placebos (mutation)**

Tres mutaciones:

1. Cambiar `p = declared_file_or_none(...)` por `p = Path(t["repo_path"]) / design["artifact_path"] / "tasks.md"`.
   Expected: `test_progress_is_not_a_second_door_to_disk` en **rojo**.
2. Cambiar `return {...} if total else None` por `return {"hechas": hechas, "total": total}`.
   Expected: `test_tasks_md_without_boxes_means_no_bar` en **rojo**.
3. Cambiar `DONE_BOX` a `re.compile(r"^\s*- \[.\]", re.MULTILINE)`.
   Expected: `test_progress_counts_the_boxes` en **rojo**. Concretamente da
   **5 hechas de 7**, no 5 de 5: el regex ensanchado cuenta las 5 casillas como
   hechas, y `total = hechas + abiertas` vuelve a sumar las 2 abiertas. Lo que
   importa es que se ponga rojo; el número exacto va aquí porque una predicción
   equivocada en un plan hace dudar del test en vez de del plan.

Revertir las tres.

- [x] **Step 6: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py apps/orchestrator/frontend/src/api.ts
git commit -m "feat(backend): el avance de implement sale de contar casillas de tasks.md"
```

---

## Task 11: La barra en el timeline

**Files:**
- Modify: `apps/orchestrator/frontend/src/Timeline.tsx:145-147` (insertar la barra) y `:139` (el chevron)

**Interfaces:**
- Consumes: `progreso` del tipo `Phase` (Task 10).
- Produces: nada.

- [x] **Step 1: Add the bar**

En `Timeline.tsx`, justo después del bloque `{reason && f.disponible && ...}` (línea 147) e inmediatamente antes de `{f.estado === "error" && ...}`:

```tsx
              {/* An 83-minute run used to say only "corriendo". The bar answers "how
                  much is left"; the count next to it is the honest part — the width is
                  a proportion of tasks, not of time. */}
              {f.progreso && (
                <div className="flex items-center gap-2 pb-2 text-xs">
                  <div className="h-1.5 w-40 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-blue-500 transition-all"
                         style={{ width: `${Math.round(100 * f.progreso.hechas / f.progreso.total)}%` }} />
                  </div>
                  <span className="text-muted-foreground">
                    tarea {f.progreso.hechas} de {f.progreso.total}
                  </span>
                </div>
              )}
```

- [x] **Step 2: Give the chevron a label**

En la línea 139, reemplazar `▾` por `▾ Ajustar`. Tenía `aria-label`, así que un lector de pantalla lo anunciaba, pero visualmente era un galón pelado que nadie encuentra.

- [x] **Step 3: Verify build, lint and the screen**

Run: `npm run build && npm run lint` → verdes.

Verificación manual — se puede montar sin esperar 83 minutos, con `sqlite3` sobre la DB de desarrollo:
1. Crear un ticket, insertarle a mano una corrida de `design` con `artifact_state='ok'` y `artifact_path` apuntando a un directorio real bajo el repo del ticket, con un `tasks.md` de 3 marcadas y 2 sin marcar.
2. Insertarle una corrida de `implement` con `status='running'`.
3. Abrir el detalle: la fila **Código** muestra la barra al 60% y el texto `tarea 3 de 5`.
4. Marcar una casilla más en `tasks.md` y esperar el poll de 3 segundos: la barra pasa a `4 de 5` sola.

- [x] **Step 4: Commit**

```bash
git add apps/orchestrator/frontend/src/Timeline.tsx
git commit -m "feat(ui): la corrida larga dice por que tarea va"
```

---

# Cierre

- [x] **Actualizar `docs/STATUS.md`**: marcar el rediseño como hecho, anotar el resultado de las tres fases, y tachar de "Immediate pending items" lo que este plan cerró. Anotar la deuda que sigue abierta: el interruptor de tema y el artefacto en markdown crudo.
- [x] **Verificación final completa**: `.venv/Scripts/python -m pytest tests/ -v` (todos verdes) y `npm run build && npm run lint` (verdes), con el conteo de tests antes y después anotado en el commit.
