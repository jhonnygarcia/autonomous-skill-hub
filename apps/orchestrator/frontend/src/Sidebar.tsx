import type { Project } from "@/api"
import { Button } from "@/components/ui/button"

export function Sidebar({ projects, current, settings, onSelect, onNew, onSettings }: {
  projects: Project[]
  current: string | null
  settings: boolean
  onSelect: (name: string) => void
  onNew: () => void
  onSettings: () => void
}) {
  const row = "w-full rounded-md px-2 py-1.5 text-left text-sm"
  return (
    <aside className="flex w-56 shrink-0 flex-col gap-1 border-r pr-3">
      <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Proyectos
      </p>

      {projects.map(p => (
        <button key={p.name} onClick={() => onSelect(p.name)}
                className={`${row} ${p.name === current && !settings
                  ? "bg-gray-900 font-medium text-white" : "hover:bg-gray-100"}`}>
          {p.name}
        </button>
      ))}
      {projects.length === 0 && (
        <p className="px-2 py-1 text-xs text-gray-400">Ninguno todavía</p>
      )}

      <Button size="sm" variant="outline" className="mt-1" onClick={onNew}>+ Nuevo</Button>

      <button onClick={onSettings}
              className={`${row} mt-auto ${settings ? "bg-gray-100 font-medium" : "hover:bg-gray-100"}`}>
        ⚙ Ajustes
      </button>
    </aside>
  )
}
