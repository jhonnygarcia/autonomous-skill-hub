import { Fragment, useEffect, useState, type ReactNode } from "react"
import { api, type Engine, type PhaseModels as Config } from "@/api"
import { Button } from "@/components/ui/button"
import { Info } from "@/Info"
import { phaseLabel } from "@/status"
import { lang, t, type Lang } from "@/strings"

// The fan-out is Claude's: each child is a session rooted in the other repo, with ITS
// rules, hooks and `.mcp.json`, and that mounting is Claude Code's. The backend rejects
// anything else for this phase — offering it here and letting the save fail would be
// making the human discover the rule by hitting it.
const SINGLE_ENGINE_PHASES: Record<string, string> = { survey: "claude" }

// The aliases each CLI resolves to its family's latest model. A full id
// (`claude-opus-5`, `gpt-5.6-sol`) also works and the backend accepts it; aliases go
// here because they're the ones that don't go stale.
const MODELS: Record<string, string[]> = {
  claude: ["opus", "sonnet", "haiku", "fable"],
  codex: ["gpt-5.6-sol", "gpt-5.6-codex"],
}

const Path = ({ children }: { children: ReactNode }) =>
  <code className="text-foreground">{children}</code>

/**
 * What each phase does and what it leaves behind, behind the row's own `[i]`.
 *
 * It used to sit open in the row. Six of these turned a table you scan into a page you
 * scroll, and the choice being made — engine, model, effort — is one line per row. So
 * the text moved one click away and stayed exactly where it's asked for.
 *
 * The audience is someone who is not a developer, so the wording avoids the terms this
 * codebase uses among itself: no "artefacto", no "stamp", no "fan-out".
 */
