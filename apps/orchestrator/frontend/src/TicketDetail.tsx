import { useState } from "react"
import type { ActiveRun, TicketDetail as Detail } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Timeline } from "@/Timeline"
import { bloqueo, colorCorrida, duracion, estado } from "@/estado"

// Los desplegables de texto (Historial, Log) son <button> nativos: sin el anillo de foco
// propio de shadcn, así que se lo damos a mano para que se puedan navegar con teclado.
const TOGGLE =
  "rounded text-sm font-medium hover:underline focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-ring/50"

export function TicketDetail({ detail, activo, projectName, onBack, onRun, onDelete }: {
  detail: Detail
  activo: ActiveRun | null
  projectName: string
  onBack: () => void
  onRun: (instructions?: string, phase?: string) => void
  onDelete: () => void
}) {
  const [verLog, setVerLog] = useState(false)
  const [verHistorial, setVerHistorial] = useState(false)
  const t = detail.ticket
  const { label, color } = estado(t, activo)
  const motivo = bloqueo(t, activo)

  return (
    <div className="space-y-4">
      <button onClick={onBack}
              className="rounded text-sm text-muted-foreground hover:underline hover:text-foreground
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
        ← {projectName} / ticket #{t.ado_id}
      </button>

      {/* La cabecera se queda con el identificador, el estado y Borrar: las acciones de
          fase viven en su fila del timeline, junto a la información que las justifica. */}
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">#{t.ado_id}</h2>
        <Badge className={color}>{label}</Badge>
        <Button size="sm" variant="destructive" className="ml-auto" onClick={onDelete}>
          Borrar
        </Button>
      </div>
      {motivo && <p className="text-xs text-amber-700 dark:text-amber-500">{motivo}</p>}

      <Timeline fases={detail.fases} activo={activo} ticketId={t.id}
                onRun={(fase, ins) => onRun(ins, fase)} />

      <div>
        <button className={TOGGLE} onClick={() => setVerHistorial(v => !v)}>
          {verHistorial ? "▾" : "▸"} Historial de corridas ({detail.runs.length})
        </button>
        {verHistorial && (
          <ul className="mt-2 space-y-1 text-sm">
            {detail.runs.map(r => (
              <li key={r.id} className="flex items-center gap-2">
                <Badge className={colorCorrida(r.status)}>{r.status}</Badge>
                <span className="text-xs text-muted-foreground">{r.phase}</span>
                <span className="text-muted-foreground">{r.started_at ?? "en cola"}</span>
                <span className="text-muted-foreground">{duracion(r.started_at, r.finished_at)}</span>
                {r.artifact_path && (
                  <span className="truncate font-mono text-xs text-muted-foreground"
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

      {/* El log se queda, colapsado: es la herramienta de diagnóstico cuando el timeline
          dice que algo falló, no lo primero que hay que leer. */}
      <div>
        <button className={TOGGLE} onClick={() => setVerLog(v => !v)}>
          {verLog ? "▾" : "▸"} Log de la última corrida
        </button>
        {verLog && (
          <pre className="mt-2 max-h-[28rem] overflow-auto rounded border border-border
                          bg-gray-950 p-3 text-xs text-gray-100">
            {detail.log_tail || "(el log aparecerá cuando arranque la corrida)"}
          </pre>
        )}
      </div>
    </div>
  )
}
