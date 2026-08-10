import type { ActiveRun, Fase, Ticket } from "@/api"

const COLOR: Record<string, string> = {
  registrado: "bg-gray-100 text-gray-700",
  corriendo: "bg-blue-100 text-blue-800",
  analizado: "bg-green-100 text-green-800",
  planificado: "bg-violet-100 text-violet-800",
  error: "bg-red-100 text-red-800",
}
const LABEL: Record<string, string> = {
  queued: "registrado", running: "corriendo", analyzed: "analizado",
  planned: "planificado", error: "error",
}

/** `queued` significa dos cosas en el backend — recién añadido y a punto de correr.
 *  La corrida activa lo desambigua sin pedir nada nuevo a la API. */
export function estado(t: Ticket, activo: ActiveRun | null) {
  const label = activo?.ticket_id === t.id ? "corriendo" : (LABEL[t.status] ?? t.status)
  return { label, color: COLOR[label] ?? "bg-gray-100 text-gray-700" }
}

/** Motivo por el que NO se puede lanzar, o "" si sí se puede. El lock es global:
 *  lo que bloquea puede estar en un proyecto que ni siquiera estás mirando. */
export function bloqueo(t: Ticket, activo: ActiveRun | null): string {
  if (!activo) return ""
  if (activo.ticket_id === t.id) return "esta corrida ya está en marcha"
  return `esperando a #${activo.ado_id} en ${activo.project}`
}

/** Los estados de una corrida son los suyos (queued/running/success/error), no los del ticket. */
export function colorCorrida(status: string): string {
  return status === "success" ? COLOR.analizado
    : status === "error" ? COLOR.error
    : status === "running" ? COLOR.corriendo
    : COLOR.registrado
}

export function duracion(desde: string | null, hasta: string | null): string {
  if (!desde || !hasta) return ""
  const s = Math.round((Date.parse(hasta) - Date.parse(desde)) / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`
}

/** Las seis fases del pipeline, con el nombre que se le enseña al usuario. */
export const FASE_LABEL: Record<string, string> = {
  analyze: "Análisis", design: "Plan", implement: "Código",
  test: "Pruebas", guards: "Revisión", pr: "PR",
}

/** Qué se lee bajo la fila cuando la fase dejó algo. */
export const FASE_NOUN: Record<string, string> = {
  analyze: "análisis", design: "plan",
}

/** Tamaño legible de un artefacto: bytes, KB o MB. */
export function tamaño(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Hora local corta, para la marca de cada corrida en la fila de una fase. */
export function hora(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  })
}

export function iconoFase(estado?: string): string {
  return estado === "ok" ? "✓" : estado === "parcial" ? "!" : estado === "error" ? "✕"
    : estado === "corriendo" ? "·" : "—"
}

export function colorFase(estado?: string): string {
  return estado === "ok" ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-700"
    : estado === "parcial" ? "border-amber-500/60 bg-amber-500/10 text-amber-700"
    : estado === "error" ? "border-red-500/60 bg-red-500/10 text-red-700"
    : estado === "corriendo" ? "border-blue-500/60 bg-blue-500/10 text-blue-700"
    : "border-border bg-muted text-muted-foreground"
}

/**
 * Motivo por el que NO se puede lanzar esta fase, o "" si sí se puede. Generaliza al
 * viejo `puedePlanificar`, cuya regla —"solo con análisis hecho"— era un caso particular
 * de esto: una fase se lanza si está disponible, no hay corrida activa, y la anterior
 * quedó en `ok` o `parcial`. La primera fase no tiene anterior, así que siempre se puede.
 */
export function puedeLanzar(
  fases: Fase[], i: number, activo: ActiveRun | null, ticketId: number,
): string {
  const f = fases[i]
  if (!f.disponible) return "esta fase todavía no existe"
  if (activo) {
    return activo.ticket_id === ticketId ? "esta corrida ya está en marcha"
      : `esperando a #${activo.ado_id} en ${activo.project}`
  }
  const previa = fases.slice(0, i).filter(p => p.disponible).pop()
  if (previa && previa.estado !== "ok" && previa.estado !== "parcial") {
    return `necesita ${FASE_LABEL[previa.fase]} en verde`
  }
  return ""
}
