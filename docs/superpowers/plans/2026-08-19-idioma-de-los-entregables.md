# Idioma de los entregables — plan de implementación (motor)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que una perilla global en la UI decida el idioma —español o inglés— de
todo lo que el agente escribe y de todo lo que el runner escribe dentro de un
`.md` del repo destino.

**Architecture:** una fila en `settings` (`idioma`), leída en el momento en que
se necesita. El runner la inyecta como directiva en los tres constructores de
prompt que existen; las seis SKILL.md ganan una sección `## Output language` con
su lista de excepciones. Los marcadores que el humano lee y edita
(`DECIDIR`/`BLOQUEA`/`Propuesta:`/`**Respuesta:**`/`## Decisiones para ti`/
`## Corridas`/`## Hallazgos`) viajan traducidos en el documento, y **la API los
normaliza al español** para que el frontend no se entere. Al escribir dentro de
un archivo que ya existe, el idioma se deduce **del archivo**, nunca de la
perilla.

**Tech Stack:** FastAPI + SQLite sin ORM (`app.py`, un solo archivo), React +
TypeScript + Tailwind (`frontend/src/`), pytest, markdown para el plugin.

**Spec:** `docs/superpowers/specs/2026-08-19-idioma-de-los-entregables-design.md`

**Alcance:** este plan cubre las **fases 0-3** del spec (el motor: plugin,
perilla, marcadores, vocabulario del runner). Las fases 4-5 —i18n de la UI (287
líneas en 18 archivos) y los 49 `HTTPException`— van en un plan aparte, porque
entregan valor por su cuenta y no bloquean nada de esto.

## Global Constraints

- **Código, comentarios y docs de proceso en inglés; español sólo en texto de
  UI.** Los documentos de planificación (`docs/superpowers/`) están exentos.
- **Los literales de contrato no se traducen en ninguna dirección:** `HUELLA`,
  `SONDEAR`, los valores `ok|parcial|nada`, las claves JSON de la API
  (`fases`, `puntos`, `tipo`, `decidir`, `bloquea`), las rutas HTTP
  (`/modelos`, `/artefacto?ruta=`). **Leer `STAMP_RE` antes de tocar cualquiera.**
- **Tocar una skill obliga a subir `version` en `plugin.json` — y hay tres
  lugares:** `plugins/ticket-agent/.claude-plugin/plugin.json` (hoy `0.11.0`),
  el sello del análisis en `ticket-comprehension/SKILL.md:109`, y el de la
  colección en `ticket-brief/SKILL.md:100`. Los tres suben a `0.12.0`.
- **`claude plugin validate .` desde la raíz tiene que pasar antes de commitear**
  cualquier cambio del plugin.
- **Nunca `uvicorn --reload` en Windows.**
- Backend: `cd apps/orchestrator/backend`, tests con
  `.venv/Scripts/python -m pytest tests/ -v`.
- Frontend: `cd apps/orchestrator/frontend`, `npm run build` (tsc -b + vite) y
  `npm run lint` (oxlint).
- **Idiomas válidos: exactamente `"es"` y `"en"`.** Default `"es"`. No hay
  tercer valor «auto».

---

### Task 1: La perilla — `settings.idioma`, `GET/PUT /idioma`, y el helper `lang()`

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (junto a `setting`/`set_setting`, :243-254; endpoints junto a `/archivo`, :987-1013)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `setting(key)` / `set_setting(key, value)`, ya existentes.
- Produces: `LANGS: tuple[str, ...]`, `lang() -> str`, `GET /idioma → {"idioma": "es"|"en"}`, `PUT /idioma {"idioma": ...} → {"idioma": ...}`.

- [ ] **Step 1: Write the failing tests**

En `tests/test_app.py`, al final del archivo:

```python
def test_idioma_defaults_to_spanish(client):
    assert client.get("/idioma").json() == {"idioma": "es"}


def test_idioma_can_be_switched_to_english(client):
    assert client.put("/idioma", json={"idioma": "en"}).json() == {"idioma": "en"}
    assert client.get("/idioma").json() == {"idioma": "en"}


def test_idioma_rejects_anything_outside_the_two(client):
    for bad in ["fr", "EN", "", "es-AR"]:
        assert client.put("/idioma", json={"idioma": bad}).status_code == 400
    # and the stored value is untouched by a rejected write
    assert client.get("/idioma").json() == {"idioma": "es"}
```

- [ ] **Step 2: Run the tests to verify they fail**

```
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/test_app.py -k idioma -v
```

Expected: FAIL — 404 en `/idioma` (la ruta no existe todavía).

- [ ] **Step 3: Add `LANGS` and `lang()` next to `setting`**

En `app.py`, justo **después** de `set_setting` (:254):

```python
# The two languages the deliverables can be written in. There is no third "auto"
# value: guessing the language of a technical `.md` — full of English identifiers —
# fails exactly where it would matter.
LANGS = ("es", "en")


def lang() -> str:
    """The deliverable language, read at the moment it's needed (like `setting` and
    `model_for`), never cached at startup: on Windows the backend isn't hot-reloaded.

    Anything unrecognized — including the empty string every DB had before this row
    existed — reads as `es`, which is what those installations were already producing.
    """
    v = setting("idioma")
    return v if v in LANGS else "es"
```

- [ ] **Step 4: Add the endpoints next to `/archivo`**

En `app.py`, justo **después** de `put_archive` (:1013):

```python
class IdiomaIn(BaseModel):
    idioma: str


@app.get("/idioma")
def get_idioma():
    return {"idioma": lang()}


@app.put("/idioma")
def put_idioma(body: IdiomaIn):
    """Governs what the agent writes and what the runner writes into a `.md` of the
    target repo — never the API's own JSON keys, which stay Spanish contract literals
    (see `CANON_TIPO`)."""
    if body.idioma not in LANGS:
        raise HTTPException(400, f"Idioma no reconocido: {body.idioma}")
    set_setting("idioma", body.idioma)
    return {"idioma": body.idioma}
```

- [ ] **Step 5: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k idioma -v
```

Expected: 3 passed.

- [ ] **Step 6: Run the full suite — nothing else may move**

```
.venv/Scripts/python -m pytest tests/ -q
```

Expected: todo verde, mismo conteo que antes más 3.

- [ ] **Step 7: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): perilla global de idioma en settings"
```

---

### Task 2: La perilla en la UI — `Language.tsx` y la tercera sección de Settings

**Files:**
- Create: `apps/orchestrator/frontend/src/Language.tsx`
- Modify: `apps/orchestrator/frontend/src/api.ts:159-166` (junto a `archive`/`saveArchive`)
- Modify: `apps/orchestrator/frontend/src/Settings.tsx`

