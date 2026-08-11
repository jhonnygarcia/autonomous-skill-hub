---
name: change-planning
description: Converts the analysis of an Azure DevOps ticket into a change plan another agent can execute - reads docs/tickets/<id>-analysis.md, studies the pattern in the code, and writes an OpenSpec change in the target repo. Use when asked to plan, design the changes, or prepare the implementation of a ticket that's already been analyzed.
---

# Change plan from an analysis

Produce a plan that **another agent can execute without re-investigating**.
Don't write product code — not implementation, not tests: the deliverable is the
OpenSpec change.

Five golden rules:

1. **What couldn't be read is reported; it is never filled in with assumptions.**
2. **Every number that doesn't come from the work item cites its source** — `file:line`,
   commit, or command.
3. **Every task cites the mirror it's copied from, with `file:line`.** "Create
   `XpoRateCall.cs`" without saying where it's copied from isn't a task, it's a
   wish.
4. **What's blocked is declared blocked, not planned around.** If something can't
   be done yet, it goes into the blockers section with its reason and its
   reference — never as a task that looks executable and isn't.
5. **Saying "it doesn't exist" is a claim and needs its source just like any
   number.** A `Grep` for symbols only finds what mentions them, and the twin
   file almost never mentions your file's symbols: searching for
   `UpdateApReadyToProcess` will never find
   `UpdateArReadyToProcessCommandTest.cs`. Before writing "no mirror exists",
   **search by name shape** (`Glob`, e.g. `**/*Command*Test*.cs`) and **name the
   search you did in the task**. An absence is only worth as much as the search
   backing it; without one it isn't honesty, it's a guess in a humble tone.

## 1. Configuration

