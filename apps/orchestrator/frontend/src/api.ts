export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  status: string; created_at: string; updated_at: string
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
  artifact_state: string | null; artifact_path: string | null
  // Solo la fase que prepara rama (`implement`) la deja; el resto de corridas
  // llega en `null`, que es el caso normal, no una ausencia de dato.
  branch: string | null
}
export type Huella = {
  ruta: string; existe: boolean; archivos: number; bytes: number; nombres: string[]
}
// `disponible: false` no lleva estado: una fase que no se puede lanzar no tiene nada
// que informar. El resto de campos solo aparecen si hubo alguna corrida.
export type Fase = {
  fase: string; disponible: boolean
  estado?: "pendiente" | "corriendo" | "ok" | "parcial" | "error"
  corridas?: number; fallidas?: number
  en?: string | null; duracion_s?: number | null; motivo?: string; huella?: Huella
}
export type Artefacto = { ruta: string; texto: string; bytes: number; truncado: boolean }
export type TicketDetail = { ticket: Ticket; fases: Fase[]; runs: Run[]; log_tail: string }
// El runner corre de uno en uno entre TODOS los proyectos: esto es lo que permite
// explicar por qué no se puede lanzar, en vez de fallar con un 409 mudo.
export type ActiveRun = {
  id: number; ticket_id: number; started_at: string | null; ado_id: number; project: string
}
// Un proyecto tiene UNA lista de repos y tú marcas cuál es el principal (el cwd de
// la corrida). `label` no es decorativa: viaja al prompt del agente y es lo que le
// dice cuándo mirar en ese repo — sin ella lo monta y lo ignora.
export type Repo = { path: string; label: string; primary: boolean }
export type Project = { name: string; org: string; project: string; repos: Repo[] }

const json = async <T,>(r: Response): Promise<T> => {
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? r.statusText)
  return r.status === 204 ? (undefined as T) : r.json()
}

export const api = {
  projects: () => fetch("/api/projects").then(r => json<Project[]>(r)),
  saveProject: (p: Project, original: string | null) =>
    fetch(original ? `/api/projects/${encodeURIComponent(original)}` : "/api/projects", {
      method: original ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    }).then(r => json<Project>(r)),
  removeProject: (name: string) =>
    fetch(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" }).then(r => json<void>(r)),
  tickets: () => fetch("/api/tickets").then(r => json<Ticket[]>(r)),
  activeRun: () => fetch("/api/runs/active").then(r => json<ActiveRun | null>(r)),
  detail: (id: number) => fetch(`/api/tickets/${id}`).then(r => json<TicketDetail>(r)),
  artefacto: (id: number, ruta: string) =>
    fetch(`/api/tickets/${id}/artefacto?ruta=${encodeURIComponent(ruta)}`)
      .then(r => json<Artefacto>(r)),
  create: (ado_id: number, project: string) =>
    fetch("/api/tickets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ado_id, project }),
    }).then(r => json<Ticket>(r)),
  run: (id: number, instructions?: string, phase = "analyze") =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null, phase }),
    }).then(r => json<Run>(r)),
  remove: (id: number) => fetch(`/api/tickets/${id}`, { method: "DELETE" }).then(r => json<void>(r)),
}
