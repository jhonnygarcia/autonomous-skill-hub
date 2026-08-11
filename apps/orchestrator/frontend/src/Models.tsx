import { useEffect, useState } from "react"
import { api, type PhaseModels as Config } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PHASE_LABEL } from "@/status"

// The aliases the CLI resolves to each family's latest model. A full id
// (`claude-opus-5`) also works and the backend accepts it; aliases go here
// because they're the ones that don't go stale.
const MODELS = ["opus", "sonnet", "haiku", "fable"]
const EFFORTS = ["low", "medium", "high", "xhigh", "max"]

function Selector({ value, onChange, options, label }: {
  value: string; onChange: (v: string) => void; options: string[]; label: string
}) {
  return (
    <select aria-label={label} value={value} onChange={e => onChange(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm">
      <option value="">(por defecto)</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

export function Models() {
  const [cfg, setCfg] = useState<Config | null>(null)
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => { api.models().then(setCfg).catch(e => setError(String(e))) }, [])

  const set = (phase: string, field: "model" | "effort", v: string) => {
    setCfg(c => c && { ...c, [phase]: { ...c[phase], [field]: v } })
    setDirty(true)
  }
  const save = () => cfg && api.saveModels(cfg)
    .then(m => { setCfg(m); setDirty(false); setError("") })
    .catch(e => setError(String(e)))

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Modelo por fase</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Con qué modelo y con cuánto esfuerzo de razonamiento corre cada fase.
          <strong> (por defecto)</strong> deja decidir al repo destino, que es lo que
          hacía el orquestador hasta ahora. Aplica a la siguiente corrida; no hace falta
          reiniciar el backend.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}

        {cfg && (
          <div className="space-y-1">
            <div className="flex gap-2 text-[11px] uppercase tracking-wide text-muted-foreground/70">
              <span className="w-24">fase</span>
              <span className="w-40">modelo</span>
              <span className="w-40">effort</span>
            </div>
            {Object.entries(cfg).map(([phase, f]) => (
              <div key={phase} className="flex items-center gap-2">
                <span className="w-24 text-sm font-medium">{PHASE_LABEL[phase] ?? phase}</span>
                <div className="w-40">
                  <Selector label={`Modelo de ${PHASE_LABEL[phase] ?? phase}`} value={f.model}
                            options={MODELS} onChange={v => set(phase, "model", v)} />
                </div>
                <div className="w-40">
                  <Selector label={`Effort de ${PHASE_LABEL[phase] ?? phase}`} value={f.effort}
                            options={EFFORTS} onChange={v => set(phase, "effort", v)} />
                </div>
              </div>
            ))}
          </div>
        )}

        <Button size="sm" onClick={save} disabled={!dirty}>Guardar</Button>
      </CardContent>
    </Card>
  )
}
