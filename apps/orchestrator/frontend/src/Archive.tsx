import { useEffect, useState } from "react"
import { api } from "@/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Info } from "@/Info"
import { t } from "@/strings"

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
    <div className="space-y-3">
      <div className="max-w-3xl text-xs text-muted-foreground">
        Una carpeta en tu disco donde cada corrida deja copia de lo que leyó y de lo que
        escribió. <strong>Déjala vacía para no archivar nada.</strong>
        <Info label={t("common.archiveTitle")}>
          <p>
            Por cada corrida se crea una subcarpeta con lo que la fase{" "}
            <strong>leyó</strong> (<code className="text-foreground">entrada/</code>) y lo
            que <strong>escribió</strong> (<code className="text-foreground">salida/</code>).
          </p>
          <p>
            Es <strong>solo un respaldo</strong>: ninguna fase lo lee, y apagarlo no
            cambia en nada lo que hace el agente.
          </p>
          <p>
            Sirve para dos cosas: ver qué había antes y después de cada corrida, y{" "}
            <strong>volver a poner un documento en el repo</strong> desde la pantalla del
            ticket si se borró o si una corrida lo dejó peor.
          </p>
        </Info>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Input aria-label={t("archive.dirAriaLabel")} value={dir} placeholder={t("archive.dirPlaceholder")}
               className="min-w-0 flex-1" onChange={e => setDir(e.target.value)} />
        <Button size="sm" onClick={save} disabled={dir.trim() === saved}>{t("archive.savePath")}</Button>
      </div>
    </div>
  )
}
