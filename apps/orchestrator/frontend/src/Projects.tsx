import { useState } from "react"
import { api, type ExtraDir, type Project } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

const EMPTY: Project = { name: "", org: "", project: "", repoPath: "", extraDirs: [] }
const describe = (d: ExtraDir) => d.path + (d.label ? ` — ${d.label}` : "")

export function Projects({ projects, onChange }: { projects: Project[]; onChange: () => void }) {
  const [form, setForm] = useState<Project | null>(null)
  const [original, setOriginal] = useState<string | null>(null)  // null = alta; si no, edición
  const [error, setError] = useState("")

  const open = (p: Project | null) => { setForm(p ? { ...p } : { ...EMPTY }); setOriginal(p?.name ?? null); setError("") }
  const fail = (e: unknown) => setError(String(e))
  const patchDirs = (fn: (ds: ExtraDir[]) => ExtraDir[]) =>
    setForm(f => f ? { ...f, extraDirs: fn(f.extraDirs) } : f)

  const save = () => form && api
    // las filas en blanco se descartan aquí; el backend rechaza rutas que no existen
    .saveProject({ ...form, extraDirs: form.extraDirs.filter(d => d.path.trim()) }, original)
    .then(() => { setForm(null); onChange() }).catch(fail)
  const remove = (name: string) => api.removeProject(name).then(onChange).catch(fail)

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
            <span className="truncate text-xs text-gray-400" title={p.repoPath}>{p.repoPath}</span>
            {p.extraDirs.length > 0 && (
              <span className="text-xs text-gray-400"
                    title={p.extraDirs.map(describe).join("\n")}>
                +{p.extraDirs.map(d => d.label || "sin etiqueta").join(", ")}
              </span>
            )}
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
          <div className="space-y-3 rounded-md border p-3">
            <div className="grid grid-cols-3 gap-2">
              {/* El nombre es la clave del catálogo: renombrar = borrar y volver a crear. */}
              <Input placeholder="Nombre" value={form.name} disabled={!!original}
                     onChange={e => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="Organización ADO" value={form.org}
                     onChange={e => setForm({ ...form, org: e.target.value })} />
              <Input placeholder="Proyecto ADO" value={form.project}
                     onChange={e => setForm({ ...form, project: e.target.value })} />
            </div>

            <div>
              <p className="mb-1 text-xs font-medium">Repo principal</p>
              <Input placeholder="D:/ruta/al/repo — aquí corre el agente y se escribe el análisis"
                     value={form.repoPath}
                     onChange={e => setForm({ ...form, repoPath: e.target.value })} />
            </div>

            <div>
              <p className="text-xs font-medium">Repos adicionales</p>
              <p className="mb-1 text-xs text-gray-500">
                Solo lectura. La etiqueta viaja al prompt del agente y es lo que le dice
                cuándo mirar ahí — sin ella tiende a ignorarlos.
              </p>
              <div className="space-y-1">
                {form.extraDirs.map((d, i) => (
                  <div key={i} className="flex gap-2">
                    <Input className="flex-1" placeholder="D:/ruta/al/repo" value={d.path}
                           onChange={e => patchDirs(ds =>
                             ds.map((x, j) => j === i ? { ...x, path: e.target.value } : x))} />
                    <Input className="w-64" placeholder="backend, app de autenticación…"
                           value={d.label}
                           onChange={e => patchDirs(ds =>
                             ds.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
                    <Button size="sm" variant="ghost" title="Quitar"
                            onClick={() => patchDirs(ds => ds.filter((_, j) => j !== i))}>
                      ✕
                    </Button>
                  </div>
                ))}
              </div>
              <Button size="sm" variant="outline" className="mt-1"
                      onClick={() => patchDirs(ds => [...ds, { path: "", label: "" }])}>
                + Agregar repo
              </Button>
            </div>

            <div className="flex gap-2">
              <Button size="sm" onClick={save}
                      disabled={!form.name || !form.org || !form.project || !form.repoPath}>
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
