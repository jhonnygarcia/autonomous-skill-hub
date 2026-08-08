import { useEffect, useState } from "react"
import { api, type Project, type Ticket, type TicketDetail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

const PHASES = [
  { key: "analyze", label: "Análisis" }, { key: "design", label: "Diseño" },
  { key: "implement", label: "Implementación" }, { key: "test", label: "Pruebas" },
  { key: "guards", label: "Guards" }, { key: "pr", label: "PR" },
]
const STATUS_COLOR: Record<string, string> = {
  queued: "bg-amber-100 text-amber-800", running: "bg-blue-100 text-blue-800",
  analyzed: "bg-green-100 text-green-800", error: "bg-red-100 text-red-800",
  success: "bg-green-100 text-green-800",
}

function Stepper({ ticket }: { ticket: Ticket }) {
  return (
    <div className="flex items-center gap-1 text-xs">
      {PHASES.map((p, i) => {
        const active = p.key === ticket.current_phase
        const done = active && ticket.status === "analyzed"
        const enabled = i === 0
        return (
          <div key={p.key} className="flex items-center gap-1">
            {i > 0 && <span className="text-gray-300">→</span>}
            <span className={
              done ? "rounded-full bg-green-600 px-2 py-0.5 text-white"
                : active ? "rounded-full bg-blue-600 px-2 py-0.5 text-white"
                : enabled ? "rounded-full bg-gray-200 px-2 py-0.5 text-gray-700"
                : "rounded-full bg-gray-100 px-2 py-0.5 text-gray-400"
            } title={enabled ? p.label : `${p.label} (próximamente)`}>
              {p.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [adoId, setAdoId] = useState("")
  const [project, setProject] = useState("")
  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [instructions, setInstructions] = useState("")
  const [error, setError] = useState("")

  const refresh = () => {
    api.tickets().then(setTickets).catch(e => setError(String(e)))
    if (selected != null) api.detail(selected).then(setDetail).catch(() => setDetail(null))
  }

  useEffect(() => {
    api.projects().then(ps => { setProjects(ps); if (ps[0]) setProject(ps[0].name) })
  }, [])
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected])

  const enqueue = async () => {
    setError("")
    try {
      const t = await api.create(Number(adoId), project)
      setAdoId(""); setSelected(t.id); refresh()
    } catch (e) { setError(String(e)) }
  }
  const act = (fn: () => Promise<unknown>) => fn().then(refresh).catch(e => setError(String(e)))

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">Ticket Orchestrator</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <CardHeader><CardTitle className="text-base">Encolar ticket</CardTitle></CardHeader>
        <CardContent className="flex gap-2">
          <Input className="w-32" placeholder="ID (ej. 3311)" value={adoId}
                 onChange={e => setAdoId(e.target.value)} />
          <select className="rounded-md border px-2 text-sm" value={project}
                  onChange={e => setProject(e.target.value)}>
            {projects.map(p => <option key={p.name}>{p.name}</option>)}
          </select>
          <Button onClick={enqueue} disabled={!adoId || !project}>Agregar</Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          {tickets.map(t => (
            <Card key={t.id} onClick={() => setSelected(t.id)}
                  className={`cursor-pointer ${selected === t.id ? "border-blue-500" : ""}`}>
              <CardContent className="space-y-2 pt-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">#{t.ado_id} · {t.project}</span>
                  <Badge className={STATUS_COLOR[t.status] ?? ""}>{t.status}</Badge>
                </div>
                <Stepper ticket={t} />
              </CardContent>
            </Card>
          ))}
          {tickets.length === 0 && <p className="text-sm text-gray-500">Sin tickets en cola.</p>}
        </div>

        {detail && (
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base">Ticket #{detail.ticket.ado_id}</CardTitle>
              <div className="flex gap-2">
                <Button size="sm" disabled={["queued", "running"].includes(detail.ticket.status)}
                        onClick={() => act(() => api.run(detail.ticket.id))}>
                  {detail.runs.length ? "Re-correr análisis" : "Correr análisis"}
                </Button>
                <Button size="sm" variant="destructive"
                        onClick={() => { act(() => api.remove(detail.ticket.id)); setSelected(null) }}>
                  Borrar
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="mb-1 text-sm font-medium">Ajustar y re-correr</p>
                <Textarea rows={2} placeholder="Describe el problema o ajuste…"
                          value={instructions} onChange={e => setInstructions(e.target.value)} />
                <Button size="sm" className="mt-2"
                        disabled={!instructions || ["queued", "running"].includes(detail.ticket.status)}
                        onClick={() => { act(() => api.run(detail.ticket.id, instructions)); setInstructions("") }}>
                  Enviar ajuste
                </Button>
              </div>
              <div>
                <p className="mb-1 text-sm font-medium">Historial de corridas</p>
                <ul className="space-y-1 text-sm">
                  {detail.runs.map(r => (
                    <li key={r.id} className="flex items-center gap-2">
                      <Badge className={STATUS_COLOR[r.status] ?? ""}>{r.status}</Badge>
                      <span>{r.phase}</span>
                      <span className="text-gray-500">{r.started_at ?? "en cola"}</span>
                      {r.instructions && <span className="truncate text-gray-500" title={r.instructions}>✎ {r.instructions}</span>}
                    </li>
                  ))}
                  {detail.runs.length === 0 && <li className="text-gray-500">Sin corridas aún.</li>}
                </ul>
              </div>
              <div>
                <p className="mb-1 text-sm font-medium">Log</p>
                <pre className="max-h-64 overflow-auto rounded bg-gray-950 p-2 text-xs text-gray-100">
                  {detail.log_tail || "(vacío)"}
                </pre>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
