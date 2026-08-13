import { useEffect, useState } from "react"
import { api, type ActiveRun, type Project, type Ticket, type TicketDetail as Detail } from "@/api"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Models } from "@/Models"
import { ProjectForm } from "@/ProjectForm"
import { ProjectHeader } from "@/ProjectHeader"
import { Projects } from "@/Projects"
import { Sidebar } from "@/Sidebar"
import { TicketDetail } from "@/TicketDetail"
import { TicketList } from "@/TicketList"

// Four views switched by hand. No router: it's a single-user local app and
// `react-router` would be a dependency for nothing.
type View =
  | { kind: "project" }
  | { kind: "ticket"; id: number }
  | { kind: "settings" }
  // `name: null` = creating. The form used to be a block expanded inside the settings
  // card, which is why `+ Nuevo` had to jump to another view and open it via a prop.
  | { kind: "projectForm"; name: string | null }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [view, setView] = useState<View>({ kind: "project" })
  // User-initiated actions and the project load land here. What does NOT is the 3-second
  // poll: it retries on its own, and a banner for a transient blip is noise that trains
  // you to ignore the banner. Loading the projects is different — it runs on mount and
  // after saving, and failing silently there leaves an empty app with no explanation.
  const [error, setError] = useState("")

  // The project form reports whether it has unsaved changes, and a navigation requested
  // while it does is held here until the user confirms. The form guards its own Cancelar
  // and Escape; without this the sidebar routes around that guard and discards what was
  // typed — same situation, three ways out, and only two of them used to ask.
  const [formDirty, setFormDirty] = useState(false)
  const [pendingNav, setPendingNav] = useState<(() => void) | null>(null)

  const navigate = (go: () => void) => {
    if (view.kind === "projectForm" && formDirty) setPendingNav(() => go)
    else go()
  }

  // `select` is sent by the form after saving, so a rename doesn't change the
  // active project out from under it (the old name is no longer in the list).
  const refreshProjects = (select?: string) =>
    api.projects().then(ps => {
      setProjects(ps)
      setCurrent(c => {
        const wanted = select ?? c
        return ps.some(p => p.name === wanted) ? wanted : (ps[0]?.name ?? null)
      })
    }).catch(e => setError(String(e)))

  const refresh = () => {
    api.tickets().then(setTickets).catch(() => {})
    api.activeRun().then(setActiveRun).catch(() => {})
    if (view.kind === "ticket") api.detail(view.id).then(setDetail).catch(() => setDetail(null))
  }

  useEffect(() => { refreshProjects() }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.kind, view.kind === "ticket" ? view.id : null])

  const project = projects.find(p => p.name === current) ?? null
  // The ticket stores the ADO project, not the catalog key.
  // ponytail: today they match; if they ever diverge, tickets need a `project_key`.
  const myTickets = project ? tickets.filter(t => t.project === project.project) : []

  const act = (fn: () => Promise<unknown>) => {
    setError("")
    return fn().then(refresh).catch(e => setError(String(e)))
  }

  const addTicket = (adoId: number) =>
    project && act(() => api.create(adoId, project.name))

  const open = (id: number) => { setDetail(null); setView({ kind: "ticket", id }) }
  const back = () => { setDetail(null); setView({ kind: "project" }) }
  const editing = view.kind === "projectForm" ? view.name : null

  return (
    <div className="mx-auto flex w-full max-w-[92rem] gap-6 p-6">
      <Sidebar projects={projects} current={current}
               settings={view.kind === "settings" || view.kind === "projectForm"}
               onSelect={n => navigate(() => { setCurrent(n); back() })}
               onSettings={() => navigate(() => setView({ kind: "settings" }))} />

      <main className="min-w-0 flex-1 space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40
                          bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="flex-1">{error}</span>
            <button onClick={() => setError("")} aria-label="Descartar el error"
                    className="rounded px-1 focus-visible:outline-none focus-visible:ring-2
                               focus-visible:ring-ring/50">✕</button>
          </div>
        )}

        {view.kind === "settings" && (
          <>
            <Projects projects={projects}
                      onEdit={name => setView({ kind: "projectForm", name })}
                      onNew={() => setView({ kind: "projectForm", name: null })}
                      onChange={() => refreshProjects()} />
            <Models />
          </>
        )}

        {view.kind === "projectForm" && (
          <ProjectForm initial={projects.find(p => p.name === editing) ?? null}
                       onDirtyChange={setFormDirty}
                       onSaved={name => { refreshProjects(name); setView({ kind: "settings" }) }}
                       onCancel={() => setView({ kind: "settings" })} />
        )}

        {(view.kind === "project" || view.kind === "ticket") && !project && (
          <p className="text-sm text-muted-foreground">
            Aún no hay proyectos.{" "}
            <button className="underline" onClick={() => setView({ kind: "projectForm", name: null })}>
              Agrega uno
            </button>{" "}
            para poder encolar tickets.
          </p>
        )}

        {view.kind === "project" && project && (
          <>
            <ProjectHeader project={project} />
            <TicketList tickets={myTickets} activeRun={activeRun} onAdd={addTicket} onOpen={open}
                        onRun={id => act(() => api.run(id))} />
          </>
        )}

        {view.kind === "ticket" && project && detail && (
          <TicketDetail detail={detail} activeRun={activeRun} projectName={project.name}
                        onBack={back}
                        onRun={(ins, phase, resume) => act(() => api.run(detail.ticket.id, ins, phase, resume))}
                        onDelete={() => { act(() => api.remove(detail.ticket.id)); back() }} />
        )}
      </main>

      {/* Same wording and same component the form uses for Cancelar and Escape: leaving
          by a third route shouldn't feel like a different question. */}
      <ConfirmDialog open={!!pendingNav} title="Hay cambios sin guardar."
                     body="Si sales ahora se pierden." confirmLabel="Descartar"
                     onConfirm={() => { const go = pendingNav; setPendingNav(null); go?.() }}
                     onCancel={() => setPendingNav(null)} />
    </div>
  )
}