const PHASE_INFO: Record<Lang, Record<string, ReactNode>> = {
  es: {
    analyze: (
      <>
        <p>
          Lee el ticket de Azure DevOps —o la solicitud que escribiste tú— con sus
          comentarios y adjuntos, revisa el repo, y escribe <strong>qué hay que hacer y
          por qué</strong>. <strong>No toca ni una línea de código.</strong>
        </p>
        <p>
          Es la ruta corta: sirve cuando el proyecto es <strong>un solo repo</strong>.
        </p>
        <p>Entrega: <Path>docs/tickets/&lt;id&gt;-analysis.md</Path></p>
      </>
    ),
    brief: (
      <>
        <p>
          Primer paso de la <strong>ruta larga</strong>, para proyectos con{" "}
          <strong>varios repos</strong>. Lee el ticket y decide cuáles de ellos vale la
          pena revisar, en vez de revisarlos todos.
        </p>
        <p>Entrega: <Path>docs/tickets/&lt;id&gt;-brief.md</Path></p>
      </>
    ),
    survey: (
      <>
        <p>
          Abre <strong>cada repo elegido por separado</strong>, cada uno con sus propias
          reglas, y anota qué le pide el ticket a <em>ese</em> repo. Es lo que evita que
          se le apliquen a un repo las convenciones de otro.
        </p>
        <p>
          <strong>Solo puede correr con claude</strong>: abrir un repo cargando su propia
          configuración es algo que hoy solo Claude Code sabe hacer.
        </p>
        <p>Entrega: un sondeo por cada repo revisado</p>
      </>
    ),
    consolidate: (
      <>
        <p>
          Junta los sondeos en <strong>un solo documento</strong>, incluyendo lo que cada
          repo espera de los otros — que es justo lo que ninguno podía escribir solo.
        </p>
        <p>
          Termina en el <strong>mismo archivo</strong> que produce Análisis, así que de
          aquí en adelante da igual qué ruta tomaste.
        </p>
        <p>Entrega: <Path>docs/tickets/&lt;id&gt;-analysis.md</Path></p>
      </>
    ),
    design: (
      <>
        <p>
          Convierte ese documento en una <strong>lista de tareas que otro pueda
          ejecutar</strong>: cada tarea con la prueba que debe pasar y el comando para
          comprobarla.
        </p>
        <p><strong>Todavía no escribe código del producto</strong>: su entregable es el plan.</p>
        <p>Entrega: <Path>openspec/changes/&lt;id&gt;-.../</Path></p>
      </>
    ),
    implement: (
      <>
        <p>
          Ejecuta el plan <strong>tarea por tarea</strong>: escribe primero la prueba,
          luego el código, lo hace revisar por un segundo agente, y hace{" "}
          <strong>un commit por tarea</strong>.
        </p>
        <p>
          Todo ocurre en una <strong>rama aparte</strong>, nunca en la principal.{" "}
          <strong>No abre el pull request</strong>: pedirle a tu equipo que mire es una
          decisión tuya y se toma fuera de aquí.
        </p>
        <p>Entrega: commits en la rama <Path>ticket-agent/&lt;id&gt;</Path></p>
      </>
    ),
  },
  en: {
    analyze: (
      <>
        <p>
          Reads the Azure DevOps ticket —or the request you wrote yourself— with its
          comments and attachments, reviews the repo, and writes <strong>what needs to
          be done and why</strong>. <strong>It doesn't touch a single line of code.</strong>
        </p>
        <p>
          It's the short route: useful when the project is <strong>a single repo</strong>.
        </p>
        <p>Delivers: <Path>docs/tickets/&lt;id&gt;-analysis.md</Path></p>
      </>
    ),
    brief: (
      <>
        <p>
          First step of the <strong>long route</strong>, for projects with{" "}
          <strong>several repos</strong>. Reads the ticket and decides which of them are
          worth reviewing, instead of reviewing all of them.
        </p>
        <p>Delivers: <Path>docs/tickets/&lt;id&gt;-brief.md</Path></p>
      </>
    ),
    survey: (
      <>
        <p>
          Opens <strong>each chosen repo separately</strong>, each with its own rules,
          and writes down what the ticket asks of <em>that</em> repo. That's what keeps
          one repo's conventions from being applied to another.
        </p>
        <p>
          <strong>Can only run with claude</strong>: opening a repo while loading its
          own configuration is something only Claude Code knows how to do today.
        </p>
        <p>Delivers: one survey per repo reviewed</p>
      </>
    ),
    consolidate: (
      <>
        <p>
          Merges the surveys into <strong>a single document</strong>, including what
          each repo expects from the others — which is exactly what none of them could
          write alone.
        </p>
        <p>
          Ends in the <strong>same file</strong> that Analyze produces, so from here on
          it doesn't matter which route you took.
        </p>
        <p>Delivers: <Path>docs/tickets/&lt;id&gt;-analysis.md</Path></p>
      </>
    ),
    design: (
      <>
        <p>
          Turns that document into a <strong>list of tasks someone else can
          execute</strong>: each task with the test it must pass and the command to
          check it.
        </p>
        <p><strong>It still doesn't write product code</strong>: its deliverable is the plan.</p>
        <p>Delivers: <Path>openspec/changes/&lt;id&gt;-.../</Path></p>
      </>
    ),
    implement: (
      <>
        <p>
          Executes the plan <strong>task by task</strong>: writes the test first, then
          the code, has it reviewed by a second agent, and makes{" "}
          <strong>one commit per task</strong>.
        </p>
        <p>
          It all happens on a <strong>separate branch</strong>, never on the main one.{" "}
          <strong>It doesn't open the pull request</strong>: asking your team to look is
          your call, made outside of here.
        </p>
        <p>Delivers: commits on branch <Path>ticket-agent/&lt;id&gt;</Path></p>
      </>
    ),
  },
}

/** A phase that opens a stage. Injected as a header row above it, so the six rows stop
 *  reading as six steps in a line — Análisis and Brief+Sondeo+Consolidación are two
 *  ROUTES to the same file, and the table never said so. This note stays open and not
 *  behind an `[i]`: it's what keeps the table from being misread, and a misreading you
 *  have to click to correct is a misreading. Keyed by phase and consulted during the
 *  normal iteration, so a phase the backend adds later can't fall through a hardcoded
 *  list and disappear from the screen.
 *
 *  These strings resolve once, at module load, via `t()` — safe only because a
 *  language switch remounts the whole app (`location.reload()` in `Language.tsx`).
 *  Replace that reload with a context provider and this constant goes stale until
 *  the next full page load. */