**Interfaces:**
- Consumes: `GET/PUT /idioma` de la Task 1; `Section` de `Settings.tsx`; `Info` de `Info.tsx`.
- Produces: `api.idioma()`, `api.saveIdioma(code)`, el componente `<Language />`.

- [ ] **Step 1: Add the two client calls**

En `api.ts`, justo **después** de `saveArchive` (:166), dentro de `export const api = {`:

```ts
  idioma: () => fetch("/api/idioma").then(r => json<{ idioma: string }>(r)),
  saveIdioma: (idioma: string) =>
    fetch("/api/idioma", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idioma }),
    }).then(r => json<{ idioma: string }>(r)),
```

- [ ] **Step 2: Create `Language.tsx`**

```tsx
import { useEffect, useState } from "react"
import { api } from "@/api"
import { Info } from "@/Info"

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
      .then(r => setIdioma(r.idioma))
      .catch(e => { setError(String(e)); api.idioma().then(r => setIdioma(r.idioma)) })
  }

  return (
    <div className="space-y-3">
      <div className="max-w-3xl text-xs text-muted-foreground">
        En qué idioma escribe el agente el análisis, el brief, los surveys, el plan y
        las preguntas que te deja. <strong>No cambia el idioma de esta app.</strong>
        <Info label="Idioma de los entregables">
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
        </Info>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap gap-4">
        {[["es", "Español"], ["en", "English"]].map(([code, label]) => (
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
```

- [ ] **Step 3: Add the third `Section` to `Settings.tsx`**

Importar `Language` junto a los otros dos:

```tsx
import { Language } from "@/Language"
```

Y agregar la sección **primera** del bloque (es la que condiciona a las otras dos),
dentro del `<div className="space-y-6">`:

```tsx
      <Section mark="+" title="Idioma de los entregables"
               aside="global · aplica a la siguiente corrida">
        <Language />
      </Section>
```

- [ ] **Step 4: Build and lint**

```
cd apps/orchestrator/frontend
npm run build
npm run lint
```

Expected: sin errores de tsc ni de oxlint.

- [ ] **Step 5: Verify it in the browser**

Levantar backend y frontend (ver CLAUDE.md, «Bringing the app up»), abrir
**http://localhost:5173** —`localhost`, no `127.0.0.1`—, ir a Settings y
comprobar: el radio arranca en Español, al elegir English la elección
sobrevive a un refresh.

- [ ] **Step 6: Commit**

```bash
git add apps/orchestrator/frontend/src/Language.tsx apps/orchestrator/frontend/src/api.ts apps/orchestrator/frontend/src/Settings.tsx
git commit -m "feat(orchestrator): radio de idioma en Settings"
```

---

### Task 3: `## Output language` en las seis skills, y la deuda de OpenSpec

**Files:**
- Modify: `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md`
- Modify: `plugins/ticket-agent/skills/ticket-brief/SKILL.md`
- Modify: `plugins/ticket-agent/skills/repo-survey/SKILL.md`
- Modify: `plugins/ticket-agent/skills/analysis-consolidation/SKILL.md`
- Modify: `plugins/ticket-agent/skills/change-planning/SKILL.md`
- Modify: `plugins/ticket-agent/skills/change-implementation/SKILL.md`
- Modify: `plugins/ticket-agent/.claude-plugin/plugin.json`
- Modify: `plugins/ticket-agent/README.md`

**Interfaces:**
- Consumes: nada de código.
- Produces: la sección `## Output language`, que la Task 4 cita desde el prompt; la clave `language` documentada, que la Task 5 escribe.

- [ ] **Step 1: Normalize `repo-survey`'s template headings to English**

En `repo-survey/SKILL.md`, dentro del bloque de template de la sección `## 4. The
survey` (líneas 60-84), reemplazar los ocho encabezados españoles:

| Actual | Nuevo |
|---|---|
| `## Veredicto` | `## Verdict` |
| `## Qué exige de este repo` | `## What it demands of this repo` |
| `## Rutas afectadas` | `## Affected paths` |
| `## Espejo a copiar` | `## Mirror to copy` |
| `## Reglas de este repo que aplican` | `## This repo's rules that apply` |
| `## Espero de otros` | `## What I expect from others` |
| `## Ofrezco a otros` | `## What I offer others` |
| `## No pude determinar` | `## Could not determine` |

Y en la línea 120, `## Hallazgos fuera de alcance` → `## Out-of-scope findings`.

**No tocar** los encabezados de `ticket-comprehension` ni de `change-planning`:
ya están en inglés.

- [ ] **Step 2: Fix the cross-skill reference in `analysis-consolidation`**

`analysis-consolidation/SKILL.md:124` cita hoy `## Hallazgos fuera de alcance`
de los surveys. Como ese encabezado ahora se traduce con el documento, la
referencia tiene que dejar de ser un literal. Reemplazar esa mención por:

```markdown
every out-of-scope findings section from the surveys (`## Out-of-scope findings`,
or its translation — the survey was written in whatever language the run asked
for, and its headings travel translated)
```

- [ ] **Step 3: Write the `## Output language` section, identical in all six skills**

Insertar esta sección en cada SKILL.md, **inmediatamente antes** de la sección de
cierre de cada una (`## 4. Closing based on autonomy` en `ticket-comprehension`,
`## 7. Closing based on autonomy` en `change-planning`, `## 5. Closing` en
`repo-survey`, y la sección de cierre equivalente en las otras tres). Texto
literal, igual en las seis salvo el sustantivo de la primera línea:

````markdown
## Output language

Write **the analysis** — headings, prose, and every question you leave for the
human — in the language named by, in this order:

1. the prompt, if it names one;
2. `language` in `.claude/ticket-agent.json` (`"es"` or `"en"`);
3. Spanish, if neither says anything.

The section headings above are shown in English because this procedure is
written in English. **Translate them too** when the target language is not
English: they are part of the document, not part of the contract.

**What never gets translated, in either language:**

- **Literal quotes from the work item, comments, wiki or any cited document.**
  They keep the source's language. An analyst has to be able to check a quote
  against the ticket, and a translated quote can't be checked. Put the
  translation next to it if it helps, marked as a translation.
- **Code identifiers, file paths, `file:line` references, branch names, commit
  subjects, and command lines** copied from a build or a test run.
- **The `HUELLA:` line and its values** (`ok`, `parcial`, `nada`), and the
  `SONDEAR:` line with its repo labels. The runner matches them byte for byte.
- **OpenSpec's structural headers**, wherever they appear:
  `## Why`, `## What Changes`, `## Purpose`, `## Requirements`,
  `## ADDED Requirements` (and `MODIFIED`, `REMOVED`, `RENAMED`),
  `### Requirement:`, `#### Scenario:`, and the `**WHEN**` / `**THEN**` /
  `**AND**` bullets. Its validator parses those literals; a translated one
  fails the change.

