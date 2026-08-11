import { useState } from "react"
import type { ActiveRun, Ticket } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { blockReason, ticketStatus } from "@/status"

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
      <div className="flex gap-2">
        <Input className="w-40" placeholder="ID del ticket (ej. 3322)" value={adoId}
               onChange={e => setAdoId(e.target.value.replace(/\D/g, ""))}
               onKeyDown={e => e.key === "Enter" && adoId && add()} />
        <Button onClick={add} disabled={!adoId}>+ Añadir</Button>
      </div>

      <div className="divide-y rounded-md border">
        {tickets.map(t => {
          const { label, color } = ticketStatus(t, activeRun)
          const reason = blockReason(t, activeRun)
          return (
            <div key={t.id} className="flex items-center gap-3 px-3 py-2 text-sm transition-colors hover:bg-muted/40">
              <button className="rounded font-medium hover:underline focus-visible:outline-none
                                  focus-visible:ring-2 focus-visible:ring-ring/50"
                      onClick={() => onOpen(t.id)}>
                #{t.ado_id}
              </button>
              <Badge className={color}>{label}</Badge>
              {reason && activeRun?.ticket_id !== t.id && (
                <span className="text-xs text-muted-foreground">{reason}</span>
              )}
              <div className="ml-auto flex gap-1">
                <Button size="sm" variant="outline" disabled={!!reason}
                        title={reason || "Lanza la Fase 1; el resto se lanza desde el detalle"}
                        onClick={() => onRun(t.id)}>
                  {t.status === "queued" ? "Analizar" : "Re-analizar"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onOpen(t.id)}>Ver</Button>
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
