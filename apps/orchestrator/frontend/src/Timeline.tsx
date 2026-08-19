import { useEffect, useRef, useState } from "react"
import { api, type ActiveRun, type Artifact, type Phase, type Preflight, type Run } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Decisions } from "@/Decisions"
import { Markdown } from "@/Markdown"
import { canRunPhase, durationText, formatSize, formatTime, phaseLabel, phaseColor, phaseIcon } from "@/status"
import { plural, t } from "@/strings"

// Shared focus/hover style for the viewer's native <button>s: shadcn buttons already
// have their own ring, but these are plain (file chips, close, adjust) and without
// this they'd be silent when navigating by keyboard.
const CHIP =
  "rounded border px-1.5 py-0.5 font-mono text-[11px] transition-colors " +
  "hover:bg-accent hover:text-accent-foreground " +
  "focus-visible:outline-1 focus-visible:outline-ring"

/**
 * The ticket's phase timeline: one row per phase in PHASES, with its action and the
 * artifact it declared having left. Replaces the header buttons — the action goes
 * where the information is, the same principle that moved the repos into the project
 * header. Phases that don't exist yet show dimmed: the pending path is context.
 */
export function Timeline({ phases, runs, activeRun, ticketId, onRun, onRestore, restoring }: {
  phases: Phase[]
  runs: Run[]
  activeRun: ActiveRun | null
  ticketId: number
  onRun: (phase: string, instructions?: string, resume?: boolean) => void
  onRestore: (runId: number) => void
  /** Run ids with a restore in flight — disables the button so a fast double-click
   *  doesn't send a second request for the file the first one just put back. */
  restoring: Set<number>
}) {
  const [openPhase, setOpenPhase] = useState<string | null>(null)   // instructions box
  const [instructions, setInstructions] = useState("")
  // Shared across phases, like `instructions`, so it resets on every open and on send:
  // without that, what you chose on `analyze` shows up already ticked on `implement`.
  const [resume, setResume] = useState(false)
  const [viewer, setViewer] = useState<Artifact | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<{ ruta: string; msg: string } | null>(null)
  // Rendered by default — raw stays one click away, never hidden. Shared across every
  // chip like `instructions`: switching files keeps whatever view you were in, and a
  // fresh viewer always opens rendered, the more readable default.
  const [rendered, setRendered] = useState(true)
  // Each click on a chip bumps the sequence; a response that lands when it's no longer
  // the last one requested is discarded entirely (it neither overwrites the viewer nor
  // clears the `loading` of the click still in flight). Without this, a slow click on A
  // followed by a fast one on B leaves B shown and then A overwrites it once it resolves late.
  const requestId = useRef(0)
  // What the repo and the machine are missing before anything can be launched. Asked
  // once per ticket: the credential check spawns `az`, so one call per phase would tax
  // merely opening a ticket. `null` while it's in flight or if the request failed —
  // neither is a reason to block the buttons, since `POST /run` checks again anyway.
  const [pf, setPf] = useState<Preflight | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [pfError, setPfError] = useState("")
  useEffect(() => { api.preflight(ticketId).then(setPf).catch(() => setPf(null)) }, [ticketId])

  // The blockers that apply to THIS phase — same filter as `preflight_blockers` in
  // app.py, which is the authoritative one.
  const pfBlock = (fase: string) =>
    (pf?.bloqueos ?? []).filter(b => b.fases === null || b.fases.includes(fase))
  const repairable = (pf?.bloqueos ?? []).some(b => b.reparable)

  const prepare = () => {
    setPreparing(true); setPfError("")
    api.preparar(ticketId)
      .then(setPf)
      .catch(e => setPfError(String(e)))
      .finally(() => setPreparing(false))
  }

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
    <>
      {/* Above the timeline and not inside a phase row: these are conditions of the
          repo and the machine, not of a phase, and half of them can't be fixed from
          here at all. Saying it before you click is the whole feature — every one of
          these used to be discovered minutes into a run, as a CLI error about
          something else. */}
      {pf && (pf.bloqueos.length > 0 || pf.avisos.length > 0) && (
        <div className={`mb-3 rounded-lg border px-3 py-2 text-xs ${
          pf.bloqueos.length ? "border-destructive/40 bg-destructive/5" : "border-border bg-muted/40"}`}>
          {pf.bloqueos.map(b => (
            <p key={b.que} className="text-destructive">
              ✖ {b.msg}
              {b.fases && <span className="text-muted-foreground">
                {" "}({t("timeline.blocksLabel")}: {b.fases.map(x => phaseLabel(x)).join(", ")})
              </span>}
            </p>
          ))}
          {pf.avisos.map(a => (
            <p key={a.que} className="text-warning-active">⚠ {a.msg}</p>
          ))}
          {repairable && (
            <Button size="sm" variant="outline" className="mt-2" disabled={preparing}
                    onClick={prepare}>
              {preparing ? t("timeline.preparing") : t("timeline.prepareRepo")}
            </Button>
          )}
          {pfError && <p className="mt-1 text-destructive">{pfError}</p>}
        </div>
      )}

    <ol className="space-y-0">
      {phases.map((f, i) => {
        // Two variables and not one: `blocked` disables the buttons and fills their
        // tooltip, `reason` is the line printed under the row. A preflight blocker is
        // NOT printed per row — it's the same sentence for all six phases and the
        // banner above already says it once.
        const reason = canRunPhase(phases, i, activeRun, ticketId)
        const blocked = pfBlock(f.fase)[0]?.msg || reason
        const h = f.huella
        // `runs` arrives sorted by id DESC, same as `phases_for` in the backend: the
        // first one matching this phase is its most recent run, the same one that
        // produced `h`. Only `implement` sets it — the rest arrive as `null`.
        const branch = runs.find(r => r.phase === f.fase)?.branch ?? null
        // The most recent good run of this phase whose salida actually holds the
        // declared deliverable: what the Restore shortcut puts back when it's gone
        // from disk. Older snapshots are reachable from the run history. Gated on
        // `restorable`, not on `archive_path` alone — a fan-out survey gets an
        // `archive_path` too, but its HUELLA is a scratch path outside every repo, so
        // its `salida/` never has anything a restore could put back.
        const restorableRun = runs.find(r => r.phase === f.fase && r.restorable
          && (r.artifact_state === "ok" || r.artifact_state === "parcial")) ?? null
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
        // A phase that declared a deliverable nobody can find must not read as success.
        // It keeps the state the agent claimed —that decision stands, a false stamp
        // gives itself away rather than being hidden— but it wears the amber this app
        // already uses for "done, with caveats" instead of the green that means done.
        const badge = f.entregable === false ? "parcial" : f.estado

        // Neutral metadata on a single line — time, duration, run count — instead
        // of a row of loose chips: this way the phase name stays the only element
        // with visual weight and the rest reads as data, not another label.
        const metaParts: string[] = []
        if (!f.disponible) metaParts.push(t("timeline.notAvailableYet"))
        else if (f.estado === "pendiente") metaParts.push(t("timeline.noRunsShort"))
        if (f.en) metaParts.push(formatTime(f.en))
        if (f.duracion_s != null) metaParts.push(durationText(f.duracion_s))
        if (f.corridas) metaParts.push(`${f.corridas} ${plural(f.corridas, t("timeline.oneRun"), t("timeline.manyRuns"))}`)

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
                          ${phaseColor(badge)}
                          ${isRunning ? "animate-pulse" : ""}`}
            >
              {phaseIcon(badge)}
            </span>

            <div className={`-mx-2 rounded-lg px-2 transition-colors ${isRunning ? "bg-info/5" : ""}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className={`text-sm font-semibold tracking-tight ${f.disponible ? "text-foreground" : "text-muted-foreground"}`}>
                  {phaseLabel(f.fase)}
                </span>
                {metaParts.length > 0 && (
                  <span className="text-xs text-muted-foreground">{metaParts.join(" · ")}</span>
                )}
                {!!f.fallidas && (
                  <span className="text-xs font-medium text-warning-active">
                    ⚠ {f.fallidas} falló
                  </span>
                )}

                {f.disponible && (
                  <div className="ml-auto flex gap-1">
                    <Button size="sm" variant={f.estado === "pendiente" ? "default" : "outline"}
                            disabled={!!blocked} title={blocked || undefined}
                            onClick={() => onRun(f.fase)}>
                      {f.corridas ? t("timeline.rerun") : t("timeline.run")}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={!!blocked}
                            title={blocked || t("timeline.runWithAdjustmentsTitle")}
                            aria-label={`${t("timeline.adjustAndRunAriaLabel")} ${phaseLabel(f.fase)}`}
                            aria-expanded={openPhase === f.fase}
                            aria-controls={`ajuste-${f.fase}`}
                            onClick={() => {
                              setOpenPhase(openPhase === f.fase ? null : f.fase)
                              setInstructions(""); setResume(false)
                            }}>
                      ▾ {t("timeline.adjust")}
                    </Button>
                  </div>
                )}
              </div>

              {reason && f.disponible && f.estado !== "corriendo" && (
                <p className="pb-2 text-xs text-muted-foreground">{reason}</p>
              )}

              {/* An 83-minute run used to say only "corriendo". The bar answers "how
                  much is left"; the count next to it is the honest part — the width is
                  a proportion of tasks, not of time. */}
              {f.progreso && (
                <div className="flex items-center gap-2 pb-2 text-xs">
                  <div className="h-1.5 w-40 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-info transition-all"
                         style={{ width: `${Math.round(100 * f.progreso.hechas / f.progreso.total)}%` }} />
                  </div>
                  <span className="text-muted-foreground">
                    {t("timeline.taskLabel")} {f.progreso.hechas} {t("timeline.taskOfLabel")} {f.progreso.total}
                  </span>
                </div>
              )}

              {/* Answerable in place — without this nobody reads the `Decisiones para
                  ti` sections: finding them meant opening an 8 KB document and
                  hunting, answering them meant editing it by hand. `f.decisiones` only
                  ever arrives alongside a single-FILE footprint (`open_decisions` in
                  app.py resolves through `declared_file_or_none`, which rejects a
                  directory), so `h.ruta` is always the right `ruta` here. */}
              {f.decisiones && h && (
                <Decisions ticketId={ticketId} ruta={h.ruta} counts={f.decisiones} />
              )}

              {f.estado === "error" && f.motivo && (
                <p className="pb-2 text-xs text-destructive">{f.motivo}</p>
              )}

              {/* The reserve of a `parcial`: the footprint was declared, but with
                  caveats (e.g. `openspec validate` didn't pass). Goes next to the
                  footprint, in the same amber this state already uses — doesn't
                  replace the artifact row. */}
              {f.estado === "parcial" && f.motivo && (
                <p className="pb-2 text-xs text-warning-active">{f.motivo}</p>
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
                  <span className="text-muted-foreground">{t("timeline.branchLabel")}</span>
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
                        <span className="text-muted-foreground">{t("timeline.artifactLabel")}</span>
                        <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
                          {h.ruta}
                        </span>
                        <span className="text-muted-foreground">
                          {h.archivos === 1 ? formatSize(h.bytes) : `${h.archivos} ${t("timeline.filesLabel")} · ${formatSize(h.bytes)}`}
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
                            {loading === it.ruta ? t("common.loading") : it.etiqueta}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <span className="flex flex-wrap items-center gap-2 text-warning-active">
                      <span>
                        Artefacto declarado en{" "}
                        <span className="font-mono">{h.ruta}</span>, no se encontró en disco
                      </span>
                      {restorableRun && (
                        <Button size="sm" variant="outline" className="h-6 text-xs"
                                disabled={restoring.has(restorableRun.id)}
                                onClick={() => onRestore(restorableRun.id)}>
                          {t("timeline.restoreFromArchive")}
                        </Button>
                      )}
                    </span>
                  )}
                </div>
              )}

              {openPhase === f.fase && (
                <div id={`ajuste-${f.fase}`} className="pb-3">
                  <Textarea rows={2} value={instructions}
                            placeholder={`${t("timeline.adjustmentFor")} ${phaseLabel(f.fase)}…`}
                            aria-label={`${t("timeline.adjustmentFor")} ${phaseLabel(f.fase)}`}
                            onChange={e => setInstructions(e.target.value)} />

                  {/* Two mutually exclusive routes, so a radio and not a checkbox:
                      they read against each other. `Sesión nueva` is the default
                      because it's the safe one — continuing drags along the very
                      reasoning the adjustment may be correcting. */}
                  <fieldset className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                    <legend className="sr-only">{t("timeline.howAdjustmentApplies")}</legend>
                    <label className="flex items-center gap-1.5">
                      <input type="radio" name={`modo-${f.fase}`} checked={!resume}
                             onChange={() => setResume(false)} />
                      {t("timeline.newSession")}
                    </label>
                    <label className="flex items-center gap-1.5"
                           title={f.puede_continuar
                             ? undefined
                             : t("timeline.noPreviousSessionTitle")}>
                      <input type="radio" name={`modo-${f.fase}`} checked={resume}
                             disabled={!f.puede_continuar}
                             onChange={() => setResume(true)} />
                      <span className={f.puede_continuar ? "" : "text-muted-foreground"}>
                        {t("timeline.continuePrevious")}
                      </span>
                    </label>
                    {!!f.continuaciones && (
                      <span className="text-muted-foreground">
                        #{f.continuaciones + 1} {t("timeline.continuationLabel")}
                      </span>
                    )}
                  </fieldset>

                  {/* The criterion, written down: it's the one decision only the human
                      can make, and it doesn't survive as something to remember. */}
                  <p className="mt-1 text-xs text-muted-foreground">
                    Si <strong>añades</strong> alcance, continuar ahorra la exploración.
                    Si <strong>corriges</strong> lo que entendió, sesión nueva.
                  </p>

                  <Button size="sm" className="mt-2" disabled={!instructions || !!reason}
                          onClick={() => {
                            onRun(f.fase, instructions, resume)
                            setInstructions(""); setResume(false); setOpenPhase(null)
                          }}>
                    {t("timeline.runWithAdjustmentButton")}
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
                    <span className="text-muted-foreground">{t("timeline.viewing")}</span>
                    <span className="font-mono text-foreground">{viewer.ruta}</span>
                    <span className="text-muted-foreground">· {formatSize(viewer.bytes)}</span>
                    {viewer.truncado && (
                      <span className="text-warning-active">
                        · {t("timeline.truncatedNote")}
                      </span>
                    )}
                    {/* Toggle, never a replacement: the rendered view is a convenience
                        over the same text, and nothing is ever hidden behind it. */}
                    <button onClick={() => setRendered(v => !v)}
                            aria-pressed={!rendered}
                            className={`${CHIP} ml-auto border-border text-muted-foreground`}>
                      {rendered ? t("timeline.viewRaw") : t("timeline.viewRendered")}
                    </button>
                    <button onClick={() => setViewer(null)}
                            className={`${CHIP} border-transparent text-muted-foreground`}>
                      {t("timeline.close")}
                    </button>
                  </div>
                  {rendered ? (
                    <div className="max-h-[32rem] overflow-auto px-3 py-2">
                      <Markdown text={viewer.texto} />
                    </div>
                  ) : (
                    <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words
                                    px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
                      {viewer.texto}
                    </pre>
                  )}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ol>
    </>
  )
}
