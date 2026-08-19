import { useEffect, useState } from "react"
import { api } from "@/api"
import { Info } from "@/Info"
import { lang, setLang, t, type Lang } from "@/strings"
import type { ReactNode } from "react"

/** The short description above `<Info>` and the popover body. Markup lands inside
 *  the sentence, so — same reasoning as `Models.tsx`'s `PHASE_INFO` — it's indexed
 *  by language where it already lives instead of split into dictionary keys. */
const LANGUAGE_DESCRIPTION: Record<Lang, ReactNode> = {
  es: (
    <>
      En qué idioma escribe el agente el análisis, el brief, los surveys, el plan y
      las preguntas que te deja. <strong>No cambia el idioma de esta app.</strong>
    </>
  ),
  en: (
    <>
      What language the agent writes the analysis, the brief, the surveys, the plan
      and the questions it leaves you in. <strong>It doesn't change this app's own
      language.</strong>
    </>
  ),
}

const LANGUAGE_INFO: Record<Lang, ReactNode> = {
  es: (
    <>
      <p>
        Afecta a los documentos que el agente escribe en el repo y a las decisiones
        que te deja para responder. <strong>Ninguna corrida ya hecha se retraduce.</strong>
      </p>
      <p>
        Hay cosas que <strong>no</strong> se traducen nunca: las citas literales del
        work item (para que puedas contrastarlas contra el ticket), las rutas,
        los <code className="text-foreground">file:line</code>, los mensajes de
        commit y el esqueleto que exige OpenSpec.
      </p>
    </>
  ),
  en: (
    <>
      <p>
        Affects the documents the agent writes in the repo and the decisions it
        leaves for you to answer. <strong>No run that already happened gets
        retranslated.</strong>
      </p>
      <p>
        Some things are <strong>never</strong> translated: literal quotes from the
        work item (so you can check them against the ticket), paths,{" "}
        <code className="text-foreground">file:line</code> references, commit
        messages, and the skeleton OpenSpec requires.
      </p>
    </>
  ),
}

/** El idioma en que el agente escribe sus entregables. Global, como el archivo y
 *  los modelos: un mismo ticket con el análisis en un idioma y el plan en otro es
 *  peor que la molestia de cambiar una perilla, porque la fase 2 consume la fase 1. */
export function Language() {
  const [idioma, setIdioma] = useState("es")
  const [error, setError] = useState("")

  useEffect(() => {
    api.idioma().then(r => setIdioma(r.idioma)).catch(e => setError(String(e)))
  }, [])

  const pick = (code: string) => {
    setError("")
    api.saveIdioma(code)
      .then(r => {
        setIdioma(r.idioma)
        setLang(r.idioma)
        // Recarga en vez de re-render: el idioma se resuelve una sola vez, antes
        // del montaje (ver `main.tsx`), así que no hay forma de propagarlo sin
        // volver a arrancar. Es una perilla que se toca dos veces en la vida.
        location.reload()
      })
      .catch(e => { setError(String(e)); api.idioma().then(r => setIdioma(r.idioma)) })
  }

  return (
    <div className="space-y-3">
      <div className="max-w-3xl text-xs text-muted-foreground">
        {LANGUAGE_DESCRIPTION[lang()]}
        <Info label={t("common.languageTitle")}>
          {LANGUAGE_INFO[lang()]}
        </Info>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-4">
        {[["es", t("language.spanish")], ["en", t("language.english")]].map(([code, label]) => (
          <label key={code} className="flex items-center gap-2 text-sm">
            <input type="radio" name="idioma" value={code}
                   checked={idioma === code}
                   onChange={() => pick(code)} />
            {label}
          </label>
        ))}
      </div>
    </div>
  )
}
