import type { ActiveRun, Phase, Ticket } from "@/api"

const COLOR: Record<string, string> = {
  registrado: "border-border bg-muted text-muted-foreground",
  corriendo: "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-500",
  analizado: "border-emerald-500/60 bg-emerald-500/10 text-emerald-700 dark:text-emerald-500",
  planificado: "border-violet-500/60 bg-violet-500/10 text-violet-700 dark:text-violet-500",
  implementado: "border-sky-500/60 bg-sky-500/10 text-sky-700 dark:text-sky-500",
  error: "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-500",
}
const LABEL: Record<string, string> = {
  queued: "registrado", running: "corriendo", analyzed: "analizado",
  planned: "planificado", implemented: "implementado", error: "error",
}

/** `queued` means two things in the backend — just added and about to run.
 *  The active run disambiguates it without asking the API for anything new. */
export function ticketStatus(t: Ticket, activeRun: ActiveRun | null) {
  const label = activeRun?.ticket_id === t.id ? "corriendo" : (LABEL[t.status] ?? t.status)
  return { label, color: COLOR[label] ?? COLOR.registrado }
}

/** Reason there's an active run that blocks, or "" if there isn't one. Shared by
 *  `blockReason` and `canRunPhase`: the two phrases ("esta corrida ya está en marcha" /
 *  "esperando a #N en proyecto") used to be duplicated literally in both. */
function activeRunReason(activeRun: ActiveRun | null, ticketId: number): string {
  if (!activeRun) return ""
  if (activeRun.ticket_id === ticketId) return "esta corrida ya está en marcha"
  return `esperando a #${activeRun.ado_id} en ${activeRun.project}`
}

/** Reason it CANNOT be launched, or "" if it can. The lock is global: what's
 *  blocking may be in a project you aren't even looking at. */
export function blockReason(t: Ticket, activeRun: ActiveRun | null): string {
  return activeRunReason(activeRun, t.id)
}

/** A run's own states are (queued/running/success/error), not the ticket's. */
export function runColor(status: string): string {
  return status === "success" ? COLOR.analizado
    : status === "error" ? COLOR.error
    : status === "running" ? COLOR.corriendo
    : COLOR.registrado
}

/** `Xm00s` or `Xs`: the same expression that used to be duplicated by `duration`
 *  (from two ISO timestamps) and `Timeline.tsx` (from `duracion_s`, already computed
 *  by the backend). */
export function durationText(s: number): string {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`
}

export function duration(from: string | null, to: string | null): string {
  if (!from || !to) return ""
  return durationText(Math.round((Date.parse(to) - Date.parse(from)) / 1000))
}

/** The pipeline's five phases, with the name shown to the user.
 *  `test` disappeared on 2026-08-11: tests are written inside `implement`,
 *  because each plan task carries its own check. It wasn't a phase, it was a step. */
export const PHASE_LABEL: Record<string, string> = {
  analyze: "Análisis", design: "Plan", implement: "Código",
  guards: "Revisión", pr: "PR",
}

/** Human-readable size of an artifact: bytes, KB or MB. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Short local time, for the timestamp on each run in a phase's row. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  })
}

export function phaseIcon(status?: string): string {
  return status === "ok" ? "✓" : status === "parcial" ? "!" : status === "error" ? "✕"
    : status === "corriendo" ? "·" : "—"
}

export function phaseColor(status?: string): string {
  return status === "ok" ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-700 dark:text-emerald-500"
    : status === "parcial" ? "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-500"
    : status === "error" ? "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-500"
    : status === "corriendo" ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-500"
    : "border-border bg-muted text-muted-foreground"
}

/**
 * Reason this phase CANNOT be launched, or "" if it can. Generalizes the old
 * `puedePlanificar`, whose rule —"only once analysis is done"— was a special case
 * of this: a phase can be launched if it's available, there's no active run, and
 * the previous one landed on `ok` or `parcial`. The first phase has no previous one,
 * so it can always be launched.
 */
export function canRunPhase(
  phases: Phase[], i: number, activeRun: ActiveRun | null, ticketId: number,
): string {
  const f = phases[i]
  if (!f.disponible) return "esta fase todavía no existe"
  const m = activeRunReason(activeRun, ticketId)
  if (m) return m
  const previous = phases.slice(0, i).filter(p => p.disponible).pop()
  if (previous && previous.estado !== "ok" && previous.estado !== "parcial") {
    return `necesita ${PHASE_LABEL[previous.fase]} en verde`
  }
  return ""
}
