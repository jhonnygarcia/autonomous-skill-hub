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

/** Updates the language both in memory and in localStorage. */
export function setLang(code: Lang): void {
  current = code
  localStorage.setItem(KEY, code)
}

/** Resuelve el idioma antes del primer render. Arranca con lo cacheado —si no hay
 *  nada, español, que es el default del backend— y consulta la DB después. Sin el
 *  caché, la app pinta un frame en español y salta al inglés a la vista del usuario. */
export async function initLang(): Promise<void> {
  const cached = localStorage.getItem(KEY)
  if (cached === "es" || cached === "en") current = cached
  try {
    const r = await fetch("/api/idioma")
    if (!r.ok) return                       // la DB manda, pero si no contesta el
    const { idioma } = await r.json()       // caché es mejor que nada
    if (idioma === "es" || idioma === "en") {
      current = idioma
      localStorage.setItem(KEY, idioma)
    }
  } catch {
    // sin red no hay nada que corregir: seguimos con el caché
  }
}

const ES: Record<string, string> = {
  "common.save": "Guardar",
  "common.cancel": "Cancelar",
}

const EN: Record<string, string> = {
  "common.save": "Save",
  "common.cancel": "Cancel",
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
