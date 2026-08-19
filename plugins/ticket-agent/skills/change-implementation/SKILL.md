---
name: change-implementation
description: Executes an Azure DevOps ticket's change plan - reads openspec/changes/<id>-*/tasks.md, implements each task with a subagent test-first, reviews the diff with a second subagent, runs its check, commits per task on the ticket's branch, and checks off the boxes. Use when asked to implement, execute the plan, or write the code for a ticket that's already been planned.
---

# Implementing a change plan

Executes a plan already written by Phase 2: writes the code, commits it on the
ticket's branch, and leaves verifiable evidence of what was done and what
wasn't. It's the first phase that writes production code into a client's repo —
act with that caution.

The run **ends on a branch with commits, and opens no pull request**: don't run
`gh pr create`, `az repos pr create`, or any equivalent, and don't ask anyone to
review. Opening a PR puts a team on the hook to look at this, and that call
belongs to the human, who makes it after reading what you left.

**Don't `git push` on your own initiative either** — the human reads the `git log`
locally. But it is no longer forbidden: `ticket-agent/<id>` is this phase's own
branch, so if the human asks you to push it, push it. Nothing else about the
remote is yours to change: no new remotes, no `set-url`, no other branch.

## 1. Configuration

Read `.claude/ticket-agent.json` from the current project. If it doesn't exist,
stop and guide the user to create it (template in the plugin's README). Read
`autonomy` and, if present, `subagent_model`: an alias (`opus`, `sonnet`,
`haiku`) or a full id to launch the loop's subagents with — the implementer and
the reviewer both. If it's not present,
subagents inherit this session's model, which is normal.

## 2. Preconditions

1. **The plan.** Look for `openspec/changes/<id>-*/tasks.md`. If there's no
   match → stop, ask the user to run `/ticket-agent:plan <id>` first, and close
   with `HUELLA: nada — missing plan for <id>`.
2. **Unique slug.** If there's **more than one match** (two changes for the same
   id) → stop and ask the user which one to use. This isn't hypothetical: the
   same ticket has ended up with two slugs on the same day before. Don't choose
   for them, and close with
   `HUELLA: nada — multiple changes for <id>, need to pick which one`.
3. **The branch.** Check that the main repo's current branch is
   `ticket-agent/<id>`. If it isn't, the runner didn't set it up — fixing it
   isn't this skill's job: stop, report it, and close with
   `HUELLA: nada — repo isn't on ticket-agent/<id>`.
4. **The open decisions**, in `design.md` and in the analysis. An unticked
   `- [ ] **BLOQUEA**` stops you: close
   `HUELLA: nada — <N> decisiones sin resolver` and name them. Writing code on
   top of a question nobody answered is how you end up deleting a day's work.
   Under `autonomy: supervised`, an unticked `- [ ] **DECIDIR**` stops you too —
   that's what the setting means. Under `autonomous` you proceed with its
   proposal and **record it in section 6**. A ticked `- [x]` carries the human's
   answer underneath, and **it wins over the plan's text**.

## 3. Reading the plan

Read `tasks.md` in full — the checklist with destination, mirror, and check for
each task —, plus `design.md` and `proposal.md` from the same change. The
plan's headers also carry a map of affected repos and warnings like "without
`design.md` tasks 1-4 won't make sense".

Don't go back and read Phase 1's analysis or the work item: the plan is the
interface between planning and executing.

**The real repo map, however, comes from the prompt, not the plan.** If the
prompt names additional mounted repos with their label (backend, auth app…),
those are the ones actually mounted with `--add-dir` in this run, and the ones
you'll pass to each subagent in step 4. Use it together with the map the plan's
header carries; if they differ, **the prompt wins**, because it describes what's
mounted in this run — the plan's header may be out of date relative to the
repos the project has configured today.

## 4. The loop

For each **unchecked** task (`- [ ]`) in `tasks.md`, **in order** — a plan's
tasks come ordered by dependency (model before filter, migration before using
it), don't move them ahead or reorder them:

