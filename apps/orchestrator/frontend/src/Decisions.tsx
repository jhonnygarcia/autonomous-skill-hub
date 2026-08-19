import { useState } from "react"
import { api, ApiError, type Decision } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { plural, t } from "@/strings"

/**
 * The `## Decisiones para ti` items of one phase's deliverable, answerable in place —
 * without this, finding them means opening an 8 KB document and hunting, and answering
 * them means editing it by hand. Collapsed by default (the counter alone, same as
 * before this existed); opening it fetches the parsed items from
 * `GET /tickets/{id}/decisiones`, which is the SAME door as the artifact viewer
 * (`declared_file_or_none`, backend side).
 *
 * `BLOQUEA` and `DECIDIR` are visually distinguished on purpose: a `BLOQUEA` left
 * unanswered stops the next phase outright, a `DECIDIR` only means the agent proceeds
 * with its own proposal — those are different stakes, not different flavors of the
 * same badge.
 */
export function Decisions({ ticketId, ruta, counts }: {
  ticketId: number
  ruta: string
  counts: { decidir: number; bloquea: number }
}) {
  const [open, setOpen] = useState(false)
  const [puntos, setPuntos] = useState<Decision[] | null>(null)
  const [error, setError] = useState("")
  // The id currently mid-request: disables just that card's buttons, not the whole
  // panel — answering one item must not freeze the others while it's in flight.
  const [busy, setBusy] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const load = () => {
    setError("")
    api.decisiones(ticketId, ruta).then(r => setPuntos(r.puntos)).catch(e => setError(String(e)))
  }

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next) load()   // re-fetch every time it's opened: a run may have closed since
  }

  const answer = (id: string, aceptarPropuesta: boolean) => {
    setBusy(id)
    setError("")
    api.responderDecision(ticketId, { ruta, id, aceptar_propuesta: aceptarPropuesta,
                                       respuesta: aceptarPropuesta ? undefined : drafts[id] })
      .then(() => {
        setDrafts(d => { const next = { ...d }; delete next[id]; return next })
        load()   // refresh: the answered item's id changes (its text just did too)
      })
      .catch(e => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setBusy(null))
  }

  const total = counts.decidir + counts.bloquea

  return (
    <div className="pb-2">
      <button onClick={toggle}
              className="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline
                         focus-visible:outline-1 focus-visible:outline-ring rounded">
        {open ? "▾" : "▸"}{" "}
        {!!counts.decidir && (
          <span className="text-warning-active">
            {counts.decidir} {plural(counts.decidir, t("decisions.oneForYou"), t("decisions.manyForYou"))}
          </span>
        )}
        {!!counts.decidir && !!counts.bloquea && " · "}
        {!!counts.bloquea && (
          <span className="text-destructive">
            {counts.bloquea} {plural(counts.bloquea, t("decisions.oneBlocks"), t("decisions.manyBlock"))}
          </span>
        )}
        {total === 0 && <span>{t("decisions.allAnswered")}</span>}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {error && <p className="text-xs text-destructive">{error}</p>}
          {puntos === null && !error && <p className="text-xs text-muted-foreground">{t("decisions.loading")}</p>}
          {puntos?.map(p => (
            <div key={p.id}
                 className={`rounded-md border p-2 text-xs ${
                   p.respondido ? "border-border bg-muted/30"
                     : p.tipo === "BLOQUEA" ? "border-destructive/40 bg-destructive/5"
                     : "border-warning/40 bg-warning/5"}`}>
              <div className="flex items-center gap-2">
                <span className={`font-semibold ${
                  p.tipo === "BLOQUEA" ? "text-destructive" : "text-warning-active"}`}>
                  {p.tipo === "BLOQUEA" ? t("decisions.blocksNextPhase") : t("decisions.decideWithProposal")}
                </span>
                {p.respondido && <span className="text-muted-foreground">· {t("decisions.answeredSuffix")}</span>}
              </div>
              <p className="mt-1 font-medium text-foreground">{p.pregunta}</p>
              {p.cuerpo && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{p.cuerpo}</p>}

              {!p.respondido && (
                <div className="mt-2 space-y-1.5">
                  {p.propuesta && (
                    <Button size="sm" variant="outline" className="h-6 text-xs"
                            disabled={busy === p.id}
                            onClick={() => answer(p.id, true)}>
                      {t("decisions.acceptProposal")}
                    </Button>
                  )}
                  <Textarea rows={2} placeholder={t("decisions.yourAnswerPlaceholder")}
                            aria-label={`${t("decisions.answerForAriaLabel")}: ${p.pregunta}`}
                            value={drafts[p.id] ?? ""}
                            onChange={e => setDrafts(d => ({ ...d, [p.id]: e.target.value }))} />
                  <Button size="sm" className="h-6 text-xs"
                          disabled={busy === p.id || !drafts[p.id]?.trim()}
                          onClick={() => answer(p.id, false)}>
                    {t("decisions.respond")}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
