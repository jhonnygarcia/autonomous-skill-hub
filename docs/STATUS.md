# Project status — Autonomous Skill Hub

> Living document. Update it when closing each milestone or making a decision.
> Last updated: 2026-08-14 (**la solicitud sin ticket y el journal**, plugin
> **v0.10.0**, 217 tests backend)

## Purpose

Personal hub of Claude Code plugins that captures Jhonny's experience as
reusable skills/agents/hooks. First goal: an agent that reads an Azure DevOps
ticket, understands it thoroughly (relations, attachments, wiki, project
rules), and will progress through phases to design, implement, test and
validate the code with guards — installable in any project and able to learn
from each one.

## Roadmap and status

| Phase | What it delivers | Status |
|---|---|---|
| 0 — Hub foundation | Plugin marketplace + ticket-agent skeleton | ✅ Done |
| 1 — Ticket comprehension | `ticket-comprehension` skill + `/ticket-agent:analyze` (read-only) | ✅ **Accepted** (3311 and 3322) — skill **v0.3.0** |
| Orchestrator (cross-cutting) | Local app: SQLite queue + multi-engine CLI runner + React UI | ✅ **Three phases launchable**, per-phase progress, stamps and timeline. Clean-tree guard and branch under the lock. Containment hook removed and `ENGINES` (claude, codex) added on 2026-08-16 (decisions 18 and 20) |
| 2 — From analysis to a change plan | `change-planning` skill + `/ticket-agent:plan` → OpenSpec change | ✅ **Closed** (3323 and 3320, n=2) — plugin **v0.5.2**, with the negative-claim rule verified on a re-run |
| 2b — From plan to code | Execute the plan: write code and commit on a branch | ✅ **Built and validated** (3332) — plugin **v0.6.1**, n=1. Ends on a branch and opens no PR |
| ~~3 — Tests~~ | Unit tests tied to acceptance criteria | ✅ **Absorbed by 2b** (2026-08-11) — it wasn't a phase, it was a step |
| 4 — Guards | Read-only reviewer agents + deterministic guards | 🔄 **Rethought** (2026-08-16): the containment hook is gone (decision 18); what guards `implement` is the branch. The per-task reviewer exists inside 2b; a phase-level reviewer is still missing |
| 5 — Per-project learning | Local memory that feeds the skills | 🔄 **Shrunk** (2026-08-08): the target repo's `CLAUDE.md` already does this |

**The roadmap shrinks as it gets built, and it's not worth fighting that.** Three of
the four "future" phases turned out not to be phases at all. Phase 5 shrank once it
became clear the host project's `CLAUDE.md` already is the memory. Phase 3 disappeared
entirely: 3332 wrote **12 test files inside `implement`**, because every task in the
plan carries its own *"Check"* and the skill requires running it — asking for a
separate phase would have meant asking for the tests twice. And phase 4 shrank the
same way, twice over: the per-task reviewer that 2b already runs is half of it, and
the containment it was supposed to add turned out to be the branch itself once the
push hook was removed (decision 18).

Practical consequence, applied on 2026-08-11: **`test` was removed from `PHASES`**. A
declared phase that will never be launched isn't documentation, it's a broken promise
taking up a slot in the timeline. Five remain: `analyze`, `design`, `implement`,
`guards`, `pr`.

## What exists and where

- **Marketplace**: `.claude-plugin/marketplace.json` — install with
  `/plugin marketplace add <hub-path>` + `/plugin install ticket-agent@autonomous-skill-hub`.
- **ticket-agent plugin**: `plugins/ticket-agent/` — `.mcp.json` (official
  Azure DevOps MCP, org via the `ADO_ORG` env var, filtered domains, `az login`
  auth), `ticket-comprehension` skill, `analyze` command, install README.
- **Orchestrator**: `apps/orchestrator/` — FastAPI+SQLite backend (`backend/app.py`,
  **18 pytest tests**), startup README. No config file: projects live in the
  DB and are edited from the UI.
  Frontend (Vite+React+Tailwind+shadcn), one view per file:
  `App.tsx` (view switcher and state), `Sidebar`, `ProjectHeader`,
  `TicketList`, `TicketDetail`, `Projects` (settings), `status.ts` (labels,
  lock while a run is active, durations).
- **Designs**: `docs/superpowers/specs/` (hub+phase1, orchestrator, UI
  navigation). **Plans** with checkboxes: `docs/superpowers/plans/`.
- Per-target-project configuration: `.claude/ticket-agent.json` (org, project,
  `autonomy: supervised|autonomous`) + `ADO_ORG` in the project's settings.

## Key decisions (and why)

1. **A thin plugin that reuses public pieces**: Microsoft's official MCP +
   superpowers skills; only what encodes our own experience gets built.
2. **Subscription, never an API key**: programmatic execution uses the
   headless CLI (`claude -p`) — the Agent SDK requires `ANTHROPIC_API_KEY`. On
   top of that, the runner removes `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`
   from the subprocess environment (a test guarantees this).
3. **SQLite without an ORM, one ticket at a time** (global lock): a transient
   local queue.
4. **The pipeline's state lives in the orchestrator; the analysis lives in the
   project's repo** (`docs/tickets/<id>-analysis.md`) — one source of truth
   per thing.
5. **OpenSpec: adopted** (2026-08-10) as Phase 2's output format, with its
   folder in the **target repo**, not here. The package is
   `@fission-ai/openspec` — *not* `openspec`, which is a different thing and
   doesn't exist as an executable. Still a candidate for Phase 5's live
   memory.
6. **A ticket can span N repos, but writes to one** (2026-08-08). 3311 sends
   backend fixes to `ProvidenceTMSTenant`, a sibling repo of the primary one.
   A project declares a `repo_path` (the run's cwd, where the analysis is
   written) and `extra_dirs`, which the runner mounts with `--add-dir`.
   Decision 4 doesn't change. **Corollary (2026-08-09): mounting isn't
   enough.** See "Lessons learned".
7. **Projects live in the DB and are edited from the UI** (2026-08-08), not in
   a file. With `extra_dirs` being a list, hand-editing JSON stopped making
   sense; and a project that can't be registered from the UI is a hole in the
   product. The ticket **copies** the project's data when created (like a
   line item on an order preserves the price), so there's no FK and deleting
   a project doesn't break history.
8. **Don't build `CLAUDE.md` discovery**: Claude Code already loads them in a
   cascade from `cwd` upward, crossing the repo boundary. Verified in 3311,
   which picked up three levels — including
   `D:/Companies/ProvidenceSolutions/CLAUDE.md`, which is outside the repo —
   without anyone telling it to.
9. **A project has repos; the user marks which one is primary** (2026-08-09).
   The API exposes a flat list `repos: [{path, label, primary}]`. Internally
   they're still stored separately because the runner uses them differently,
   but that stops being a concept the user has to understand. The `label`
   isn't decorative: it travels into the prompt. The project's name is
   editable — renaming is safe because tickets copy its data when created
   (decision 7).
10. **The project is the UI's context** (2026-08-09, spec
    `2026-08-09-orchestrator-ui-navegacion-design.md`): a sidebar of projects,
    a header showing which repos the agent will see, and the right-hand panel
    becomes the ticket once one is selected. Three views with `useState`, no
    router.
11. **Phase 2 delivers a document, not code** (2026-08-10, spec
    `2026-08-09-fase-2-plan-de-cambios-design.md`). The plan is written **for
    the agent that will implement it**: destination, mirror with
    `file:line`, and how it's checked. That keeps the run read-only + writing
    markdown, so there are no branches or write permissions to sort out yet.
    Writing the code is a separate phase.
12. **Two chained skills, not one with two modes** (2026-08-10).
    `change-planning` consumes `docs/tickets/<id>-analysis.md` and **stops if
    it doesn't exist**. The analysis is the interface: if it comes out wrong,
    it shows in the file and Phase 1 gets re-run on its own.
13. **A run's status isn't inferred from the exit code** (2026-08-10).
    `claude -p` exits with 0 even if the agent stops without doing anything,
    so `planned` came to mean "the subprocess didn't crash." Now the skill
    closes with a stamp and the runner decides based on the **last** match in
    the log. See "Lessons learned" for why *last* and not *present*.
    **Generalized on 2026-08-10**: the stamp is
    `HUELLA: <ok|parcial|nada> — <ruta>`, both skills close with it, and it
    governs every phase. `PLAN:` is kept only as a legacy alias so old logs
    don't break.
14. **Progress lives in `runs`, not in a status column** (2026-08-10, spec
    `2026-08-10-avance-por-fases-y-timeline-design.md`, **implemented on
    2026-08-10**). The `PLAN:` stamp is generalized to
    `HUELLA: <ok|parcial|nada> — <ruta>` for every phase, `runs` gains the
    stamp, `current_phase` is dropped and `tickets.status` becomes computed.
    The ticket UI becomes a phase journey with the action and the artifact
    for each one, and the artifact is read inside the app. This deliberately
    reverts the earlier decision to remove the stepper: there it was 6 dimmed
    phases on **every row of the list**; here they appear once, in the detail
    view, where the remaining path is context.
15. **`ProvidenceTMSTenant` is the guinea pig** (2026-08-10). Whatever runs
    leave there —analysis, `openspec/`, whatever `openspec init` installs
    under `.claude/` and `.opencode/`— **doesn't need to be versioned or
    reverted**. What's being tested is the plugin and the orchestrator, not
    that repo. It is worth **measuring** the footprint they leave, though:
    that's evidence about the tool.
