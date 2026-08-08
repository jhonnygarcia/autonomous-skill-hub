import { useState } from "react"
import { api, type Project } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

const EMPTY: Project = { name: "", org: "", project: "", repoPath: "", extraDirs: [] }

export function Projects({ projects, onChange }: { projects: Project[]; onChange: () => void }) {
  const [form, setForm] = useState<Project | null>(null)
  const [original, setOriginal] = useState<string | null>(null)  // null = alta; si no, edición
  const [error, setError] = useState("")

  const open = (p: Project | null) => { setForm(p ? { ...p } : { ...EMPTY }); setOriginal(p?.name ?? null); setError("") }
  const fail = (e: unknown) => setError(String(e))

  const save = () => form && api.saveProject(form, original)
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
              <span className="text-xs text-gray-400" title={p.extraDirs.join("\n")}>
                +{p.extraDirs.length} repo{p.extraDirs.length > 1 ? "s" : ""}
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
          <div className="space-y-2 rounded-md border p-3">
            <div className="grid grid-cols-3 gap-2">
              {/* El nombre es la clave del catálogo: renombrar = borrar y volver a crear. */}
              <Input placeholder="Nombre" value={form.name} disabled={!!original}
                     onChange={e => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="Organización ADO" value={form.org}
                     onChange={e => setForm({ ...form, org: e.target.value })} />
              <Input placeholder="Proyecto ADO" value={form.project}
                     onChange={e => setForm({ ...form, project: e.target.value })} />
            </div>
            <Input placeholder="Ruta del repo primario — ahí corre el agente y se escribe el análisis"
                   value={form.repoPath}
                   onChange={e => setForm({ ...form, repoPath: e.target.value })} />
            <Textarea rows={2}
                      placeholder="Repos extra que el ticket necesita leer, uno por línea (opcional)"
                      value={form.extraDirs.join("\n")}
                      onChange={e => setForm({
                        ...form,
                        extraDirs: e.target.value.split("\n").map(s => s.trim()).filter(Boolean),
                      })} />
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
