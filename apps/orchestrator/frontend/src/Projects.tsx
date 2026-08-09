import { useState } from "react"
import { api, type Project, type Repo } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

const EMPTY: Project = {
  name: "", org: "", project: "",
  repos: [{ path: "", label: "", primary: true }],
}

function Campo({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium">{label}</span>
      {hint && <span className="ml-1 text-xs text-gray-500">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  )
}

export function Projects({ projects, onChange }: {
  projects: Project[]
  /** `select` viaja para que, al renombrar, la barra lateral siga al mismo proyecto. */
  onChange: (select?: string) => void
}) {
  const [form, setForm] = useState<Project | null>(null)
  const [original, setOriginal] = useState<string | null>(null)  // null = alta; si no, edición
  const [error, setError] = useState("")

  const open = (p: Project | null) => {
    setForm(p ? { ...p, repos: p.repos.map(r => ({ ...r })) } : { ...EMPTY, repos: [{ ...EMPTY.repos[0] }] })
    setOriginal(p?.name ?? null)
    setError("")
  }
  const fail = (e: unknown) => setError(String(e))
  const patch = (fn: (rs: Repo[]) => Repo[]) =>
    setForm(f => f ? { ...f, repos: fn(f.repos) } : f)

  const save = () => form && api
    // las filas en blanco se descartan aquí; el backend rechaza rutas que no existan
    .saveProject({ ...form, repos: form.repos.filter(r => r.path.trim()) }, original)
    .then(p => { setForm(null); onChange(p.name) }).catch(fail)
  const remove = (name: string) => api.removeProject(name).then(() => onChange()).catch(fail)

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-base">Proyectos</CardTitle>
        <Button size="sm" variant="outline" onClick={() => open(null)}>Agregar proyecto</Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {projects.map(p => (
          <div key={p.name} className="flex items-center gap-2 text-sm">
            <span className="font-medium">{p.name}</span>
            <span className="text-gray-500">{p.org}/{p.project}</span>
            <span className="text-xs text-gray-400"
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
          <p className="text-sm text-gray-500">Sin proyectos. Agrega uno para poder encolar tickets.</p>
        )}

        {form && (
          <div className="space-y-4 rounded-md border p-4">
            <Campo label="Nombre del proyecto" hint="como quieras llamarlo tú; puedes cambiarlo">
              <Input placeholder="p. ej. TMS" value={form.name}
                     onChange={e => setForm({ ...form, name: e.target.value })} />
            </Campo>

            <div className="grid grid-cols-2 gap-3">
              <Campo label="Organización de Azure DevOps">
                <Input placeholder="ProvidenceSolutions" value={form.org}
                       onChange={e => setForm({ ...form, org: e.target.value })} />
              </Campo>
              <Campo label="Proyecto de Azure DevOps" hint="donde viven los tickets">
                <Input placeholder="ProvidenceTMS" value={form.project}
                       onChange={e => setForm({ ...form, project: e.target.value })} />
              </Campo>
            </div>

            <div>
              <p className="text-xs font-medium">Repos del proyecto</p>
              <p className="mb-2 text-xs text-gray-500">
                El marcado como <strong>principal</strong> es donde corre el agente y donde se
                escribe el análisis; los demás los lee. La descripción viaja al prompt y es lo
                que le dice cuándo mirar en cada uno.
              </p>

              <div className="space-y-1">
                <div className="flex gap-2 text-[11px] uppercase tracking-wide text-gray-400">
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
                              const quedan = rs.filter((_, j) => j !== i)
                              // si se va el principal, el primero que quede toma el relevo
                              return quedan.some(x => x.primary)
                                ? quedan
                                : quedan.map((x, j) => ({ ...x, primary: j === 0 }))
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