17. **Phase 2b stops on a branch with commits, no push** (2026-08-11, spec
    `2026-08-10-fase-2b-del-plan-al-codigo-design.md`, six decisions voted
    there). The two that matter most: work happens **in place with a
    clean-tree guard** —a worktree wouldn't bring along `node_modules` or
    `obj/`, and every run would pay for an install before it could run the
    plan's checks— and **containment is a deterministic hook**, not an
    instruction in the skill. The hook contains **accidents, not malice**:
    it's a latch, and if this phase ever runs unattended it needs to be
    redone. **The hook half of this decision was reversed on 2026-08-16 — see
    decision 18.** The clean-tree guard and the in-place work stand.
16. **A negative claim carries its source just like a figure does**
    (2026-08-10, rule 5 of `change-planning`, plugin v0.5.2). The golden
    rules disciplined what the agent **finds**; nothing disciplined what it
    declares **absent**, and that's where 3320 failed. Now declaring
    "doesn't exist" requires having searched **by name pattern** (`Glob`),
    not by symbols, and **naming that search in the task**. Generalizable to
    future phases: every negative claim the agent makes is either verifiable
    or invalid.

18. **No push guard, and the PR is the only thing the run won't do**
    (2026-08-16). The `PreToolUse` hook on Bash (`hooks/deny_push.py`,
    injected with `--settings`) is deleted, along with its test. Two reasons,
    and the second is the load-bearing one:

    - **Pushing was never the danger.** `ticket-agent/<id>` is the run's own
      branch; sending it to the server touches nobody's work. What does put a
      team on the hook is the **pull request** — so that, and only that, stays
      out of the run. The hook conflated the two and denied push even when the
      human explicitly asked for it in a resume, which made the adjustment
      loop lie about what it could do.
    - **A hook is a Claude Code mechanism.** The runner is headed toward
      launching other engines per phase (Codex, Gemini, Kimi, Copilot — none
      of them share this hook format; each contains differently, via sandbox,
      `excludeTools`, `--deny-tool`, or permission config). Anything built on
      `--settings` is a bet on one CLI, and the containment it bought was
      already available for free: the branch. `prepare_branch` is the real
      boundary and it is engine-agnostic.

    What replaces it is a contract in the skill, not a mechanism: don't open a
    PR, don't push on your own initiative, push if the human asks. **This is
    weaker than a hook and that's accepted** — it's the price of the runner
    not being Claude-shaped, and the same tradeoff already governs everything
    else the skills promise. If `implement` ever runs unattended against a
    repo where a stray push would hurt, the guard comes back **in git**
    (`GIT_CONFIG_COUNT` + `url.<dead>.pushInsteadOf` in the subprocess env,
    verified working on 2026-08-16), not in a CLI's hook format.

19. **The runner is headed toward being engine-agnostic** (2026-08-16, spec
    `2026-08-16-orquestador-agnostico-de-engine-design.md`). The orchestrator
    is a wrapper: it launches a prompt against a repo with a model and an
    effort, and collects what got written to disk. None of that is Claude's.
    The contract is already there — subprocess + `HUELLA` + files — so what
    gets abstracted is only **how it's launched and where the stamp is read
    from**. Two findings decide the shape: **`effort` is not universal**
    (Gemini, Kimi and Copilot have no such knob, so the registry carries
    `supports_effort` and the UI hides the field — it is not emulated with
    "think harder" in the prompt), and **Copilot has no structured output**,
    so it can be orchestrated but will never have continuations.

    **Validated the same day, by hand, before writing any adapter.** `codex
    exec` 0.147.0 ran `analyze` and then `plan` on an `R-` request against
    `ProvidenceTMSTenant`, each with its skill's `SKILL.md` inline as the
    prompt — no plugin installed anywhere. `analyze` stopped correctly on a
    missing `ticket-agent.json`, then wrote the full 14-section template with
    31 of 32 citations resolving to real files. `plan` **refused to plan**:
    it found the unanswered `BLOQUEA` and closed `HUELLA: nada — 5 decisiones
    sin resolver`. The journal accumulated both runs.

    That last one is the finding that matters: **the human-in-the-loop seam
    is a markdown convention, and an engine that never saw the skill obeys
    it.** So does the stamp — `read_stamp` parses Codex's JSONL with zero
    changes. Only `SESSION_RE` is Claude-shaped (Codex emits `thread_id`).

    Two things the test added to the scope: the **binary path must be
    configurable per engine** (the PATH had a stale 0.118.0 while the app
    shipped 0.147.0, and the user's default model only runs on the new one),
    and **each engine must declare its read boundary, not just its write
    one** — Codex's `-C` is a working root, not a limit, and it read the
    neighbouring repo nobody had mounted.

20. **`ENGINES`: the runner launches Claude or Codex, chosen per phase**
    (2026-08-16, same spec as decision 19). Built the day the validation
    passed, not before it. `phase_config` gains `engine`, `runs` gains
    `engine`, Settings gains a third selector, and `ENGINES` is the one place
    that knows how each CLI is spelled.

    Four properties are what make it small rather than a framework:

    - **The deliverable is a file**, so phases can be mixed freely: Phase 2
      never learns who wrote the analysis. This is the same property that let
      the two Phase-1 routes coexist.
    - **The slash command is Claude's spelling of the skill, not the skill.**
      Engines without a plugin get `PACK_HEADER` + `skill_body(phase)` — the
      same `SKILL.md`, inline, through stdin because a pack is 12 KB and
      Windows caps a command line at 32 KB.
    - **`HUELLA` needed no adapter; `session_id` did.** The stamp is the
      contract with the skills and parses both engines unchanged. The session
      is each CLI's own shape (`thread_id` in Codex), so a resume never
      crosses engines.
    - **Effort is per engine.** `max` is Claude's and Codex answers it with a
      400; `none`/`minimal` are the reverse. Each entry carries its own list
      and the UI reads it from `GET /engines` rather than keeping a copy.

    **What this does not fix, and it's worth writing down:** the read boundary
    is the engine's, not the runner's. Codex's `-C` is a working root — a
    verified run read the neighbouring repo and the parent's `CLAUDE.md` with
    nobody mounting them, which is what the multi-repo fan-out exists to
    prevent. Claude stays confined to `cwd` + `--add-dir`. Picking an engine
    picks its blast radius, and today that's a fact to know rather than a knob
    to set.

    **Verified end to end on 2026-08-17**, with `ORCH_CODEX_CMD` pointing at the
    real binary and a run launched through `POST /tickets/{id}/run`: `engine:
    codex`, `status: success`, `HUELLA: parcial — docs/tickets/R-1-analysis.md`,
    session captured from `thread_id`, and a journal holding all three attempts
    with their durations and the reserve line. That last part matters more than
    it looks: `JOURNAL_CLAIM` travels inside the pack and is obeyed, and
    `split_reserve` parses a ` · ` written by Codex.

    Also found by running it for real end to end: with the prompt on stdin the
    log held only the argv line, so it recorded that something was launched
    and not what was asked. The runner now writes the prompt into the log
    under its own heading. The test that was supposed to catch this passed
    because the fake echoed the prompt back — a fake being too helpful is a
    test asserting nothing.

## Phase 1 acceptance — closed on 2026-08-08

Run on ticket **3311** in the TMS repo, twice: with skill v0.1.0 and, after
fixing it, with v0.2.0. The file `docs/tickets/3311-analysis.md` was written
both times.

**The issue of the missing file is now explained, and it wasn't the skill.**
In headless mode, `--permission-mode acceptEdits` does **not** auto-approve
MCP tools: they get denied on their own and the agent is left unable to read
the work item. The orchestrator's runner wasn't passing `--allowedTools`. It
now does, with a test that pins it.

**What went well in v0.1.0** (verified against the real work item): all 15
acceptance criteria complete and in order; "What it asks for" faithful without
over-interpreting; deductions all tagged `DEDUCIDO`; parent #285 summarized
honestly ("has no description" ≠ "I couldn't read it"); the 2 comments with
their exact figures; and "Missing information" flagging itself honestly.

**What failed, and what was changed in the skill (v0.2.0):**

| Failure | Fix |
|---|---|
| `docs/quote-visibility-rules.md` and Bug #3271 listed **without reading them**, excused by the "1 level" limit — which only applies to `relations`, not to what the ticket cites in its text | Its own mandatory step (2.6) + a *Cited references* section in the template |
| Two figures from the repo **with no source and wrong**: "5 commits" (it was 12) and the 27% of baseline A.6 attributed to the full script | Second golden rule: every figure not from the work item cites `file:line`, a commit, or a command. Plus its own *State of the work in the repo* section, separate from what the ticket says |
| The template had nowhere to put comments even though step 2.2 requires reading them | A first-level *Comments* section; on contradiction, the most recent comment wins |

**v0.2.0 verification**: it read #3271 (pulled the cascade model and the
`QuoteVisibilityService.IsPricingOwnerMember` checkpoint) and the 121 lines of
`quote-visibility-rules.md` (6 display rules that condition v2, which v0.1.0
didn't have). All figures cite a source; the 27% is now attributed to A.6. As
a bonus it caught an internal inconsistency in `ESTADO.md` (states 179/179 in
one place and 144/144 in another).

## Second session — 2026-08-09

**The orchestrator completed the real cycle.** Project registration via API
with path validation (correct `400`/`409`), queueing, a run of **3322 in
5m33s** ending `analyzed`, and a live log. The subprocess argv was verified:
`--allowedTools mcp__azure-devops … --add-dir …Tenant --add-dir …TMS.wiki`.

**Phase 1 at n=2, and the prediction failed.** The worry was that the skill
would break on a Bug —its content lives in
`Microsoft.VSTS.TCM.ReproSteps`, not `System.Description`, and the format is
Repro/Expected/Actual—. It handled it fine: it pulled **5 explicit criteria**
out of a ticket whose `AC:` line is a single sentence, and correctly told
apart that load **16791**, cited in the text, is production data, not a work
item that needs opening. It also **contradicted the ticket's hypothesis with
evidence**: exception icons aren't gated by role
(`load-icon-exception.component.ts:21` only covers HotLoad), so the root
cause is in the backend.

**Redesign of the orchestrator's UI** (its own spec, see decision 10), in
response to "everything was on one screen and it wasn't intuitive." Also:
repos as a flat list with the primary marked by the user, editable project
name, a single registration button, and full width.

## Third session — 2026-08-10

**v0.3.0 passed its trial by fire.** Re-ran 3322 with the adjustment
instruction: **26 invocations with a path inside `ProvidenceTMSTenant`**
(previously 0), zero occurrences of "not inspected," 24 `.cs` files cited
versus 5. And it answered the question: the cutoff is at
`BaseProviderGroupService.cs:1559-1575`, where a client role that isn't
*pricing owner* has its `Audit`-category exceptions erased — and Rate Change
(311) is Audit. Mounting a repo isn't enough; **naming it in the prompt with
its label is.**

**Phase 2 built and validated on 3323** (*Carrier API V2 Migration - XPO*),
in four tasks with subagent review between each one. All three acceptance
criteria green on the second run: `openspec validate --changes` passes, 10 of
15 mirrors cite `file:line`, and **GetDocs appears under `## Blocked` with
zero associated tasks**.

The plan it produced has 21 tasks and 5 blockers, and **found two gateway
gaps that weren't in the analysis**, by comparing code:
`ApiRateService.V2.cs:103-108` forces `AuthType.Basic` with
`TokenUri: null`, so XPO's Rate would travel without a bearer token; and the
V2 Track adapter drops the `AuditTrackingResponse` that XPO's legacy code
**does** generate, documented as *"Gap B: verified equal"* because it was
evaluated against ABF, which doesn't generate it.

**3323 turned out to be a better candidate than 3320.** Its parent Feature
**#3319** carries a verified inventory with a *Definition of Done* per
carrier, and the pattern to replicate is already written twice in the repo
(`Carriers/Abf/`, `Carriers/Estes/`). The agent chose Estes as the mirror
instead of ABF —and it was right to: XPO is REST + OAuth like Estes, while
ABF has no token— and **read the 9 files it cites**, so the line numbers
aren't made up.

## Fourth session — 2026-08-10 (afternoon): per-phase progress, stamps and timeline

**The whole spec implemented**, with `subagent-driven-development`: 8 tasks,
21 commits (`4044a91..76f6f5d`) counting the final review wave and the visual
touch-up fix. Plan at
`docs/superpowers/plans/2026-08-10-avance-por-fases-y-timeline.md`, with all
53 checkboxes checked. Backend: **66 tests** (up from 18). Frontend: build and
lint green.

What exists now that didn't before: both skills close with `HUELLA:`; `runs`
stores `artifact_state` and `artifact_path`; `current_phase` is gone and
`tickets.status` is **computed** from the runs; `GET /tickets/{id}` returns
`fases`; there's an artifact viewer (`GET /tickets/{tid}/artefacto`) and a
`Timeline.tsx` that paints the journey with the artifact readable inside the
app.

**What cost the most wasn't building it, it was review knocking it down three
times.** The artifact viewer needed **three rounds** of fixing, each closing a
hole the previous one had opened: (1) an un-normalized `..` allowed reading
`.env` and `.git/config` from the client's repo and from sibling repos; (2)
while resolving paths to close that, a declared path that resolves to the
root became a wildcard (`HUELLA: ok — ..` is reachable); (3) the predicate
that fixed that merged two questions into one `any` and failed again with
nested roots (an `extra_dir` that contains the `repo_path`). Closed and
verified with **638 vectors** against the real endpoint —six root
configurations, NTFS junctions, ADS, 8.3 names, UNC paths and wildcards of
every spelling—: zero leaks, and the 30 legitimate cases keep working.

**The trial by fire passed.** Phase 1 was re-run on **3322** with plugin
v0.5.1, **8m14s**, and the whole journey closed outside the lab for the first
time:

- The agent stamped `HUELLA: ok — docs/tickets/3322-analysis.md`, with `/`
  and as the last line. The log has **6 matches of the stamp**: 4 are the
  skill's body filtered in (including the `parcial` example that mentions
  3323), and the real one is **190 characters** from the end. *Anchoring on
  the last match wasn't a theoretical precaution: without it, this run would
  have read a documentation example as if it were its own result.*
