import { useRef, useState } from "react"
import { api, type ActiveRun, type Artifact, type Phase, type Run } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { canRunPhase, durationText, formatSize, formatTime, PHASE_LABEL, phaseColor, phaseIcon } from "@/status"

// Shared focus/hover style for the viewer's native <button>s: shadcn buttons already
// have their own ring, but these are plain (file chips, close, adjust) and without
// this they'd be silent when navigating by keyboard.
const CHIP =
  "rounded border px-1.5 py-0.5 font-mono text-[11px] transition-colors " +
  "hover:bg-accent hover:text-accent-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"

/**
 * The ticket's phase timeline: one row per phase in PHASES, with its action and the
 * artifact it declared having left. Replaces the header buttons — the action goes
 * where the information is, the same principle that moved the repos into the project
 * header. Phases that don't exist yet show dimmed: the pending path is context.
 */
export function Timeline({ phases, runs, activeRun, ticketId, onRun }: {
  phases: Phase[]
  runs: Run[]
  activeRun: ActiveRun | null
  ticketId: number
  onRun: (phase: string, instructions?: string) => void
}) {
  const [openPhase, setOpenPhase] = useState<string | null>(null)   // instructions box
  const [instructions, setInstructions] = useState("")
  const [viewer, setViewer] = useState<Artifact | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<{ ruta: string; msg: string } | null>(null)
  // Each click on a chip bumps the sequence; a response that lands when it's no longer
  // the last one requested is discarded entirely (it neither overwrites the viewer nor
  // clears the `loading` of the click still in flight). Without this, a slow click on A
  // followed by a fast one on B leaves B shown and then A overwrites it once it resolves late.
  const requestId = useRef(0)

  const viewArtifact = (ruta: string) => {
    if (viewer?.ruta === ruta) return setViewer(null)     // second click: close
    const id = ++requestId.current
    setLoading(ruta); setError(null)
    api.artifact(ticketId, ruta)
      .then(a => { if (id === requestId.current) setViewer(a) })
      .catch(e => { if (id === requestId.current) { setViewer(null); setError({ ruta, msg: String(e) }) } })
      .finally(() => { if (id === requestId.current) setLoading(null) })
  }

  return (
    <ol className="space-y-0">
      {phases.map((f, i) => {
        const reason = canRunPhase(phases, i, activeRun, ticketId)
        const h = f.huella
        // `runs` arrives sorted by id DESC, same as `phases_for` in the backend: the
        // first one matching this phase is its most recent run, the same one that
        // produced `h`. Only `implement` sets it — the rest arrive as `null`.
        const branch = runs.find(r => r.phase === f.fase)?.branch ?? null
        // Two shapes of artifact: a directory (path + "/" + each name) or a lone
        // file (the path is already complete and matches its own name). The
        // decision is made ONCE, outside the map — doing it inside the map (as in
        // the first version) made the "doesn't match" branch recompute
        // `archivos === 1` and reach the same conclusion as the "matches" branch,
        // so a `parcial` plan that stops with a single file in the directory
        // (e.g. only `proposal.md`) rendered a chip labeled with the DIRECTORY
        // name, which 400'd on click.
        const isFile = h?.existe ? h.archivos === 1 && h.nombres[0] === h.ruta.split("/").pop() : false
        // ponytail: a directory "X/" that happens to contain a single file also
        // named "X" produces the same payload {ruta:"X", nombres:["X"]} as a lone
        // file "X" — a real ambiguity, unresolvable from the frontend unless the
        // backend marks `es_dir`. Doesn't happen in practice today (analyze is
        // always a lone file; design always brings 2+), so it's left noted and
        // not resolved here.
        const items: { ruta: string; etiqueta: string }[] = !h?.existe ? []
          : isFile ? [{ ruta: h.ruta, etiqueta: h.nombres[0] }]
          // The label is the RELATIVE name the backend sent (`specs/pagos/spec.md`),
          // not its basename: with two capabilities, two `spec.md` would be indistinguishable.
          : h.nombres.map(n => ({ ruta: `${h.ruta}/${n}`, etiqueta: n }))
        const paths = items.map(it => it.ruta)
        const isLast = i === phases.length - 1
        const isRunning = f.estado === "corriendo"

        // Neutral metadata on a single line — time, duration, run count — instead
        // of a row of loose chips: this way the phase name stays the only element
        // with visual weight and the rest reads as data, not another label.
        const metaParts: string[] = []
        if (!f.disponible) metaParts.push("no disponible aún")
        else if (f.estado === "pendiente") metaParts.push("sin corridas")
        if (f.en) metaParts.push(formatTime(f.en))
        if (f.duracion_s != null) metaParts.push(durationText(f.duracion_s))
        if (f.corridas) metaParts.push(`${f.corridas} ${f.corridas === 1 ? "corrida" : "corridas"}`)

        return (
          <li key={f.fase} className={`relative pl-9 ${f.disponible ? "" : "opacity-60"}`}>
            {/* The line connecting phases; not drawn under the last one. Starts behind
                the node (`top-7`, which the node covers once painted after it) and
                **sticks out 6px below the row** to where the next node starts
                (`top-1.5` = 6px). With `bottom-0` it stayed inside its own row: on
                dimmed phases, which measure 36px, it measured 4px and the path looked
                like loose circles right where the pending path is the whole message. */}
            {!isLast && <span aria-hidden className="absolute left-[11px] top-7 -bottom-1.5 w-px bg-border" />}
            <span
              className={`absolute left-0 top-1.5 flex h-6 w-6 items-center justify-center
                          rounded-full border text-[11px] font-semibold shadow-sm transition-colors
                          ${phaseColor(f.estado)}
                          ${isRunning ? "animate-pulse ring-2 ring-blue-500/30 ring-offset-2 ring-offset-background" : ""}`}
            >
              {phaseIcon(f.estado)}
            </span>

            <div className={`-mx-2 rounded-lg px-2 transition-colors ${isRunning ? "bg-blue-500/5" : ""}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className={`text-sm font-semibold tracking-tight ${f.disponible ? "text-foreground" : "text-muted-foreground"}`}>
                  {PHASE_LABEL[f.fase] ?? f.fase}
                </span>
                {metaParts.length > 0 && (
                  <span className="text-xs text-muted-foreground">{metaParts.join(" · ")}</span>
                )}
                {!!f.fallidas && (
                  <span className="text-xs font-medium text-amber-600 dark:text-amber-500">
                    ⚠ {f.fallidas} falló
                  </span>
                )}

                {f.disponible && (
                  <div className="ml-auto flex gap-1">
                    <Button size="sm" variant={f.estado === "pendiente" ? "default" : "outline"}
                            disabled={!!reason} title={reason || undefined}
                            onClick={() => onRun(f.fase)}>
                      {f.corridas ? "Re-correr" : "Correr"}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={!!reason}
                            title={reason || "Correr con instrucciones de ajuste"}
                            aria-label={`Ajustar y correr ${PHASE_LABEL[f.fase] ?? f.fase}`}
                            aria-expanded={openPhase === f.fase}
                            aria-controls={`ajuste-${f.fase}`}
                            onClick={() => {
                              setOpenPhase(openPhase === f.fase ? null : f.fase); setInstructions("")
                            }}>
                      ▾
                    </Button>
                  </div>
                )}
              </div>

              {reason && f.disponible && f.estado !== "corriendo" && (
                <p className="pb-2 text-xs text-muted-foreground">{reason}</p>
              )}

              {f.estado === "error" && f.motivo && (
                <p className="pb-2 text-xs text-destructive">{f.motivo}</p>
              )}

              {/* The reserve of a `parcial`: the footprint was declared, but with
                  caveats (e.g. `openspec validate` didn't pass). Goes next to the
                  footprint, in the same amber this state already uses — doesn't
                  replace the artifact row. */}
              {f.estado === "parcial" && f.motivo && (
                <p className="pb-2 text-xs text-amber-600 dark:text-amber-500">{f.motivo}</p>
              )}

              {/* The branch `implement` prepared, treated the same as the artifact path
                  (same monospace, same size): a sibling technical fact, not a new
                  element. Goes OUTSIDE the footprint block, not inside: the runner
                  already switched all the ticket's repos to the new branch before
                  launching the agent, so a run that closes with `nada` or crashes
                  leaves the repos just as moved — and that's exactly when it matters
                  to know where to look. The design accepts leaving them on the new
                  branch because "it's visible and reversible"; nested under the
                  footprint it was only visible when it wasn't needed.
                  No slot when there's no branch — that's normal for the rest of the phases. */}
              {branch && (
                <div className="flex flex-wrap items-center gap-x-2 pb-2 text-xs">
                  <span className="text-muted-foreground">Rama</span>
                  <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
                    {branch}
                  </span>
                </div>
              )}

              {h && (
                <div className="pb-2 text-xs">
                  {h.existe ? (
                    <>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-muted-foreground">Artefacto</span>
                        <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
                          {h.ruta}
                        </span>
                        <span className="text-muted-foreground">
                          {h.archivos === 1 ? formatSize(h.bytes) : `${h.archivos} archivos · ${formatSize(h.bytes)}`}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {items.map(it => (
                          <button key={it.ruta} onClick={() => viewArtifact(it.ruta)}
                                  title={it.ruta}
                                  aria-pressed={viewer?.ruta === it.ruta}
                                  className={`${CHIP} ${viewer?.ruta === it.ruta
                                    ? "border-ring bg-accent text-accent-foreground"
                                    : "border-border text-muted-foreground"}`}>
                            {loading === it.ruta ? "cargando…" : it.etiqueta}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-500">
                      Artefacto declarado en{" "}
                      <span className="font-mono">{h.ruta}</span>, no se encontró en disco
                    </span>
                  )}
                </div>
              )}

              {openPhase === f.fase && (
                <div id={`ajuste-${f.fase}`} className="pb-3">
                  <Textarea rows={2} value={instructions}
                            placeholder={`Ajuste para ${PHASE_LABEL[f.fase] ?? f.fase}…`}
                            aria-label={`Ajuste para ${PHASE_LABEL[f.fase] ?? f.fase}`}
                            onChange={e => setInstructions(e.target.value)} />
                  <Button size="sm" className="mt-2" disabled={!instructions || !!reason}
                          onClick={() => {
                            onRun(f.fase, instructions); setInstructions(""); setOpenPhase(null)
                          }}>
                    Correr con este ajuste
                  </Button>
                </div>
              )}

              {/* The path travels along with the message: with analyze and design both
                  showing a footprint at the same time, a 400 opening one phase's file
                  shouldn't also render under the other. */}
              {error && paths.includes(error.ruta) && (
                <p className="pb-2 text-xs text-destructive">{error.msg}</p>
              )}

              {viewer && paths.includes(viewer.ruta) && (
                <div className="mb-3 overflow-hidden rounded-md border border-border">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/50 px-3 py-1.5 text-xs">
                    <span className="text-muted-foreground">Viendo</span>
                    <span className="font-mono text-foreground">{viewer.ruta}</span>
                    <span className="text-muted-foreground">· {formatSize(viewer.bytes)}</span>
                    {viewer.truncado && (
                      <span className="text-amber-600 dark:text-amber-500">
                        · truncado a 512 KB, se muestra solo el inicio
                      </span>
                    )}
                    <button onClick={() => setViewer(null)}
                            className={`${CHIP} ml-auto border-transparent text-muted-foreground`}>
                      cerrar
                    </button>
                  </div>
                  <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words
                                  px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
                    {viewer.texto}
                  </pre>
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
