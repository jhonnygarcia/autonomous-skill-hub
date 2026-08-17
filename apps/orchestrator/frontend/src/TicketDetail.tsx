import { useState } from "react"
import { ApiError, RESTORE_EXISTS_CODE, type ActiveRun, type TicketDetail as Detail } from "@/api"
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

export function TicketDetail({ detail, activeRun, projectName, onBack, onRun, onDelete, onRestore }: {
  detail: Detail
  activeRun: ActiveRun | null
  projectName: string
  onBack: () => void
  onRun: (instructions?: string, phase?: string, resume?: boolean) => void
  onDelete: () => void
  onRestore: (runId: number, overwrite: boolean) => Promise<void>
}) {
  const [showLog, setShowLog] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmRestore, setConfirmRestore] = useState<number | null>(null)   // run id
  const [restoreError, setRestoreError] = useState("")
  // Which run ids have an in-flight restore: without this, a fast double-click sends
  // a second request for the file the first one just put back, and that one 409s and
  // pops a dialog nobody asked for.
  const [restoring, setRestoring] = useState<Set<number>>(new Set())
  const t = detail.ticket
  const { label, color } = ticketStatus(t, activeRun)
  const reason = blockReason(t, activeRun)

  const restore = (runId: number, overwrite = false) => {
    setRestoring(prev => new Set(prev).add(runId))
    return onRestore(runId, overwrite).then(() => setRestoreError("")).catch((e: ApiError) => {
      // The backend tags the ONE retryable 409 with a code — never sniffed out of the
      // Spanish sentence, which CLAUDE.md classifies as free to reword. A tree's 409
      // carries no code, and the dialog must not offer what the backend will refuse
      // anyway.
      // A stale error from an earlier, unrelated restore must not still be on screen
      // once this dialog is up — otherwise a genuine failure from before reads like
      // it's about the confirmation now showing.
      if (e.code === RESTORE_EXISTS_CODE) { setRestoreError(""); setConfirmRestore(runId) }
      else setRestoreError(String(e.message))
    }).finally(() => setRestoring(prev => {
      const next = new Set(prev)
      next.delete(runId)
      return next
    }))
  }

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
                onRun={(phase, ins, resume) => onRun(ins, phase, resume)}
                onRestore={runId => restore(runId)} restoring={restoring} />

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
                {/* `restorable` — not `archive_path` — is what says the button can
                    actually work: a fan-out survey gets an `archive_path` too, but its
                    HUELLA is a scratch path outside every repo, so its `salida/` never
                    holds the declared deliverable. */}
                {!!r.restorable && (r.artifact_state === "ok" || r.artifact_state === "parcial") && (
                  <Button size="sm" variant="ghost" className="ml-auto h-6 text-xs"
                          disabled={restoring.has(r.id)}
                          onClick={() => restore(r.id)} title={r.archive_path ?? undefined}>
                    Restaurar
                  </Button>
                )}
              </li>
            ))}
            {detail.runs.length === 0 && (
              <li className="text-muted-foreground">Sin corridas aún.</li>
            )}
          </ul>
        )}
        {restoreError && <p className="text-xs text-destructive">{restoreError}</p>}
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

      <ConfirmDialog open={confirmRestore !== null} title="El archivo ya existe"
                     body="Reemplazarlo con la versión del snapshot. La versión actual se pierde (salvo que otra corrida la haya archivado)."
                     confirmLabel="Reemplazar"
                     onConfirm={() => { const id = confirmRestore!; setConfirmRestore(null); restore(id, true) }}
                     onCancel={() => setConfirmRestore(null)} />
    </div>
  )
}
