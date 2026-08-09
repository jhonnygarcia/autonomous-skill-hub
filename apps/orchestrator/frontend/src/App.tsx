import { useEffect, useState } from "react"
import { api, type ActiveRun, type Project, type Ticket, type TicketDetail as Detail } from "@/api"
import { ProjectHeader } from "@/ProjectHeader"
import { Projects } from "@/Projects"
import { Sidebar } from "@/Sidebar"
import { TicketDetail } from "@/TicketDetail"
import { TicketList } from "@/TicketList"

// Tres vistas conmutadas a mano. Sin router: es una app local de un usuario y
// `react-router` sería una dependencia a cambio de nada.
type View =
  | { kind: "proyecto" }
  | { kind: "ticket"; id: number }
  | { kind: "ajustes" }

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [activo, setActivo] = useState<ActiveRun | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [view, setView] = useState<View>({ kind: "proyecto" })
  const [error, setError] = useState("")

  const fail = (e: unknown) => setError(String(e))

  const refreshProjects = () =>
    api.projects().then(ps => {
      setProjects(ps)
      setCurrent(c => ps.some(p => p.name === c) ? c : (ps[0]?.name ?? null))
    }).catch(fail)

  const refresh = () => {
    api.tickets().then(setTickets).catch(fail)
    api.activeRun().then(setActivo).catch(fail)
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
  // El ticket guarda el proyecto de ADO, no la clave del catálogo.
  // ponytail: hoy coinciden; si algún día difieren, hace falta `project_key` en tickets.
  const míos = project ? tickets.filter(t => t.project === project.project) : []

  const act = (fn: () => Promise<unknown>) => { setError(""); return fn().then(refresh).catch(fail) }

  const addTicket = (adoId: number) =>
    project && act(() => api.create(adoId, project.name))

  const open = (id: number) => { setDetail(null); setView({ kind: "ticket", id }) }
  const back = () => { setDetail(null); setView({ kind: "proyecto" }) }

  return (
    <div className="mx-auto flex max-w-7xl gap-5 p-6">
      <Sidebar projects={projects} current={current} settings={view.kind === "ajustes"}
               onSelect={n => { setCurrent(n); back() }}
               onNew={() => setView({ kind: "ajustes" })}
               onSettings={() => setView({ kind: "ajustes" })} />

      <main className="min-w-0 flex-1 space-y-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {view.kind === "ajustes" && (
          <Projects projects={projects} onChange={refreshProjects} />
        )}

        {view.kind !== "ajustes" && !project && (
          <p className="text-sm text-gray-500">
            Aún no hay proyectos.{" "}
            <button className="underline" onClick={() => setView({ kind: "ajustes" })}>
              Agrega uno
            </button>{" "}
            para poder encolar tickets.
          </p>
        )}

        {view.kind === "proyecto" && project && (
          <>
            <ProjectHeader project={project} />
            <TicketList tickets={míos} activo={activo} onAdd={addTicket} onOpen={open}
                        onRun={id => act(() => api.run(id))} />
          </>
        )}

        {view.kind === "ticket" && project && detail && (
          <TicketDetail detail={detail} activo={activo} projectName={project.name}
                        onBack={back}
                        onRun={ins => act(() => api.run(detail.ticket.id, ins))}
                        onDelete={() => { act(() => api.remove(detail.ticket.id)); back() }} />
        )}
      </main>
    </div>
  )
}
