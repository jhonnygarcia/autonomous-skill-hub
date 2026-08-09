export type Ticket = {
  id: number; ado_id: number; org: string; project: string
  current_phase: string; status: string; created_at: string; updated_at: string
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
}
export type TicketDetail = { ticket: Ticket; runs: Run[]; log_tail: string }
// La etiqueta no es decorativa: viaja al prompt del agente y es lo que le dice
// cuándo mirar en ese repo. Sin ella lo monta y lo ignora.
export type ExtraDir = { path: string; label: string }
export type Project = {
  name: string; org: string; project: string
  repoPath: string          // repo primario: cwd de la corrida y donde se escribe el análisis
  extraDirs: ExtraDir[]     // repos hermanos que el ticket necesita leer (--add-dir)
}

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
  detail: (id: number) => fetch(`/api/tickets/${id}`).then(r => json<TicketDetail>(r)),
  create: (ado_id: number, project: string) =>
    fetch("/api/tickets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ado_id, project }),
    }).then(r => json<Ticket>(r)),
  run: (id: number, instructions?: string) =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null }),
    }).then(r => json<Run>(r)),
  remove: (id: number) => fetch(`/api/tickets/${id}`, { method: "DELETE" }).then(r => json<void>(r)),
}
