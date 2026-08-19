import { useEffect, useRef, useState, type ReactNode } from "react"
import { api, type Project, type Repo } from "@/api"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/ConfirmDialog"
import { Input } from "@/components/ui/input"
import { lang, t, type Lang } from "@/strings"

const EMPTY: Project = {
  name: "", org: "", project: "",
  repos: [{ path: "", label: "", primary: true }],
}

// Two prose blocks with markup inside the sentence, indexed by language where they
// already live — same reasoning as `Models.tsx`'s `PHASE_INFO`, not split into keys.
const PAT_DISCLAIMER: Record<Lang, ReactNode> = {
  es: (
    <>
      Se guarda tal cual, en texto plano, en <code>orchestrator.db</code>: no hay
      cifrado en reposo. Que la API nunca lo devuelva evita que se filtre por ahí,
      pero no protege el archivo en disco.
    </>
  ),
  en: (
    <>
      It's stored as-is, in plain text, in <code>orchestrator.db</code>: there's no
      encryption at rest. The API never returning it keeps it from leaking through
      there, but that doesn't protect the file on disk.
    </>
  ),
}

const REPOS_DESCRIPTION: Record<Lang, ReactNode> = {
  es: (
    <>
      El marcado como <strong>principal</strong> es donde corre el agente y donde se
      escribe el análisis; los demás los lee. La descripción viaja al prompt y es lo
      que le dice cuándo mirar en cada uno.
    </>
  ),
  en: (
    <>
      The one marked <strong>primary</strong> is where the agent runs and where the
      analysis gets written; it reads the rest. The description travels into the
      prompt, and it's what tells it when to look at each one.
    </>
  ),
}

// Module-local, both of them: nothing outside this file uses them, and exporting a
// non-component alongside a component trips oxlint's `react/only-export-components`.
const newProject = (): Project => ({ ...EMPTY, repos: [{ ...EMPTY.repos[0] }] })

/**
 * What's missing, per field. Replaces the four-condition `disabled` that named none of
 * them: the button stays alive and pressing it paints what's missing.
 */
function validate(f: Project): Record<string, string> {
  const e: Record<string, string> = {}
  if (!f.name.trim()) e.name = t("projectform.errorName")
  if (!f.org.trim()) e.org = t("projectform.errorOrg")
  if (!f.project.trim()) e.project = t("projectform.errorProject")
  if (!f.repos.some(r => r.path.trim())) e.repos = t("projectform.errorReposMissing")
  // Blank rows get dropped on save. If the one marked primary is among them, the payload
  // arrives with no primary at all: the backend answers 400 (`split_repos`) with a banner
  // that doesn't say which row to fix — a round trip to learn something the form already
  // knows. Reachable by filling the second row and forgetting to move the radio.
  else if (!f.repos.some(r => r.primary && r.path.trim())) {
    e.repos = t("projectform.errorPrimaryRepoPath")
  }
  return e
}

function Field({ id, label, hint, error, children }: {
  id: string; label: string; hint?: string; error?: string; children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className="text-xs font-medium">{label}</label>
      {hint && <span className="ml-1 text-xs text-muted-foreground">{hint}</span>}
      <div className="mt-1">{children}</div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  )
}

