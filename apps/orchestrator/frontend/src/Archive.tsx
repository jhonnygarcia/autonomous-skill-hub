import { useEffect, useState } from "react"
import { api } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

/** Where every run leaves its snapshot (entrada/, salida/, run.json). Empty = off.
 *  A human preference, not a deployment knob: it lives in the DB with the models. */
export function Archive() {
  const [dir, setDir] = useState("")
  const [saved, setSaved] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    api.archive().then(a => { setDir(a.dir); setSaved(a.dir) }).catch(e => setError(String(e)))
  }, [])

  const save = () => api.saveArchive(dir.trim())
    .then(a => { setDir(a.dir); setSaved(a.dir); setError("") })
    .catch(e => setError(String(e)))

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Archivo de entregables</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Cada corrida copia ahí lo que leyó (<code>entrada/</code>) y lo que escribió
          (<code>salida/</code>), con un <code>run.json</code>. Es un respaldo: ninguna
          fase lo lee. Si borran un entregable del repo, se restaura desde el ticket.
          Vacío = apagado.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Input aria-label="Directorio de archivo" value={dir} placeholder="D:/archivo-tickets"
                 onChange={e => setDir(e.target.value)} />
          <Button size="sm" onClick={save} disabled={dir.trim() === saved}>Guardar</Button>
        </div>
      </CardContent>
    </Card>
  )
}