**What does get translated**, and is easy to forget: the `DECIDIR`/`BLOQUEA`
markers and their section. In Spanish they read `## Decisiones para ti`,
`**DECIDIR**`, `**BLOQUEA**`, `Propuesta:`, and `Si no respondes, sigo con la
propuesta.`; in English, `## Decisions for you`, `**DECIDE**`, `**BLOCKS**`,
`Proposal:`, and `If you don't answer, I proceed with the proposal.`. The
orchestrator reads both.
````

Sustantivo de la primera línea por skill: `the analysis`
(`ticket-comprehension`, `analysis-consolidation`), `the brief`
(`ticket-brief`), `the survey` (`repo-survey`), `the change`
(`change-planning`), `the implementation` (`change-implementation`).

- [ ] **Step 4: Document OpenSpec's required literals in `change-planning`**

En `change-planning/SKILL.md`, sección `## 5. Writing the change`, en la
descripción de `proposal.md` (que hoy empieza «**`proposal.md`** — why, what, and
with what impact»), agregar **antes** del bloque de código existente:

````markdown
Two headings are **mandatory and parsed by the validator**, and the run fails
without them — they are not optional prose:

```markdown
## Why
[at least 50 characters, at most 1000]

## What Changes
[the list of changes, in the form below]
```
````

Y en la descripción de `specs/<capability>/spec.md`, reemplazar el párrafo actual
(«the future state of the affected capability…») por:

````markdown
**`specs/<capability>/spec.md`** — the future state of the affected capability.
`<capability>` is the **system capability**, not the ticket: it's the folder
OpenSpec reuses across changes. If one already exists under `openspec/specs/`
that fits, use it; don't invent a new one per ticket.

**This file is always written in English, whatever the output language is.**
Every one of its structural tokens belongs to the OpenSpec validator's parser,
and a translated one is an ERROR that fails the change:

```markdown
## ADDED Requirements

### Requirement: The system SHALL do the thing
[the requirement text; it must contain SHALL or MUST]

#### Scenario: Descriptive name
- **WHEN** [the condition]
- **THEN** [the expected result]
- **AND** [anything else]
```

`## ADDED Requirements` can also be `## MODIFIED`, `## REMOVED` or
`## RENAMED Requirements`. **Every requirement needs at least one scenario, and
the scenario has to be a level-4 header** — a bullet list instead of
`#### Scenario:` is an ERROR. A main spec under `openspec/specs/` needs
`## Purpose` and `## Requirements` instead of the delta headers.
````

- [ ] **Step 5: Pin the commit language in `change-implementation`**

En `change-implementation/SKILL.md`, en el paso que describe el commit por tarea
(cerca de la línea 139, `check the box `- [x]` in `tasks.md`. One commit per
task.`), agregar inmediatamente después:

```markdown
**The commit subject is always in English**, whatever the output language is.
`tasks.md` may be in Spanish and the commit still reads
`3323 task 4: add the carrier mapper` — the `git log` of a client's repo is
shared infrastructure and rewriting it is expensive, so it doesn't hang off a
setting in a tool they don't run.
```

- [ ] **Step 6: Document the `language` key in the plugin README**

En `plugins/ticket-agent/README.md`, en la tabla/lista de claves de
`.claude/ticket-agent.json` (junto a `autonomy` y `subagent_model`), agregar:

```markdown
| `language` | `"es"` \| `"en"` | Idioma de los entregables. Ausente o no reconocido → `"es"`. El orquestador lo escribe al crear el archivo; una directiva en el prompt gana sobre esta clave. |
```

- [ ] **Step 7: Bump the version in the three places**

1. `plugins/ticket-agent/.claude-plugin/plugin.json`: `"version": "0.11.0"` → `"0.12.0"`
2. `plugins/ticket-agent/skills/ticket-comprehension/SKILL.md:109`:
   `**Analyzed:** <date> by ticket-agent v0.11.0` → `v0.12.0`
3. `plugins/ticket-agent/skills/ticket-brief/SKILL.md:100`:
   `**Collected:** <date> by ticket-agent v0.11.0` → `v0.12.0`

- [ ] **Step 8: Validate the plugin**

```
cd D:/Companies/Jorge.Gutierrez/autonomous-skill-hub
claude plugin validate .
```

Expected: pasa sin errores.

- [ ] **Step 9: Verify no Spanish heading survived in a template**

```
cd D:/Companies/Jorge.Gutierrez/autonomous-skill-hub
grep -rn "^## \(Veredicto\|Qué\|Rutas\|Espejo\|Reglas\|Espero\|Ofrezco\|No pude\)" plugins/ticket-agent/skills/
```

Expected: sin resultados. (En PowerShell:
`Select-String -Path plugins/ticket-agent/skills/*/SKILL.md -Pattern '^## (Veredicto|Qué exige|Rutas afectadas|Espejo|Reglas de este|Espero de|Ofrezco a|No pude)'`)

- [ ] **Step 10: Commit**

```bash
git add plugins/ticket-agent/
git commit -m "feat(ticket-agent): regla de idioma de salida y literales de OpenSpec

Bump 0.11.0 -> 0.12.0 en plugin.json y en los dos sellos de version."
```

---

### Task 4: `LANGUAGE_PROMPT` en los tres constructores de prompt

**Files:**
- Modify: `apps/orchestrator/backend/app.py` (constantes junto a `JOURNAL_CLAIM`, :697; los tres puntos de armado: :2321, :2329-2345, :2373)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `lang()` de la Task 1; `noun` (ya en scope en los tres sitios); `LANGUAGE_NAME`.
- Produces: `LANGUAGE_PROMPT`, `language_text(noun) -> str`.

- [ ] **Step 0: Read the two tests whose harness you are about to reuse**

```
cd apps/orchestrator/backend
.venv/Scripts/python -m pytest tests/test_app.py -k "survey_children_never_hear or journal_gets_a_line" -v
```

Abrir esos dos tests en `tests/test_app.py` y anotar **los nombres reales** de sus
helpers para armar el ticket, lanzar la fase y leer el log del hijo. Los nombres
que este plan usa abajo (`_ticket`, `_run_phase`, `_log_of_last_run`,
`_child_logs`, `_ticket_with_extras`, `_write_brief`) son marcadores de posición
para los que ya existan: **usar los del archivo, no crear duplicados**.

- [ ] **Step 1: Write the failing tests**

Los fakes (`tests/fake_claude.py`, `tests/fake_codex.py`) hacen eco del prompt en
el log, así que la aserción va sobre el log de la corrida.

