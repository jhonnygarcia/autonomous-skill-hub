import type { ActiveRun, Ticket } from "@/api"

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

/** La Fase 2 lee el análisis de la Fase 1: sin análisis no hay nada que planificar.
 *  `planned` también vale — re-planificar es legítimo si cambió el análisis. Y un
 *  ticket en `error` cuya última corrida fue `design` también: la Fase 2 falló a
 *  medias y la única salida no puede ser re-correr toda la Fase 1 de nuevo. */
export function puedePlanificar(t: Ticket, ultimaFase?: string): boolean {
  return t.status === "analyzed" || t.status === "planned"
    || (t.status === "error" && ultimaFase === "design")
}
