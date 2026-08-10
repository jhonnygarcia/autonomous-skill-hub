import { useRef, useState } from "react"
import { api, type ActiveRun, type Artefacto, type Fase } from "@/api"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { colorFase, duracionTexto, FASE_LABEL, hora, iconoFase, puedeLanzar, tamaño } from "@/estado"

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
  const [error, setError] = useState<{ ruta: string; msg: string } | null>(null)
  // Cada click a un chip incrementa la secuencia; una respuesta que llega cuando ya no es
  // la última pedida se descarta entera (ni pisa el visor, ni borra el `cargando` del
  // clic que sí sigue en vuelo). Sin esto, un clic lento en A seguido de uno rápido en B
  // deja a B mostrado y luego lo sobreescribe A al resolver tarde.
  const peticion = useRef(0)

  const ver = (ruta: string) => {
    if (visor?.ruta === ruta) return setVisor(null)     // segundo clic: cerrar
    const id = ++peticion.current
    setCargando(ruta); setError(null)
    api.artefacto(ticketId, ruta)
      .then(a => { if (id === peticion.current) setVisor(a) })
      .catch(e => { if (id === peticion.current) { setVisor(null); setError({ ruta, msg: String(e) }) } })
      .finally(() => { if (id === peticion.current) setCargando(null) })
  }

  return (
    <ol className="space-y-0">
      {fases.map((f, i) => {
        const motivo = puedeLanzar(fases, i, activo, ticketId)
        const h = f.huella
        // Dos formas de artefacto: un directorio (ruta + "/" + cada nombre) o un archivo
        // suelto (la ruta ya es completa y coincide con su propio nombre). La decisión se
        // toma UNA vez, fuera del map — meterla dentro del map (como en la primera versión)
        // hacía que la rama "no coincide" recalculara `archivos === 1` y llegara a la misma
        // conclusión que la rama "sí coincide", así que un plan `parcial` que se detiene con
        // un solo archivo en el directorio (p.ej. solo `proposal.md`) pintaba un chip
        // rotulado con el nombre del DIRECTORIO, que al pulsarlo daba 400.
        const esArchivo = h?.existe ? h.archivos === 1 && h.nombres[0] === h.ruta.split("/").pop() : false
        // ponytail: un directorio "X/" que por casualidad contuviera un único archivo
        // también llamado "X" produce el mismo payload {ruta:"X", nombres:["X"]} que un
        // archivo suelto "X" — ambigüedad real, irresoluble desde el frontend sin que el
        // backend marque `es_dir`. No se da en la práctica hoy (analyze siempre es archivo
        // suelto; design siempre trae 2+), así que se deja anotada y no se resuelve aquí.
        const items: { ruta: string; etiqueta: string }[] = !h?.existe ? []
          : esArchivo ? [{ ruta: h.ruta, etiqueta: h.nombres[0] }]
          // La etiqueta es el nombre RELATIVO que mandó el backend (`specs/pagos/spec.md`),
          // no su basename: con dos capacidades, dos `spec.md` serían indistinguibles.
          : h.nombres.map(n => ({ ruta: `${h.ruta}/${n}`, etiqueta: n }))
        const rutas = items.map(it => it.ruta)
        const ultima = i === fases.length - 1
        const corriendo = f.estado === "corriendo"

        // Metadatos neutros en una sola línea — hora, duración, nº de corridas — en vez de
        // una fila de chips sueltos: así el nombre de la fase queda como el único elemento
        // con peso visual y el resto se lee como un dato, no como otra etiqueta.
        const metaParts: string[] = []
        if (!f.disponible) metaParts.push("no disponible aún")
        else if (f.estado === "pendiente") metaParts.push("sin corridas")
        if (f.en) metaParts.push(hora(f.en))
        if (f.duracion_s != null) metaParts.push(duracionTexto(f.duracion_s))
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
                            aria-controls={`ajuste-${f.fase}`}
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

              {/* La reserva de un `parcial`: la huella se declaró, pero con matices
                  (p.ej. `openspec validate` no pasó). Va junto a la huella, en el mismo
                  ámbar que ya usa este estado — no reemplaza la fila del artefacto. */}
              {f.estado === "parcial" && f.motivo && (
                <p className="pb-2 text-xs text-amber-600 dark:text-amber-500">{f.motivo}</p>
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
                        {items.map(it => (
                          <button key={it.ruta} onClick={() => ver(it.ruta)}
                                  title={it.ruta}
                                  aria-pressed={visor?.ruta === it.ruta}
                                  className={`${CHIP} ${visor?.ruta === it.ruta
                                    ? "border-ring bg-accent text-accent-foreground"
                                    : "border-border text-muted-foreground"}`}>
                            {cargando === it.ruta ? "cargando…" : it.etiqueta}
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
                <div id={`ajuste-${f.fase}`} className="pb-3">
                  <Textarea rows={2} value={instrucciones}
                            placeholder={`Ajuste para ${FASE_LABEL[f.fase] ?? f.fase}…`}
                            aria-label={`Ajuste para ${FASE_LABEL[f.fase] ?? f.fase}`}
                            onChange={e => setInstrucciones(e.target.value)} />
                  <Button size="sm" className="mt-2" disabled={!instrucciones || !!motivo}
                          onClick={() => {
                            onRun(f.fase, instrucciones); setInstrucciones(""); setAbierta(null)
                          }}>
                    Correr con este ajuste
                  </Button>
                </div>
              )}

              {/* La ruta va guardada junto al mensaje: con analyze y design mostrando huella
                  a la vez, un 400 al abrir un archivo de una fase no debe pintarse también
                  bajo la otra. */}
              {error && rutas.includes(error.ruta) && (
                <p className="pb-2 text-xs text-destructive">{error.msg}</p>
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
