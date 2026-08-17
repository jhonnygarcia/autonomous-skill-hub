export type Ticket = {
  id: number
  // number for Azure work items, the string key ("R-7") for local requests — the
  // backend returns each as stored, and every use here is display.
  ado_id: number | string
  origen: "ado" | "local"
  request: string | null
  org: string; project: string
  status: string; created_at: string; updated_at: string
  /** Read from the analysis when `analyze` closes well. `null` before that: we don't
   *  know what the ticket is about yet, and saying so is honest. */
  title: string | null
  /** Per-phase state, for the list's three-dot stepper. Same shape as the detail
   *  view's `fases`, but built with `with_footprint=False`: cheap enough to compute
   *  for every ticket on every poll. */
  fases: Phase[]
}
export type Run = {
  id: number; phase: string; instructions: string | null
  status: string; started_at: string | null; finished_at: string | null
  artifact_state: string | null; artifact_path: string | null
  // Only the phase that prepares the branch (`implement`) sets this; every other
  // run leaves it `null`, which is the normal case, not a missing value.
  branch: string | null
  // The snapshot folder this run left, when the archive was on. `null` is the normal
  // case for every run before the archive existed and for runs with it switched off.
  archive_path: string | null
  // Whether `salida/` actually holds the declared deliverable — NOT the same thing as
  // `archive_path` being set (a fan-out survey's HUELLA is a scratch path outside every
  // repo, so it gets an `archive_path` with nothing restorable inside it). `null` means
  // "nobody checked": every run before this column existed, treated as not-restorable.
  restorable: number | null
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
  /** Did what the stamp declared exist on disk when the run closed? Absent means
   *  nobody checked — a run older than the column — which is not the same as `true`. */
  entregable?: boolean
  /** Only on `implement` and only while running. An estimate: a big task weighs the
   *  same as a small one, so it's shown as a count and never as a percentage. */
  progreso?: { hechas: number; total: number } | null
  /** Unticked markers in the deliverable. Absent when there are none — absence is not
   *  zero, and a phase with nothing to decide must not paint a counter. */
  decisiones?: { decidir: number; bloquea: number }
  /** Whether this phase has a previous session to continue. Computed in the backend:
   *  it's the same condition that decides whether the resume applies or falls back to
   *  fresh, and a second copy here would drift from it. */
  puede_continuar?: boolean
  /** The CURRENT chain of continuations, not the historical total — a fresh run breaks
   *  it. Says how much context has piled up in the session now in play. */
  continuaciones?: number
}
export type Artifact = { ruta: string; texto: string; bytes: number; truncado: boolean }
export type TicketDetail = { ticket: Ticket; fases: Phase[]; runs: Run[]; log_tail: string }
// The runner runs one at a time across ALL projects: this is what lets us explain
// why something can't be launched, instead of failing with a silent 409.
export type ActiveRun = {
  id: number; ticket_id: number; started_at: string | null; ado_id: number | string; project: string
}
// A project has ONE list of repos and you mark which one is primary (the cwd of
// the run). `label` isn't decorative: it travels into the agent's prompt and is
// what tells it when to look in that repo — without it, it's mounted but ignored.
export type Repo = { path: string; label: string; primary: boolean }
export type Project = { name: string; org: string; project: string; repos: Repo[] }
// Which CLI runs each phase, and with what model and effort. Empty model/effort =
// whatever the target repo defaults to, which is what the orchestrator always did
// before this was configurable; `engine` has no empty value, it defaults to claude.
export type PhaseConfig = { engine: string; model: string; effort: string }
export type PhaseModels = Record<string, PhaseConfig>
// The engines the runner knows how to launch, served from the backend's own registry.
// The efforts differ per engine and the list is NOT hardcoded here on purpose: `max`
// is Claude's and Codex rejects it, and a second copy of that table would be free to
// disagree with the one that validates.
export type Engine = { id: string; label: string; efforts: string[] }

/** Thrown by `json()` below. `code` only travels on the one refusal the caller may
 *  legitimately retry (`/restaurar`'s "file already exists"); every other error is
 *  Spanish prose meant for display, not for branching on. */
export class ApiError extends Error {
  code?: string
  constructor(message: string, code?: string) {
    super(message)
    this.code = code
  }
}

const json = async <T,>(r: Response): Promise<T> => {
  if (!r.ok) {
    const detail = (await r.json().catch(() => null))?.detail
    // `detail` is normally a plain Spanish sentence (CLAUDE.md: reworded at will, never
    // matched on). The ONE exception is `/restaurar`'s retryable 409, shaped as
    // `{code, msg}` — a machine-readable marker instead of sniffing a word out of the
    // prose, which broke the day a ticket's own path happened to contain that word.
    const isTagged = detail !== null && typeof detail === "object"
    throw new ApiError(isTagged ? detail.msg : (detail ?? r.statusText),
                        isTagged ? detail.code : undefined)
  }
  return r.status === 204 ? (undefined as T) : r.json()
}

// Contract literal — matches `RESTORE_EXISTS_CODE` in `app.py`. The only `/restaurar`
// 409 the UI may retry with `overwrite: true`.
export const RESTORE_EXISTS_CODE = "existe_archivo"

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
  engines: () => fetch("/api/engines").then(r => json<Engine[]>(r)),
  models: () => fetch("/api/modelos").then(r => json<PhaseModels>(r)),
  saveModels: (m: PhaseModels) =>
    fetch("/api/modelos", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(m),
    }).then(r => json<PhaseModels>(r)),
  archive: () => fetch("/api/archivo").then(r => json<{ dir: string }>(r)),
  saveArchive: (dir: string) =>
    fetch("/api/archivo", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dir }),
    }).then(r => json<{ dir: string }>(r)),
  /** Puts a run's declared deliverable back into the repo from its snapshot. Files
   *  need `overwrite` when the destination exists; a tree is never overwritten. */
  restore: (id: number, runId: number, overwrite = false) =>
    fetch(`/api/tickets/${id}/restaurar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, overwrite }),
    }).then(r => json<{ restaurado: string; archivos: number }>(r)),
  tickets: () => fetch("/api/tickets").then(r => json<Ticket[]>(r)),
  activeRun: () => fetch("/api/runs/active").then(r => json<ActiveRun | null>(r)),
  detail: (id: number) => fetch(`/api/tickets/${id}`).then(r => json<TicketDetail>(r)),
  artifact: (id: number, ruta: string) =>
    fetch(`/api/tickets/${id}/artefacto?ruta=${encodeURIComponent(ruta)}`)
      .then(r => json<Artifact>(r)),
  create: (body: { ado_id?: number; request?: string }, project: string) =>
    fetch("/api/tickets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, project }),
    }).then(r => json<Ticket>(r)),
  run: (id: number, instructions?: string, phase = "analyze", resume = false) =>
    fetch(`/api/tickets/${id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions: instructions || null, phase, resume }),
    }).then(r => json<Run>(r)),
  remove: (id: number) => fetch(`/api/tickets/${id}`, { method: "DELETE" }).then(r => json<void>(r)),
}
