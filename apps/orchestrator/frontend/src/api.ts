export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  status: string; created_at: string; updated_at: string
  /** Read from the analysis when `analyze` closes well. `null` before that: we don't
   *  know what the ticket is about yet, and saying so is honest. */
  title: string | null
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
  artifact_state: string | null; artifact_path: string | null
  // Only the phase that prepares the branch (`implement`) sets this; every other
  // run leaves it `null`, which is the normal case, not a missing value.
  branch: string | null
}
export type Footprint = {
  ruta: string; existe: boolean; archivos: number; bytes: number; nombres: string[]
}
// `disponible: false` carries no `estado`: a phase that can't be launched has
// nothing to report. The rest of the fields only show up once there's been a run.
export type Phase = {
  fase: string; disponible: boolean
  estado?: "pendiente" | "corriendo" | "ok" | "parcial" | "error"
  corridas?: number; fallidas?: number
  en?: string | null; duracion_s?: number | null; motivo?: string; huella?: Footprint
}
export type Artifact = { ruta: string; texto: string; bytes: number; truncado: boolean }
export type TicketDetail = { ticket: Ticket; fases: Phase[]; runs: Run[]; log_tail: string }
// The runner runs one at a time across ALL projects: this is what lets us explain
// why something can't be launched, instead of failing with a silent 409.
export type ActiveRun = {
  id: number; ticket_id: number; started_at: string | null; ado_id: number; project: string
}
// A project has ONE list of repos and you mark which one is primary (the cwd of
// the run). `label` isn't decorative: it travels into the agent's prompt and is
// what tells it when to look in that repo — without it, it's mounted but ignored.
export type Repo = { path: string; label: string; primary: boolean }
export type Project = { name: string; org: string; project: string; repos: Repo[] }
// Model and effort each phase is launched with. Empty string = whatever the target
// repo defaults to, which is what the orchestrator always did before this was
// configurable.
export type PhaseConfig = { model: string; effort: string }
export type PhaseModels = Record<string, PhaseConfig>

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
  /** Does this path exist on disk? A courtesy for the form: saving validates again,
   *  and that one is the authoritative check. */
  validatePath: (ruta: string) =>
    fetch("/api/rutas/validar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ruta }),
    }).then(r => json<{ existe: boolean }>(r)).then(x => x.existe),
  models: () => fetch("/api/modelos").then(r => json<PhaseModels>(r)),
  saveModels: (m: PhaseModels) =>
    fetch("/api/modelos", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(m),
    }).then(r => json<PhaseModels>(r)),
  tickets: () => fetch("/api/tickets").then(r => json<Ticket[]>(r)),
  activeRun: () => fetch("/api/runs/active").then(r => json<ActiveRun | null>(r)),
  detail: (id: number) => fetch(`/api/tickets/${id}`).then(r => json<TicketDetail>(r)),
  artifact: (id: number, ruta: string) =>
    fetch(`/api/tickets/${id}/artefacto?ruta=${encodeURIComponent(ruta)}`)
      .then(r => json<Artifact>(r)),
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
