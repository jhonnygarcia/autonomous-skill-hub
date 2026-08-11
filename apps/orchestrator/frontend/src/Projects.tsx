import { useState } from "react"
import { api, type Project, type Repo } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

const EMPTY: Project = {
  name: "", org: "", project: "",
  repos: [{ path: "", label: "", primary: true }],
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium">{label}</span>
      {hint && <span className="ml-1 text-xs text-muted-foreground">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  )
}

const newForm = (): Project => ({ ...EMPTY, repos: [{ ...EMPTY.repos[0] }] })

export function Projects({ projects, startNew, onChange }: {
  projects: Project[]
  /** Entering via "+ Nuevo" opens the creation form directly. The component
   *  remounts on view change, so it's enough to initialize the state. */
  startNew?: boolean
  /** `select` travels along so that, after a rename, the sidebar follows the same project. */
  onChange: (select?: string) => void
}) {
  const [form, setForm] = useState<Project | null>(startNew ? newForm() : null)
  const [original, setOriginal] = useState<string | null>(null)  // null = creating; otherwise, editing
  const [error, setError] = useState("")

  const open = (p: Project | null) => {
    setForm(p ? { ...p, repos: p.repos.map(r => ({ ...r })) } : newForm())
    setOriginal(p?.name ?? null)
    setError("")
  }
  const fail = (e: unknown) => setError(String(e))
  const patch = (fn: (rs: Repo[]) => Repo[]) =>
    setForm(f => f ? { ...f, repos: fn(f.repos) } : f)

  const save = () => form && api
    // blank rows are discarded here; the backend rejects paths that don't exist
    .saveProject({ ...form, repos: form.repos.filter(r => r.path.trim()) }, original)
    .then(p => { setForm(null); onChange(p.name) }).catch(fail)
  const remove = (name: string) => api.removeProject(name).then(() => onChange()).catch(fail)

  return (
    <Card>
      {/* No creation button here: the sidebar's ("+ Nuevo") already opens this
          view with the form expanded, and two buttons for the same thing is confusing. */}
      <CardHeader><CardTitle className="text-base">Proyectos</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {projects.map(p => (
          <div key={p.name} className="flex items-center gap-2 text-sm">
            <span className="font-medium">{p.name}</span>
            <span className="text-muted-foreground">{p.org}/{p.project}</span>
            <span className="text-xs text-muted-foreground/70"
                  title={p.repos.map(r => `${r.path}${r.label ? ` — ${r.label}` : ""}`).join("\n")}>
              {p.repos.length} repo{p.repos.length > 1 ? "s" : ""}
            </span>
            <div className="ml-auto flex gap-1">
              <Button size="sm" variant="outline" onClick={() => open(p)}>Editar</Button>
              <Button size="sm" variant="destructive" onClick={() => remove(p.name)}>Borrar</Button>
            </div>
          </div>
        ))}
        {projects.length === 0 && !form && (
          <p className="text-sm text-muted-foreground">Sin proyectos. Agrega uno para poder encolar tickets.</p>
        )}

        {form && (
          <div className="space-y-4 rounded-md border p-4">
            <Field label="Nombre del proyecto" hint="como quieras llamarlo tú; puedes cambiarlo">
              <Input placeholder="p. ej. TMS" value={form.name}
                     onChange={e => setForm({ ...form, name: e.target.value })} />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Organización de Azure DevOps">
                <Input placeholder="ProvidenceSolutions" value={form.org}
                       onChange={e => setForm({ ...form, org: e.target.value })} />
              </Field>
              <Field label="Proyecto de Azure DevOps" hint="donde viven los tickets">
                <Input placeholder="ProvidenceTMS" value={form.project}
                       onChange={e => setForm({ ...form, project: e.target.value })} />
              </Field>
            </div>

            <div>
              <p className="text-xs font-medium">Repos del proyecto</p>
              <p className="mb-2 text-xs text-muted-foreground">
                El marcado como <strong>principal</strong> es donde corre el agente y donde se
                escribe el análisis; los demás los lee. La descripción viaja al prompt y es lo
                que le dice cuándo mirar en cada uno.
              </p>

              <div className="space-y-1">
                <div className="flex gap-2 text-[11px] uppercase tracking-wide text-muted-foreground/70">
                  <span className="w-16 text-center">principal</span>
                  <span className="flex-1">ruta</span>
                  <span className="w-64">descripción</span>
                  <span className="w-9" />
                </div>
                {form.repos.map((r, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="flex w-16 justify-center">
                      <input type="radio" name="principal" checked={r.primary} aria-label="principal"
                             onChange={() => patch(rs => rs.map((x, j) => ({ ...x, primary: j === i })))} />
                    </span>
                    <Input className="flex-1" placeholder="D:/ruta/al/repo" value={r.path}
                           onChange={e => patch(rs =>
                             rs.map((x, j) => j === i ? { ...x, path: e.target.value } : x))} />
                    <Input className="w-64" placeholder="frontend, backend, app de auth…"
                           value={r.label}
                           onChange={e => patch(rs =>
                             rs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
                    <Button size="sm" variant="ghost" title="Quitar" className="w-9"
                            disabled={form.repos.length === 1}
                            onClick={() => patch(rs => {
                              const remaining = rs.filter((_, j) => j !== i)
                              // if the primary one leaves, the first one left takes over
                              return remaining.some(x => x.primary)
                                ? remaining
                                : remaining.map((x, j) => ({ ...x, primary: j === 0 }))
                            })}>
                      ✕
                    </Button>
                  </div>
                ))}
              </div>
              <Button size="sm" variant="outline" className="mt-2"
                      onClick={() => patch(rs => [...rs, { path: "", label: "", primary: false }])}>
                + Agregar repo
              </Button>
            </div>

            <div className="flex gap-2">
              <Button size="sm" onClick={save}
                      disabled={!form.name || !form.org || !form.project
                                || !form.repos.some(r => r.path.trim())}>
                Guardar
              </Button>
              <Button size="sm" variant="outline" onClick={() => setForm(null)}>Cancelar</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