1. **Subagent in a clean context** (the `Task` tool, with the configuration's
   `subagent_model` if there is one). Give it the task's literal text
   (destination, mirror, `Test`, `Check`), the ticket's repo map with its label and path,
   the active branch, and the commit rules from "Golden rules" below. Every
   mounted repo for the ticket — main or extra — is writable for this phase;
   don't treat it as read-only.

   **Order it red first.** Write the test the task's `Test` line names, run the
   `Check`, and keep that output: a test that passes before the code exists is
   testing the wrong thing, and the subagent fixes it before going on. Then the
   code, then the `Check` again. It returns: files touched, **the `Check`'s
   output before and after** — the text it printed, not a summary — and any
   deviation from the plan.

   A `Check: manual — ...` has no red phase. The subagent does what the line
   says and returns what it observed. Carry that forward: it's the one kind of
   task that closes without machine evidence, and step 6 has to say so.

   Don't assume the subagent can write to the mounted repos: unlike reading and
   `Bash`, that isn't verified. If it reports it couldn't write (permission
   denied, path out of scope), treat it as a task failure — don't look for a
   shortcut to write in its place yourself.

2. **Review the diff** of the paths the subagent says it touched (`git diff` on
   those specific paths) before accepting anything. Compare it against the
   destination and the mirror the task asked for.

3. **Code-review it with a second subagent, not with yourself.** You wrote the
   implementer's prompt; reviewing its output is reviewing your own instruction,
   and it approves nearly everything. Dispatch a fresh `Task` with a clean
   context and hand it only the task's literal text, the diff from step 2, and
   the paths it covers — nothing about the rest of the run. Scoped to those
   paths: the rest of the branch was reviewed when its own task was committed,
   and re-reviewing it turns every task into a review of the whole plan.

   Ask it for two things: whether the diff does what the task asked **and
   nothing else**, and a list of findings, each one graded

   - `critical` — wrong, unsafe, or an error swallowed to make the check green
   - `important` — right, but with a defect worth fixing before the commit
   - `minor` — style, naming, taste

   **Only `critical` and `important` block**; they send the task to the retry in
   step 5 like any other failure. `minor` is never retried: collect them for step 6. A
   review that can stop a plan on taste is worse than no review, because two
   rounds of taste stop it for good.

   **A finding against what the plan explicitly ordered doesn't block either.**
   The plan is this phase's contract and there's no human mid-run to break the
   tie: log it, don't retry it, let step 6 surface it. Reviewing the plan was
   Phase 2's job.

4. **Run the `Check` yourself** before committing — the same command, in the repo
   it belongs to. The subagent's transcript is a claim; this is the evidence,
   and it's the only real backing a checked box ever gets. Not green, not
   committed, whatever the report said.

   Green, plus a diff that matches the task, plus a review with nothing
   `critical` or `important`: **commit those specific paths** — never
   `git add -A` or `git add .` — with the message `<id> task N: <subject>`, and
   check the box `- [x]` in `tasks.md`. One commit per task.

   **The commit subject is always in English**, whatever the output language is.
   `tasks.md` may be in Spanish and the commit still reads
   `3323 task 4: add the carrier mapper` — the `git log` of a client's repo is
   shared infrastructure and rewriting it is expensive, so it doesn't hang off a
   setting in a tool they don't run.

   The asymmetry is deliberate: green you can re-run, red you cannot — the code
   exists now. So the red evidence stays the subagent's word, and it's the
   weakest link in the chain. If its report shows no red output, the task is
   **unverified**: it still commits if everything else holds, and step 6 names
   it. Retrying wouldn't recover the red — the test is already written.

5. **The retry.** If something fails (the check doesn't pass, the diff doesn't
   match, the review came back `critical` or `important`, the subagent couldn't
   write), log it and retry that same task once more, giving the new subagent
   the previous failure as context. Two failures on the same task and the loop
   stops — section 5 below, which is a different thing from this step.

   **Exception: a permission denial isn't a task failure.** If the subagent is
   denied a command by the environment (a hook in the client's repo, a tool
   allowlist), it tried something outside this phase's scope — that says nothing
   about whether the implementation is right. Log it in the report, **don't
   retry the denied command**, and **don't count that denial as one of the two
   failures** in golden rule 4: the task keeps its normal course (diff, check,
   commit) with whatever else the subagent did manage to do.

## 5. Stopping