export function ProjectForm({ initial, onSaved, onCancel, onDirtyChange }: {
  /** `null` = creating. Otherwise, the project as it is saved. */
  initial: Project | null
  onSaved: (name: string) => void
  onCancel: () => void
  /** Reported upward so the sidebar can route its navigation through the same
   *  confirmation this component already uses for Cancelar and Escape. Without it,
   *  clicking another project unmounts the form and discards what was typed — the
   *  guard exists, and the navigation walks around it. */
  onDirtyChange?: (dirty: boolean) => void
}) {
  const original = initial?.name ?? null
  const [form, setForm] = useState<Project>(
    initial ? { ...initial, repos: initial.repos.map(r => ({ ...r })) } : newProject())
  const [errors, setErrors] = useState<Record<string, string>>({})
  // path → exists. Keyed by the string and not by the row index on purpose: removing a
  // row would otherwise shift every verdict below it onto the wrong path.
  const [paths, setPaths] = useState<Record<string, boolean>>({})
  const [actionError, setActionError] = useState("")
  const [confirmLeave, setConfirmLeave] = useState(false)
  const snapshot = useRef(JSON.stringify(initial ?? newProject()))
  // The token never round-trips (the API is write-only for it), so it can't live in
  // `form`/`snapshot` like every other field: there is nothing to snapshot it against.
  // `tokenInput` is what replaces the stored token, if anything; `clearToken` is the
  // explicit "remove it" action — two different intents that an empty string can't
  // tell apart on its own (typing nothing must leave the token untouched, not erase it).
  const [tokenInput, setTokenInput] = useState("")
  const [clearToken, setClearToken] = useState(false)

  const dirty = JSON.stringify(form) !== snapshot.current || !!tokenInput.trim() || clearToken
  const patch = (fn: (rs: Repo[]) => Repo[]) => setForm(f => ({ ...f, repos: fn(f.repos) }))

  // No cleanup clearing the flag on unmount, and that's load-bearing. `App` guards
  // navigation from a `hashchange` listener, and React's own listener (behind
  // `useSyncExternalStore` in `router.ts`) is registered first: it re-renders, this
  // form unmounts, and an unmount-clear would report `false` a beat before the guard
  // reads it — which is exactly the bug it looked like it was preventing. `App` clears
  // the flag itself on every way out of the form, so nothing stale survives.
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])

  /** On blur, not debounced while typing: a path gets pasted whole, and validating
   *  mid-word produces a run of reds that mean nothing. */
  const checkPath = (ruta: string) => {
    const v = ruta.trim()
    // Only a cached `true` is trusted. A cached `false` must be re-checked on every
    // blur: that's exactly the case where the user created the folder and blurred
    // again to clear the red mark — skipping the request would leave it stuck.
    if (!v || paths[v] === true) return
    api.validatePath(v)
      .then(existe => setPaths(p => ({ ...p, [v]: existe })))
      // No mark and no block: the save validates again and that is the authoritative
      // check. A courtesy endpoint being down must not stop the user from saving.
      .catch(() => {})
  }

  const save = () => {
    const e = validate(form)
    setErrors(e)
    if (Object.keys(e).length) {
      // `campo-repos` sits on the PRIMARY row's path input, not on the wrapping <div>:
      // both `repos` errors are about that row, and a <div> without tabindex silently
      // refuses focus, which made this a no-op for the most reachable failure.
      document.getElementById(`campo-${Object.keys(e)[0]}`)?.focus()
      return
    }
    setActionError("")
    // blank rows are dropped here; the backend rejects paths that don't exist
    const payload: Project = { ...form, repos: form.repos.filter(r => r.path.trim()) }
    // `ado_pat_configured` is server-reported and read-only here; sending it back
    // would be harmless (the backend ignores unknown intent on that field) but it's
    // not this form's to echo. `ado_pat` itself stays OMITTED unless the human acted:
    // omitted is what tells the backend "leave the stored token untouched".
    delete payload.ado_pat_configured
    if (clearToken) payload.ado_pat = ""
    else if (tokenInput.trim()) payload.ado_pat = tokenInput.trim()
    api.saveProject(payload, original)
      .then(p => onSaved(p.name))
      .catch(err => setActionError(String(err)))
  }

  const leave = () => (dirty ? setConfirmLeave(true) : onCancel())

  return (
    <div className="space-y-4">
      {/* The breadcrumb in `TopBar` is the way back now, and it goes through the same
          guard. A second `←` here was two answers to one question. */}
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold">
          {original ? t("projectform.editTitle") : t("common.newProject")}
        </h2>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={leave}>{t("common.cancel")}</Button>
          <Button size="sm" onClick={save}>{t("common.save")}</Button>
        </div>
      </div>

      {actionError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40
                        bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <span className="flex-1">{actionError}</span>
          <button onClick={() => setActionError("")} aria-label={t("common.dismissError")}
                  className="rounded px-1 focus-visible:outline-1 focus-visible:outline-ring">✕</button>
        </div>
      )}

      <Field id="campo-name" label={t("projectform.nameLabel")} error={errors.name}
             hint={t("projectform.nameHint")}>
        <Input id="campo-name" placeholder={t("projectform.namePlaceholder")} value={form.name}
               aria-invalid={!!errors.name}
               onChange={e => setForm({ ...form, name: e.target.value })} />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field id="campo-org" label={t("projectform.orgLabel")} error={errors.org}>
          <Input id="campo-org" placeholder={t("projectform.orgPlaceholder")} value={form.org}
                 aria-invalid={!!errors.org}
                 onChange={e => setForm({ ...form, org: e.target.value })} />
        </Field>
        <Field id="campo-project" label={t("projectform.projectLabel")} error={errors.project}
               hint={t("projectform.projectHint")}>
          <Input id="campo-project" placeholder={t("projectform.projectPlaceholder")} value={form.project}
                 aria-invalid={!!errors.project}
                 onChange={e => setForm({ ...form, project: e.target.value })} />
        </Field>
      </div>

      <Field id="campo-ado-pat" label={t("projectform.patLabel")}
             hint={t("projectform.patHint")}>
        <Input id="campo-ado-pat" type="password" autoComplete="new-password"
               placeholder={form.ado_pat_configured && !clearToken
                 ? t("projectform.patPlaceholderConfigured")
                 : t("projectform.patPlaceholderEmpty")}
               value={tokenInput} disabled={clearToken}
               onChange={e => setTokenInput(e.target.value)} />
        {form.ado_pat_configured && (
          <label className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={clearToken}
                   onChange={e => { setClearToken(e.target.checked); setTokenInput("") }} />
            {t("projectform.removeTokenLabel")}
          </label>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          {PAT_DISCLAIMER[lang()]}
        </p>
      </Field>

      <div>
        <p className="text-xs font-medium">{t("projectheader.reposSeen")}</p>
        <p className="mb-3 text-xs text-muted-foreground">
          {REPOS_DESCRIPTION[lang()]}
        </p>

        <div className="space-y-4">
          {form.repos.map((r, i) => {
            const key = r.path.trim()
            // `undefined` = not visited yet. Absence is not a verdict.
            const exists = key in paths ? paths[key] : undefined
            return (
              <div key={i} className="rounded-md border border-border p-3">
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 text-xs">
                    <input type="radio" name="principal" checked={r.primary}
                           onChange={() => patch(rs => rs.map((x, j) => ({ ...x, primary: j === i })))} />
                    {r.primary ? <strong>{t("projectform.primaryLabel")}</strong> : <span className="text-muted-foreground">{t("projectform.primaryLabel")}</span>}
                  </label>
                  {exists === true && <span className="text-xs text-foreground">✓ {t("projectform.pathExists")}</span>}
                  {exists === false && <span className="text-xs text-destructive">✗ {t("projectform.pathNotExists")}</span>}
                  <Button size="sm" variant="ghost" className="ml-auto"
                          disabled={form.repos.length === 1}
                          onClick={() => patch(rs => {
                            const remaining = rs.filter((_, j) => j !== i)
                            // if the primary one leaves, the first one left takes over
                            return remaining.some(x => x.primary)
                              ? remaining
                              : remaining.map((x, j) => ({ ...x, primary: j === 0 }))
                          })}>
                    ✕ {t("projectform.removeRepoButton")}
                  </Button>
                </div>

                <Input className="mt-2 font-mono" placeholder={t("projectform.repoPathPlaceholder")} value={r.path}
                       id={r.primary ? "campo-repos" : undefined}
                       aria-label={t("projectform.repoPathAriaLabel")}
                       aria-invalid={!!errors.repos && r.primary}
                       onBlur={e => checkPath(e.target.value)}
                       onChange={e => patch(rs =>
                         rs.map((x, j) => j === i ? { ...x, path: e.target.value } : x))} />
                {exists === false && (
                  <p className="mt-1 text-xs text-destructive">
                    ⚠ {t("projectform.pathNotFoundWarning")}
                  </p>
                )}

                <Input className="mt-2" placeholder={t("projectform.repoLabelPlaceholder")}
                       aria-label={t("projectform.repoLabelAriaLabel")} value={r.label}
                       onChange={e => patch(rs =>
                         rs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
              </div>
            )
          })}
        </div>
        {errors.repos && <p className="mt-1 text-xs text-destructive">{errors.repos}</p>}

        <Button size="sm" variant="outline" className="mt-2"
                onClick={() => patch(rs => [...rs, { path: "", label: "", primary: false }])}>
          + {t("projectform.addRepoButton")}
        </Button>
      </div>

      <ConfirmDialog open={confirmLeave} title={t("app.unsavedTitle")}
                     body={t("app.unsavedBody")} confirmLabel={t("common.discard")}
                     onConfirm={() => { setConfirmLeave(false); onCancel() }}
                     onCancel={() => setConfirmLeave(false)} />
    </div>
  )
}
