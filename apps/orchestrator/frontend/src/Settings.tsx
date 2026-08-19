import type { ReactNode } from "react"
import { Archive } from "@/Archive"
import { Language } from "@/Language"
import { Models } from "@/Models"
import { t } from "@/strings"

/**
 * A section is a hairline rectangle with a bracketed header — the system's only
 * iconography (DESIGN.md: "the brackets are the icons"). The chrome lives here and
 * nowhere else, so `Models` and `Archive` render content and no frame.
 */
export function Section({ mark, title, aside, children }: {
  mark: string; title: string; aside?: ReactNode; children: ReactNode
}) {
  return (
    <section className="border border-border">
      <header className="flex flex-wrap items-center gap-3 px-4 py-3">
        <h2 className="text-sm font-bold uppercase tracking-wide">
          <span className="text-muted-foreground">[{mark}]</span> {title}
        </h2>
        {aside && <div className="ml-auto text-xs text-muted-foreground">{aside}</div>}
      </header>
      <div className="border-t border-border px-4 py-4">{children}</div>
    </section>
  )
}

/**
 * What's global and nothing else. The projects are Home's — they were briefly listed
 * here too, following a mock that framed both of the sections below under an "active
 * project" heading. The backend has no such thing: `phase_config` and `settings` hold
 * one row each, and the labels say so.
 */
export function Settings() {
  return (
    <div className="space-y-6">
      <Section mark="+" title={t("common.languageTitle")}
               aside={t("settings.globalNextRun")}>
        <Language />
      </Section>

      <Section mark="+" title={t("settings.phaseRunTitle")}
               aside={t("settings.globalNextRun")}>
        <Models />
      </Section>

      <Section mark="+" title={t("common.archiveTitle")}
               aside={t("settings.globalOptional")}>
        <Archive />
      </Section>
    </div>
  )
}
