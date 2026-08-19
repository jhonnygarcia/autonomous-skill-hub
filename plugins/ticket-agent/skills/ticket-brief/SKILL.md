---
name: ticket-brief
description: Reads an Azure DevOps ticket and decides which of the project's mounted repos deserve their own survey - work item, relations, comments, attachments and wiki into docs/tickets/<id>-brief.md, with the routing line. Use when asked to brief, collect, or route a ticket that spans more than one repo.
---

# Brief of a ticket, and its routing

Two jobs, and only two: collect what the work item says, and decide which repos
have to be looked at. **You don't analyze code** — each routed repo gets its own
session rooted in it, and that session is the only one that loads that repo's
rules. Doing the analysis here would put the main repo's conventions in front of
every repo at once, which is the exact defect this phase exists to avoid.

Three golden rules:

1. **What couldn't be read is reported under "Missing information"; it is never
   filled in with assumptions.**
2. **Acceptance criteria travel verbatim.** The surveys can't come back to the
   work item — Azure DevOps isn't reachable from them. What this file omits does
   not exist for the rest of Phase 1.
3. **When in doubt about a repo, include it.** Surveying one too many costs a
   session; leaving one out costs the ticket, and nothing downstream detects it.

## 1. Configuration

Read `.claude/ticket-agent.json` from the current project. If it doesn't exist,
stop and guide the user to create it (template in the plugin's README) — do not
continue without it. Use `project` for all MCP queries. Also read `autonomy`.

## 2. Collection (all read-only)

**Local request (`R-` key) — the source cut.** If the id starts with `R-`, there is
no work item: the whole request is `docs/tickets/<id>-request.md`, written by the
human who asked for it. If that file doesn't exist, stop and guide the user to
create it. Skip the work-item steps below — there is no work item, no comments, no
relations, no attachments to read; the brief quotes the request's own words where
the work item's description would go, and its acceptance criteria are proposals
(`DECIDIR`), never given. Wiki search, cited references and the host project's
rules still apply in full. If the MCP is not connected, cited work items and the
wiki go under "Missing information" with that cause and the brief **continues**:
the request file is the source; the MCP is supplementary here, not a precondition.

Tools from the azure-devops MCP. **Never use any `*_write` tool.**

1. **Work item**: `wit_work_item` action `get` with `expand: "All"`.
2. **Comments**: `wit_work_item` action `list_comments`. Where a comment
   contradicts the description, **the most recent comment wins**, and the brief
   says so.
3. **Relations — 1 level maximum**: parent, direct children, related items,
   linked PRs. For each: id, title, type, status, relation type, and two or
   three lines on what it contributes.
4. **Attachments**: `wit_work_item_attachment`. Images: describe what they show.
   Documents: summarize what bears on the ticket. Unreadable → "Missing
   information", with the cause.
5. **Wiki**: `search_wiki` with the ticket's key terms. Maximum 5 searches.
6. **References cited in the text**: work items cited by id are read with
   `wit_work_item`; not being in `relations` doesn't exempt them.

## 3. Size discipline

**The brief must fit in about 4 KB**, and this isn't a style preference: it
travels **inline in the prompt of every survey**, so its cost is paid once per
routed repo.

If it doesn't fit, something is being copied that should be summarized. What
never gets cut: the acceptance criteria, and the ambiguities.

## 4. The routing

The prompt names the repos this ticket mounts, with their labels. Decide which
of them the ticket touches — to write **or to read**.

Judge by what the ticket describes, not by what it names: a ticket asking for an
Excel export of a report touches whoever serves the data and whoever draws the
button, and it rarely says so.

**The asymmetry is the whole point.** A survey of an irrelevant repo comes back
`not-touched` in two minutes. A repo left out is a hole in the analysis that the
plan will consume without knowing. So: **any repo you have reasonable doubt
about goes in.**

Close the file with the routing line, alone on its line, with the labels exactly
as the prompt gave them:

    SONDEAR: back, front

The runner reads this line. If it can't understand it — an unknown label, an
empty line, no line at all — it surveys **every** mounted repo. That's the safe
direction, but it's the fallback, not the plan.

## 5. The brief

Write `docs/tickets/<id>-brief.md` (create the directory if missing) with EXACTLY
this structure. Presenting it in chat without writing the file is a task failure.

```markdown
# Brief of ticket <id>: <title>

**Type/Status:** ... · **Assigned:** ... · **Iteration:** ...
**Collected:** <date> by ticket-agent v0.12.1

## What it asks for
(2-6 lines, faithful to the ticket, without over-interpreting)

## Acceptance criteria
(verbatim, one per line. If there are none stated, say so — don't invent them)

## Context from relations
- #<id> <title> (<type>, <status>, <relation>) — what it contributes

## Ambiguities
(what the ticket doesn't settle and someone has to decide)

## Missing information
(what couldn't be read, with the cause)

## Routing
(one line per repo: label, whether it's read or write, and why)

## Decisiones para ti

- [ ] **DECIDIR** — <the question>
      Propuesta: <the proposal>
      Si no respondes, sigo con la propuesta.

- [ ] **BLOQUEA** — <the question>
      <why no defensible default exists>

SONDEAR: <labels, comma-separated>
```

The `Decisiones para ti` section is where the human's judgement is worth more
than more reading. Two levels, and the difference is whether a defensible
default exists:

- `DECIDIR` — has a proposal. Unanswered, the next phase proceeds with it **and
  records that it did**.
- `BLOQUEA` — there is no safe default, and the marker says why none is. The
  next phase does not start.

**`BLOQUEA` is for when there is genuinely no defensible default.** If every
ambiguity blocks, the tool stops helping and becomes a form.

The routing line goes **last**, after everything, because the runner anchors on
the last match — this file's own example carries the literal.

## Output language

Write **the brief** — headings, prose, and every question you leave for the
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

## 6. Closing

Under `autonomy: supervised`, besides the stamp, leave a summary in chat: what
the ticket asks for, which repos you routed and why, and what you left marked as
a decision. Under `autonomous`, the same summary, flagging what you decided on
your own. Any other value is treated as `supervised`, with a warning.

Say in one line what it would cost to redo this: how many relations, attachments
and wiki pages you read. The human needs it to choose between a fresh session
and continuing this one — and only they know whether their adjustment adds scope
or corrects your reading.

**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Close
by appending one line to `## Corridas` — `<date> · brief · <ok|parcial|nada> ·
<path>` — **unless the prompt says the runner keeps the `## Corridas` section**, in
which case the run line is the runner's and only `## Hallazgos` is yours.

Always finish with one of these three lines, and make it the **last** one:

    HUELLA: ok — docs/tickets/<id>-brief.md
    HUELLA: parcial — docs/tickets/<id>-brief.md · <one-line caveat>
    HUELLA: nada — <reason>

`parcial` when the work item was read but something important couldn't be
(attachments, a cited work item), with the caveat saying what. `nada` when the
configuration is missing, the MCP isn't connected, or the file wasn't written.