```python
def test_the_language_directive_travels_in_the_prompt(client, monkeypatch, tmp_path):
    """The knob is worth nothing if the directive doesn't reach the child."""
    client.put("/idioma", json={"idioma": "en"})
    tid = _ticket(client)                      # same helper the neighbouring tests use
    _run_phase(client, tid, "analyze")
    log = _log_of_last_run(client, tid)
    assert "in English" in log
    assert "in Spanish" not in log


def test_the_language_directive_reaches_every_fan_out_child(client, monkeypatch, tmp_path):
    """`SURVEY_PROMPT` is a second constructor: a survey that misses the directive
    comes out in whatever language the child feels like, and nothing reports it."""
    client.put("/idioma", json={"idioma": "en"})
    tid = _ticket_with_extras(client)
    _write_brief(tmp_path, "SONDEAR: front, backend")
    _run_phase(client, tid, "survey")
    for child_log in _child_logs(client, tid):
        assert "in English" in child_log


def test_the_resume_prompt_carries_the_current_language(client, monkeypatch, tmp_path):
    """`repos_text` is dropped on resume because it's already in context; the language
    is not, because it's exactly what may have changed since the previous run."""
    tid = _ticket(client)
    _run_phase(client, tid, "analyze")          # first run, Spanish
    client.put("/idioma", json={"idioma": "en"})
    _run_phase(client, tid, "analyze", resume=True)
    assert "in English" in _log_of_last_run(client, tid)
```

**Nota para quien implemente:** los helpers `_ticket`, `_ticket_with_extras`,
`_run_phase`, `_log_of_last_run`, `_child_logs`, `_write_brief` ya existen o
tienen equivalente en `test_app.py` — buscar cómo lo hacen
`test_the_survey_children_never_hear_the_journal_claim` y
`test_the_journal_gets_a_line_per_closed_run` y reusar los suyos en vez de
inventar unos nuevos.

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/test_app.py -k language -v
```

Expected: FAIL — `"in English" not in log`.

- [ ] **Step 3: Add the constants next to `JOURNAL_CLAIM`**

En `app.py`, después de `JOURNAL_CLAIM` (:699):

```python
LANGUAGE_NAME = {"es": "Spanish", "en": "English"}
# Prompt-facing, so it's English like every other instruction the agent reads. The
# exemption list is short here and complete in the skill's own `Output language`
# section: run 3320 taught that what a prompt doesn't name, the agent invents — but a
# prompt that repeats a whole SKILL.md section is a second source free to drift, so
# this names the traps and points at the skill for the rest.
LANGUAGE_PROMPT = (
    "\n\nWrite {noun} in {language}: headings, prose, and every question you leave "
    "for the human, including the DECIDIR/BLOQUEA section. Do NOT translate: literal "
    "quotes from the work item (they keep the source's language, so they can still be "
    "checked against the ticket), code identifiers, paths, `file:line`, branch names, "
    "commit subjects, the `HUELLA:` and `SONDEAR:` lines, or OpenSpec's structural "
    "headers. Your skill's `Output language` section carries the full list.")


def language_text(noun: str) -> str:
    """The language directive for a run, read from the knob at launch time."""
    return LANGUAGE_PROMPT.format(noun=noun, language=LANGUAGE_NAME[lang()])
```

- [ ] **Step 4: Wire it into the three constructors**

**(a)** Resume, `app.py:2321`. Actual:

```python
            prompt = (instructions or "") + RESUME_STAMP_REMINDER + JOURNAL_CLAIM
```

Nuevo:

```python
            # The language is NOT dropped the way `repos_text` is: what's already in
            # that session's context is the OLD language, and the knob may have moved
            # between runs — which is precisely why a resume has to restate it.
            prompt = ((instructions or "") + RESUME_STAMP_REMINDER
                      + language_text(noun) + JOURNAL_CLAIM)
```

**(b)** Hijo único, `app.py:2344-2345`. Actual:

```python
            prompt += adjustment_text(phase, noun, instructions)
            prompt += JOURNAL_CLAIM
```

Nuevo:

```python
            prompt += adjustment_text(phase, noun, instructions)
            prompt += language_text(noun)
            prompt += JOURNAL_CLAIM
```

**(c)** Hijo del fan-out, `app.py:2373`. Actual:

```python
                child_prompt += adjustment_text(phase, noun, instructions)
```

Nuevo:

```python
                child_prompt += adjustment_text(phase, noun, instructions)
                # A second constructor, and the one where forgetting this doesn't show:
                # the survey would just come out in whatever language the child picked.
                child_prompt += language_text(noun)
```

- [ ] **Step 5: Fix the Spanish word stranded in an English prompt**

`app.py:2341` tiene `surveyed=", ".join(sorted(done)) or "ninguno"` dentro de
`CONSOLIDATE_PROMPT`, que es prompt-facing y por tanto inglés. Cambiar `"ninguno"`
por `"none"`. No se hace bilingüe: los prompts son inglés fijo.

- [ ] **Step 6: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k language -v
```

Expected: 3 passed.

- [ ] **Step 7: Run the full suite**

```
.venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): directiva de idioma en los tres prompts"
```

---

### Task 5: `language` en `.claude/ticket-agent.json`

