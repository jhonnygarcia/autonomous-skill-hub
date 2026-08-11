import type { ActiveRun, Fase, Ticket } from "@/api"

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

/** `queued` significa dos cosas en el backend — recién añadido y a punto de correr.
 *  La corrida activa lo desambigua sin pedir nada nuevo a la API. */
export function estado(t: Ticket, activo: ActiveRun | null) {
  const label = activo?.ticket_id === t.id ? "corriendo" : (LABEL[t.status] ?? t.status)
  return { label, color: COLOR[label] ?? COLOR.registrado }
}

/** Motivo por el que hay una corrida activa que bloquea, o "" si no la hay. Compartido
 *  por `bloqueo` y `puedeLanzar`: las dos frases ("esta corrida ya está en marcha" /
 *  "esperando a #N en proyecto") vivían duplicadas literalmente en ambas. */
function motivoCorridaActiva(activo: ActiveRun | null, ticketId: number): string {
  if (!activo) return ""
  if (activo.ticket_id === ticketId) return "esta corrida ya está en marcha"
  return `esperando a #${activo.ado_id} en ${activo.project}`
}

/** Motivo por el que NO se puede lanzar, o "" si sí se puede. El lock es global:
 *  lo que bloquea puede estar en un proyecto que ni siquiera estás mirando. */
export function bloqueo(t: Ticket, activo: ActiveRun | null): string {
  return motivoCorridaActiva(activo, t.id)
}

/** Los estados de una corrida son los suyos (queued/running/success/error), no los del ticket. */
export function colorCorrida(status: string): string {
  return status === "success" ? COLOR.analizado
    : status === "error" ? COLOR.error
    : status === "running" ? COLOR.corriendo
    : COLOR.registrado
}

/** `Xm00s` o `Xs`: la misma expresión que usaban por separado `duracion` (a partir de
 *  dos ISO) y `Timeline.tsx` (a partir de `duracion_s`, ya calculado por el backend). */
export function duracionTexto(s: number): string {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m${String(s % 60).padStart(2, "0")}s`
}

export function duracion(desde: string | null, hasta: string | null): string {
  if (!desde || !hasta) return ""
  return duracionTexto(Math.round((Date.parse(hasta) - Date.parse(desde)) / 1000))
}

/** Las cinco fases del pipeline, con el nombre que se le enseña al usuario.
 *  `test` desapareció el 2026-08-11: las pruebas se escriben dentro de `implement`,
 *  porque cada tarea del plan trae su comprobación. No era una fase, era un paso. */
export const FASE_LABEL: Record<string, string> = {
  analyze: "Análisis", design: "Plan", implement: "Código",
  guards: "Revisión", pr: "PR",
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
  return estado === "ok" ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-700 dark:text-emerald-500"
    : estado === "parcial" ? "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-500"
    : estado === "error" ? "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-500"
    : estado === "corriendo" ? "border-blue-500/60 bg-blue-500/10 text-blue-700 dark:text-blue-500"
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
  const m = motivoCorridaActiva(activo, ticketId)
  if (m) return m
  const previa = fases.slice(0, i).filter(p => p.disponible).pop()
  if (previa && previa.estado !== "ok" && previa.estado !== "parcial") {
    return `necesita ${FASE_LABEL[previa.fase]} en verde`
  }
  return ""
}
