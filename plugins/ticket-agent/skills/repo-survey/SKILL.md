---
name: repo-survey
description: Answers what an Azure DevOps ticket demands of THIS repo, under THIS repo's own rules - affected paths, the mirror to copy, the rules that apply, and what it expects from and offers to the other repos. Use when asked to survey, inspect, or assess a repo against a ticket brief.
---

# Survey of one repo

You are rooted in one repo, and **this session is the only one in the whole run
that loads its rules, its hooks and its configuration**. That's why it exists: a
single session covering every repo has the primary repo's conventions in front
of it and applies them to everyone else, confidently, with nothing to catch it.

Answer only for this repo. What belongs to another is the other survey's job.

## 1. What you have, and what you don't

**The brief travels in your prompt.** It's the whole ticket as far as you're
concerned.

**Azure DevOps is not reachable from here.** There's no MCP in this session, and
that's deliberate: the brief was read once so that N sessions don't produce N
divergent readings of the same ticket. What the brief doesn't say goes under
`No pude determinar` — never filled in, never guessed.

**This repo is read-only.** You write one file: the survey, at the path the
prompt gives you. Nothing else.

## 2. Read this repo's rules first

`CLAUDE.md`, `.claude/rules/*`, and any CLAUDE.md above the repo root — Claude
Code loads them in cascade. They're loaded because this session is rooted here,
which is the point of the whole arrangement. Use them, and cite the ones that
bear on the ticket: the plan that comes later needs them and won't have them.

## 3. Explore

Locate what the ticket touches: the files, the components, the equivalent
pattern that already exists. Delegate the breadth to an `Explore` subagent if it
helps, but the survey is yours to write.

**Every claim carries its source or its label:**

- `[verificado <file:line>]` — you opened it and it says what you claim.
- `[asumido]` — you're inferring, usually about another repo.

This isn't decoration. **The `[asumido]` lines are exactly the candidates for a
broken contract**, and the consolidation prioritizes them.

Saying "there's no mirror" is a claim like any other and needs its search named.
A `Grep` for symbols only finds what mentions them, and a twin file almost never
mentions your file's symbols. Search by name shape (`Glob`, e.g.
`**/*Export*.tsx`) and **name the search you ran**. An absence is worth exactly
as much as the search behind it.

## 4. The survey

Write EXACTLY this structure, at the path the prompt gives you:

```markdown
# Survey <id> — <label> (<repo path>)

## Verdict
touched

## What it demands of this repo
(2-6 lines. What has to change here, without proposing how)

## Affected paths
- `src/reports/TrendTable.tsx:112` — what role it plays  [verificado]

## Mirror to copy
- `src/reports/CsvExport.tsx:1-90` — the equivalent pattern that already exists
  (or: "no encontrado — busqué `Glob **/*Export*.tsx`")

## This repo's rules that apply
- CLAUDE.md:31 — new components don't go in the barrel export

## What I expect from others
- de `back`: `GET /api/trends/export?format=xlsx` → xlsx binary   [asumido]

## What I offer others
- the export button on the trends view                            [nuevo]

## Could not determine
- whether the back already paginates that response — lives outside this repo
```

Four rules about that shape, each with its reason:

**`Verdict` first, one word.** `touched` or `not-touched`. If the ticket
doesn't touch this repo, write `not-touched`, say why in one line, and leave the
rest empty. This is what makes over-inclusive routing cheap: the consolidation
discards you without reading further, and being routed by mistake costs almost
nothing.

**`What I expect from others` and `What I offer others` are the point of the whole run.**
Everything else could be written by a session that saw all the repos at once.
These two can't: they're your assumptions about the others, in a shape that can
be collated. The consolidation matches every `espero` against an `ofrezco` —
unmatched means a gap, two offers of the same thing means duplication, and the
same concept under two names shows up because they end up side by side. Write
them in the exact shape you'd need if you had to consume them: name, signature,
field. "The back gives me the data" is useless; `GET /api/trends/export →
xlsx binary` is checkable.

**`Could not determine` is mandatory and can't be empty out of laziness.** It's
this session's declared blindness, and it's the raw material for the questions
the consolidation asks the human. A survey that claims to know everything about
a cross-repo ticket is lying.

**Don't propose a solution.** No tasks, no design, no code. That's a later
phase; mixing it in hands the consolidation N incompatible partial plans instead
of N observations.

## Output language

Write **the survey** — headings, prose, and every question you leave for the
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

## 5. Closing

**Journal.** This session usually can't reach the primary repo's journal — a
fan-out child mounts only its own repo and the scratch. Findings outside the
survey's scope still matter: put them in the survey itself under a final
`## Out-of-scope findings` section. The consolidation reads every survey and
carries them to the journal.

Always finish with one of these three lines, and make it the **last** one:

    HUELLA: ok — <the path you were given>
    HUELLA: parcial — <the path you were given> · <one-line caveat>
    HUELLA: nada — <reason>

`ok` also covers `not-touched`: deciding this repo isn't involved is a complete
answer, not a failure. `parcial` when you wrote the survey but a section is
weaker than it should be (couldn't read something, the brief was too thin).
`nada` when you couldn't write the file at all.
