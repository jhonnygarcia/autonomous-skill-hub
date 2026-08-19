import { useState } from "react"
import type { ActiveRun, Phase, Ticket } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { blockReason, phaseLabel, ticketStatus } from "@/status"
// Aliased: `tickets.map(t => ...)` below shadows a plain `t` with the ticket itself.
import { t, t as tt } from "@/strings"

const DOT: Record<string, string> = {
  ok: "bg-success",
  parcial: "bg-warning",
  error: "bg-destructive",
  corriendo: "bg-info animate-pulse",
  pendiente: "bg-muted-foreground/25",
}

/**
 * Three dots, one per launchable phase.
 *
 * It was removed in the 2026-08-09 redesign for showing six phases with five dimmed on
 * every row, and `STATUS.md` left it written that it comes back once phases 2-4 really
 * exist. They do, and with `guards`/`pr` gone there are exactly three.
 *
 * `role="img"` with one composed name — NOT `aria-hidden`, and not a label per dot. The
 * badge beside it cannot stand in for these: `folded_status` collapses every phase into
 * a single word, so it says "error" and never which phase failed. That detail lives only
 * in the dots, and hiding them would leave it available on hover and nowhere else. One
 * name because it reads as one graphic; three names would be thirty stops in a list of
 * ten tickets. `role="img"` also makes the subtree presentational, so the per-dot
 * `title`s stay for the mouse without being announced twice.
 */
/**
 * The journey is three stages however Phase 1 was run. On a multi-repo ticket that
 * phase is four rows —`analyze` as the fallback plus the `brief`/`survey`/`consolidate`
 * fan-out— but they're all the same stage: understand the ticket. A row that grew to
 * six dots would answer "which sub-step", a question only the detail view asks, and it
 * would carry a permanently grey `analyze` dot on every ticket that took the fan-out.
 */
const STAGES: { id: "analyze" | "design" | "implement"; phases: string[] }[] = [
  { id: "analyze", phases: ["analyze", "brief", "survey", "consolidate"] },
  { id: "design", phases: ["design"] },
  { id: "implement", phases: ["implement"] },
]
/** The phases that actually produce the stage's deliverable. A stage only goes green
 *  when one of these did: `brief` and `survey` being done doesn't mean there's an
 *  analysis to plan from, and painting them green would say there is. */
const TERMINAL = new Set(["analyze", "consolidate", "design", "implement"])

function stageState(members: Phase[]): string {
  if (members.some(f => f.estado === "corriendo")) return "corriendo"
  const done = members.find(f => TERMINAL.has(f.fase)
    && (f.estado === "ok" || f.estado === "parcial"))
  if (done) return done.estado!
  if (members.some(f => f.estado === "error")) return "error"
  return "pendiente"
}

function Stepper({ fases }: { fases: Phase[] }) {
  const stages = STAGES
    .map(s => ({ ...s, label: t(`phase.${s.id}`),
                 members: fases.filter(f => f.disponible && s.phases.includes(f.fase)) }))
    .filter(s => s.members.length)
  // The hover carries the full truth the dot compresses: which sub-step got where.
  const detail = (s: typeof stages[number]) =>
    `${s.label}: ${s.members.map(f => `${phaseLabel(f.fase)} ${f.estado ?? "pendiente"}`).join(", ")}`
  return (
    <span className="flex items-center" role="img" aria-label={stages.map(detail).join(" · ")}>
      {stages.map((s, i) => (
        <span key={s.label} className="flex items-center">
          {i > 0 && <span aria-hidden className="h-px w-3 bg-border" />}
          <span title={detail(s)}
                className={`h-2 w-2 rounded-full ${DOT[stageState(s.members)]}`} />
        </span>
      ))}
    </span>
  )
}

