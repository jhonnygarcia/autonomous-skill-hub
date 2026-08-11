---
name: change-implementation
description: Executes an Azure DevOps ticket's change plan - reads openspec/changes/<id>-*/tasks.md, implements each task with a subagent, runs its check, commits per task on the ticket's branch, and checks off the boxes. Use when asked to implement, execute the plan, or write the code for a ticket that's already been planned.
---

# Implementing a change plan

Executes a plan already written by Phase 2: writes the code, commits it on the
ticket's branch, and leaves verifiable evidence of what was done and what
wasn't. It's the first phase that writes production code into a client's repo —
act with that caution.

The run **stops on a branch with commits, no push**: don't do `git push`, don't
create a PR, and don't touch the remote. That's out of scope for this phase; the
human decides when to push what you left.

## 1. Configuration

Read `.claude/ticket-agent.json` from the current project. If it doesn't exist,
stop and guide the user to create it (template in the plugin's README). Read
`autonomy` and, if present, `subagent_model`: an alias (`opus`, `sonnet`,
`haiku`) or a full id to launch step 4's subagents with. If it's not present,
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
   (destination, mirror, check), the ticket's repo map with its label and path,
   the active branch, and the commit rules from "Golden rules" below. Every
   mounted repo for the ticket — main or extra — is writable for this phase;
   don't treat it as read-only. Ask it to implement the task and **run the
   "Check" the task itself provides** — run it, don't just describe it — and
   have it return: files touched, the check's actual result (the output, not a
   summary), and any deviation from the plan.

   Don't assume the subagent can write to the mounted repos: unlike reading and
   `Bash`, that isn't verified. If it reports it couldn't write (permission
   denied, path out of scope), treat it as a task failure — don't look for a
   shortcut to write in its place yourself.

2. **Review the diff** of the paths the subagent says it touched (`git diff` on
   those specific paths) before accepting anything. Compare it against the
   destination and the mirror the task asked for.

3. If the diff matches what was asked and the check passed: **commit those
   specific paths** — never `git add -A` or `git add .` — with the message
   `<id> task N: <subject>`, and check the box `- [x]` in `tasks.md`. One commit
   per task.

4. If something fails (the check doesn't pass, the diff doesn't match, the
   subagent couldn't write), log it and retry that same task once more, giving
   the new subagent the previous failure as context.

   **Exception: a hook denial isn't a task failure.** It's recognized because
   the denial message comes from the hook itself and mentions that this phase
   stops on a branch without touching the remote (`git push`,
   `git remote add`/`set-url`, `gh pr create`, `az repos pr create`). It means
   the subagent tried something out of this phase's scope, not that the
   implementation is wrong: log it in the report, **don't retry the denied
   command**, and **don't count that denial as one of the two failures** in
   golden rule 5 — the task keeps its normal course (diff, check, commit) with
   whatever else the subagent did manage to do.

## 5. Stopping

If a task fails **two times in a row, the loop stops there**: it doesn't skip to
the next one or continue with the rest of the plan. Stamp `parcial`, with the
remaining boxes unchecked — it's the plan's real state at that point, not a
failure to hide.

## 6. Verification and summary

Before closing, run the build (or the project's equivalent) for every repo the
loop touched. Green is a necessary condition for `ok`: a plan with every box
checked but a red build closes as `parcial`, not `ok`.

Under `autonomy: supervised`, besides the stamp, leave a summary in chat of what
was implemented and what was left blocked or pending. Under `autonomous`, the
same summary, flagging which decisions you made on your own. Any other value of
`autonomy` is treated as `supervised`, and the user is warned that the value
isn't recognized.

## 7. Golden rules

1. **Commit specific paths.** Never `git add -A` or `git add .`.
2. **One commit per task**, with its number and subject. The `git log` is the
   record of what happened.
3. **A task's check is run, not declared.** A checked task whose check never ran
   is a lying checkbox.
4. **A task that fails twice stops the plan.** What's blocked is declared
   blocked.
5. **What the hook denies is not retried.** If the denial shows up, it's logged
   and the plan continues.

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