const STAGE: Record<string, { title: string; note?: string }> = {
  analyze: {
    title: t("models.stageAnalyzeTitle"),
    note: t("models.stageAnalyzeNote"),
  },
  design: { title: t("models.stageDesignTitle") },
  implement: { title: t("models.stageImplementTitle") },
}

/** The intro paragraph above the table and the `<Info>` popover body beside it.
 *  Same reasoning as `PHASE_INFO`: markup lands inside the sentence, so the block
 *  is indexed by language where it already lives instead of split into keys. */
const MODELS_INTRO: Record<Lang, ReactNode> = {
  es: (
    <>
      Un ticket pasa por tres etapas: <strong>entenderlo</strong>,{" "}
      <strong>planearlo</strong> y <strong>escribir el código</strong>. Aquí eliges,
      para cada fase, con qué <strong>motor</strong> corre, con qué{" "}
      <strong>modelo</strong> y con cuánto <strong>esfuerzo</strong> de razonamiento.
    </>
  ),
  en: (
    <>
      A ticket goes through three stages: <strong>understanding it</strong>,{" "}
      <strong>planning it</strong>, and <strong>writing the code</strong>. Here you
      choose, for each phase, which <strong>engine</strong> it runs with, which{" "}
      <strong>model</strong>, and how much reasoning <strong>effort</strong>.
    </>
  ),
}

const MODELS_INFO: Record<Lang, ReactNode> = {
  es: (
    <>
      <p>
        El <strong>motor</strong> es el programa de IA que ejecuta la fase:{" "}
        <code className="text-foreground">claude</code> o{" "}
        <code className="text-foreground">codex</code>. Tiene que estar instalado y
        con la sesión iniciada <strong>en esta máquina</strong> — eso corre por tu
        cuenta, no del orquestador.
      </p>
      <p>
        Cada fase deja su resultado en un archivo dentro de tu repo y la siguiente
        parte de ese archivo, así que <strong>puedes usar un motor distinto en cada
        una</strong> sin que se estorben. Lo único que no se puede es continuar una
        corrida con un motor distinto del que la empezó.
      </p>
      <p>
        <strong>(por defecto)</strong> deja que el modelo o el esfuerzo los decida el
        repo donde corre, que es lo que hacía antes de ser configurable. Lo que
        guardes aquí aplica <strong>a la siguiente corrida</strong>.
      </p>
    </>
  ),
  en: (
    <>
      <p>
        The <strong>engine</strong> is the AI program that runs the phase:{" "}
        <code className="text-foreground">claude</code> or{" "}
        <code className="text-foreground">codex</code>. It has to be installed and
        logged in <strong>on this machine</strong> — that's on you, not the
        orchestrator.
      </p>
      <p>
        Each phase leaves its result in a file inside your repo, and the next one
        reads that same file, so <strong>you can use a different engine for each
        one</strong> without them getting in each other's way. The only thing you
        can't do is continue a run with a different engine than the one that started
        it.
      </p>
      <p>
        <strong>(default)</strong> lets the model or the effort be decided by the
        repo it runs in, which is what it did before it became configurable. What you
        save here applies <strong>to the next run</strong>.
      </p>
    </>
  ),
}