export function TicketList({ tickets, activeRun, onAdd, onOpen, onRun }: {
  tickets: Ticket[]
  activeRun: ActiveRun | null
  onAdd: (body: { ado_id?: number; request?: string }) => void
  onOpen: (id: number) => void
  onRun: (id: number) => void
}) {
  const [adoId, setAdoId] = useState("")
  const [request, setRequest] = useState("")
  const [mode, setMode] = useState<"ado" | "request">("ado")
  const add = () => { onAdd({ ado_id: Number(adoId) }); setAdoId("") }
  const addRequest = () => { onAdd({ request: request.trim() }); setRequest("") }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border p-3">
        <div className="flex gap-1" role="tablist" aria-label={t("ticketlist.originAriaLabel")}>
          {([["ado", t("ticketlist.tabAdo")], ["request", t("ticketlist.tabRequest")]] as const)
            .map(([k, label]) => (
              <Button key={k} size="sm" role="tab" aria-selected={mode === k}
                      variant={mode === k ? "secondary" : "ghost"}
                      onClick={() => setMode(k)}>
                {label}
              </Button>
            ))}
        </div>
        {mode === "ado" ? (
          <>
            <label htmlFor="ado-id" className="mt-3 block text-xs font-medium">
              {t("ticketlist.workItemIdLabel")}
            </label>
            <div className="mt-1 flex gap-2">
              <Input id="ado-id" className="w-40" placeholder="3332" value={adoId}
                     onChange={e => setAdoId(e.target.value.replace(/\D/g, ""))}
                     onKeyDown={e => e.key === "Enter" && adoId && add()} />
              <Button onClick={add} disabled={!adoId}>{t("ticketlist.add")}</Button>
            </div>
            {/* The number is not validated against Azure DevOps on purpose: the backend has
                no ADO credentials. Saying where it comes from costs a line and does the
                same job. */}
            <p className="mt-2 text-xs text-muted-foreground">
              {t("ticketlist.workItemUrlHint")}{" "}
              <span className="font-mono">…/_workitems/edit/<strong>3332</strong></span>
            </p>
          </>
        ) : (
          <>
            <label htmlFor="request-text" className="mt-3 block text-xs font-medium">
              {t("ticketlist.whatDoYouNeedLabel")}
            </label>
            {/* Native textarea, mirroring the Input component's classes: the answer
                arrives while the decision is being made — the placeholder IS the
                cheapest quality lever this feature has (spec §4.5). */}
            <textarea id="request-text" rows={4} value={request}
                      onChange={e => setRequest(e.target.value)}
                      placeholder={t("ticketlist.requestPlaceholder")}
                      className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:outline-1 focus-visible:outline-ring" />
            <div className="mt-2 flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {t("ticketlist.firstLineTitle")}
              </p>
              <Button onClick={addRequest} disabled={!request.trim()}>{t("ticketlist.add")}</Button>
            </div>
          </>
        )}
      </div>

      <div className="divide-y rounded-md border">
        {tickets.map(t => {
          const { label, color } = ticketStatus(t, activeRun)
          const reason = blockReason(t, activeRun)
          return (
            <div key={t.id} className="px-3 py-2 transition-colors hover:bg-muted/40">
              <div className="flex items-center gap-2">
                <button className="rounded text-sm font-medium hover:underline
                                   focus-visible:outline-1 focus-visible:outline-ring"
                        onClick={() => onOpen(t.id)}>
                  #{t.ado_id}
                </button>
                {/* No title before the analysis runs: we don't know what it is yet. */}
                {t.title && (
                  <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground"
                        title={t.title}>
                    {t.title}
                  </span>
                )}
                <div className={`flex gap-1 ${t.title ? "" : "ml-auto"}`}>
                  <Button size="sm" variant="outline" disabled={!!reason}
                          title={reason || tt("ticketlist.launchPhase1Hint")}
                          onClick={() => onRun(t.id)}>
                    {t.status === "queued" ? tt("ticketlist.analyze") : tt("ticketlist.reanalyze")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onOpen(t.id)}>{tt("common.view")}</Button>
                </div>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <Stepper fases={t.fases} />
                <Badge className={color}>{label}</Badge>
                {reason && activeRun?.ticket_id !== t.id && (
                  <span className="text-xs text-muted-foreground">{reason}</span>
                )}
              </div>
            </div>
          )
        })}
        {tickets.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">
            {t("ticketlist.empty")}
          </p>
        )}
      </div>
    </div>
  )
}
