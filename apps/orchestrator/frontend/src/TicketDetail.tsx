import { useState } from "react"
import type { ActiveRun, TicketDetail as Detail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { bloqueo, colorCorrida, duracion, estado, puedePlanificar } from "@/estado"

export function TicketDetail({ detail, activo, projectName, onBack, onRun, onDelete }: {
  detail: Detail
  activo: ActiveRun | null
  projectName: string
  onBack: () => void
  onRun: (instructions?: string, phase?: string) => void
  onDelete: () => void
}) {
  const [instructions, setInstructions] = useState("")
  const t = detail.ticket
  const { label, color } = estado(t, activo)
  const motivo = bloqueo(t, activo)

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-sm text-gray-500 hover:underline">
        ← {projectName} / ticket #{t.ado_id}
      </button>

      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">#{t.ado_id}</h2>
        <Badge className={color}>{label}</Badge>
        <div className="ml-auto flex gap-2">
          <Button size="sm" disabled={!!motivo} title={motivo || undefined}
                  onClick={() => onRun()}>
            {detail.runs.length ? "Re-correr análisis" : "Correr análisis"}
          </Button>
          <Button size="sm" variant="secondary"
                  disabled={!!motivo || !puedePlanificar(t, detail.runs[0]?.phase)}
                  title={motivo || (puedePlanificar(t, detail.runs[0]?.phase) ? undefined
                                    : "Necesita un análisis: corre primero la Fase 1")}
                  onClick={() => onRun(undefined, "design")}>
            Planificar
          </Button>
          <Button size="sm" variant="destructive" onClick={onDelete}>Borrar</Button>
        </div>
      </div>
      {motivo && <p className="text-xs text-amber-700">{motivo}</p>}

      <div>
        <p className="mb-1 text-sm font-medium">Ajustar y re-correr</p>
        <Textarea rows={2} placeholder="Describe el problema o el ajuste…"
                  value={instructions} onChange={e => setInstructions(e.target.value)} />
        <Button size="sm" className="mt-2" disabled={!instructions || !!motivo}
                title={motivo || undefined}
                onClick={() => { onRun(instructions); setInstructions("") }}>
          Enviar ajuste
        </Button>
      </div>

      <div>
        <p className="mb-1 text-sm font-medium">Historial de corridas</p>
        <ul className="space-y-1 text-sm">
          {detail.runs.map(r => (
            <li key={r.id} className="flex items-center gap-2">
              <Badge className={colorCorrida(r.status)}>{r.status}</Badge>
              <span className="text-xs text-gray-500">{r.phase}</span>
              <span className="text-gray-500">{r.started_at ?? "en cola"}</span>
              <span className="text-gray-400">{duracion(r.started_at, r.finished_at)}</span>
              {r.instructions && (
                <span className="truncate text-gray-500" title={r.instructions}>✎ {r.instructions}</span>
              )}
            </li>
          ))}
          {detail.runs.length === 0 && (
            <li className="text-gray-500">Sin corridas aún. Pulsa Correr para lanzar el análisis.</li>
          )}
        </ul>
      </div>

      <div>
        <p className="mb-1 text-sm font-medium">Log</p>
        <pre className="max-h-[28rem] overflow-auto rounded bg-gray-950 p-3 text-xs text-gray-100">
          {detail.log_tail || "(el log aparecerá cuando arranque la corrida)"}
        </pre>
      </div>
    </div>
  )
}
