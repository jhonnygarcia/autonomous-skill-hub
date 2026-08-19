import { useState } from "react"
import { api, type ActiveRun, type Project, type Ticket } from "@/api"
import { ConfirmDialog } from "@/ConfirmDialog"
import { go, href } from "@/router"

// The system's one dark surface per page (DESIGN.md: "a narrative device, not a chrome
// treatment"), and the brand's only iconography is type. So the wordmark is type too.
const WORDMARK = [
  "█▀█ █▀█ █▀█ █ █ █▀▀ █▀▀ ▀█▀ █▀█ █▀▄ █▀█ █▀█",
  "█ █ █▀▄ █ █ █ █ █▀▀ ▀▀█  █  █▀█ █ █ █ █ █▀▄",
  "▀▀▀ ▀ ▀ ▀▀█  ▀  ▀▀▀ ▀▀▀  ▀  ▀ ▀ ▀▀  ▀▀▀ ▀ ▀",
].join("\n")

/**
 * The landing screen, and the ONE place projects are listed, created, edited and
 * deleted. Ajustes used to carry a second copy of that list; two lists of the same
 * thing means one of them is wrong the moment they disagree, and the top bar's own
 * `+ Nuevo proyecto` followed you into screens (a ticket's timeline) where creating a
 * project is not a thing anyone is about to do.
 */
export function Home({ projects, tickets, activeRun, onChange }: {
  projects: Project[]
  tickets: Ticket[]
  activeRun: ActiveRun | null
  onChange: () => void
}) {
  const [toDelete, setToDelete] = useState<string | null>(null)
  const [error, setError] = useState("")

  const remove = (name: string) => {
    setToDelete(null)
    api.removeProject(name).then(onChange).catch(e => setError(String(e)))
  }

  const action = "rounded-sm border border-border px-2 py-1 text-xs " +
    "hover:bg-secondary focus-visible:outline-1 focus-visible:outline-ring"

  return (
    <div className="space-y-8">
      {/* `--tui` is the dark surface in BOTH themes — this block is the TUI mockup, not
          a primary action, and `bg-primary` inverts to cream once the canvas is ink. */}
      <div className="bg-tui px-6 py-10 text-tui-foreground">
        <pre className="overflow-x-auto text-[10px] leading-tight sm:text-xs">{WORDMARK}</pre>
        <div className="mt-6 max-w-xl rounded-sm bg-tui-foreground/10 px-3 py-2 text-xs">
          {activeRun
            ? <>│ corriendo #{activeRun.ado_id} · {activeRun.project}</>
            : <>│ sin corridas activas · el runner corre una a la vez</>}
        </div>
        <p className="mt-4 text-xs text-tui-foreground/60">
          elige un proyecto para encolar tickets · [*] ajustes para engines, modelos y archivo
        </p>
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-bold uppercase tracking-wide">
            <span className="text-muted-foreground">[x]</span> Proyectos
          </h2>
          <button className={`${action} ml-auto bg-primary text-primary-foreground hover:bg-primary/80`}
                  onClick={() => go({ kind: "projectForm", name: null })}>
            [+] Nuevo proyecto
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-sm border border-destructive/40
                          bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="flex-1">{error}</span>
            <button onClick={() => setError("")} aria-label="Descartar el error"
                    className="rounded px-1 focus-visible:outline-1 focus-visible:outline-ring">✕</button>
          </div>
        )}

        {projects.map(p => {
          const mine = tickets.filter(t => t.project === p.project)
          const open = mine.filter(t => t.status !== "implemented").length
          const main = p.repos.find(r => r.primary) ?? p.repos[0]
          return (
            <div key={p.name} className="border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <a href={href({ kind: "project", name: p.name })}
                   className="font-bold hover:underline focus-visible:outline-1 focus-visible:outline-ring">
                  {p.name}
                </a>
                <span className="text-xs text-muted-foreground">{p.org}/{p.project}</span>
                <span className="text-xs text-muted-foreground">
                  · {mine.length} tickets · {open} abiertos
                </span>
                <div className="ml-auto flex items-center gap-2">
                  <button className={action}
                          onClick={() => go({ kind: "projectForm", name: p.name })}>
                    [/] Editar
                  </button>
                  {/* Separated from `Editar` and muted: it used to sit right next to it,
                      same size and same weight, and it executed on the first click. */}
                  <button className={`${action} text-muted-foreground hover:text-destructive`}
                          onClick={() => setToDelete(p.name)}>
                    [-] Borrar
                  </button>
                </div>
              </div>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                principal: <span className="text-foreground">{main?.path ?? "sin repos"}</span>
                {p.repos.length > 1 && <> · +{p.repos.length - 1} montados</>}
              </p>
            </div>
          )
        })}

        {projects.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Aún no hay proyectos. Agrega uno para poder encolar tickets.
          </p>
        )}
      </section>

      <ConfirmDialog open={!!toDelete} title={`¿Borrar el proyecto "${toDelete}"?`}
                     body="Los tickets ya creados no se rompen: cada uno guardó su propia
                           copia de los datos. Pero no vas a poder encolar nuevos."
                     onConfirm={() => toDelete && remove(toDelete)}
                     onCancel={() => setToDelete(null)} />
    </div>
  )
}
