---
name: analysis-consolidation
description: Merges the per-repo surveys of an Azure DevOps ticket into a single analysis in docs/tickets/, with the contract between repos that no repo could write on its own. Use when asked to consolidate, merge the surveys, or close the analysis of a multi-repo ticket.
---

# Consolidation of the surveys

Produce `docs/tickets/<id>-analysis.md` — the same file, at the same path, that a
single-session `analyze` would produce, so the planning phase never learns which
route ran.

**Your deliverable is the contract table.** Everything else in this file could be
had by concatenating. The table is the only thing no single repo could write, and
it's what justifies having run one session per repo. A consolidation that glues N
documents together spent three sessions to produce what one would have.

## 1. Configuration and inputs

Read `.claude/ticket-agent.json` for `autonomy`.

Then:

- `docs/tickets/<id>-brief.md` — the ticket, and the routing decision.
- **Every survey** in the directory the prompt names.
- **The full list of repos the ticket mounts**, which the prompt gives you — not
  just the surveyed ones. The difference between those two lists is a section of
  the analysis.

If there are no surveys, stop: `HUELLA: nada — no hay surveys que consolidar`.
Don't write them yourself. They're separate phases and this is the last one; a
survey written from here would carry the primary repo's rules, which is the
defect the split exists to remove.

## 2. Collate the expectations

For every `Espero de otros` line in every survey, look for its match in another
survey's `Ofrezco a otros`. Four verdicts, and each one is a different problem:

| Verdict | What it means | What the plan has to do |
|---|---|---|
| ✅ cuadra | Someone expects it and someone offers it | Nothing; order the tasks so the offer lands first |
| ❌ hueco | Expected, nobody offers it | Someone has to build it — decide who |
| ⚠️ duplicado | Two repos offer the same thing | Decide where it lives, or it gets built twice |
| ❓ sin resolver | It came from a `No pude determinar` | Nobody could see it; it needs the human |

Two things that don't announce themselves and you have to look for:

**The same concept under two names.** `exportId` on one side, `reportKey` on the
other. They only show up because the table puts them side by side — read the
rows against each other, not one at a time.

**The `[asumido]` lines first.** They're where the surveys guessed about each
other, so they're where the contract breaks. A `[verificado]` expectation that
matches an offer is fine; an `[asumido]` one that matches is fine *by luck*, and
worth saying so.

## 3. The analysis

Write `docs/tickets/<id>-analysis.md` with the structure a single-session
analysis has, plus these sections:

```markdown
## Contrato entre repos

| Qué | Lo espera | Lo ofrece | Veredicto |
|---|---|---|---|
| `GET /api/trends/export` | front | back | ✅ cuadra |
| campo `trendId` en la lista | front | — | ❌ hueco: nadie lo ofrece |
| formateo de fecha del xlsx | — | back + front | ⚠️ duplicado: decidir dónde |
| paginación de la respuesta | front (no pudo determinar) | — | ❓ sin resolver |

Repos sondeados: front, back
No sondeados: auth-app
```

**`No sondeados` is mandatory whenever a mounted repo wasn't surveyed**, and it
says why: not routed, or its session failed. A reader has to be able to see the
hole. Without that line the document looks complete and lies by omission — the
most expensive failure in this system, because the planning phase consumes it
without knowing.

Then the surveys as an appendix, one section per repo, verbatim. That way the
human has **one file in the repo** with everything, and the scratch directory is
disposable.

And the open decisions:

```markdown
## Decisiones para ti

- [ ] **DECIDIR** — ¿el `trendId` lo expone el back o lo calcula el front?
      Propuesta: el back, sigue el patrón de `Controllers/Trends.cs:88`.
      Si no respondes, sigo con la propuesta.
```

**Every `❌ hueco` and every `❓ sin resolver` row becomes a `DECIDIR`.** They are
literally the questions no repo could answer alone: the exact place where the
human's knowledge of the system is worth more than any amount of further
reading. A `DECIDIR` carries a proposal; a `BLOQUEA` is for when there is no
defensible default, and says why none is.

## 4. The rule that keeps this honest

**If you can't produce the contract table, close `parcial` — never `ok`.**

If the surveys came back too thin to collate, say so in the caveat. The silent
failure mode of this whole design is a consolidation that concatenates and
stamps `ok`, and nobody finds out until the PR doesn't build.

`parcial` is also the verdict when a survey is missing because its session
failed: you have fewer repos than the ticket mounts, and the analysis says which.

## 5. Closing

Under `autonomy: supervised`, besides the stamp, leave a summary in chat: what
the ticket needs, what the contract table found (especially the gaps and the
duplications), and how many decisions you left open. Under `autonomous`, the same
summary, flagging what you decided on your own. Any other value is treated as
`supervised`, with a warning.

**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Carry
every `## Hallazgos fuera de alcance` entry from the surveys there too — the
children can't reach the journal; this session is the one that closes that loop.
Close by appending one line to `## Corridas` — `<date> · consolidate ·
<ok|parcial|nada> · <path>` — **unless the prompt says the runner keeps the
`## Corridas` section**, in which case the run line is the runner's and only
`## Hallazgos` is yours.

Always finish with one of these three lines, and make it the **last** one:

    HUELLA: ok — docs/tickets/<id>-analysis.md
    HUELLA: parcial — docs/tickets/<id>-analysis.md · <one-line caveat>
    HUELLA: nada — <reason>

`ok` requires all of it: every mounted repo either surveyed or listed as not
surveyed, the contract table produced, and the file written.