function Selector({ value, onChange, options, label, empty = t("models.selectorDefault") }: {
  value: string; onChange: (v: string) => void; options: string[]
  label: string; empty?: string | null
}) {
  return (
    <select aria-label={label} value={value} onChange={e => onChange(e.target.value)}
            className="h-9 w-full rounded-sm border border-input bg-muted px-2 text-sm">
      {empty !== null && <option value="">{empty}</option>}
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

export function Models() {
  const [cfg, setCfg] = useState<Config | null>(null)
  const [engines, setEngines] = useState<Engine[]>([])
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    Promise.all([api.models(), api.engines()])
      .then(([m, e]) => { setCfg(m); setEngines(e) })
      .catch(e => setError(String(e)))
  }, [])

  const set = (phase: string, field: "model" | "effort" | "engine", v: string) => {
    setCfg(c => {
      if (!c) return c
      const next = { ...c[phase], [field]: v }
      // Changing the engine clears the model and the effort instead of carrying them
      // over: they belong to the CLI that was selected. `opus` means nothing to Codex
      // and `max` is an effort Codex rejects outright — keeping them would save a
      // configuration the next run dies on, after the UI said "guardado".
      if (field === "engine") { next.model = ""; next.effort = "" }
      return { ...c, [phase]: next }
    })
    setDirty(true)
  }
  const save = () => cfg && api.saveModels(cfg)
    .then(m => { setCfg(m); setDirty(false); setError("") })
    .catch(e => setError(String(e)))

  const th = "pb-2 pr-3 text-left text-[11px] font-normal uppercase tracking-wide text-muted-foreground"

  return (
    <div className="space-y-4">
      {/* A `div` and not a `p`: `Info` renders its popover as a sibling of the button,
          and a block element inside a paragraph is invalid nesting. */}
      <div className="max-w-3xl text-xs text-muted-foreground">
        {MODELS_INTRO[lang()]}
        <Info label={t("models.infoLabel")}>
          {MODELS_INFO[lang()]}
        </Info>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {cfg && (
        <div className="overflow-x-auto">
          {/* `table-fixed` + a `colgroup` so the widths are declared once and hold;
              auto layout sizes columns from content and the phase column ends up a
              narrow ribbon beside three roomy selects. */}
          <table className="w-full min-w-[38rem] table-fixed">
            <colgroup>
              <col className="w-[34%]" />
              <col className="w-[22%]" />
              <col className="w-[22%]" />
              <col className="w-[22%]" />
            </colgroup>
            <thead>
              <tr>
                <th className={th}>{t("models.tableHeaderPhase")}</th>
                <th className={th}>{t("models.tableHeaderEngine")}</th>
                <th className={th}>{t("models.tableHeaderModel")}</th>
                <th className={th}>{t("models.tableHeaderEffort")}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cfg).map(([phase, f]) => {
                const name = phaseLabel(phase)
                const info = PHASE_INFO[lang()][phase]
                const stage = STAGE[phase]
                // The effort list comes from the backend's registry, per engine. An
                // engine it doesn't know about yet (a stale tab against a newer backend)
                // gets no options rather than someone else's.
                const efforts = engines.find(e => e.id === f.engine)?.efforts ?? []
                const forced = SINGLE_ENGINE_PHASES[phase]
                return (
                  <Fragment key={phase}>
                    {stage && (
                      <tr>
                        <td colSpan={4} className="border-t border-border pb-2 pt-5">
                          <p className="text-xs font-bold uppercase tracking-wide">{stage.title}</p>
                          {stage.note && (
                            <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{stage.note}</p>
                          )}
                        </td>
                      </tr>
                    )}
                    <tr className="border-t border-border">
                      <td className="py-2 pr-4">
                        <span className="text-sm font-medium">{name}</span>
                        {info && <Info label={name}>{info}</Info>}
                      </td>
                      <td className="py-2 pr-3">
                        <Selector label={`${t("models.engineLabel")} ${name}`} value={f.engine} empty={null}
                                  options={forced ? [forced] : engines.map(e => e.id)}
                                  onChange={v => set(phase, "engine", v)} />
                      </td>
                      <td className="py-2 pr-3">
                        <Selector label={`${t("models.modelLabel")} ${name}`} value={f.model}
                                  options={MODELS[f.engine] ?? []}
                                  onChange={v => set(phase, "model", v)} />
                      </td>
                      <td className="py-2">
                        <Selector label={`${t("models.effortLabel")} ${name}`} value={f.effort}
                                  options={efforts.filter(Boolean)}
                                  onChange={v => set(phase, "effort", v)} />
                      </td>
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <Button size="sm" onClick={save} disabled={!dirty}>{t("models.saveButton")}</Button>
    </div>
  )
}
