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
