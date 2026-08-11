import { useEffect, useState } from "react"
import { api, type ActiveRun, type Project, type Ticket, type TicketDetail as Detail } from "@/api"
import { Models } from "@/Models"
import { ProjectHeader } from "@/ProjectHeader"
import { Projects } from "@/Projects"
import { Sidebar } from "@/Sidebar"
import { TicketDetail } from "@/TicketDetail"
import { TicketList } from "@/TicketList"

// Three views switched by hand. No router: it's a single-user local app and
// `react-router` would be a dependency for nothing.
type View =
  | { kind: "project" }
  | { kind: "ticket"; id: number }
  | { kind: "settings"; isNew?: boolean }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [view, setView] = useState<View>({ kind: "project" })
  const [error, setError] = useState("")

  const fail = (e: unknown) => setError(String(e))

  // `select` is sent by Settings after saving, so a rename doesn't change the
  // active project out from under it (the old name is no longer in the list).
  const refreshProjects = (select?: string) =>
    api.projects().then(ps => {
      setProjects(ps)
      setCurrent(c => {
        const wanted = select ?? c
        return ps.some(p => p.name === wanted) ? wanted : (ps[0]?.name ?? null)
      })
    }).catch(fail)

  const refresh = () => {
    api.tickets().then(setTickets).catch(fail)
    api.activeRun().then(setActiveRun).catch(fail)
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

  const act = (fn: () => Promise<unknown>) => { setError(""); return fn().then(refresh).catch(fail) }

  const addTicket = (adoId: number) =>
    project && act(() => api.create(adoId, project.name))

  const open = (id: number) => { setDetail(null); setView({ kind: "ticket", id }) }
  const back = () => { setDetail(null); setView({ kind: "project" }) }

  return (
    <div className="mx-auto flex w-full max-w-[92rem] gap-6 p-6">
      <Sidebar projects={projects} current={current} settings={view.kind === "settings"}
               onSelect={n => { setCurrent(n); back() }}
               onNew={() => setView({ kind: "settings", isNew: true })}
               onSettings={() => setView({ kind: "settings" })} />

      <main className="min-w-0 flex-1 space-y-4">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {view.kind === "settings" && (
          <>
            {/* the `key` forces a remount when "+ Nuevo" is pressed while already in Settings */}
            <Projects key={view.isNew ? "new" : "list"} projects={projects}
                      startNew={view.isNew} onChange={refreshProjects} />
            <Models />
          </>
        )}

        {view.kind !== "settings" && !project && (
          <p className="text-sm text-muted-foreground">
            Aún no hay proyectos.{" "}
            <button className="underline" onClick={() => setView({ kind: "settings" })}>
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
                        onRun={(ins, phase) => act(() => api.run(detail.ticket.id, ins, phase))}
                        onDelete={() => { act(() => api.remove(detail.ticket.id)); back() }} />
        )}
      </main>
    </div>
  )
}
