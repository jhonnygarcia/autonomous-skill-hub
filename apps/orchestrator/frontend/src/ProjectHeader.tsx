import type { Project } from "@/api"

/**
 * Los repos que el agente va a montar tienen que estar a la vista JUSTO donde se
 * decide lanzar un ticket — no escondidos en el formulario donde se configuraron.
 */
export function ProjectHeader({ project }: { project: Project }) {
  const repos = [
    { label: "principal", path: project.repoPath },
    ...project.extraDirs.map(d => ({ label: d.label || "sin etiqueta", path: d.path })),
  ]
  return (
    <div className="space-y-2">
      <div>
        <h2 className="text-xl font-semibold">{project.name}</h2>
        <p className="text-sm text-gray-500">{project.org}/{project.project}</p>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-gray-600">Repos que verá el agente</p>
        <table className="text-xs">
          <tbody>
            {repos.map(r => (
              <tr key={r.path}>
                <td className="pr-3 align-top text-gray-500">{r.label}</td>
                <td className="font-mono text-gray-700">{r.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {project.extraDirs.length === 0 && (
          <p className="mt-1 text-xs text-gray-400">
            Sin repos adicionales. Se añaden en Ajustes.
          </p>
        )}
      </div>
    </div>
  )
}