Read `.claude/ticket-agent.json` from the current project. If it doesn't exist,
stop and guide the user to create it (template in the plugin's README). Read
`autonomy`.

## 2. Preconditions

1. **The analysis.** `docs/tickets/<id>-analysis.md` must exist. If it isn't
   there, **stop** and tell the user to run `/ticket-agent:analyze <id>` first.
   Don't generate it yourself: these are two phases and this is the second one.
2. **OpenSpec.** If the `openspec/` folder doesn't exist at the repo root, run
   `npx --yes @fission-ai/openspec@latest init`. If the command isn't available
   or fails, **stop** and report it: without the CLI there's no validation, and
   validation is part of the deliverable.

## 3. Reading the analysis

Read `docs/tickets/<id>-analysis.md` in full. From it come the scope, the
acceptance criteria, the affected code, the cited references, and whatever was
left blocked or unresolved.

**Don't go back to the Azure DevOps MCP.** The analysis is the interface between
the two phases. If it's missing something you need, that's a Phase 1 failure:
log it under "Missing information" in the plan, saying the analysis doesn't
provide it, and continue with what you can plan.

## 4. Studying the pattern

Open the files the analysis points to. If the change consists of replicating
something that already exists (another carrier, another provider, another
handler), **open the already-solved example and read it**: it's the mirror the
tasks will cite. Every claim you make about the code gets verified by opening
it, not deduced from the file name.

If the prompt names additional mounted repos with their label, they're in scope
for this step.

**Look for the mirror by kinship, not just by symbols.** Before giving up on a
task's example, try the repo's own symmetry: if you're touching AP, look for AR;
if you're touching a command, look for the sibling command's test; if you're
touching an entity, look for the twin entity. A `Glob` by name shape
(`**/*Command*Test*.cs`, `**/Ar*Invoice*.cs`) finds in one step what a `Grep` for
symbols can never find. A repo with two symmetric halves is the best mirror
there is, and it's exactly the one that escapes when searching by content.

## 5. Writing the change

Write into `openspec/changes/<id>-<slug>/`:

- `<slug>`: the work item's title in kebab-case, no punctuation, trimmed to about
  5 words. Example: 3323 *"Carrier API V2 Migration - XPO"* →
  `openspec/changes/3323-carrier-api-v2-migration-xpo/`.

Four files:

**`proposal.md`** — why, what, and with what impact. Each change in the form:

```markdown
**[Behavior or section name]**
- From: [current state]
- To: [future state]
- Reason: [why]
- Impact: [breaking or not, who's affected]
```

Close `proposal.md` with a top-level section, `## Missing information`, with
what Phase 1's analysis doesn't provide and is needed to plan well. If there's
nothing to log, omit the section — don't leave it empty.

**`tasks.md`** — the executable checklist. Each task carries a destination,
mirror with lines, and how it's checked:

```markdown
- [ ] Create `path/to/Destination.cs`
      Mirror: `path/to/Example.cs:1-140`
      Reuse: `path/to/what/already/exists.cs`
      Check: [what has to pass for the task to be considered done]
```

And its own top-level section for what **can't** be done:

```markdown
## Blocked

- **[What]** — [why it can't be done yet], per [reference backing it].
  Unblocks: [what would be needed].
```

**`design.md`** — the technical decisions and the alternatives ruled out. If
there's no decision to make, say so in one line instead of padding it out.

**`specs/<capability>/spec.md`** — the future state of the affected capability.
`<capability>` is the **system capability**, not the ticket: it's the folder
OpenSpec reuses across changes. If one already exists under `openspec/specs/`
that fits, use it; don't invent a new one per ticket.

## 6. Validation

Run exactly:

    npx --yes @fission-ai/openspec@latest validate --changes --no-interactive

Without either `--changes` or `--no-interactive` the CLI enters interactive mode
waiting for a terminal selection, and in headless there's no terminal to answer
it: the run hangs. If it fails, fix it and validate again. **On the second
failed validation, stop**: leave the change written and report what doesn't
pass. An invalid change that can be reviewed is worth more than none at all.

## 7. Closing based on autonomy

- `supervised`: summarize in chat what was planned, what was left blocked, and
  what's missing; don't touch the work item.
- `autonomous`: same, and also explicitly flag which decisions you made on your
  own.
- Any other value of `autonomy` is treated as `supervised`, and the user is
  warned that the value isn't recognized.

**Mandatory closing rule.** The last line of the summary —with nothing after
it— has to be exactly one of these three stamps, followed by the change path
relative to the main repo (or by the reason, in the `nada` case) — **always with
`/` as the separator, never `\`, even if the repo is on Windows**: the
orchestrator uses it as-is to read the file from disk and as an allowlist for
its viewer, and a backslash breaks the regex that extracts it from the log. The
orchestrator reads this line to decide whether the run counts: the CLI's exit
code doesn't say so, because it exits 0 even if the agent stopped without
writing anything.

- `HUELLA: ok — openspec/changes/<id>-<slug>` — the change is written and
  `openspec validate --changes --no-interactive` passed.
- `HUELLA: parcial — openspec/changes/<id>-<slug> · <one-line caveat>` — the
  change was written but validation didn't pass (two attempts) or never ran.
  The caveat goes ON the stamp line, after the path, separated by ` · ` (space,
  middle dot, space) — not in the summary: it's the only thing the orchestrator
  stores and shows alongside the stamp. Example:
  `HUELLA: parcial —
  openspec/changes/3323-carrier-api-v2-migration-xpo · openspec validate didn't
  pass after two attempts`.
- `HUELLA: nada — <reason>` — no change was ever written: the analysis is
  missing, `npx` isn't available, or `openspec init` failed.

## Error handling

- Missing analysis → stop, ask for Phase 1, and close with
  `HUELLA: nada — missing docs/tickets/<id>-analysis.md`.
- `npx` unavailable or `openspec init` fails → stop, report it, and close with
  `HUELLA: nada — npx unavailable or openspec init failed`.
- The analysis exists but doesn't bring the affected code → plan what you can,
  log the gap noting it comes from Phase 1, and close with `HUELLA: ok` or
  `HUELLA: parcial` depending on whether validation passed.
- `openspec validate` fails twice → leave the change written, report what
  doesn't pass, and close with `HUELLA: parcial`.
- No mirror found for a task → **first search by name shape** (rule 5): the
  repo's symmetric half usually has it. If it's still not there, say so in the
  task **citing the search backing it** ("`Glob **/*Command*Test*.cs` → no
  AR/AP command test found"). A task without a mirror is a task the implementer
  will have to investigate, and that has to be flagged (it doesn't change the
  stamp by itself). A task without a mirror *that actually had one* is worse
  than a wrong citation: nobody reviews it.
