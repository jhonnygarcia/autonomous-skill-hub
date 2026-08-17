import { useEffect, useState } from "react"
import { api, type Engine, type PhaseModels as Config } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PHASE_LABEL } from "@/status"

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

function Selector({ value, onChange, options, label, empty = "(por defecto)" }: {
  value: string; onChange: (v: string) => void; options: string[]
  label: string; empty?: string | null
}) {
  return (
    <select aria-label={label} value={value} onChange={e => onChange(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm">
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

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Engine y modelo por fase</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Con qué CLI, qué modelo y cuánto esfuerzo de razonamiento corre cada fase.
          Cada fase deja su entregable en un archivo, así que la siguiente no necesita
          saber quién lo escribió: se pueden mezclar. <strong>(por defecto)</strong>
          deja decidir al repo destino. Aplica a la siguiente corrida; no hace falta
          reiniciar el backend.
        </p>
        <p className="text-xs text-muted-foreground">
          El CLI que elijas tiene que estar instalado y con sesión iniciada en esta
          máquina — eso es tuyo, no del orquestador. Una continuación nunca cruza
          engines: la sesión pertenece al CLI que la creó.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}

        {cfg && (
          <div className="space-y-1">
            <div className="flex gap-2 text-[11px] uppercase tracking-wide text-muted-foreground/70">
              <span className="w-24">fase</span>
              <span className="w-36">engine</span>
              <span className="w-40">modelo</span>
              <span className="w-36">effort</span>
            </div>
            {Object.entries(cfg).map(([phase, f]) => {
              const name = PHASE_LABEL[phase] ?? phase
              // The effort list comes from the backend's registry, per engine. An
              // engine it doesn't know about yet (a stale tab against a newer backend)
              // gets no options rather than someone else's.
              const efforts = engines.find(e => e.id === f.engine)?.efforts ?? []
              const forced = SINGLE_ENGINE_PHASES[phase]
              return (
                <div key={phase} className="flex items-center gap-2">
                  <span className="w-24 text-sm font-medium">{name}</span>
                  <div className="w-36">
                    <Selector label={`Engine de ${name}`} value={f.engine} empty={null}
                              options={forced ? [forced] : engines.map(e => e.id)}
                              onChange={v => set(phase, "engine", v)} />
                  </div>
                  <div className="w-40">
                    <Selector label={`Modelo de ${name}`} value={f.model}
                              options={MODELS[f.engine] ?? []}
                              onChange={v => set(phase, "model", v)} />
                  </div>
                  <div className="w-36">
                    <Selector label={`Effort de ${name}`} value={f.effort}
                              options={efforts.filter(Boolean)}
                              onChange={v => set(phase, "effort", v)} />
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <Button size="sm" onClick={save} disabled={!dirty}>Guardar</Button>
      </CardContent>
    </Card>
  )
}
