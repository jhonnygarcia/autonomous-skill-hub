/** El idioma de la UI. Vive en la DB (`settings.idioma`, la misma perilla que
 *  gobierna lo que escribe el agente) y se cachea en `localStorage` sólo para
 *  poder pintar el primer frame sin esperar la red. La DB es la fuente de verdad:
 *  si el caché miente, `initLang` lo corrige y recarga. */
export type Lang = "es" | "en"

const KEY = "orq.idioma"
let current: Lang = "es"

export function lang(): Lang {
  return current
}

/** Updates the language both in memory and in localStorage. Silently ignores
 *  invalid values (not "es" or "en"). */
export function setLang(code: unknown): void {
  if (code !== "es" && code !== "en") return
  current = code
  try {
    localStorage.setItem(KEY, code)
  } catch {
    // Storage write failed; the value is in memory, which is enough
  }
}

/** Resuelve el idioma antes del primer render. Arranca con lo cacheado —si no hay
 *  nada, español, que es el default del backend— y consulta la DB después. Sin el
 *  caché, la app pinta un frame en español y salta al inglés a la vista del usuario.
 *  Swallows all errors to guarantee it never rejects: this runs before React mounts,
 *  so a rejection is a blank page with no way to recover. */
export async function initLang(): Promise<void> {
  try {
    const cached = localStorage.getItem(KEY)
    if (cached === "es" || cached === "en") current = cached
  } catch {
    // Storage unavailable or disabled (e.g., Safari private browsing, sandboxed iframe);
    // stay with default "es"
  }

  try {
    const r = await fetch("/api/idioma")
    if (!r.ok) return                       // la DB manda, pero si no contesta el
    const { idioma } = await r.json()       // caché es mejor que nada
    if (idioma === "es" || idioma === "en") {
      current = idioma
      try {
        localStorage.setItem(KEY, idioma)
      } catch {
        // Storage write failed; the value is in memory, which is enough
      }
    }
  } catch {
    // sin red no hay nada que corregir: seguimos con el caché
  }
}

const ES: Record<string, string> = {
  "common.save": "Guardar",
  "common.cancel": "Cancelar",
  "status.queued": "registrado",
  "status.running": "corriendo",
  "status.analyzed": "analizado",
  "status.briefed": "briefeado",
  "status.surveyed": "sondeado",
  "status.planned": "planificado",
  "status.implemented": "implementado",
  "status.error": "error",
  "phase.analyze": "Análisis",
  "phase.brief": "Brief",
  "phase.survey": "Sondeo",
  "phase.consolidate": "Consolidación",
  "phase.design": "Plan",
  "phase.implement": "Código",
}

const EN: Record<string, string> = {
  "common.save": "Save",
  "common.cancel": "Cancel",
  "status.queued": "queued",
  "status.running": "running",
  "status.analyzed": "analyzed",
  "status.briefed": "briefed",
  "status.surveyed": "surveyed",
  "status.planned": "planned",
  "status.implemented": "implemented",
  "status.error": "error",
  "phase.analyze": "Analysis",
  "phase.brief": "Brief",
  "phase.survey": "Survey",
  "phase.consolidate": "Consolidation",
  "phase.design": "Plan",
  "phase.implement": "Code",
}

/** Una cadena de UI. Una clave que falta se devuelve tal cual, en vez de romper la
 *  pantalla: un texto raro es un bug visible, una pantalla en blanco es una llamada. */
export function t(key: string): string {
  const dict = current === "en" ? EN : ES
  return dict[key] ?? ES[key] ?? key
}

/** Plural para dos idiomas de plural simple. `Intl.PluralRules` es de más acá, y lo
 *  que había antes —pegar el sufijo a mano (`decisión{n > 1 && "es"}`)— no sobrevive
 *  a un idioma donde el plural no es un sufijo del singular. */
export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many
}
