---
name: ticket-comprehension
description: Fully understands an Azure DevOps ticket - reads the work item with its relations, comments, attachments and wiki, absorbs the host project's rules, and produces a structured analysis in docs/tickets/. Use when asked to analyze, understand, or investigate an Azure DevOps ticket/work item.
---

# Azure DevOps ticket comprehension

Produces a complete, faithful analysis of a work item. Two golden rules:

1. **What couldn't be read is reported under "Missing information"; it is never
   filled in with assumptions.**
2. **Every number that doesn't come from the work item cites its source** —
   `file:line`, a commit id, or the command that produced it. Without a verified
   source, don't write it down.

## 1. Configuration

Read `.claude/ticket-agent.json` from the current project. If it doesn't exist,
stop and guide the user to create it (template in the plugin's README) — do not
continue without it. Use `project` for all MCP queries. Also read `autonomy`.

## 2. Collection (all read-only)

Tools from the azure-devops MCP. **Never use any `*_write` tool.**

1. **Work item**: `wit_work_item` action `get` with `expand: "All"` — fields,
   description, acceptance criteria, relations, attachments.
2. **Comments**: `wit_work_item` action `list_comments`. Comments frequently
   correct the description (scope that gets added or dropped, revised figures):
   wherever a comment contradicts the description, **the most recent comment
   wins**, and the
   analysis says so.
3. **Relations — 1 level maximum**: from the previous result, identify parent,
   direct children, related items, and linked PRs/commits. Delegate the reading to
   a subagent (`Explore` or general-purpose) that returns, FOR EACH ONE: id,
   title, type, status, relation type, and a 2-3 line summary of what it
   contributes to the main ticket. Don't follow relations of relations. The
   1-level limit applies **only to `relations`** — it doesn't excuse skipping what
   the ticket cites in its text (step 6).
4. **Attachments**: download them with `wit_work_item_attachment`. Images:
   describe them by looking at their content. Documents: summarize what's
   relevant to the ticket. Unreadable or not downloadable → log it under "Missing
   information" with the cause.
5. **Wiki**: `search_wiki` with the ticket's key terms (components, screens,
   domain). Maximum 5 searches; include only relevant findings.
6. **References cited in the text — MANDATORY READING.** Go through the
   description and comments and extract every explicit reference:
   - **Work items cited by id** (e.g. "ADO Bug #3271") → read them with
     `wit_work_item` action `get`. Not being in `relations` doesn't exempt them:
     they're a reference, not a relation, and the step-3 limit doesn't apply.
   - **Repo documents cited by path** (e.g. `docs/quote-visibility-rules.md`) →
     open and read them.

   Listing them as "applicable" is not enough — the content has to be read. They
   only go under "Missing information" if the reading attempt **failed**, with
   the cause; never for not having been attempted.
7. **Host project rules**: read CLAUDE.md and `.claude/rules/*` if they exist.
   Claude Code loads CLAUDE.md files in cascade from the working directory
   upward, so there may be rules above the repo root — include them. These rules
   condition the analysis; they don't get replaced by it.
8. **Affected code**: `Explore` subagent with the files/components/classes the
   ticket mentions; it returns concrete paths and the role each one plays. If the
   prompt names **additional mounted repos** (with their label: backend, auth
   app…), they're in scope for this step: when the ticket points to behavior that
   doesn't live in the main repo, open them instead of declaring that behavior
   "out of scope".
9. **State of work already started** (only if there is any): if the ticket is in
   progress, you can inspect the branch, its commits, and the repo's working
   documents. It's valuable material, but it's **repo state, not ticket content**:
   it goes in its own section, and every figure (commit counts, progress
   percentages, test counts) is verified against the command or the `file:line`
   that backs it, and cited. Don't attribute to a document a percentage that
   belongs to one of its parts.

## 3. Analysis

**Mandatory first step of this section: create the file.** Write
`docs/tickets/<id>-analysis.md` (create the directory if missing) with EXACTLY
this structure. Presenting the analysis in chat without having written the file
is a task failure, not an acceptable variant.