**Files:**
- Modify: `apps/orchestrator/backend/app.py:1310-1313` (`ensure_ticket_agent_config`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `lang()` de la Task 1.
- Produces: nada nuevo; cambia el contenido del archivo que escribe `POST /preparar`.

- [ ] **Step 1: Write the failing tests**

```python
def test_preparar_writes_the_current_language(client, tmp_path):
    client.put("/idioma", json={"idioma": "en"})
    tid = _ticket_in_unconfigured_repo(client, tmp_path)   # repo without .claude/
    client.post(f"/tickets/{tid}/preparar")
    cfg = json.loads((tmp_path / "otro-repo" / ".claude" / "ticket-agent.json")
                     .read_text(encoding="utf-8"))
    assert cfg["language"] == "en"
    assert cfg["organization"] and cfg["project"]


def test_preparar_still_never_overwrites_a_tuned_file(client, tmp_path):
    """A human may have set `language` by hand, or `autonomy`, or anything else:
    an existing file is left byte-for-byte alone. This is the promise the runner
    depends on, and adding a key must not weaken it."""
    tid = _ticket_in_unconfigured_repo(client, tmp_path)
    cfg_path = tmp_path / "otro-repo" / ".claude" / "ticket-agent.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"organization": "Mio", "project": "Mio", "autonomy": "autonomous"}\n'
    cfg_path.write_text(original, encoding="utf-8")
    client.put("/idioma", json={"idioma": "en"})
    client.post(f"/tickets/{tid}/preparar")
    assert cfg_path.read_text(encoding="utf-8") == original
```

**Nota:** `_ticket_in_unconfigured_repo` es el helper que ya usan los tests de
`preflight`/`preparar`; buscarlo antes de escribir uno nuevo.

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/test_app.py -k preparar -v
```

Expected: el primero FALLA con `KeyError: 'language'`; el segundo pasa ya (la
promesa de no sobreescribir es previa) y sirve de red.

- [ ] **Step 3: Add the key**

`app.py:1310-1313`. Actual:

```python
        path.write_text(
            json.dumps({"organization": ticket["org"], "project": ticket["project"]},
                      indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
```

Nuevo:

```python
        path.write_text(
            json.dumps({"organization": ticket["org"], "project": ticket["project"],
                        "language": lang()},
                      indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
```

Y en el docstring de la función (:1298-1303), donde dice «Writes only what the
orchestrator actually has a source for: `organization` and `project`», agregar:

```
    `language` too, since this change: the knob IS a source, and the skills read
    this key as the fallback when the prompt names no language — which is the only
    thing a plugin-only session (no orchestrator, no prompt directive) has to go on.
```

- [ ] **Step 4: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k preparar -v
```

- [ ] **Step 5: Run the full suite**

```
.venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): escribe language en ticket-agent.json"
```

---

### Task 6: Marcadores bilingües — lectura y normalización

**Files:**
- Modify: `apps/orchestrator/backend/app.py:1674` (`DECISION_RE`), `:1692-1695` (`open_decisions`), `:1702` (`DECISION_ITEM_RE`), `:1707` (`PROPOSAL_RE`), `:1743` (el heading), `:1786-1797` (el dict que arma `_decision_items`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `LANGS` de la Task 1.
- Produces: `MARKERS: dict[str, dict[str, str]]`, `CANON_TIPO: dict[str, str]`, `DECISION_HEADING_RE`, y la clave interna `_marker` en cada ítem de `_decision_items` (la consume la Task 7).

- [ ] **Step 1: Write the failing tests**

```python
# The same six real items as REAL_3359_DECISIONS_DOC, in English. Kept as a separate
# constant rather than a translation helper: the point of the fixture is to be a real
# document, and a document produced by a function is a shape we imagined.
REAL_3359_DECISIONS_DOC_EN = (
    "# Analysis of ticket 3359\n\n"
    "## Decisions for you\n\n"
    "- [ ] **BLOCKS** — Does this ticket include closing the V2 parity gap, or\n"
    "      does it assume V2 is already at parity?\n"
    "      No defensible default exists: either assumption breaks something.\n\n"
    "- [ ] **DECIDE** — What happens to the URLs?\n"
    "      Proposal: **repoint the legacy routes and delete only the implementation**\n"
    "      If you don't answer, I proceed with the proposal.\n"
)


def test_decisiones_parses_an_english_document(client, monkeypatch, tmp_path):
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path,
                                       doc=REAL_3359_DECISIONS_DOC_EN)
    bloquea, decidir = _puntos(client, tid, ruta)
    assert bloquea["pregunta"].endswith("already at parity?")
    assert decidir["propuesta"] == "repoint the legacy routes and delete only the implementation"


def test_the_api_always_speaks_the_spanish_marker(client, monkeypatch, tmp_path):
    """`Decisions.tsx` compares `p.tipo === "BLOQUEA"` and `api.ts` types it as the
    Spanish pair. A `BLOCKS` reaching the frontend fails NO comparison: it just paints
    the gravest signal in the mildest colour. The JSON key is a contract literal."""
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path,
                                       doc=REAL_3359_DECISIONS_DOC_EN)
    bloquea, decidir = _puntos(client, tid, ruta)
    assert bloquea["tipo"] == "BLOQUEA"
    assert decidir["tipo"] == "DECIDIR"


def test_the_open_decisions_counter_counts_english_markers(client, monkeypatch, tmp_path):
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path,
                                       doc=REAL_3359_DECISIONS_DOC_EN)
    fases = client.get(f"/tickets/{tid}").json()["fases"]
    fase = next(f for f in fases if f["fase"] == "analyze")
    assert fase["decisiones"] == {"decidir": 1, "bloquea": 1}
```

**Nota:** `_decisions_declared` hoy no toma `doc`; hay que agregarle el parámetro
con default al documento español actual, para no tocar los ~20 tests que ya lo
llaman. Ese es el «helper parametrizado por idioma» del spec.

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "english or spanish_marker" -v
```

Expected: FAIL — el documento inglés parsea cero ítems.

- [ ] **Step 3: Add the marker tables**

En `app.py`, **antes** de `DECISION_RE` (:1671), reemplazando el comentario actual
de tres líneas:

```python
# The deliverable-facing markers, per language. The KEYS are the canonical names —
# the Spanish ones — because that is what the API's JSON, `runs`, and the frontend
# speak; the VALUES are what travels inside the document, which follows the knob.
# `HUELLA` and `SONDEAR` are deliberately absent: they are runner-facing contract
# literals and never translate (see `STAMP_RE`).
MARKERS = {
    "es": {"DECIDIR": "DECIDIR", "BLOQUEA": "BLOQUEA",
           "decisiones": "Decisiones para ti", "propuesta": "Propuesta",
           "respuesta": "Respuesta", "corridas": "Corridas", "hallazgos": "Hallazgos"},
    "en": {"DECIDIR": "DECIDE", "BLOQUEA": "BLOCKS",
           "decisiones": "Decisions for you", "propuesta": "Proposal",
           "respuesta": "Answer", "corridas": "Runs", "hallazgos": "Findings"},
}
# The marker as it appears in a document -> the canonical name. Everything that leaves
# this module through the API or into `runs` goes through here first: `api.ts` types
# `tipo` as the Spanish pair and `Decisions.tsx` compares against `"BLOQUEA"`, so a
# `BLOCKS` arriving there fails no comparison — it silently paints a blocking item in
# the warning colour instead of the destructive one.
CANON_TIPO = {"DECIDIR": "DECIDIR", "DECIDE": "DECIDIR",
              "BLOQUEA": "BLOQUEA", "BLOCKS": "BLOQUEA"}
_ANY_TIPO = "|".join(CANON_TIPO)


def marker_lang(marker: str) -> str:
    """Which language a document is in, judged by one of its own markers. Used where
    something is written INTO an existing file: an analysis written in Spanish keeps
    being answered in Spanish, whatever the knob says today."""
    return "en" if marker in ("DECIDE", "BLOCKS") else "es"
```

- [ ] **Step 4: Widen the four regexes**

```python
# `DECISION_RE` (:1674)
DECISION_RE = re.compile(r"^\s*- \[ \]\s*\*\*(" + _ANY_TIPO + r")\*\*", re.MULTILINE)

# `DECISION_ITEM_RE` (:1702)
DECISION_ITEM_RE = re.compile(r"^- \[([ xX])\] \*\*(" + _ANY_TIPO + r")\*\* — ",
                              re.MULTILINE)

# `PROPOSAL_RE` (:1707)
PROPOSAL_RE = re.compile(r"(?:Propuesta|Proposal):\s*\*\*(.+?)\*\*", re.DOTALL)

# New, replacing the inline `re.search` at :1743
DECISION_HEADING_RE = re.compile(
    r"^## (?:" + "|".join(re.escape(MARKERS[c]["decisiones"]) for c in LANGS) + r")\s*$",
    re.MULTILINE)
```

- [ ] **Step 5: Normalize on the way out**

En `open_decisions` (:1695). Actual:

```python
    return {"decidir": found.count("DECIDIR"), "bloquea": found.count("BLOQUEA")}
```

Nuevo:

```python
    canon = [CANON_TIPO[f] for f in found]
    return {"decidir": canon.count("DECIDIR"), "bloquea": canon.count("BLOQUEA")}
```

En `_decision_items` (:1743), reemplazar:

```python
    heading = re.search(r"^## Decisiones para ti\s*$", text, re.MULTILINE)
```

por:

```python
    heading = DECISION_HEADING_RE.search(text)
```

Y en el dict que arma cada ítem (:1786-1797), cambiar `"tipo"` y agregar `_marker`:

```python
            "tipo": CANON_TIPO[m.group(2)],
            ...
            # Internal-only, like the two offsets below: the marker AS WRITTEN, so
            # `_write_answer` can answer in the document's own language instead of
            # the knob's.
            "_marker": m.group(2),
```

- [ ] **Step 6: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "decision or english" -v
```

- [ ] **Step 7: Run the full suite — the ~20 existing decision tests must stay green**

```
.venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): parsea marcadores en ingles y normaliza tipo"
```

---

### Task 7: Marcadores bilingües — escritura

**Files:**
- Modify: `apps/orchestrator/backend/app.py:1801-1823` (`_write_answer`), `:1829-1831` (`ANSWER_BLOCK_RE`)
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `MARKERS`, `marker_lang`, y la clave `_marker` de la Task 6.
- Produces: nada nuevo hacia afuera; `_pre_answer_id` sigue con la misma firma.

- [ ] **Step 1: Write the failing tests**

```python
def test_answering_an_english_item_writes_an_english_label(client, monkeypatch, tmp_path):
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path,
                                       doc=REAL_3359_DECISIONS_DOC_EN)
    decidir = [x for x in _puntos(client, tid, ruta) if x["tipo"] == "DECIDIR"][0]
    client.post(f"/tickets/{tid}/decisiones",
                json={"ruta": ruta, "id": decidir["id"], "aceptar_propuesta": True})
    text = p.read_text(encoding="utf-8")
    assert "**Answer:** repoint the legacy routes" in text
    assert "**Respuesta:**" not in text


def test_a_spanish_document_is_answered_in_spanish_even_with_the_knob_in_english(
        client, monkeypatch, tmp_path):
    """The document's language wins over the knob. Otherwise an old analysis answered
    today comes out half and half, and `_pre_answer_id` stops recognising its own
    work — the 'already answered' 409 degrades into 'the file changed', which is the
    wrong story told to the human."""
    client.put("/idioma", json={"idioma": "en"})
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path)   # Spanish doc
    punto = _puntos(client, tid, ruta)[1]
    client.post(f"/tickets/{tid}/decisiones",
                json={"ruta": ruta, "id": punto["id"], "aceptar_propuesta": True})
    assert "**Respuesta:**" in p.read_text(encoding="utf-8")
    assert "**Answer:**" not in p.read_text(encoding="utf-8")


def test_stale_id_is_recognised_in_english_too(client, monkeypatch, tmp_path):
    """`_pre_answer_id` undoes exactly what `_write_answer` did. If it only knows the
    Spanish label, an English resubmit falls through to 'the file changed'."""
    tid, ruta, p = _decisions_declared(client, monkeypatch, tmp_path,
                                       doc=REAL_3359_DECISIONS_DOC_EN)
    punto = _puntos(client, tid, ruta)[1]
    body = {"ruta": ruta, "id": punto["id"], "aceptar_propuesta": True}
    assert client.post(f"/tickets/{tid}/decisiones", json=body).status_code == 200
    r = client.post(f"/tickets/{tid}/decisiones", json=body)   # the double click
    assert r.status_code == 409
    assert "ya fue respondido" in r.json()["detail"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "english_item or knob_in_english or stale_id_is" -v
```

Expected: el primero FALLA (escribe `**Respuesta:**`), el tercero FALLA con «El
archivo cambió».

- [ ] **Step 3: Make `_write_answer` follow the item's language**

`app.py:1817-1822`. Actual:

```python
    eol = _dominant_eol(text)
    lines = answer.splitlines() or [""]
    answer_block = eol.join(
        f"{DECISION_INDENT}**Respuesta:** {ln}" if i == 0 else f"{DECISION_INDENT}{ln}"
        for i, ln in enumerate(lines)
    )
```

Nuevo:

```python
    eol = _dominant_eol(text)
    # The DOCUMENT's language, not the knob's: a Spanish analysis answered while the
    # knob says English must stay Spanish, or the file comes out half and half and
    # `_pre_answer_id` no longer recognises what this function wrote.
    label = MARKERS[marker_lang(item["_marker"])]["respuesta"]
    lines = answer.splitlines() or [""]
    answer_block = eol.join(
        f"{DECISION_INDENT}**{label}:** {ln}" if i == 0 else f"{DECISION_INDENT}{ln}"
        for i, ln in enumerate(lines)
    )
```

Y en el docstring de la función, donde dice «appends an indented `**Respuesta:**`
line», cambiar a «appends an indented `**Respuesta:**` / `**Answer:**` line, in
the document's own language».

- [ ] **Step 4: Make `ANSWER_BLOCK_RE` bilingual**

`app.py:1829-1831`. Actual:

```python
ANSWER_BLOCK_RE = re.compile(
    r"^" + re.escape(DECISION_INDENT) + r"\*\*Respuesta:\*\*.*\Z", re.MULTILINE | re.DOTALL
)
```

Nuevo:

```python
ANSWER_BLOCK_RE = re.compile(
    r"^" + re.escape(DECISION_INDENT)
    + r"\*\*(?:" + "|".join(re.escape(MARKERS[c]["respuesta"]) for c in LANGS)
    + r"):\*\*.*\Z",
    re.MULTILINE | re.DOTALL
)
```

`_pre_answer_id` no cambia: hashea `pre`, que es el texto **anterior** al bloque,
y ese texto ya trae el marcador en su propio idioma.

- [ ] **Step 5: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "english_item or knob_in_english or stale_id_is" -v
```

- [ ] **Step 6: Run the whole decisions group, both endings included**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "decision" -v
```

Expected: verde, incluidos `test_responder_decision_preserves_crlf_line_endings`,
`test_responder_decision_preserves_lf_line_endings` y
`test_responder_decision_touches_only_that_items_bytes` — los tres que garantizan
que esto sigue siendo un splice y no una reescritura.

- [ ] **Step 7: Run the full suite**

```
.venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 8: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py
git commit -m "feat(orchestrator): responde decisiones en el idioma del documento"
```

---

### Task 8: El journal y el vocabulario del runner

**Files:**
- Modify: `apps/orchestrator/backend/app.py:422` (`NO_STAMP_REASON`), `:636` (`NO_SURVEYS_REASON`), `:690` (`NO_BRIEF_REASON`), `:692` (`JOURNAL_HEADER`), `:1218-1251` (`append_journal`), `:1261-1276` (`journal_note`), `:1465`, `:1547`, `:1556` (notas del archivo), `:2098-2103` (log del fan-out), `:2621`, `:2720`, `:2964`
- Modify: `CLAUDE.md` (la regla de idioma), `docs/STATUS.md`
- Test: `apps/orchestrator/backend/tests/test_app.py`

**Interfaces:**
- Consumes: `lang()`, `MARKERS`, `LANGS`.
- Produces: `WORDS: dict[str, dict[str, str]]`, `w(key) -> str`, `journal_marks(text) -> dict`, `journal_header(ado_id, code) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_fresh_journal_follows_the_knob(client, monkeypatch, tmp_path):
    client.put("/idioma", json={"idioma": "en"})
    tid = _ticket(client)
    _run_phase(client, tid, "analyze")
    journal = (tmp_path / "repo" / "docs" / "tickets").glob("*-journal.md")
    text = next(journal).read_text(encoding="utf-8")
    assert "## Runs" in text and "## Findings" in text
    assert "## Corridas" not in text


def test_appending_follows_the_journal_not_the_knob(client, monkeypatch, tmp_path):
    """A journal created in Spanish keeps growing in Spanish. Otherwise a knob flipped
    mid-ticket leaves a file with `## Corridas` AND `## Findings`, and the run lines
    start landing at the end of the file instead of inside the runs section."""
    tid = _ticket(client)
    _run_phase(client, tid, "analyze")            # creates it in Spanish
    client.put("/idioma", json={"idioma": "en"})
    _run_phase(client, tid, "analyze")            # second line, still Spanish
    text = next((tmp_path / "repo" / "docs" / "tickets").glob("*-journal.md")) \
        .read_text(encoding="utf-8")
    assert "## Findings" not in text
    assert text.count("## Hallazgos") == 1
    # both run lines landed BEFORE the findings heading, which is the whole point
    assert text.index("analyze") < text.index("## Hallazgos")


    # `test_the_journal_lines_stay_out_of_the_findings` already exists and is the
    # guard for the insertion point. It must keep passing unchanged — do not edit it,
    # do not duplicate it. Step 7 runs it.
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv/Scripts/python -m pytest tests/test_app.py -k journal -v
```

Expected: el primero FALLA (`## Runs` no aparece).

- [ ] **Step 3: Add the runner's vocabulary table**

En `app.py`, junto a `MARKERS` (Task 6):

```python
# What the RUNNER writes inside a `.md` of the target repo. A fourth category, added
# 2026-08-19: it is neither prompt-facing (no agent reads the journal — it is a record,
# never an input) nor UI-facing (it never reaches the browser). It is deliverable-facing,
# and it is the only category that varies at runtime.
WORDS = {
    "es": {"rama": "rama", "resume": "← resume de", "reserva": "reserva",
           "archivo": "archivo", "no_copiado": "no copiado",
           "mas_de": "más de {n} archivos", "desde_run": "desde run {n}",
           "respondida": "respondida", "config_ui": "creaste {rel} desde la UI",
           "sin_huella": "la corrida no declaró huella",
           "sin_brief": "no existe el brief de la fase anterior; corre primero la fase «brief»",
           "sin_surveys": "no hay surveys que consolidar; corre primero la fase «survey»",
           "ningun_repo": "ningún repo pudo sondearse"},
    "en": {"rama": "branch", "resume": "← resumed from", "reserva": "caveat",
           "archivo": "archive", "no_copiado": "not copied",
           "mas_de": "more than {n} files", "desde_run": "from run {n}",
           "respondida": "answered", "config_ui": "you created {rel} from the UI",
           "sin_huella": "the run declared no stamp",
           "sin_brief": "the previous phase's brief does not exist; run the «brief» phase first",
           "sin_surveys": "there are no surveys to consolidate; run the «survey» phase first",
           "ningun_repo": "no repo could be surveyed"},
}


def w(key: str, code: str | None = None, **fmt) -> str:
    """One deliverable-facing word or phrase. `code` defaults to the knob; pass it
    explicitly when appending to a file whose own language already decided."""
    return WORDS[code or lang()][key].format(**fmt)
```

- [ ] **Step 4: Turn the three reason constants into functions**

`NO_STAMP_REASON` (:422), `NO_SURVEYS_REASON` (:636) y `NO_BRIEF_REASON` (:690)
son hoy constantes de módulo. Como se **guardan** en `runs.artifact_path` y se
escriben en el journal, pasan a leerse en el momento:

```python
# `NO_STAMP_REASON` (:422) — was a module constant
def no_stamp_reason() -> str:
    return w("sin_huella")
```

Ídem `no_surveys_reason()` y `no_brief_reason()`. Actualizar los **tres** sitios
de uso (`:2243` con su `reason`, `:2266`, `:2354-2357`) para llamar a la función.

**Cuidado:** `NO_BRIEF_REASON` se usa dos veces en el mismo bloque (:2354 en el
log y :2356 en `set_run`) — calcular una vez en una variable local y usarla en
las dos, para que el mensaje del log y el guardado no puedan divergir.

Antes de tocar nada, listar **todos** los usos, incluidos los de los tests:

```
cd apps/orchestrator/backend
.venv/Scripts/python -c "import re,pathlib; [print(f'{f}:{i+1}: {l.rstrip()}') for f in ['app.py','tests/test_app.py'] for i,l in enumerate(pathlib.Path(f).read_text(encoding='utf-8').splitlines()) if re.search(r'NO_(STAMP|BRIEF|SURVEYS)_REASON', l)]"
```

Un test que compare contra la constante tiene que pasar a comparar contra la
función; uno que compare contra el texto español literal tiene que envolverse en
`client.put("/idioma", json={"idioma": "es"})` o mudarse a la función.

- [ ] **Step 5: Make the journal detect its own language**

Reemplazar `JOURNAL_HEADER` (:692) por una función:

```python
def journal_header(ado_id, code: str) -> str:
    m = MARKERS[code]
    return f"# Journal — {ado_id}\n\n## {m['corridas']}\n\n## {m['hallazgos']}\n"


def journal_lang(text: str) -> str:
    """A journal's own language, judged by the headings it already carries — never by
    the knob. A file created in Spanish keeps growing in Spanish: otherwise a knob
    flipped mid-ticket leaves `## Corridas` next to `## Findings`, and every later run
    line lands at the end of the file instead of inside the runs section."""
    for code in LANGS:
        if f"## {MARKERS[code]['hallazgos']}" in text:
            return code
    return lang()
```

En `append_journal` (:1232-1247):

```python
        text = read_text_preserving_newlines(p) if p.exists() else \
            journal_header(ticket["ado_id"], lang())
        code = journal_lang(text)
        eol = _dominant_eol(text)
        mins, secs = divmod(duration_s or 0, 60)
        line = (f"{now()[:10]} · {phase} · {state} · {detail}"
                + (f" · {mins}m{secs:02d}s" if duration_s is not None else "")
                + (f" · {w('rama', code)} {branch}" if branch else "")
                + (f" · {w('resume', code)} {resumed_from}" if resumed_from else "")
                + "\n"
                + (f"   · {w('reserva', code)}: {note}\n" if note else "")
                + "".join(f"   · {x}\n" for x in (extra or [])))
        if eol != "\n":
            line = line.replace("\n", eol)
        mark = f"## {MARKERS[code]['hallazgos']}"
        i = text.find(mark)
        text = text + line if i < 0 else text[:i] + line + text[i:]
```

En `journal_note` (:1266-1272), el mismo par de cambios: `journal_header(...)` al
crear, y `mark = f"## {MARKERS[journal_lang(body)]['hallazgos']}"` al buscar.

- [ ] **Step 6: Translate the remaining runner phrases**

| app.py | Actual | Nuevo |
|---|---|---|
| :1465 | `f"más de {ARCHIVE_TREE_MAX_FILES} archivos"` | `w("mas_de", n=ARCHIVE_TREE_MAX_FILES)` |
| :1547 | `f"archivo: {skipped}"` | `f"{w('archivo')}: {skipped}"` |
| :1556 | `f"archivo: no copiado — {exc}"` | `f"{w('archivo')}: {w('no_copiado')} — {exc}"` |
| :2098 | `"HUELLA: nada — ningún repo pudo sondearse (...)"` | `f"HUELLA: nada — {w('ningun_repo')} ({...})"` — **`HUELLA: nada` NO se toca** |
| :2621 | `f"creaste {TICKET_AGENT_CONFIG_REL} desde la UI"` | `w("config_ui", rel=TICKET_AGENT_CONFIG_REL)` |
| :2720 | `extra=[f"desde run {r['id']}"]` | `extra=[w("desde_run", n=r["id"])]` |
| :2964 | `extra=[f"{item['tipo']} respondida: ..."]` | `extra=[f"{item['tipo']} {w('respondida')}: ..."]` |

Los nombres de fase (`analyze`, `design`, `restaurar`, `decision`) son
identificadores y **no** se traducen.

- [ ] **Step 7: Run the tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_app.py -k "journal or archivo or restaurar" -v
```

- [ ] **Step 8: Run the full suite**

```
.venv/Scripts/python -m pytest tests/ -q
```

- [ ] **Step 9: Update `CLAUDE.md` — the fourth category**

En la sección «Project rules», en la regla que hoy dice «**Code, comments, and
process docs in English; Spanish only in UI text.** … Three categories decide
it», cambiar a **cuatro** y agregar la nueva:

```markdown
  **Deliverable-facing** strings (the journal's own vocabulary, the reasons stored
  in `runs.artifact_path`, the archive notes) end up inside a `.md` of the TARGET
  repo, which is neither the browser nor a prompt. They follow the language knob
  (`settings.idioma`, `lang()`), and — this is the part that isn't obvious — when
  something is appended to a file that ALREADY exists, the language is taken from
  the file (`journal_lang`, `marker_lang`), never from the knob: a journal created
  in Spanish keeps growing in Spanish, and an analysis written in Spanish is
  answered in Spanish, whatever the knob says today.
```

Y agregar, junto a la explicación de `## Decisiones para ti`, que los marcadores
viajan traducidos pero **la API los normaliza** (`CANON_TIPO`), con la razón: la
comparación de `Decisions.tsx` no falla ruidosamente.

- [ ] **Step 10: Update `docs/STATUS.md`**

Agregar la sesión con: la decisión de la perilla global, el hallazgo de que
OpenSpec impone inglés (con el nivel de cada literal), la cuarta categoría de
texto, y que las fases 4-5 (i18n de la UI y los 49 `HTTPException`) quedan
pendientes en su propio plan.

- [ ] **Step 11: Commit**

```bash
git add apps/orchestrator/backend/app.py apps/orchestrator/backend/tests/test_app.py CLAUDE.md docs/STATUS.md
git commit -m "feat(orchestrator): vocabulario del runner por idioma

El journal deduce su idioma del archivo, no de la perilla: uno creado en
espanol sigue creciendo en espanol aunque la perilla cambie a mitad de ticket."
```

---

## Verificación final (después de la Task 8)

- [ ] `cd apps/orchestrator/backend && .venv/Scripts/python -m pytest tests/ -v` — todo verde
- [ ] `cd apps/orchestrator/frontend && npm run build && npm run lint` — sin errores
- [ ] `claude plugin validate .` desde la raíz — pasa
- [ ] Prueba manual de punta a punta: perilla en English → correr `analyze` sobre un
      ticket real → el análisis sale en inglés con `## Decisions for you` y
      `**DECIDE**`, el panel de decisiones lo lista y **pinta el `BLOCKS` en rojo**
      (no en amarillo), responder un punto escribe `**Answer:**`, y el journal trae
      `## Runs` / `## Findings`.
- [ ] Prueba de regresión del caso mixto: con la perilla en English, abrir un ticket
      viejo cuyo análisis está en español y responder un punto — tiene que escribir
      `**Respuesta:**` y el journal seguir con `## Corridas`.

## Lo que este plan NO hace

- **i18n de la UI** (287 líneas, 18 archivos) y **los 49 `HTTPException`**: fases 4-5
  del spec, plan aparte.
- **No retraduce nada ya escrito.** El archivo y el journal son registro histórico.
- **No detecta ni avisa** si el análisis quedó en un idioma y el plan en otro.
- **No agrega `--strict`** al validador de OpenSpec.
