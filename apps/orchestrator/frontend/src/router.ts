import { useSyncExternalStore } from "react"

/**
 * Hash routing, by hand.
 *
 * The four views used to be a `useState` in `App`, which meant no back button, no
 * reload-in-place and no link to a ticket. `react-router` buys nested routes and
 * loaders this app has no use for, so this is the ~30 lines that cover what it does
 * need: parse, build, navigate, subscribe.
 *
 * ponytail: hash and not `history.pushState` because the backend serves nothing —
 * Vite's dev server would 404 a deep path on reload, and there is no SPA fallback
 * to add.
 */
export type Route =
  | { kind: "home" }
  | { kind: "project"; name: string }
  | { kind: "ticket"; id: number }
  | { kind: "settings" }
  // `name: null` = creating one.
  | { kind: "projectForm"; name: string | null }

/** Pure, and the only place that knows the URL shape. Anything unrecognized is home:
 *  a bad hash is a typo or a stale bookmark, not an error worth a screen. */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent)
  if (parts[0] === "ajustes") return { kind: "settings" }
  // Not under `#/ajustes/`: the form is reached from Home's project list, which is
  // where projects live. A URL saying otherwise is a URL that lies.
  if (parts[0] === "proyecto") return { kind: "projectForm", name: parts[1] ?? null }
  if (parts[0] === "p" && parts[1]) return { kind: "project", name: parts[1] }
  if (parts[0] === "t" && /^\d+$/.test(parts[1] ?? "")) return { kind: "ticket", id: Number(parts[1]) }
  return { kind: "home" }
}

export function href(r: Route): string {
  switch (r.kind) {
    case "home": return "#/"
    case "settings": return "#/ajustes"
    case "projectForm":
      return r.name ? `#/proyecto/${encodeURIComponent(r.name)}` : "#/proyecto"
    case "project": return `#/p/${encodeURIComponent(r.name)}`
    case "ticket": return `#/t/${r.id}`
  }
}

export const go = (r: Route) => { location.hash = href(r) }

/**
 * Veto over a hash change: return `false` to keep the current route. Used by the
 * unsaved-changes confirmation.
 *
 * **This listener is registered at module load, and that ordering is the whole
 * point.** `hashchange` listeners fire in registration order, and React's — the
 * `subscribe` below, registered when `App`'s effects commit — re-renders
 * synchronously, unmounting the form and taking what was typed with it. A guard that
 * runs after that reverts the URL onto a form that has already lost its state, and
 * asks about changes it just destroyed. Registered here it runs first, so
 * `location.replace` puts the URL back before React ever sees a new value.
 */
type Guard = (next: string) => boolean
let guard: Guard | null = null
export const setGuard = (g: Guard | null) => { guard = g }

let allowed = location.hash
addEventListener("hashchange", () => {
  if (guard && !guard(location.hash)) {
    // `replace` and not `location.hash =`: a refused exit must not leave a history
    // entry behind, or every one of them adds a step to walk back through.
    location.replace(allowed || "#/")
    return
  }
  allowed = location.hash
})

const subscribe = (cb: () => void) => {
  addEventListener("hashchange", cb)
  return () => removeEventListener("hashchange", cb)
}

export const useRoute = (): Route =>
  parseRoute(useSyncExternalStore(subscribe, () => location.hash))
