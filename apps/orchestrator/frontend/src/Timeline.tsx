import { useState } from "react"
import { api, type ActiveRun, type Artefacto, type Fase } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { colorFase, FASE_LABEL, hora, iconoFase, puedeLanzar, tamaño } from "@/estado"

// Estilo compartido de foco/hover para los <button> nativos del visor: los botones de
// shadcn ya traen su propio anillo, pero estos son planos (chips de archivo, cerrar,
// ajuste) y sin esto quedarían mudos al navegar con teclado.
const CHIP =
  "rounded border px-1.5 py-0.5 font-mono text-[11px] transition-colors " +
  "hover:bg-accent hover:text-accent-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"

/**
 * El recorrido de fases del ticket: una fila por fase de PHASES, con su acción y el
 * artefacto que declaró haber dejado. Reemplaza a los botones de la cabecera — la acción
 * va donde está la información, el mismo principio que movió los repos a la cabecera del
 * proyecto. Las fases que aún no existen salen apagadas: el camino pendiente es contexto.
 */
export function Timeline({ fases, activo, ticketId, onRun }: {
  fases: Fase[]
  activo: ActiveRun | null
  ticketId: number
  onRun: (fase: string, instructions?: string) => void
}) {
  const [abierta, setAbierta] = useState<string | null>(null)   // caja de instrucciones
  const [instrucciones, setInstrucciones] = useState("")
  const [visor, setVisor] = useState<Artefacto | null>(null)
  const [cargando, setCargando] = useState<string | null>(null)
  const [errorVisor, setErrorVisor] = useState("")

  const ver = (ruta: string) => {
    if (visor?.ruta === ruta) return setVisor(null)     // segundo clic: cerrar
    setCargando(ruta); setErrorVisor("")
    api.artefacto(ticketId, ruta)
      .then(a => setVisor(a))
      .catch(e => { setVisor(null); setErrorVisor(String(e)) })
      .finally(() => setCargando(null))
  }

  return (
    <ol className="space-y-0">
      {fases.map((f, i) => {
        const motivo = puedeLanzar(fases, i, activo, ticketId)
        const h = f.huella
        // Dos formas de artefacto: un directorio (ruta + "/" + cada nombre) o un archivo
        // suelto (la ruta ya es completa y coincide con su propio nombre). Ver el brief:
        // cuando archivos===1 la huella es siempre el caso "archivo suelto" en este dominio
        // (el análisis es un único .md; un plan siempre trae 2+ archivos).
        const rutas = h?.existe
          ? (h.archivos === 1 && h.nombres[0] === h.ruta.split("/").pop()
              ? [h.ruta] : h.nombres.map(n => (h.archivos === 1 ? h.ruta : `${h.ruta}/${n}`)))
          : []
        const ultima = i === fases.length - 1
        const corriendo = f.estado === "corriendo"

        // Metadatos neutros en una sola línea — hora, duración, nº de corridas — en vez de
        // una fila de chips sueltos: así el nombre de la fase queda como el único elemento
        // con peso visual y el resto se lee como un dato, no como otra etiqueta.
        const metaParts: string[] = []
        if (!f.disponible) metaParts.push("no disponible aún")
        else if (f.estado === "pendiente") metaParts.push("sin corridas")
        if (f.en) metaParts.push(hora(f.en))
        if (f.duracion_s != null) {
          metaParts.push(f.duracion_s < 60 ? `${f.duracion_s}s`
            : `${Math.floor(f.duracion_s / 60)}m${String(f.duracion_s % 60).padStart(2, "0")}s`)
        }
        if (f.corridas) metaParts.push(`${f.corridas} ${f.corridas === 1 ? "corrida" : "corridas"}`)

        return (
          <li key={f.fase} className={`relative pl-9 ${f.disponible ? "" : "opacity-60"}`}>
            {/* la línea que une las fases; no se dibuja bajo la última */}
            {!ultima && <span aria-hidden className="absolute left-[11px] top-8 bottom-0 w-px bg-border" />}
            <span
              className={`absolute left-0 top-1.5 flex h-6 w-6 items-center justify-center
                          rounded-full border text-[11px] font-semibold shadow-sm transition-colors
                          ${colorFase(f.estado)}
                          ${corriendo ? "animate-pulse ring-2 ring-blue-500/30 ring-offset-2 ring-offset-background" : ""}`}
            >
              {iconoFase(f.estado)}
            </span>

            <div className={`-mx-2 rounded-lg px-2 transition-colors ${corriendo ? "bg-blue-500/5" : ""}`}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className={`text-sm font-semibold tracking-tight ${f.disponible ? "text-foreground" : "text-muted-foreground"}`}>
                  {FASE_LABEL[f.fase] ?? f.fase}
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
                            disabled={!!motivo} title={motivo || undefined}
                            onClick={() => onRun(f.fase)}>
                      {f.corridas ? "Re-correr" : "Correr"}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={!!motivo}
                            title={motivo || "Correr con instrucciones de ajuste"}
                            aria-label={`Ajustar y correr ${FASE_LABEL[f.fase] ?? f.fase}`}
                            aria-expanded={abierta === f.fase}
                            onClick={() => {
                              setAbierta(abierta === f.fase ? null : f.fase); setInstrucciones("")
                            }}>
                      ▾
                    </Button>
                  </div>
                )}
              </div>

              {motivo && f.disponible && f.estado !== "corriendo" && (
                <p className="pb-2 text-xs text-muted-foreground">{motivo}</p>
              )}

              {f.estado === "error" && f.motivo && (
                <p className="pb-2 text-xs text-destructive">{f.motivo}</p>
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
                          {h.archivos === 1 ? tamaño(h.bytes) : `${h.archivos} archivos · ${tamaño(h.bytes)}`}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {rutas.map(r => (
                          <button key={r} onClick={() => ver(r)}
                                  aria-pressed={visor?.ruta === r}
                                  className={`${CHIP} ${visor?.ruta === r
                                    ? "border-ring bg-accent text-accent-foreground"
                                    : "border-border text-muted-foreground"}`}>
                            {cargando === r ? "cargando…" : r.split("/").pop()}
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

              {abierta === f.fase && (
                <div className="pb-3">
                  <Textarea rows={2} value={instrucciones}
                            placeholder={`Ajuste para ${FASE_LABEL[f.fase]}…`}
                            onChange={e => setInstrucciones(e.target.value)} />
                  <Button size="sm" className="mt-2" disabled={!instrucciones || !!motivo}
                          onClick={() => {
                            onRun(f.fase, instrucciones); setInstrucciones(""); setAbierta(null)
                          }}>
                    Correr con este ajuste
                  </Button>
                </div>
              )}

              {errorVisor && visor === null && rutas.length > 0 && (
                <p className="pb-2 text-xs text-destructive">{errorVisor}</p>
              )}

              {visor && rutas.includes(visor.ruta) && (
                <div className="mb-3 overflow-hidden rounded-md border border-border">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/50 px-3 py-1.5 text-xs">
                    <span className="text-muted-foreground">Viendo</span>
                    <span className="font-mono text-foreground">{visor.ruta}</span>
                    <span className="text-muted-foreground">· {tamaño(visor.bytes)}</span>
                    {visor.truncado && (
                      <span className="text-amber-600 dark:text-amber-500">
                        · truncado a 512 KB, se muestra solo el inicio
                      </span>
                    )}
                    <button onClick={() => setVisor(null)}
                            className={`${CHIP} ml-auto border-transparent text-muted-foreground`}>
                      cerrar
                    </button>
                  </div>
                  <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words
                                  px-3 py-2 font-mono text-xs leading-relaxed text-foreground">
                    {visor.texto}
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
