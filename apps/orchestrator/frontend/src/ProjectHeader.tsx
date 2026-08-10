import type { Project } from "@/api"

/**
 * Los repos que el agente va a montar tienen que estar a la vista JUSTO donde se
 * decide lanzar un ticket — no escondidos en el formulario donde se configuraron.
 */
export function ProjectHeader({ project }: { project: Project }) {
  // el principal primero, que es donde se escribe el análisis
  const repos = [...project.repos].sort((a, b) => Number(b.primary) - Number(a.primary))
  return (
    <div className="space-y-2">
      <div>
        <h2 className="text-xl font-semibold">{project.name}</h2>
        <p className="text-sm text-muted-foreground">{project.org}/{project.project}</p>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-foreground/70">Repos que verá el agente</p>
        <table className="text-xs">
          <tbody>
            {repos.map(r => (
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
        {repos.length === 1 && (
          <p className="mt-1 text-xs text-muted-foreground/70">
            Solo un repo. Se añaden más en Ajustes.
          </p>
        )}
      </div>
    </div>
  )
}