```markdown
# Analysis of ticket <id>: <title>

**Type/Status:** ... · **Assigned:** ... · **Iteration:** ...
**Analyzed:** <date> by ticket-agent v0.9.1

## What it asks for
(2-6 lines, faithful to the ticket, without over-interpreting)

## Acceptance criteria
### Explicit
(the ones written in the ticket, quoted or faithfully paraphrased)
### Implicit
(the ones deduced from the description/relations; mark each one as DEDUCED)

## Ambiguities and open questions
(everything an implementer would need to ask before coding)

## Relations context
(for each related item: id, relation type, summary of what it contributes)

## Comments
(for each comment: date, author, and what it changes relative to the
description; state explicitly whether it corrects the scope or a figure.
"None" if there are none)

## Cited references
(for each work item or document cited in the text: what it is and what it
contributes, read in step 2.6. "None" if there are none)

## Reviewed attachments
(for each one: name, what it contains, what it contributes)

## Applicable project rules
(rules from CLAUDE.md/.claude/rules/referenced docs that apply to THIS ticket)

## Affected code
(concrete paths and the role each one plays)

## State of work in the repo
(only if the ticket already has work started: branch, progress, and blockers,
with the source of each figure. Omit the whole section if there's no work
started)

## Risks and dependencies
(technical and business, detected)

## Missing information
(everything that couldn't be read and why; explicit empty state if nothing
was missing: "None")

## Decisiones para ti

- [ ] **DECIDIR** — <the question>
      Propuesta: <the proposal, with its file:line where one applies>
      Si no respondes, sigo con la propuesta.

- [ ] **BLOQUEA** — <the question>
      <why no defensible default exists>
```

## 3b. The open decisions

The last section isn't a summary of the ambiguities already listed above: it's
the short, bounded list of what **you need a human for**, so nobody has to read
8 KB hunting for the weak spots. Two levels, and the difference is whether a
defensible default exists:

| Marker | Left unanswered |
|---|---|
| `DECIDIR` | The next phase proceeds with the proposal **and records that it did** |
| `BLOQUEA` | The next phase doesn't start: `HUELLA: nada — <N> decisiones sin resolver` |

**`BLOQUEA` only when there is genuinely no defensible default**, and the marker
says why none is. If every ambiguity blocks, this stops being a tool that helps
and becomes a form to fill in. `DECIDIR` never blocks — but proceeding with the
proposal **without leaving a trace** is worse than blocking, which is why the
next phase has to write down that it did.

The human answers by editing the file: ticking the box and writing underneath.
Same checkbox convention as `tasks.md`. Don't invent a second format.

## 4. Closing based on autonomy

- `supervised`: present a summary of the analysis to the user with the file
  path, and stop. Don't propose implementation.
- `autonomous`: present the same summary and stop just the same — this skill's
  closing is to stop **in all cases**, no exceptions. Phase 2 (`change-planning`)
  is not chained here: it's launched as the orchestrator's own run, never inside
  the analysis run.
- Any other value of `autonomy` is treated as `supervised`, and the user is
  warned that the value isn't recognized.

**Say what it would cost to redo this**, in one line, before the stamp: how many
files you opened, how many relations and attachments you read. The human needs it
to choose between a fresh session and continuing this one — and only they know
whether their adjustment **adds** scope (where continuing saves the exploration)
or **corrects** what you understood (where a fresh session keeps their correction
from competing with the reasoning behind the mistake). Point at where you
hesitated, too: that's usually what they'll want to correct.

**Mandatory closing rule.** The last line of your summary —with nothing after
it— has to be exactly this stamp, followed by the analysis path relative to the
main repo — **always with `/` as the separator, never `\`, even if the repo is on
Windows**: the orchestrator uses it as-is to read the file from disk and as an
allowlist for its viewer, and a backslash breaks the regex that extracts it from
the log:

- `HUELLA: ok — docs/tickets/<id>-analysis.md` — the analysis is written and
  complete.
- `HUELLA: parcial — docs/tickets/<id>-analysis.md · <one-line caveat>` — it's
  written, but with caveats (couldn't read the parent, missing attachments,
  "Missing information" carries weight). The caveat goes ON the stamp line,
  after the path, separated by ` · ` (space, middle dot, space) — not in the
  summary: it's the only thing the orchestrator stores and shows alongside the
  stamp. Example:
  `HUELLA: parcial — docs/tickets/3323-analysis.md · left "Missing information"
  with the parent unread`.
- `HUELLA: nada — <reason>` — the file wasn't written. The reason goes after the
  dash.

The orchestrator reads this line to decide whether the run counts: the CLI's
exit code doesn't say so, because it exits 0 even if you stopped without writing
anything.

## Error handling

- Nonexistent ticket or no permissions → report the exact cause and stop.
- MCP not connected or `ADO_ORG` undefined → point to the plugin README's steps.
- Inaccessible relation, reference, or attachment → note it under "Missing
  information" with the cause and continue.
