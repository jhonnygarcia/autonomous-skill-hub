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