If a task fails **two times in a row, the loop stops there**: it doesn't skip to
the next one or continue with the rest of the plan. Stamp `parcial`, with the
remaining boxes unchecked — it's the plan's real state at that point, not a
failure to hide.

## 6. Verification and summary

Before closing, run the build (or the project's equivalent) for every repo the
loop touched. Green is a necessary condition for `ok`: a plan with every box
checked but a red build closes as `parcial`, not `ok`.

**What the loop set aside goes in `tasks.md`, not only in chat.** Append a
top-level `## Review notes` section to the same file, with one line per item and
the task it came from:

```markdown
## Review notes

- Task 3 · minor: `InvoiceMapper` duplicates the null guard from `OrderMapper:41`.
- Task 5 · plan-mandated: review flagged the retry loop as unbounded; `design.md`
  asks for it that way.
- Task 6 · unverified: `Check: manual`, no automated evidence.
- Task 7 · unverified: the subagent reported no red output for `InvoiceTests`.
- Plan · DECIDIR sin responder: el mapper fue a `Application`, por la propuesta.
```

That file is the change's record and the human already opens it; a summary in
chat dies with the session. Nothing else gets added to `tasks.md` — don't rewrite
a task because the review disagreed with it.

An `unverified` line doesn't downgrade the stamp on its own — a `manual` check
is a plan the human approved, not a failure. What it does is stop `ok` from
meaning more than it earned, so the summary says how many there were.

Under `autonomy: supervised`, besides the stamp, leave a summary in chat of what
was implemented and what was left blocked or pending. Under `autonomous`, the
same summary, flagging which decisions you made on your own — **including every
`DECIDIR` you proceeded on without an answer**, which also goes in `## Review
notes`. Code built on an unanswered proposal that doesn't say so reads as if a
human had chosen it. Any other value of `autonomy` is treated as `supervised`,
and the user is warned that the value isn't recognized.

**Say what it would cost to redo this**, in one line, before the stamp: how many
tasks are done and what the loop already explored. It's what lets the human
choose between a fresh session and continuing this one — continuing preserves
what you learned when they're **adding**, a fresh session keeps their correction
from competing with your reasoning when they're **correcting**.

**Journal.** Findings that fall outside this deliverable's scope go as bullets at
the end of `docs/tickets/<id>-journal.md`, under `## Hallazgos` (create the file
with `# Journal — <id>`, `## Corridas`, `## Hallazgos` if it doesn't exist). Close
by appending one line to `## Corridas` — `<date> · implement · <ok|parcial|nada> ·
<path>` — **unless the prompt says the runner keeps the `## Corridas` section**, in
which case the run line is the runner's and only `## Hallazgos` is yours. In this
phase, findings that belong to a reviewed task go to `## Review notes` in
`tasks.md` as they do today; `## Hallazgos` in the journal is for what falls
outside the change entirely.

## 7. Golden rules

1. **Commit specific paths.** Never `git add -A` or `git add .`.
2. **One commit per task**, with its number and subject. The `git log` is the
   record of what happened.
3. **A task's check is run by you, not declared by anyone.** A checked task whose
   check you didn't watch pass is a lying checkbox.
4. **A task that fails twice stops the plan.** What's blocked is declared
   blocked.
5. **What the hook denies is not retried.** If the denial shows up, it's logged
   and the plan continues.
6. **The test comes before the code**, and its first run fails. A test that was
   green the first time proved nothing.
7. **Only `critical` and `important` block.** Taste doesn't stop a plan, and what
   the plan ordered isn't a finding. Both get written down instead.

## Output language

Write **the implementation** — headings, prose, and every question you leave for
the human — in the language named by, in this order:

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

## Closing

Always finish with one of these three lines, and make it the **last** one of the
message:

    HUELLA: ok — openspec/changes/<id>-<slug>/tasks.md
    HUELLA: parcial — openspec/changes/<id>-<slug>/tasks.md · <caveat>
    HUELLA: nada — <reason>

`ok` requires **both**: every box checked and a green build. If either is
missing, it's `parcial`, and the caveat says what: `3/5 tasks, build red`.

The path uses forward slashes (`/`), never backslashes. The caveat goes **only**
on the stamp line, after ` · `; the rest of the explanation goes in the summary,
not here.
