import { useEffect, useState } from "react"
import { api } from "@/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Info } from "@/Info"
import { lang, t, type Lang } from "@/strings"
import type { ReactNode } from "react"

/** The short description above `<Info>` and the popover body. Markup lands inside
 *  the sentence, so — same reasoning as `Models.tsx`'s `PHASE_INFO` — it's indexed
 *  by language where it already lives instead of split into dictionary keys. */
const ARCHIVE_DESCRIPTION: Record<Lang, ReactNode> = {
  es: (
    <>
      Una carpeta en tu disco donde cada corrida deja copia de lo que leyó y de lo que
      escribió. <strong>Déjala vacía para no archivar nada.</strong>
    </>
  ),
  en: (
    <>
      A folder on your disk where every run leaves a copy of what it read and what it
      wrote. <strong>Leave it empty to archive nothing.</strong>
    </>
  ),
}

const ARCHIVE_INFO: Record<Lang, ReactNode> = {
  es: (
    <>
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
    </>
  ),
  en: (
    <>
      <p>
        Every run creates a subfolder with what the phase{" "}
        <strong>read</strong> (<code className="text-foreground">entrada/</code>) and
        what it <strong>wrote</strong> (<code className="text-foreground">salida/</code>).
      </p>
      <p>
        It's <strong>only a backup</strong>: no phase reads it, and turning it off
        doesn't change anything about what the agent does.
      </p>
      <p>
        It's good for two things: seeing what there was before and after each run, and{" "}
        <strong>putting a document back in the repo</strong> from the ticket screen if
        it got deleted or a run left it worse off.
      </p>
    </>
  ),
}

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
        {ARCHIVE_DESCRIPTION[lang()]}
        <Info label={t("common.archiveTitle")}>
          {ARCHIVE_INFO[lang()]}
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
