import { useState } from "react"
import type { ActiveRun, TicketDetail as Detail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Timeline } from "@/Timeline"
import { blockReason, duration, runColor, ticketStatus } from "@/status"

// The text toggles (History, Log) are native <button>s: without shadcn's own focus
// ring, so we give it to them by hand for keyboard navigation.
const TOGGLE =
  "rounded text-sm font-medium hover:underline focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-ring/50"

export function TicketDetail({ detail, activeRun, projectName, onBack, onRun, onDelete }: {
  detail: Detail
  activeRun: ActiveRun | null
  projectName: string
  onBack: () => void
  onRun: (instructions?: string, phase?: string) => void
  onDelete: () => void
}) {
  const [showLog, setShowLog] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const t = detail.ticket
  const { label, color } = ticketStatus(t, activeRun)
  const reason = blockReason(t, activeRun)

  return (
    <div className="space-y-4">
      <button onClick={onBack}
              className="rounded text-sm text-muted-foreground hover:underline hover:text-foreground
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
        ← {projectName} / ticket #{t.ado_id}
      </button>

      {/* The header keeps the id, the status and Delete: phase actions live in their
          own timeline row, next to the information that justifies them. */}
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">#{t.ado_id}</h2>
        <Badge className={color}>{label}</Badge>
        <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground"
                onClick={() => setConfirmDelete(true)}>
          Borrar
        </Button>
      </div>
      {reason && <p className="text-xs text-amber-700 dark:text-amber-500">{reason}</p>}

      <Timeline phases={detail.fases} runs={detail.runs} activeRun={activeRun} ticketId={t.id}
                onRun={(phase, ins) => onRun(ins, phase)} />

      <div>
        <button className={TOGGLE} onClick={() => setShowHistory(v => !v)}>
          {showHistory ? "▾" : "▸"} Historial de corridas ({detail.runs.length})
        </button>
        {showHistory && (
          <ul className="mt-2 space-y-1 text-sm">
            {detail.runs.map(r => (
              <li key={r.id} className="flex items-center gap-2">
                <Badge className={runColor(r.status)}>{r.status}</Badge>
                <span className="text-xs text-muted-foreground">{r.phase}</span>
                <span className="text-muted-foreground">{r.started_at ?? "en cola"}</span>
                <span className="text-muted-foreground">{duration(r.started_at, r.finished_at)}</span>
                {r.artifact_path && (
                  // Monospace only when it's actually a path: on `nada`,
                  // `artifact_path` holds the reason in prose, not a file.
                  <span className={`truncate text-xs text-muted-foreground ${
                    r.artifact_state === "nada" ? "" : "font-mono"}`}
                        title={r.artifact_path}>
                    {r.artifact_state}: {r.artifact_path}
                  </span>
                )}
                {r.instructions && (
                  <span className="truncate text-muted-foreground" title={r.instructions}>
                    ✎ {r.instructions}
                  </span>
                )}
              </li>
            ))}
            {detail.runs.length === 0 && (
              <li className="text-muted-foreground">Sin corridas aún.</li>
            )}
          </ul>
        )}
      </div>

      {/* The log stays collapsed: it's the diagnostic tool for when the timeline
          says something failed, not the first thing to read. */}
      <div>
        <button className={TOGGLE} onClick={() => setShowLog(v => !v)}>
          {showLog ? "▾" : "▸"} Log de la última corrida
        </button>
        {showLog && (
          <pre className="mt-2 max-h-[28rem] overflow-auto rounded border border-border
                          bg-gray-950 p-3 text-xs text-gray-100">
            {detail.log_tail || "(el log aparecerá cuando arranque la corrida)"}
          </pre>
        )}
      </div>

      <ConfirmDialog open={confirmDelete} title={`¿Borrar el ticket #${t.ado_id}?`}
                     body="Se borran sus corridas y sus logs. Los artefactos que el
                           agente escribió en el repo se quedan donde están."
                     onConfirm={() => { setConfirmDelete(false); onDelete() }}
                     onCancel={() => setConfirmDelete(false)} />
    </div>
  )
}
