import { useState } from "react"
import { Moon, Sun } from "lucide-react"
import { href, type Route } from "@/router"
import { t } from "@/strings"

export type Crumb = { label: string; to?: Route }

/**
 * The chrome that used to be the sidebar. It changed shape because the sidebar's only
 * two jobs — switch project, open Ajustes — are now Home's list and a route, and a
 * column repeating both on every screen was a column earning nothing.
 *
 * It carries `Ajustes` and NOT `+ Nuevo proyecto`: settings are reachable from
 * anywhere, but creating a project belongs beside the list of them, which is Home. A
 * global button for it followed you into a ticket's timeline, where it is the last
 * thing anyone is about to do.
 */
export function TopBar({ crumbs }: { crumbs: Crumb[] }) {
  const action = "rounded-sm border border-border px-2 py-1 text-xs " +
    "hover:bg-secondary focus-visible:outline-1 focus-visible:outline-ring"
  // The <html> class is the single source of truth — index.html set it before paint,
  // so this only reads it once and writes both places from then on.
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"))
  function toggleTheme() {
    const next = !dark
    document.documentElement.classList.toggle("dark", next)
    localStorage.theme = next ? "dark" : "light"
    setDark(next)
  }
  return (
    <header className="space-y-3 border-b border-border pb-3">
      <div className="flex flex-wrap items-center gap-3">
        <a href={href({ kind: "home" })} className="text-sm font-bold tracking-wide">
          [SYS // ORQUESTADOR]
        </a>
        <span className="text-xs text-muted-foreground">| {t("topbar.pluginTag")}</span>
        <button
          type="button"
          onClick={toggleTheme}
          aria-pressed={dark}
          aria-label={dark ? t("topbar.toLightTheme") : t("topbar.toDarkTheme")}
          title={dark ? t("topbar.toLightTheme") : t("topbar.toDarkTheme")}
          className={`${action} ml-auto flex items-center px-1.5 py-1.5`}
        >
          {dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
        </button>
        <a href={href({ kind: "settings" })} className={action}>[*] {t("common.settings")}</a>
      </div>

      {crumbs.length > 0 && (
        <nav className="flex flex-wrap items-center gap-1 text-xs uppercase tracking-wide
                        text-muted-foreground">
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="text-muted-foreground/50">/</span>}
              {c.to
                ? <a href={href(c.to)} className="hover:text-foreground hover:underline">{c.label}</a>
                : <span className="font-bold text-foreground">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
    </header>
  )
}