- The runner stored `artifact_state='ok'` and a clean path; the phase came
  out `ok`, the ticket folded to `analizado`, and **`Plan` unlocked on its
  own.**
- The viewer served the 28.6 KB document inside the app (200), and kept
  returning 400 to traversal attempts. The analysis stamps `ticket-agent
  v0.5.1`, so the file proves which version produced it.

**Visual pass done** (something that had been dragging since the 2026-08-09
redesign). One real defect: the timeline's rail was scoped to its row with
`bottom-0` and, on dimmed phases, was only 4px tall, so the journey looked
like loose circles right along the pending stretch. Fixed in `8f3e6a2`.
Console clean, no horizontal overflow, and dark mode legible — although
**the app has no theme switch**, so the `dark:` classes are an investment for
the future.

## Fifth session — 2026-08-10 (night): 3320 and the negative-claim failure

**Phase 2 reaches n=2.** 3320 (a *Bug*, "Ready To Pay" doesn't persist, parent
#827 with no description, **zero of its own comments**) ran end to end
through the orchestrator, reusing the existing project: Phase 1 in **4m11s**
(`HUELLA: parcial`) and Phase 2 in **7m59s** (`HUELLA: ok`). Change:
`openspec/changes/3320-ap-ready-to-pay-persistence`, 14 tasks in 7 groups and
3 blockers. `openspec validate --strict` **re-run by hand**: exit 0.

**The day's question had two expected answers, and a third one won.** It
didn't invent mirrors: the 9 `file:line` citations I verified land **exactly**
on what they claim to cite, in both repos. And it found the right mirror
where nobody had pointed it out — `ArApReceivableInvoice.cs:13-15`, AR's
`ReadyToProcessARBy`/`Date` pair, noting that AR's `Guid` is **not** nullable
and justifying the deviation in `design.md`. It also didn't stop at form: task
4.2 is "verify and **don't change**," and `## Blocked` inherits Phase 1's
reservation.

**But the negative claim turned out false.** Task 6.3 states *"No direct
mirror: there is currently no command test for AR/AP in the repo"* and warns
the implementer to pick a fixture. There is one:
`PTMS.Mediator.Tests/Load/Command/UpdateArReadyToProcessCommandTest.cs` — the
literal AR twin of the command to test, in the exact folder, and it **already
mocks `ISecurityService.GetUserIdentity()`**, exactly what task 3.1 needs to
stamp `ReadyToProcessAPBy`. The plan's best mirror, discarded.

The log explains why: **13 reads, none on a `*Test*.cs`**, and a single
search — `Grep "ForceReadyToPay|UpdateApReadyToProcessCommand"`. The AR twin
contains neither symbol, so **the pattern couldn't find it.** The
`ApGetListQueryTest.cs:297` citation is correct because it came from that same
grep with `-n`: citing from a grep is a legitimate source; **concluding an
absence from a grep is not.**

**The attachments branch is still unexercised, and now we know why.** Parent
#827 carries `AR AP V20241023 with notes.jpg`, but **inline in the HTML of
`System.Description`**
(`<img src=".../_apis/wit/attachments/<guid>?fileName=...">`), not as an
attachment under `relations`. The agent loaded `wit_work_item_attachment`'s
schema via `ToolSearch` and **never called it**: it had no id to pass. It
declared it unread in the reservation instead of making up the content.

**The stamp contract held again, barely.** Phase 2's log has **11** matches of
`HUELLA:` and the real one is **211 characters** from the end; Phase 1's, 6
and 304. Ten decoys in a single run. The viewer served `tasks.md` **under the
declared directory** (200), rejected the directory itself (400, not a regular
file), and kept rejecting traversal to `.env` (400).

**First real `parcial` in production.** Phase 1 closed with a reservation —
missing `.claude/ticket-agent.json` in the Tenant (it assumed
`project: ProvidenceTMS`), and #827's comment and image left unread— and the
reservation carried through to Phase 2's `## Blocked`. The full chain worked
without touching it.

### The fix, and the re-run with a known answer

**Rule 5 in `change-planning`** (plugin **v0.5.2**): *saying "doesn't exist"
is a claim, and it needs a source just like a figure does*. It's stated in
three places — the golden rule, a step in §4 that requires **searching by
relation** (if you touch AP, search AR; if you touch a command, search the
sibling command's test) and the edge case, which now requires **naming the
search in the task itself**. The example inside the skill is the real
failure: `Grep UpdateApReadyToProcess` can't find
`UpdateArReadyToProcessCommandTest.cs`.

Prep so the trial would be clean: the v1 change was moved out of the repo (it
remains as evidence outside `openspec/changes/`) and the
`.claude/ticket-agent.json` that was missing in the Tenant was created.
`claude plugin update` applied 0.5.2 without a TTY — the cache is keyed by
version folder.

**Re-run (5m41s, `HUELLA: ok`, `validate --strict` exit 0): the rule worked.**
Where v1 declared "there is no AR/AP command test," v2 cites
`UpdateArReadyToProcessCommandTest.cs:1-94` and backs the negative claim with
`Glob **/*ReadyToProcess*` → 3 files. Verified: the file has exactly **94
lines** and the glob returns **exactly 3**. This isn't box-checking — the
Angular spec's task cites **three** searches to support a positive and a
negative claim at once, and its three counts (1 spec under `pages/loads`, 0
under `load-ar-ap`, 0 under `*ar-ap*`) are exact. The log confirms it:
**7 `Glob` invocations versus 0 in v1.**

**What the fix doesn't explain.** v2 switched to an entirely different
strategy —5 tasks instead of 14, frontend only, and the new column +
migration moved to `## Blocked` for needing a business decision and not
fitting `Custom.EstimatedBugHrs`'s 2-hour budget—. That's **variance between
runs, not an effect of the rule**, which only touched the negative-claim
piece. Worth noting so as not to credit the fix with improvements it wasn't
designed to make.

**And along the way, the day's finding.** v2 brought **AR** auto-marking into
scope, which v1 had explicitly declared out of scope: it triggers
`UpdateArReadyToProcessCommand.cs:36-43`, which stamps `ReadyToProcessARBy`
with the identity of whoever **opened the screen** and sets `BilledOn = today`
if it was empty. Verified in the code. Opening the tab misattributes
authorship and billing date — that's no longer just a checkbox that doesn't
persist, and it's not in the ticket.

## Sixth session — 2026-08-11 (early morning): Phase 2b, and the agent writes code

**Built entirely with `subagent-driven-development`**: 8 tasks, 21 commits,
backend from 118 to **125 tests**. Spec at
`2026-08-10-fase-2b-del-plan-al-codigo-design.md`, plan with its checkboxes.
What exists now: the `implement` phase across the four tables, the
clean-tree guard, a per-ticket branch created **under the lock**, a hook that
denies push and PR delivered via `--settings`, the `change-implementation`
skill, and the branch visible in the timeline.

**The trial by fire passed, on 3332** (*Carrier API V2 Migration - Dayton*,
backend-only; the frontend was left out at the user's request, since they had
work in progress there). Full chain in one night: analysis `parcial` → plan
`ok` with 19 tasks → **implementation `ok`, 19/19 tasks, 17 commits, 83
minutes**. The ticket folded to `implemented`.

Verified, one by one:

- **The branch was prepared under the lock** and landed in `runs.branch`:
  `ticket-agent/3332`. The repo stayed on it and never left the machine:
  **zero hook denials**, because the agent never tried to push.
- **Not a single leak across 17 commits.** Zero files from `.claude/`,
  `.opencode/`, or `docs/tickets/`. Of 31 files touched, 29 are code and
  tests (8 new or extended test files) and 2 are the change's own ledger and
  a findings note. The rule of committing specific paths —something only a
  markdown file enforces— **held up in a client's repo.**
- **One commit per task**, with its number and subject: `3332 tarea 5.2: crear
  DaytonTenderCall V2 y traducir los accesoriales…`. The `git log` is the
  record, as designed.
- **The stamp**: 8 matches in a 3.72 MB log, the real one 225 characters from
  the end.
- **The viewer** served the 21.5 KB `tasks.md` and kept returning 400 to
  traversal.

**And the design's expensive part earned its price live.** In task 5.2 the
main agent detected that its subagent had touched `CarrierCallBase.cs` — a
file shared by **every** carrier — and, instead of accepting the diff,
verified that the change is equivalent for any carrier that doesn't override
`MapError`, before committing. A blast radius that an isolated task can't
see, caught by the review between tasks.

### What cost the most wasn't building it

**Seven rounds of fixes across eight tasks, and five of the failures were in
the plan I wrote:**

| Where | The failure |
|---|---|
| Task 2 | The regex denied `git commit -m "… git push …"`: it matched the substring anywhere |
| Task 3 | The `_app()` helper didn't isolate the import: `init_db()` wrote to the **real** DB and logs |
| Task 6 | The "validate all before touching any" invariant wasn't protected by any test |
| Task 8 | It was impossible while touching only the file the plan specified: `branch` travels in `runs`, not in `fases` |
| Final review | **The runner's prompt said the opposite of the design** |

The last one is what justifies reviewing the whole branch. The extra-repos
block wasn't branched by phase, so in `implement` the agent read that mounted
repos are *readable* and that the deliverable goes to the primary one —the
opposite of decision 4— and the skill, to break the tie, says **follow the
prompt**. No per-task review could have caught it: one task writes the
prompt and another contradicts it.

**Four placebo tests**, all four exposed by mutating the code. The worst one
let `PreToolUse` be swapped for `PostToolUse` —the hook would run **after**
the push, with `exit 2` already useless— and the 118 tests stayed green. The
milestone's only containment mechanism wasn't held in place by anything.

## Seventh session — 2026-08-11: the forms, and twelve defects in my own plan

**Second round of "it isn't intuitive."** The first (2026-08-09) fixed navigation;
this one fixed the **forms and the feedback**, which that round left untouched. Spec
`2026-08-11-rediseno-formularios-y-presentacion-design.md`, plan with its 58
checkboxes, executed with `subagent-driven-development`: **11 tasks, 3 internal
phases, 33 commits, 16 files, +3086/-236**. Backend from 133 to **153 tests**.
Frontend build and lint green at their exact two-warning baseline.

The user is a **technically competent but occasional** colleague: they know what a
repo path is, but not whether it takes `/` or `\`. That ruled out both tempting
answers — simplifying the vocabulary, and building a wizard. The principle that
replaced them extends 2026-08-09's lesson from space to time: *the answer has to
arrive when the decision is made, not at the end.*

What exists now: the project form is its own view with paths validated on blur
(`POST /rutas/validar`); `Guardar` is never greyed-out-and-silent; deletes confirm;
repos are visible in the list instead of hiding in a `title=`; tickets carry a title
read from their analysis; the ticket list has its three-dot stepper back; `guards`
and `pr` are gone; and a running `implement` shows "tarea 7 de 19", counted from the
checkboxes in the plan's own `tasks.md`.

**Zero new dependencies.** Confirmations run on the native `<dialog>` (focus trap,
Escape, `::backdrop`, `inert` — all free), validation is a 15-line function instead
of `zod`, and errors stay where they happened instead of a `sonner` toast that
vanishes. `shadcn add alert-dialog` exists because Radix targets browsers this app
never runs in.

### The finding that matters more than the feature

**Twelve defects were found in my own spec and plan. My self-review found none of
them; the review loop found all twelve.** They sort into three kinds, and the sort
is the useful part:

| Kind | Count | Example |
|---|---|---|
| The document contradicted itself | 4 | Global Constraints said "code in English"; the code blocks used Spanish test names. Interfaces claimed Task 5 consumed two helpers; the `App.tsx` I wrote in that same task imports neither. |
| The document was simply wrong about the code | 5 | `id="campo-repos"` on a `<div>` — a div without `tabindex` cannot take focus, so the "focus the first missing field" requirement was a silent no-op. A `validate()` that let a payload reach a backend that rejects it. An `aria-hidden` justified by a badge that doesn't say what the dots say. |
| The document promised something that shouldn't happen | 1 | D5 said the global `error` in `App.tsx` disappears. It didn't, and shouldn't: ticket create/run/delete failures have nowhere else to go. The implementation was right and left the reasoning in a comment. |

Plus two **omissions** — nothing written was wrong; something needed was missing.
Those are the interesting ones, because no review of a single task could see them:

- **Task 4 built an unsaved-changes guard; Task 5 wired the route around it.** Type
  in the project form, click another project in the sidebar, and the typed data was
  gone with no warning — while `Cancelar` and Escape both warned for the identical
  situation. Each task was correct alone. *The gap lived only between them.* This is
  the third time this project has learned that the gaps live in the seams.
- **A `try/except OSError` nobody proved fires.** The reviewer rejected the
  implementer's "low-risk defensive code" framing by asking *when this function
  actually runs*: while `implement` rewrites the same `tasks.md` it reads, polled
  every 3 seconds across an 83-minute run. A real TOCTOU window, not a device-file
  curiosity.

### And the one that should be framed

**The test I wrote to close a coverage gap was itself a placebo.** `pathlib`
collapses repeated separators at construction, before `resolve()`, so `Path("a//b")`
and `Path("a/b")` are the same object: with the `.rstrip("/")` deleted, my end-to-end
assertion still passed. The implementer caught it in the mutation step, overrode my
instruction, and rewrote it to spy on the string handed to `declared_file_or_none` —
the only level where the mutation is observable. The re-reviewer then verified the
deviation was right rather than accepting it.

Nine placebos found before this session, and the tenth was in the fix for one.

### What went right, and is worth repeating

- **The path guard survived its extraction.** `declared_file` had to move out from
  under `/artefacto` so the title reader and the progress counter could reuse it —
  the one change in this plan where a subtle difference is a security hole, not a
  bug. Rule given: *move, do not rewrite.* Result: **73 of 74 lines byte-identical**,
  the single change (`(tid,)` → `(t["id"],)`) provably equivalent, and the two
  ordered `any(...)` calls that are the round-3 fix neither collapsed nor reordered.
  The 638 vectors kept running **against the endpoint**, because a test that only
  exercises the extracted function doesn't prove the endpoint uses it.
- **The reviewer proved fidelity instead of inspecting it.** In a unified diff every
  line with a leading space is byte-identical by construction, and the whole guard
  travelled as context. For the gap git didn't print it closed the offset arithmetic
  (923/926 → 945/948, constant +3). That's a proof, not a reading.
- **Telling reviewers the brief is not a trustworthy oracle changed what they
  found.** After the third plan defect, every review prompt carried the running
  count. A reviewer who assumes the document is right can only find transcription
  errors.
- **Substituting verifications a subagent cannot perform.** Half the plan's steps
  ended in "check it in the running app". Replaced, each time, with something
  provable by reading: element-by-element markup comparison against `git show` of
  the pre-extraction file; a grep for dead props that still typecheck; hand-traced
  accessible names; hand-computed bar widths.

## Eighth session — 2026-08-12: a second org, TDD in the plan, and the multi-repo design

Three things happened, in this order.

**A second Azure DevOps organization works, with a token.** `.mcp.json` now passes
`--authentication ${ADO_AUTH:-azcli}`: unset, everything behaves as before; set to
`envvar`, the MCP reads a PAT from `ADO_MCP_AUTH_TOKEN`. Verified end to end against
`cr360dev` — server started with the flag, work item 44647 of "CallRevu Development
Lifecycle Management" read over stdio. A legacy `<org>.visualstudio.com` account
resolves as `dev.azure.com/<org>`, and a project name with spaces travels verbatim.
The full mode table lives in the plugin's README; `CLAUDE.md` carries the mechanism.

**Phase 2's `Check` became `Test` + `Check`, and 2b reviews with a second subagent.**
The plan had ordered TDD in the planner's voice while the implementer never heard it
— a task ordering "run a test that doesn't exist yet" fails twice and stops the plan.
Now the plan names the test file as a deliverable of the task, and 2b orders the
subagent red first. Three findings that shaped the rest: an invented `--filter`
matches no test and **exits 0** (hence `Check: manual — ...` as a declared escape
hatch); green can be re-run by the driver but red cannot, so a report with no red
output commits as `unverified` rather than being counted as proven; and the per-task
review moved out of the driving agent, which was reviewing its own instruction.
Findings are graded, and only `critical`/`important` block — a review that can stop a
plan on taste stops it for good. What doesn't block lands in `## Review notes` in
`tasks.md`, because a summary in chat dies with the session.

**The multi-repo design, written up in full.**
`docs/superpowers/specs/2026-08-12-multirepo-fanout-y-humano-en-el-bucle-design.md`.
It starts from a verified fact: `--add-dir` loads a repo's skills and agents but
**not** its `CLAUDE.md`, hooks or `.mcp.json`. So a ticket across front and back is
written today under the primary repo's rules, confidently and undetectably. The
design splits Phase 1 into one session rooted per repo and consolidates, with the
cross-repo contract as the deliverable no single repo could produce. It also turns
the seams between phases into marked decision points, and makes session continuation
a human choice — `-p --resume --fork-session` was verified working headless, and the
`session_id` is already in today's logs.

## Ninth session — 2026-08-13: the design built, and measured on a real ticket

The 16-task plan executed end to end and merged to `main` (13 commits ahead of
`origin`, unpushed). Plugin **v0.9.0**, **199 tests green**, build and lint clean.

**What shipped.** Six launchable phases where there were three, in two routes to the
same file. The runner gained the routing parser, the sequential fan-out with one
child per repo, `session_id` capture and `--resume --fork-session`, and
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` in `implement`. The plugin gained
three skills (`ticket-brief`, `repo-survey`, `analysis-consolidation`) and the
`DECIDIR`/`BLOQUEA` markers in the three that existed — which finally give `autonomy`
something to govern. The UI gained the decision counter and the fresh-vs-continue
radio.

**The measurement, which is the part that matters** (detail in section 15b of the
design). Ticket **3320**, two real Providence repos, three phases run for real:

- The survey rooted in the **secondary** repo located the root cause with `file:line`
  — `ap-invoice.component.ts:269-273` re-derives and re-persists the flag on every
  load. **It isn't in the primary repo**, where a single session would have hunted,
  and the `tenant` survey separately confirmed the backend persists correctly. The two
  halves only mean something together.
- The contract table caught a **⚠️ same concept, two names**: the two surveys name the
  same read endpoint differently, with different DTOs, and it changes which file gets
  touched. Each survey is internally coherent; the defect exists only when they're put
  in adjacent columns.
- The brief's central ambiguity resolved **without a human decision**, and a whole
  branch of work discarded.

**Two bugs no test double had found**, both of the same kind — information the design
assumed was transmitted and the runner never transmitted — and both failed in the safe
direction:

1. The prompt never named the **primary** repo. The agent knew the extras by label and
   invented one for the repo it was standing in: it wrote `SONDEAR: main, tms` when the
   label was `tenant`. The parser rejected `main`, voided the line and **widened to
   every repo** — the optimization was lost, never the correctness. §4.4's safety net
   did exactly what it promised.
2. **`consolidate` couldn't reach the surveys.** Neither mounted nor named: the only
   phase whose entire job is reading them was launched blind.

**Three placebo tests of my own, rewritten until their mutation breaks them**: the
chunk-boundary one (`FAKE_BIG` printed padding *after* the id), the failed-child one
(the exit code decided the verdict, not the log slicing it claimed to test), and the
routing parser's.

**And the docs were lying about the shape.** The root `README.md` said "Phase 1" and
didn't mention `apps/orchestrator/` at all — half the repo. `CLAUDE.md`'s phase table
listed three commands. `how-it-works.md` was stale for a reason that predates this
session: it described how a per-phase model *would* be built, days after it shipped.

## Décima sesión — 2026-08-14: la solicitud sin ticket, y el journal

Plan de 7 tareas ejecutado completo (6 de implementación + esta, la de
documentación). Plugin **v0.10.0**, **217 tests backend** (eran 199 al cerrar la
novena sesión: 18 nuevos, uno por cada comportamiento de la lista de verificación
del diseño), build y lint sin cambios en la línea base (dos warnings, los mismos de
siempre, en `badge.tsx` y `button.tsx`). Rama `feat/solicitud-sin-ticket`, sin mergear
a `main` todavía.

**Qué se construyó.** Dos formas de entrar a la etapa 1 sin que la 2 y la 3 se
enteren — exactamente la misma garantía que ya sostenía las dos rutas de fase 1 entre
sí. `POST /tickets` acepta `{ado_id, project}` o `{request, project}`, XOR estricto;
una solicitud acuña su propia llave `R-<rowid>` del `lastrowid` de su fila, y esa
llave reparte el espacio de nombres con el modo solo-plugin: el orquestador solo
acuña números, un humano tecleando sin orquestador elige un slug — la colisión entre
los dos es imposible sin coordinar nada (diseño §3.1). El runner proyecta la
solicitud a `docs/tickets/<id>-request.md` en el repo primario, solo antes de
`analyze` y `brief`, reescrita desde la BD en cada corrida; el MCP se queda encendido
—se consideró quitarlo y se descartó, porque una solicitud puede citar un work item
real— y quien niega el work item principal es el prompt (`REQUEST_PROMPT`), no una
resta de herramientas. Dos skills (`ticket-comprehension`, `ticket-brief`) aprendieron
la rama por llave `R-` — el disparador es la llave y la existencia del archivo, no un
bloque que solo el runner inyecta, que es lo que hace que el modo solo-plugin
funcione sin nada del orquestador (§4.4, §4.6). Y `analyze` en modo standalone acepta
prosa directa: deriva su propio slug, escribe su propio archivo, sigue.

**El journal es la pieza nueva que no estaba en el pedido original del humano y
terminó siendo la mitad del cambio.** `docs/tickets/<id>-journal.md`, para tickets de
Azure y solicitudes por igual: `## Corridas` la escribe el runner —cuatro sitios de
escritura, tres retornos tempranos más el cierre principal, con inserción antes del
encabezado `## Hallazgos` para que esa sección siga creciendo por el final— y
`## Hallazgos` la alimentan las skills con lo que encuentran fuera del alcance de su
propio entregable. `JOURNAL_CLAIM` le dice a la skill que el runner ya se hizo cargo
de `## Corridas` en esta corrida, para no duplicar la línea; sin runner —sesión
interactiva, plugin solo— la skill escribe la suya. Un test verifica que ninguna fase
lo lee como insumo: registro, nunca autoridad.

**Una desviación del diseño, decidida al planificar y no anotada en el spec original
hasta hoy:** `repo-survey` no recibió la misma instrucción de journal que las otras
cinco skills. Un hijo del fan-out monta solo su propio repo más un scratch dir —nunca
el repo primario, por diseño, para no filtrarle configuración— así que no tiene cómo
escribir en `docs/tickets/<id>-journal.md`, que vive en el repo primario. Sus
hallazgos van al survey bajo `## Hallazgos fuera de alcance`, y es
`analysis-consolidation` quien los traslada al journal cuando cierra. Corregido en el
spec, §9, en esta misma sesión.

**Nada de esto corrió contra un ticket real todavía.** Los 217 tests backend, el
build y el validador del plugin son verificación mecánica —confirman que el mecanismo
hace lo que dice que hace— pero ninguna solicitud vaga pasó por la ruta de fan-out
para ver si el análisis vuelve con `DECIDIR` honestos o con alcance inventado, que es
el riesgo que el propio diseño señala como el único que no cierra por construcción
(§6). Tampoco se probó el modo solo-plugin de punta a punta en un repo real fuera de
este hub — todo lo verificado hasta ahora es lectura de código y tests, no una sesión
interactiva real tecleando `/ticket-agent:analyze R-algo` sin el orquestador de por
medio.

**Documentando salió una corrección al propio `CLAUDE.md`:** decía que un cambio de
skill exige bumpear la versión «en dos lugares». Son tres — `plugin.json`, el sello de
la plantilla de análisis en `ticket-comprehension/SKILL.md`, y el sello de la plantilla
de recolección en `ticket-brief/SKILL.md` (`**Collected:** <date> by ticket-agent
vX.Y.Z`), que faltaba en el texto y se descubrió recién al implementar la tarea 5 de
este plan. Corregido.

## Immediate pending items

- [ ] **A first real run of a vague request through the fan-out route.** Every check
  so far is mechanical (217 backend tests, build, lint, the plugin validator) — none
  of it exercises the two new rules in §4.4 of the request design (`DECIDIR` for
  what a request doesn't say, proposed acceptance criteria, never invented ones).
  The question the design itself names as unclosed (§6): does the analysis of a
  vague, freely typed request come back with honest `DECIDIR`s, or with invented
  scope that reads with the same confidence as one derived from a work item?
- [ ] **An end-to-end test of the plugin-only mode in a real repo.** Everything
  verified for the standalone path (`R-<slug>` keys, `analyze` deriving its own slug
  from prose, the journal's run line written by the skill instead of the runner) was
  verified by reading code and running tests, never by an interactive session
  outside this hub typing `/ticket-agent:analyze R-algo` with no orchestrator
  involved.
- [x] ~~**Execute the multi-repo plan**~~ — **done 2026-08-13, all 16 tasks**, plugin
  v0.9.0, 199 tests green. Task 16 ran against **3320** with two real Providence repos:
  the survey rooted in the **secondary** repo located the root cause
  (`ap-invoice.component.ts:269-273` re-derives and re-persists the flag on every
  load) — which is **not** in the primary repo, where a single session would have
  hunted. The contract table caught a "same concept, two names" between the two
  surveys that is invisible from either alone. Full measurement in section **15b** of
  the design. Two bugs only a real run found, both fixed with tests: the prompt never
  named the primary repo (the agent invented `main`; the parser widened to every repo,
  so the safety net held) and `consolidate` couldn't reach the surveys.
- [ ] **The next two-repo ticket: copy the analysis before running the fan-out.**
  Both Phase-1 routes write `docs/tickets/<id>-analysis.md` by design, so
  `consolidate` overwrote 3320's single-session analysis and the side-by-side
  comparison is gone for that ticket. It was untracked, so git doesn't have it either.
- [x] ~~**`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` in `implement`**~~ — done
  2026-08-13 as task 1 of the plan, gated on `extras`.
- [ ] **Rotate the `cr360dev` PAT.** It was pasted in a session transcript on
  2026-08-12 to verify the token path. It worked; it should not survive. Setup notes
  for that org, credential-free, are in `docs/cr360dev.md`.
- [ ] **Push `main`.** 13 commits ahead of `origin/main` and nothing sent. One of them
  predates this work (the how-to-run-the-app doc).

### What the multi-repo work left open

Ordered by how much the next real run would gain from it. None of these block using
what shipped.

- [ ] **Nobody has planned or implemented a multi-repo ticket.** 3320's analysis is
  written and carries the contract table, but `plan` and `implement` have never
  consumed one. The table names an `⚠️ same concept, two names` the plan has to
  resolve **before** it can order tasks across repos — the first real test of whether
  the contract is usable or merely readable. This is the highest-value next step.
- [ ] **Separate "rooted" from "one whole session per repo".** The design's gain is
  measured, its cause isn't: how much comes from the session loading that repo's
  rules, and how much from simply devoting a full session to each. Running the same
  ticket with `analyze` plus `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` would
  split them. It doesn't change the decision — hooks and `.mcp.json` are recovered by
  nothing else — but it says how much is being paid for how much.
- [ ] **The parallel fan-out, and only if a run gets slow.** Sequential was chosen so
  the global lock keeps meaning something, one log preserves live progress and `runs`
  needs no schema change. With 4+ routed repos the wall-clock may justify a
  `parent_run_id`. Nothing measured yet; don't build it before something hurts.
- [ ] **Survey scratch accumulates.** `logs/<run_id>/` is never cleaned — deliberate,
  since deleting is the footgun and a re-run must never read a stale survey. It'll
  need a retention policy eventually, not now.
- [ ] **The children can't see each other, by design.** A survey states what it
  expects from another repo and only the consolidation resolves it. If real runs show
  the consolidation repeatedly answering questions a second survey pass could have,
  the answer is a second round — not letting children talk, which would reintroduce
  the shared context the split exists to remove.
- [ ] **`design` and `implement` still carry MCP they may not need.** Their skills
  consume the previous phase's file, not the work item. Dropping them from `PHASE_MCP`
  is a real reduction in surface, and it needs one live run of each to confirm — it
  wasn't this change's job.
- [ ] **A fan-out phase can't be continued.** It drives several sessions and there's
  no single one to resume, so `puede_continuar` is false for `survey` by construction.
  Fine today; if continuing one child ever matters, `runs` needs to model children.
- [ ] **`--resume` against a session deleted from disk** (`claude rm`, a cleaned
  `~/.claude`) fails and the run closes with no stamp. The CLI's error is in the log,
  which is where it's read. Probing the session store to pre-empt it isn't worth it.
- [ ] **Read the 2658 lines that 3332 left on branch `ticket-agent/3332`.**
  Nobody has looked at them. The run came out `ok` because the build is
  green and the boxes are checked, but that measures that the mechanism
  worked, **not that the code is good** — it's a close cousin of a placebo
  test. Reviewing it against the Estes and ABF pattern is what tells us
  whether 2b is usable for real work or only for demos, and it determines
  whether the last mile is worth building.
- [ ] **Recreate tickets 3322 and 3323 in the orchestrator.** They were lost
  with the DB (see "The DB wipe"). Their artifacts still live in the target
  repo; their run history doesn't come back.
- [ ] **Verify writing to an `extra_dir`.** Decision 4 of the 2b spec still
  hasn't been exercised: 3332 is single-repo. A ticket whose code lives in a
  mounted repo is needed —**3320** is one— with the frontend free. It's the
  one big assumption of the phase still unproven live.
  **Closer than it was** (2026-08-13): 3320 now has a multi-repo analysis naming the
  root cause in `ProvidenceTMS`, so planning and implementing it exercises this
  assumption and the "has anyone planned a multi-repo ticket" one in a single run.
- [ ] **Report the AR finding to the team.** AR auto-marking stamps
  authorship and `BilledOn` on opening the screen
  (`UpdateArReadyToProcessCommand.cs:36-43`). It's a data-integrity defect
  that **isn't in any ticket** and came out of planning 3320. Deserves its
  own work item; decide who opens it.
- [x] ~~**Negative-claim rule in `change-planning`**~~ — done 2026-08-10,
  plugin v0.5.2, and **verified on re-run**: the task that used to deny the
  mirror now cites it with its `Glob`.
- [ ] **Attachments embedded in HTML.** The skill mandates downloading what
  hangs off `relations`; images pasted into the description carry their GUID
  in the `src` and today nobody mines that. It's the concrete reason the
  attachments branch is still unexercised (#827 is the test case).
- [x] ~~**Second ticket for Phase 2, and make it 3320**~~ — done
  2026-08-10. Result in "Fifth session": doesn't invent mirrors, but declares
  absences without searching for them properly.
- [x] ~~**Visual pass on the UI**~~ — done 2026-08-10 with the
  chrome-devtools MCP, once the browser freed up. One real defect (the
  timeline rail), fixed.
- [ ] **Decide what to do about `Bash` in the runner.** See "Lessons
  learned": the specifier doesn't scope it. Today `analyze` runs with an
  empty list, but Phase 2 effectively has Bash available for more than
  `npx`.
- [ ] **Remove `organization` from `.claude/ticket-agent.json`** — it
  duplicates `ADO_ORG`, which can't be removed because the MCP needs it as an
  env var at startup.
- [ ] **Add a theme switch to the UI.** The dark palette is complete and its
  contrast verified (WCAG AA ratio against `#0a0a0a`), but today it can only
  be reached by forcing the `.dark` class by hand: there's no way to get
  there from the app. The 2026-08-11 redesign explicitly declined to smuggle
  it in.
- [ ] **Show the redesign to the client who asked for it.** Nobody has used any
  of it yet: the whole 11-task branch was verified by tests, builds and reading,
  never by a person clicking through it. That measures that the mechanism works,
  not that the screens are intuitive — the same trap as a test that passes
  because of its setup, and precisely what this branch was built to fix.
  **That verdict is what says whether the second round of "it isn't intuitive"
  landed.**
- [ ] **Extract a shared `ErrorBanner`.** The dismissible banner markup is now
  duplicated verbatim in `App.tsx`, `Projects.tsx` and `ProjectForm.tsx` — 12
  lines × 3, focus-ring classes and `aria-label` included. A classic seam
  artifact: each task added its copy correctly and no task owned the third.
  Deferred by the final review, not forgotten.
- [ ] **Two small holes the final review named and deferred.** `RepoTable`'s
  `key={r.path}` collides if two repos share a path — reachable, since nothing
  in `validate`, `check_dirs` or `split_repos` rejects duplicates, though the
  blast radius is a React console warning in a read-only table. And the
  `disponible: false` contract (`phases_for`'s branch, `canRunPhase`'s branch,
  `Stepper`'s filter) is now unreachable code kept **on purpose** — it is the
  seat `guards` returns to — but nothing tests that it still works when a phase
  is re-declared.

- [x] ~~**Model and effort per phase**~~ — done 2026-08-11. `phase_config`
  table + Settings → "Model per phase" in the UI; the runner adds
  `--model`/`--effort` when launching, read on every run so it doesn't
  depend on restarting the backend. Empty = whatever the target repo's CLI
  resolves to, which is how everything ran until today. In the plugin
  **there is no equivalent knob**: skill and command frontmatter has no
  model field, only subagents do — hence `subagent_model` in
  `.claude/ticket-agent.json` (plugin v0.7.0), which applies to 2b's
  per-task subagents and nothing else.

**Minor debt noted** (none blocking):

- The log is read in full just to keep the last 4 KB (`read_stamp`) and the
  last 8 KB (`log_tail`). Today they weigh hundreds of KB; with MB-sized logs
  this will need a `seek` from the end.
- The `assert` that matches up the keys of the four phase tables disappears
  under `python -O`.
- Every `success` run is painted with the "analyzed" color in history, even
  when its phase is red for not having declared a stamp. Confuses with
  pre-contract data.
- `read_stamp` doesn't unescape JSON quotes inside a path; an empty
  reservation (`ruta · `) leaves the path with the middle dot stuck to it.
  Both cosmetic, no consequences.
- Theoretical TOCTOU in the viewer between `is_file()` and `open()`. A single
  local user and the only writer is the agent itself; worst case is a 500.
- `canRunPhase` duplicates the block-reason text from `blockReason()` in
  `status.ts`.
- Plans from earlier sessions have unchecked boxes (`fase-0-1`: 15/20,
  `orchestrator`: 31/32, `fase-2`: 30/32) despite being closed.

## The orchestrator DB wipe (2026-08-11)

**The database and all run logs were lost.** It wasn't a code bug: while
reviewing Phase 2b's Task 3, the instruction given to the reviewer literally
said *"delete `orchestrator.db` and the `logs/` directory"* to confirm the
tests no longer polluted the real disk. And that was the real DB — `DB_PATH`
hangs off `BASE`, which is `app.py`'s own folder, so it doesn't depend on the
working directory. It's in `.gitignore`: there's nothing to recover from git.

What was lost: the project, tickets 3322/3323/3320 and ~10 runs with their
stamps and timings, plus **all the logs**. What survived is what mattered:
the analyses and changes are in the target repo, and the measurements are
written here and in the commit messages.

**The lesson isn't "be careful."** It's that a verification instruction that
says to **delete** something has to name a disposable directory, never a
production path. The very bug being verified —tests writing to the real
disk— proved that path was live.

## Lessons learned (2026-08-11, early morning)

- **Mutating the code is the only reliable way to know if a test tests
  anything.** Four placebos in a single milestone, and none of them showed up
  from reading: the hook's test passed with `PostToolUse`, the guard's test
  passed with the check mixed in, the branch's test passed without
  `refs/heads/`. The question *"what would have to break?"* is good for
  writing the test; **actually breaking it** is what proves it. There's now
  a mutation table in the final wave's report.
- **Fixing one finding opened another, three times out of three.** Anchoring
  the regex closed the false positives and let `then git push` slip through;
  isolating the tests put the DB inside the repo under test and created a
  new placebo. **Every round of fixing needs its own re-review**, and the
  re-review has to look for what the fix broke, not just whether it fixed
  something.
- **The prompt is part of the contract, and nobody was reviewing it.** The
  design, the skill, and the code said the right thing; the text the runner
  injects said the opposite. It lived in a different task from the one that
  defined the rule, so no per-task review ever crossed it. The gaps keep
  living in the seams: this is the second time this project has learned
  that.
- **A plan is a hypothesis, and this time it was measured**: five of its
  blocks turned out wrong. The plan's header now flags which ones, with
  "the code wins." A plan that teaches code known to be wrong is a trap for
  whoever reads it next.
- **The expensive ceremony paid for itself.** One subagent per task with diff
  review seemed like overkill for an untested phase. It caught a change to a
  file shared by every carrier in a client's repo. With a linear loop, that
  diff would have been committed without anyone looking at it.

## Lessons learned (2026-08-10, night)

- **A negative claim is a statement, and it needs its source just like a
  figure does.** The golden rule "every citation carries `file:line`"
  disciplines what the agent **does** find; nothing disciplines what it
  declares **absent**. 3320 cited nine exact mirrors and failed on the one it
  didn't cite: it said "no AR/AP command test exists" after a two-symbol
  `Grep` that the file being searched for doesn't contain. **An absence is
  only as good as the search that backs it**, and the skill didn't require
  that search or require it be named.
- **The failure came from the safe side, which is why it goes unnoticed.**
  Inventing a mirror produces a fake `file:line` that any check knocks down.
  Declaring "no mirror" produces a cautious-sounding warning that **nobody
  is going to verify** — it reads as honesty. The cost isn't a visible error
  but duplicated work for the implementer.
- **The honest output worked; what failed was the premise.** The two
  hypotheses were "invents mirrors" or "declares pending research." The
  second won **on wrong data**, which wasn't in the pool of expected
  outcomes. Worth noting the shape of it: a mechanism can fire correctly on
  a false input, and the stamp doesn't notice because the stamp measures
  deliverable, not truth.
- **A poor ticket doesn't produce a poor plan.** 3320 has no rich parent, no
  *Definition of Done*, no pattern to copy — and the plan came out with more
  verified mirrors than 3323's. It manufactured its own material, cross
  referencing AP against AR: the repo's own symmetry stood in for a parent.
- **Fixing the rule fixed the rule, and nothing more — and it's worth saying
  so.** The re-run came out better on several axes (tighter scope, a new
  defect found), but the edit only touched the negative-claim piece.
  Crediting those improvements to the fix would be exactly the mistake this
  project has been hunting for five sessions: **a good result doesn't
  validate the change that preceded it.** What the fix demonstrates is what
  was measured — the negative claim, with a known answer in advance.
- **A test with a known answer beats run number three.** Before re-running we
  already knew which file had to show up. That turns a 6-minute run into a
  verdict instead of another story to interpret. Whenever it can be set up
  that way, set it up that way.

## Lessons learned (2026-08-10, afternoon)

- **A green test isn't proof; sometimes it's an alibi.** **Five** placebo
  tests came out, all with the same shape: the setup can't produce the
  failure the test claims to prevent. The stamp-anchoring test passed just
  the same with `hits[0]` because `json.dumps` escaped the em dash to `—`
  and the decoy stamps never matched. The path-traversal battery mounted a
  declared **file**, against which traversal is impossible by construction
  — the dangerous case (a declared directory) wasn't touched by any of the 8
  tests, which is why 50 tests passed green with a hole that let `.env` be
  read. `test_current_phase_ya_no_existe` ran against a freshly created DB,
  whose `CREATE TABLE` never had that column, so it never exercised the
  `DROP COLUMN` it claimed to protect. **The question that exposes them:
  what would have to break for this test to fail?** If there's no concrete
  answer, the test proves nothing.
- **Fixing one hole opens the next if you fix the spelling and not the
  property.** The viewer needed three rounds. The second one closed `''` by
  filtering that string in the SQL and **widened** the wildcard to `'.'`,
  `'..'`, and `'x/..'`. The one that worked doesn't filter spellings: it
  requires that the declared, already-resolved path lands **strictly
  inside** a root. Filtering strings is playing cat and mouse; asserting a
  property ends it.
- **Adversarial review finds what friendly review doesn't.** All three holes
  in the viewer came from asking the reviewer to *attack* the endpoint with
  concrete vectors, not to read it. The one that only read the code gave it
  a Spec ✅.
- **The gaps live in the seams, and no per-task review sees them.** Task 1
  wrote into the skills "explain the reservation in the summary, **not** in
  the stamp line"; Tasks 3 and 6 needed that reservation to display it, as
  the design required. Each task was correct on its own. Only reviewing the
  whole branch caught it.
- **The plan is a hypothesis, not a truth.** Two code blocks I wrote in the
  plan were wrong, and the plan's own tests would have covered for them: a
  `.strip("\n")` that treats its argument as a character set, and an
  expression that produced a directory's path when the stamp had a single
  file inside it. An implementer who copies the plan verbatim inherits its
  bugs.

## Lessons learned (2026-08-10, morning)

- **A check can find itself.** The runner decided whether there was a plan by
  searching for the stamp `PLAN: validado` in the log's last 4 KB. But the
  skill's body travels in the log and contains all three stamps literally —
  the last `PLAN: validado` sits 393 characters from the end of `SKILL.md`.
  In a run that aborts early, the window swallowed the skill's own §7 and
  the run passed as good: the very bug the mechanism was meant to catch,
  rebuilt from the inside. **Anchor on the last match, not on presence.**
  The final review caught it, not the tests.
- **A specifier on `--allowedTools` doesn't scope it: it enables it.**
  Setting `Bash(npx openspec:*)` didn't restrict Bash to that command — it
  let `ls`, `find`, and `git remote -v` run in the client's repo, while at
  the same time **blocking** the correct CLI invocation for not starting
  with that literal string. The worst of both worlds. And since the list was
  built without looking at the phase, Phase 1 —declared read-only— ended up
  able to run shell commands without anyone deciding that. There's now a
  `PHASE_ALLOWED_TOOLS` table, and `analyze` carries an empty list.
- **`claude -p`'s exit code says nothing.** It exits with 0 even if the agent
  stopped without doing anything. Any status derived from it is a lie
  waiting to happen: `planned` came to mean "the subprocess didn't crash."
- **The package name can't be guessed.** `npx openspec` doesn't exist; it's
  `@fission-ai/openspec`. It cost a full 8-minute run to find out.
- **The agent was more honest than my rule.** The skill told it to stop if
  the CLI failed. It didn't stop: it wrote the plan anyway and opened its
  summary with *"Validation is missing: npx is blocked by permissions,"*
  with its own section and root-cause diagnosis. Throwing away a 21-task
  plan for not being able to validate it would have been worse. The rule
  stayed; what got added was the stamp, so the **status** can't lie even if
  the agent decides to keep going.
- **A mirror cited without being opened is a made-up number.** That's why
  reads are counted in the log, not just citations in the document: 3323
  cited 9 Estes files and read all 9.

## Lessons learned (2026-08-09)

- **`--add-dir` gives access, not attention.** Mounting a repo doesn't make
  the agent look at it: in the 3322 run, `ProvidenceTMSTenant` was
  available, got named 15 times, and logged 0 reads inside it. It has to be
  **named in the prompt with what it's for** — hence the repo's label being
  functional, not decorative. The runner injects it; `SKILL.md` 2.8 (v0.3.0)
  says those repos fall under the scope of "Affected code" instead of being
  declared out of scope.
- **`uvicorn --reload` leaves orphaned processes on Windows.** Three times in
  a row the backend kept serving old code and a test gave a false result.
  Port 8000 stayed held by a child of the reloader. **Start without
  `--reload` and restart by hand**; when behavior looks off, suspect the
  process before the code.
- **Accepting at n=1 is accepting little.** 3311 is an epic written by Jhonny
  himself, with numbered criteria: the dream ticket. The real test is the
  two-sentence ticket. It went well, but that was only known once the second
  one ran.
- **A `<select>` doesn't say what it drags along.** The origin of the UI
  redesign: the user picked a project without seeing which repos the agent
  would mount. The information has to be where the decision gets made, not
  where it was configured last week.

## Lessons learned in acceptance (2026-08-08)

- **The plugin version is the cache key.** Editing and committing a skill in
  the hub doesn't reach the installed plugin: `claude plugin update` fetches
  nothing if `version` in `plugin.json` doesn't change. Touching a skill
  requires bumping the version. The analysis template stamps the version, so
  the generated file proves which one ran.
- **Phase 5 shrinks.** The "per-project memory" that was going to be built
  already exists: it's the target project's `CLAUDE.md` + `.claude/rules/`.
  3311 absorbed Angular 21 rules, the financial gate, the git flow, and
  "developer mode" without a single line of our own code. All that's left
  for Phase 5 is what the agent **learns while running** (that B2's accounts
  are missing, that an 850ms timeout mattered) — a file the agent writes in
  the target repo, not a subsystem.
- **`organization` in `.claude/ticket-agent.json` is redundant** with
  `ADO_ORG`, and the README asked for them to "match": two sources for one
  value. Pending removal (`ADO_ORG` can't be removed, the MCP needs it as an
  env var at startup).
- **The target repo moves while it's being analyzed.** Between the two runs,
  branch `jhonny/quote-v2` went from 12 to 19 commits. That's why figures in
  the analysis must cite the command or `file:line` that produced them:
  without that there's no way to tell an old figure from a made-up one.

## Points to consider / risks

- **Subscription limits**: orchestrator runs consume the plan's window just
  like interactive use does; long analyses may hit the cap.
- **Attachments and images**: the branch is still unexercised, but no longer
  for lack of a case. 3320's parent #827 carries a `.jpg` **embedded in the
  description's HTML**, not hanging off `relations`, and the agent has no id
  to work from. See "Immediate pending items."
- **The phase stepper was removed from the UI** during the redesign: it
  showed 6 phases with 5 dimmed on every row. It comes back once phases 2-4
  really exist.
- **The stamp contract depends on the agent obeying a markdown file.** It
  worked on 3322 at n=1. But if it ever declares a path with backslashes,
  the regex only captures the first segment (`docs`) and the viewer ends up
  serving **that entire directory**, without failing visibly. That's why
  both skills say so explicitly; there's no backend guard that detects it.
- **Runner permissions** (resolved for `implement` in 2b, decision 17):
  `--allowedTools` branched by phase, bare `Bash` in `implement` because the
  specifier doesn't scope it, and containment via hook through `--settings`.
  What's still unresolved is the phase that **pushes to remote**: the
  current latch doesn't hold there, and the containment section of the spec
  will need to be redone. Historical note: **the `Bash(...)` specifier
  enables the tool, it doesn't scope it to the command** — verified in a
  real run. When the code-writing phase arrives, revisit which mode, which
  tools, and which guards apply, and remember that `extra_dirs` are for
  reading, not places the agent should write to.
- **`openspec init` leaves more of a footprint than expected** in the target
  repo: besides `openspec/`, it installs 6 skills under
  `.claude/skills/openspec-*`, `.claude/commands/opsx/`, and commands under
  `.opencode/`. In `ProvidenceTMSTenant` all of it is untracked, pending a
  decision on whether to commit or revert it.
- **Phase 2 is at n=2** (3323 and 3320), the two opposite shapes of ticket.
  What's left to measure isn't yet another shape: it's **whether its
  negative claims are reliable**, which is what 3320 exposed.
- **The orchestrator is a thin v1**: no SSE, no parallel runs, and the
  `test`, `guards`, and `pr` phases are declared but not launchable — they
  grow alongside the agent's phases.
- **An `implement` run is long**: 3332 took **83 minutes** with 19 tasks, and
  the pace is uneven (2 to 9 minutes per task depending on size). It burns
  subscription window at that rate. If interrupted, `tasks.md` keeps the
  progress and relaunching resumes it.
- **The clean-tree guard is evaluated twice** (on the POST, for the
  immediate `409`, and under the lock, which is the authoritative check).
  Two tickets on the same physical repo both get queued: the second finds
  out at launch time, with an explained error, not at click time.
- **Keep this document updated**, along with the plan checkboxes, when
  closing milestones.

## How to resume in a new session

Suggested prompt — open Claude Code in the hub
(`D:/Companies/Jorge.Gutierrez/autonomous-skill-hub`):

> Read docs/STATUS.md to get oriented. **Phase 2b is built and validated**
> (plugin v0.6.1): the agent writes code and commits on a branch. 3332 was
> fully implemented —19/19 tasks, 17 commits, 83 minutes— with not a single
> leak in the commits. The roadmap shrank: `test` stopped being a phase
> because the tests get written inside `implement`.
>
> This session's goal is to **read what the agent wrote**. On branch
> `ticket-agent/3332` of `ProvidenceTMSTenant` there are **2658 new lines
> across 31 files** that **nobody has looked at**. The run came out `ok`
> because the build is green and the boxes are checked — but that measures
> that the mechanism worked, not that the code is good. It's exactly the
> same trap as a test that passes because of its setup.
>
> 1. **Review the full diff** (`git diff Dev..ticket-agent/3332` from
>    `D:/Companies/ProvidenceSolutions/ProvidenceTMSTenant`) **against the
>    pattern it claims to copy**: the carriers already written in
>    `Carriers/Abf/` and `Carriers/Estes/`. The question isn't "does it
>    compile?" but "would a human on the team sign off on it?"
> 2. Scrutinize **the 12 test files**: do they test the logic or just pass
>    because of their setup? The technique that has exposed four placebos in
>    this project is **mutating the code and seeing if any turn red**.
> 3. **Also look at the plan that generated them**
>    (`openspec/changes/3332-carrier-api-v2-migration-dayton/`). If the code
>    is weak, the cause might be there and not in phase 2b.
>
> **That verdict decides what comes next.** If the code is good, the last
> mile (push + PR) justifies itself. If it isn't, automating delivery would
> make the problem worse, and what's needed is fixing the skills.
>
> Two minor things remain open: the **AR finding** (auto-marking stamps
> authorship and `BilledOn` on opening the screen) needs its own work item,
> and **attachments embedded in HTML** are still unexercised (#827's `.jpg`
> carries its GUID in the `src`, not in `relations`).
>
> To start the orchestrator: backend at `apps/orchestrator/backend`
> (`.venv/Scripts/uvicorn app:app --port 8000`, **no `--reload`**) and
> frontend at `apps/orchestrator/frontend` (`npm run dev`). Confirm the
> process on port 8000 started **after** `app.py`'s last change — it's
> fooled us four times already.

**Careful with the orchestrator DB's state: it's nearly empty.** It was wiped
(see "The DB wipe"), and all that's left is the *"Providence (backend
only)"* project —a single repo, the Tenant— with ticket **3332** and its
three runs. Tickets 3322, 3323, and 3320 **aren't registered**, though their
analyses and changes still live in the target repo: recreating them means
registering the ticket, not re-running the phases.

What's already done and doesn't need redoing: `ADO_ORG` in the TMS's
`.claude/settings.json`, the Tenant's `.claude/ticket-agent.json`, and the
plugin installed at the user level at **v0.6.1**. `ProvidenceTMSTenant` is
the guinea pig: whatever runs leave there doesn't need versioning or cleanup
(decision 15) — and now that includes branch **`ticket-agent/3332`** with 17
implementation commits, which also doesn't need merging or deleting unless
it gets in the way.

Five known traps: **bump the `version`** when touching a skill, or the
change won't reach the installed plugin; **don't use `uvicorn --reload`**,
which leaves orphaned processes holding port 8000 and serves old code
without warning; the OpenSpec package is **`@fission-ai/openspec`**, not
`openspec`; **`claude -p`'s exit code doesn't say whether the agent did
anything** — that's what the `HUELLA:` stamp is for; and **a green test can
be an alibi**: before trusting one, ask what would have to break for it to
fail.
