import { useRef, useState } from "react"
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

export function ProjectForm({ initial, onSaved, onCancel }: {
  /** `null` = creating. Otherwise, the project as it is saved. */
  initial: Project | null
  onSaved: (name: string) => void
  onCancel: () => void
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

        <div id="campo-repos" className="space-y-4">
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
