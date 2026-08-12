import { useState } from "react"
import type { ActiveRun, Phase, Ticket } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { blockReason, PHASE_LABEL, ticketStatus } from "@/status"

const DOT: Record<string, string> = {
  ok: "bg-emerald-500",
  parcial: "bg-amber-500",
  error: "bg-red-500",
  corriendo: "bg-blue-500 animate-pulse",
  pendiente: "bg-muted-foreground/25",
}

/**
 * Three dots, one per launchable phase.
 *
 * It was removed in the 2026-08-09 redesign for showing six phases with five dimmed on
 * every row, and `STATUS.md` left it written that it comes back once phases 2-4 really
 * exist. They do, and with `guards`/`pr` gone there are exactly three. `aria-hidden`
 * because the status badge next to it already says the same thing in words.
 */
function Stepper({ fases }: { fases: Phase[] }) {
  return (
    <span className="flex items-center" aria-hidden>
      {fases.filter(f => f.disponible).map((f, i) => (
        <span key={f.fase} className="flex items-center">
          {i > 0 && <span className="h-px w-3 bg-border" />}
          <span title={`${PHASE_LABEL[f.fase] ?? f.fase}: ${f.estado ?? "pendiente"}`}
                className={`h-2 w-2 rounded-full ${DOT[f.estado ?? "pendiente"]}`} />
        </span>
      ))}
    </span>
  )
}

export function TicketList({ tickets, activeRun, onAdd, onOpen, onRun }: {
  tickets: Ticket[]
  activeRun: ActiveRun | null
  onAdd: (adoId: number) => void
  onOpen: (id: number) => void
  onRun: (id: number) => void
}) {
  const [adoId, setAdoId] = useState("")
  const add = () => { onAdd(Number(adoId)); setAdoId("") }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border p-3">
        <label htmlFor="ado-id" className="text-xs font-medium">ID del work item</label>
        <div className="mt-1 flex gap-2">
          <Input id="ado-id" className="w-40" placeholder="3332" value={adoId}
                 onChange={e => setAdoId(e.target.value.replace(/\D/g, ""))}
                 onKeyDown={e => e.key === "Enter" && adoId && add()} />
          <Button onClick={add} disabled={!adoId}>+ Añadir</Button>
        </div>
        {/* The number is not validated against Azure DevOps on purpose: the backend has
            no ADO credentials. Saying where it comes from costs a line and does the
            same job. */}
        <p className="mt-2 text-xs text-muted-foreground">
          El número del final de la URL en Azure DevOps:{" "}
          <span className="font-mono">…/_workitems/edit/<strong>3332</strong></span>
        </p>
      </div>

      <div className="divide-y rounded-md border">
        {tickets.map(t => {
          const { label, color } = ticketStatus(t, activeRun)
          const reason = blockReason(t, activeRun)
          return (
            <div key={t.id} className="px-3 py-2 transition-colors hover:bg-muted/40">
              <div className="flex items-center gap-2">
                <button className="rounded text-sm font-medium hover:underline
                                   focus-visible:outline-none focus-visible:ring-2
                                   focus-visible:ring-ring/50"
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
                          title={reason || "Lanza la Fase 1; el resto se lanza desde el detalle"}
                          onClick={() => onRun(t.id)}>
                    {t.status === "queued" ? "Analizar" : "Re-analizar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onOpen(t.id)}>Ver</Button>
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
            Sin tickets en este proyecto. Escribe un id arriba para añadir el primero.
          </p>
        )}
      </div>
    </div>
  )
}
