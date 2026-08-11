import type { Project } from "@/api"

export function Sidebar({ projects, current, settings, onSelect, onSettings }: {
  projects: Project[]
  current: string | null
  settings: boolean
  onSelect: (name: string) => void
  onSettings: () => void
}) {
  const row = "w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
  return (
    <aside className="flex w-56 shrink-0 flex-col gap-1 border-r pr-3">
      <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Proyectos
      </p>

      {projects.map(p => (
        <button key={p.name} onClick={() => onSelect(p.name)}
                className={`${row} ${p.name === current && !settings
                  ? "bg-primary font-medium text-primary-foreground" : "hover:bg-accent"}`}>
          {p.name}
        </button>
      ))}
      {projects.length === 0 && (
        <p className="px-2 py-1 text-xs text-muted-foreground/70">Ninguno todavía</p>
      )}

      <button onClick={onSettings}
              className={`${row} mt-auto ${settings ? "bg-accent font-medium" : "hover:bg-accent"}`}>
        ⚙ Ajustes
      </button>
    </aside>
  )
}
