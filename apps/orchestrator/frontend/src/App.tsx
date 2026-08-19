import { useEffect, useRef, useState } from "react"
import { api, type ActiveRun, type Project, type Ticket, type TicketDetail as Detail } from "@/api"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Home } from "@/Home"
import { ProjectForm } from "@/ProjectForm"
import { ProjectHeader } from "@/ProjectHeader"
import { Settings } from "@/Settings"
import { TicketDetail } from "@/TicketDetail"
import { TicketList } from "@/TicketList"
import { TopBar, type Crumb } from "@/TopBar"
import { go, parseRoute, setGuard, useRoute } from "@/router"

export default function App() {
  const route = useRoute()
  const [projects, setProjects] = useState<Project[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  // User-initiated actions and the project load land here. What does NOT is the 3-second
  // poll: it retries on its own, and a banner for a transient blip is noise that trains
  // you to ignore the banner. Loading the projects is different — it runs on mount and
  // after saving, and failing silently there leaves an empty app with no explanation.
  const [error, setError] = useState("")

  // The project form reports whether it has unsaved changes, and the router's guard
  // holds every route change back until they're resolved — the top bar, the breadcrumb
  // and the browser's own back button alike, which is why this stopped being a wrapper
  // around the sidebar's click handlers. Moving WITHIN the form (create → edit) is
  // allowed: there's nothing to lose that the form isn't already holding.
  const dirty = useRef(false)
  const [pendingHash, setPendingHash] = useState<string | null>(null)

  useEffect(() => {
    setGuard(next => {
      if (!dirty.current || parseRoute(next).kind === "projectForm") return true
      setPendingHash(next)
      return false
    })
    return () => setGuard(null)
  }, [])

  const leaveForm = () => {
    dirty.current = false
    const to = pendingHash
    setPendingHash(null)
    if (to !== null) location.hash = to
  }

  const refreshProjects = () =>
    api.projects().then(setProjects).catch(e => setError(String(e)))

  const ticketId = route.kind === "ticket" ? route.id : null
  const refresh = () => {
    api.tickets().then(setTickets).catch(() => {})
    api.activeRun().then(setActiveRun).catch(() => {})
    if (ticketId !== null) api.detail(ticketId).then(setDetail).catch(() => setDetail(null))
  }

  useEffect(() => { refreshProjects() }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.kind, ticketId])

  // On a project route the URL names it; on a ticket route the ticket does, through the
  // ADO project it locked in when it was created.
  // ponytail: today the catalog name and the ADO project match one-to-one; if they ever
  // diverge, tickets need a `project_key`.
  const project =
    route.kind === "project" ? projects.find(p => p.name === route.name) ?? null
    : detail ? projects.find(p => p.project === detail.ticket.project) ?? null
    : null

  const act = (fn: () => Promise<unknown>) => {
    setError("")
    return fn().then(refresh).catch(e => setError(String(e)))
  }

  const crumbs: Crumb[] =
    route.kind === "home" ? []
    : route.kind === "settings" ? [{ label: "Ajustes" }]
    : route.kind === "projectForm"
      ? [{ label: "Proyectos", to: { kind: "home" } },
         { label: route.name ?? "Nuevo proyecto" }]
    : route.kind === "project" ? [{ label: "Proyectos", to: { kind: "home" } },
                                  { label: route.name }]
    : [{ label: "Proyectos", to: { kind: "home" } },
       ...(project ? [{ label: project.name, to: { kind: "project" as const, name: project.name } }] : []),
       { label: detail ? `#${detail.ticket.ado_id}` : "…" }]

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 p-6">
      <TopBar crumbs={crumbs} />

      <main className="min-w-0 space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-sm border border-destructive/40
                          bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <span className="flex-1">{error}</span>
            <button onClick={() => setError("")} aria-label="Descartar el error"
                    className="rounded px-1 focus-visible:outline-1 focus-visible:outline-ring">✕</button>
          </div>
        )}

        {route.kind === "home" && (
          <Home projects={projects} tickets={tickets} activeRun={activeRun}
                onChange={refreshProjects} />
        )}

        {route.kind === "settings" && <Settings />}

        {route.kind === "projectForm" && (
          <ProjectForm initial={projects.find(p => p.name === route.name) ?? null}
                       onDirtyChange={d => { dirty.current = d }}
                       onSaved={() => {
                         dirty.current = false
                         refreshProjects()
                         go({ kind: "home" })
                       }}
                       onCancel={() => { dirty.current = false; go({ kind: "home" }) }} />
        )}

        {route.kind === "project" && !project && (
          <p className="text-sm text-muted-foreground">
            No hay ningún proyecto llamado «{route.name}».{" "}
            <a className="underline" href="#/">Volver al inicio</a>
          </p>
        )}

        {route.kind === "project" && project && (
          <>
            <ProjectHeader project={project} />
            <TicketList tickets={tickets.filter(t => t.project === project.project)}
                        activeRun={activeRun} onOpen={id => go({ kind: "ticket", id })}
                        onAdd={body => act(() => api.create(body, project.name))}
                        onRun={id => act(() => api.run(id))} />
          </>
        )}

        {route.kind === "ticket" && !detail && (
          <p className="text-sm text-muted-foreground">Cargando el ticket…</p>
        )}

        {route.kind === "ticket" && detail && (
          <TicketDetail detail={detail} activeRun={activeRun}
                        onRun={(ins, phase, resume) => act(() => api.run(detail.ticket.id, ins, phase, resume))}
                        onDelete={() => {
                          act(() => api.remove(detail.ticket.id))
                          go(project ? { kind: "project", name: project.name } : { kind: "home" })
                        }}
                        // NOT through `act`: that helper swallows the error into the global banner, and
                        // TicketDetail needs the 409 to decide whether to offer the overwrite dialog.
                        onRestore={(runId, overwrite) => api.restore(detail.ticket.id, runId, overwrite).then(() => refresh())} />
        )}
      </main>

      {/* Same wording and same component the form uses for Cancelar and Escape: leaving
          by a third route shouldn't feel like a different question. */}
      <ConfirmDialog open={pendingHash !== null} title="Hay cambios sin guardar."
                     body="Si sales ahora se pierden." confirmLabel="Descartar"
                     onConfirm={leaveForm}
                     onCancel={() => setPendingHash(null)} />
    </div>
  )
}
