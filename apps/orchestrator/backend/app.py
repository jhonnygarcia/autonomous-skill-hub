import asyncio
import codecs
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from itertools import takewhile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ORCH_DB", BASE / "orchestrator.db"))
LOGS_DIR = Path(os.environ.get("ORCH_LOGS", BASE / "logs"))

# Declaring a phase and being able to launch it are two different things, and a phase
# declared without a command is a broken promise taking up a slot in the timeline. `test`
# went first on 2026-08-11 (it isn't a phase, it's part of `implement`), and `guards` and
# `pr` follow it: they were in this list from the start and never gained a command, so the
# UI painted two rows out of five that never did anything. They come back when they exist.
PHASES = ["analyze", "brief", "survey", "consolidate", "design", "implement"]

# Phase 1 has two routes to the SAME deliverable: `analyze` in one session, or the
# `brief`/`survey`/`consolidate` fan-out with a session rooted in each repo — which
# exists because `--add-dir` mounts a repo's files but not its rules, hooks or MCP, so
# a single session writes the extras' code under the primary repo's conventions. Both
# end in `docs/tickets/<id>-analysis.md`, which is why Phase 2 never learns which ran.
MULTI_REPO_PHASES = ["brief", "survey", "consolidate"]


def phase_names_for(extras: list) -> list[str]:
    """The phases a ticket offers, in order.

    The filtering is deliberately asymmetric. A single-repo ticket does NOT get the
    fan-out: with nothing to fan out it would be three sessions to reach the same
    place, and there'd be no contract between repos to build.

    A multi-repo ticket keeps `analyze` alongside the fan-out. It's the fallback when
    the fan-out gets stuck, and it's the baseline the design has to be measured
    against — the whole hypothesis is that a rooted survey beats it, and hiding the
    thing you're comparing to makes the comparison impossible. Running both is
    harmless: they write the same file and the last one wins.
    """
    return [p for p in PHASES if extras or p not in MULTI_REPO_PHASES]

# Declaring a phase doesn't mean implementing it. Only these three can be launched; the
# rest are in PHASES so the UI knows they exist, and they're rejected with 400.
PHASE_COMMANDS = {
    "analyze": "/ticket-agent:analyze",
    "brief": "/ticket-agent:brief",
    "survey": "/ticket-agent:survey",
    "consolidate": "/ticket-agent:consolidate",
    "design": "/ticket-agent:plan",
    "implement": "/ticket-agent:implement",
}
# What state a run that finishes well leaves the ticket in. `brief` and `survey` are
# steps toward the analysis, not deliverables of their own: only `consolidate` leaves
# the ticket analyzed, so an interrupted fan-out doesn't look finished.
PHASE_DONE = {"analyze": "analyzed", "brief": "briefed", "survey": "surveyed",
              "consolidate": "analyzed", "design": "planned", "implement": "implemented"}
# Bash is scoped per phase, not just per command: Phase 1 is read-only and doesn't carry
# Bash; Phase 2 needs to invoke the npm package `@fission-ai/openspec` (the CLI is NOT
# called `openspec`) for `init` and `validate`, and nothing else. The specifier has to
# match the start of the command literally or Claude blocks it, so both invocation
# forms are covered. A loose Bash in a client's repo is a different conversation — and
# that's exactly what happened when this list used to travel fixed for every phase.
PHASE_ALLOWED_TOOLS = {
    "analyze": [],
    # `brief` reads the work item, like `analyze`: MCP and nothing else.
    "brief": [],
    # `survey` and `consolidate` get NO MCP. The survey runs rooted in a secondary repo
    # and receives the brief inline in its prompt, so it needs no ADO_ORG, no token and
    # no `.claude/ticket-agent.json` in that repo — it's a pure code-comprehension
    # session. `consolidate` works off the brief and the surveys for the same reason:
    # going back to the work item would make it a second, divergent reading.
    "survey": [],
    "consolidate": [],
    "design": [
        "Bash(npx --yes @fission-ai/openspec@latest:*)",
        "Bash(npx @fission-ai/openspec:*)",
    ],
    # No specifier, on purpose: it's verified on a real run that `Bash(x:*)` enables
    # the tool and does not scope it. Pretending otherwise would be worse than not
    # setting it at all. Containment goes through `--settings` (see `settings_for`).
    "implement": ["Bash"],
}
# Noun for the deliverable, so the prompt doesn't call it "the analysis" to the agent
# when the phase is design (and vice versa).
# Which phases reach Azure DevOps at all. `PHASE_ALLOWED_TOOLS` was never enough for
# this: the MCP tool travels FIXED in the argv for every phase, so an empty list there
# doesn't take it away.
# The fan-out's children don't get it. The survey receives the brief inline in its
# prompt, and `consolidate` works off the brief and the surveys — going back to the
# work item would make it a second, divergent reading of the ticket, which is exactly
# what the brief exists to prevent.
# `design` and `implement` keep it even though their skills consume the previous
# phase's file and not the work item. Dropping it there is a real cleanup, but it needs
# a live run to confirm, and it isn't this change's job.
PHASE_MCP = {"analyze", "brief", "design", "implement"}

PHASE_NOUN = {"analyze": "the analysis", "brief": "the brief",
              "survey": "the survey", "consolidate": "the analysis",
              "design": "the plan", "implement": "the implementation"}
# If someone adds a phase to one dict and not the others, today that's an uncaught
# KeyError inside a background task that leaves the run at `success` and the ticket
# unupdated.
assert PHASE_COMMANDS.keys() == PHASE_DONE.keys() == PHASE_ALLOWED_TOOLS.keys() == PHASE_NOUN.keys()

# Model and effort per phase, editable from Settings in the UI. They live in the
# `phase_config` table and nowhere else: empty means "whatever the CLI resolves in the
# destination repo", which is the default behavior for every phase.
# ponytail: global to the app, not per project nor per run.
EFFORTS = ("", "low", "medium", "high", "xhigh", "max")
# The model goes straight into the CLI's argv, so it can't start with `-`: that would be
# another flag. Accepts the aliases (`opus`, `sonnet`…) and the full ids.
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def phase_configs() -> dict[str, dict]:
    """The launchable phases with their configuration; whichever nobody touched come out empty."""
    with db() as c:
        rows = {r["phase"]: r for r in c.execute("SELECT * FROM phase_config")}
    return {f: {"model": rows[f]["model"] if f in rows else "",
                "effort": rows[f]["effort"] if f in rows else ""}
            for f in PHASE_COMMANDS}


HOOK_DENY_PUSH = Path(__file__).resolve().parent / "hooks" / "deny_push.py"


def settings_for(phase: str) -> list[str]:
    """`--settings` accepts an inline JSON, so the hook travels without a config file
    and without writing anything into the client's repo.

    It's branched per phase just like the tools: setting it everywhere would look the
    same today —the other phases don't have Bash— but it would go back to mixing "what
    this phase needs" with "what every phase drags along".
    """
    if phase != "implement":
        return []
    cfg = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f'"{sys.executable}" "{HOOK_DENY_PUSH}"'}]}]}}
    return ["--settings", json.dumps(cfg)]


def repos_text(phase: str, extras: list[dict], noun: str, primary: str = "") -> str:
    """The prompt block that introduces the ticket's extra repos to the agent.

    Mounting them with `--add-dir` isn't enough: in run 3322 the agent had
    ProvidenceTMSTenant accessible, mentioned it 15 times and never opened it once. They
    have to be named to it, and the label is what tells it when to look there.

    It's branched per phase just like the tools and `settings_for`, for a reason that
    isn't cosmetic: design decision 4 says that in `implement` **every mounted repo of
    the ticket is writable**, and the `change-implementation` skill instructs the agent
    that, if the plan's map and the prompt disagree, it should follow the prompt. A
    single text that says "readable" and "written on the main one" is, in `implement`,
    the wrong instruction with top priority — and it leaves 3320 unimplemented, whose
    code lives entirely in an `extra_dir`.
    """
    if not extras:
        return ""
    listing = "; ".join(
        e["path"] + (f" — {e['label']}" if e["label"] else "") for e in extras)
    # The primary repo's label was missing from the prompt until run 3320 on 2026-08-13:
    # the agent knew the extras by name and had to invent one for the repo it was
    # standing in. It wrote `SONDEAR: main, tms` when the label was `tenant`, and the
    # routing widened to every repo — the safe direction held, but the optimization was
    # lost to a name nobody had told it.
    if phase == "brief" and primary:
        return (
            f"\n\nThe repos this ticket mounts, with the labels to use verbatim on the "
            f"`SONDEAR:` line — you are standing in the first one: `{primary}` (this "
            f"repo); {listing}. Use these labels exactly; anything else is unreadable "
            "to the runner and makes it survey every repo."
        )
    if phase == "implement":
        return (
            f"\n\nExtra repos mounted alongside the main one, and in this phase all of "
            f"them are writable: {listing}. The runner already prepared the working "
            "branch in each. Write the code in the repo the plan points to as the site "
            "of the change, not necessarily the main one, and commit in each repo "
            "whatever belongs to it."
        )
    return (
        f"\n\nExtra repos mounted and readable alongside the main one: {listing}. "
        "Read them when the ticket points to behavior that doesn't live in the main "
        f"repo; {noun} is still written in the main one."
    )


def adjustment_text(phase: str, noun: str, instructions: str | None) -> str:
    """The user's adjustment instructions, also per phase.

    In `analyze` and `design` the deliverable is ONE file and re-running means
    regenerating it. In `implement` there is no "the file" to regenerate: the
    deliverable is the code, and the only file the phase rewrites is `tasks.md`, which
    is the progress record — regenerating it would erase exactly what lets the run be
    resumed.
    """
    if not instructions:
        return ""
    if phase == "implement":
        return (
            f"\n\nUser's adjustment instructions for this run of {noun} "
            "(apply them to the tasks still pending; `tasks.md` is this phase's "
            "progress record: it gets checked off as you advance, it is not "
            f"regenerated and closed boxes are not reopened): {instructions}"
        )
    return (
        f"\n\nUser's adjustment instructions to rework {noun} "
        f"(apply them and regenerate the file): {instructions}"
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# The closing stamp for the skills. `PLAN:` is accepted as a legacy alias because logs
# from runs before the single contract were written that way. The actual log from
# `claude -p --output-format stream-json` isn't parsed as JSON here: the stamp travels
# nested inside `message.content[].text`, followed by `"`, `stop_reason`, `usage`,
# `session_id`, etc. on the same line. That's why the rest of the stamp stops at the
# first character that can't be part of its text — the quote or backslash that closes
# the JSON field — instead of greedily swallowing the rest of the line with `.+`. In a
# plain log without JSON (the legacy ones with `PLAN:`) there are no quotes or
# backslashes, so the behavior doesn't change: the capture reaches end of line just
# like before.
STAMP_RE = re.compile(r'(?:HUELLA|PLAN): (ok|parcial|nada|validado|sin-validar|no-escrito)\s*[—-]\s*([^"\\]+)')
# The CLI's session, as it travels in the stream-json. Not a contract with the skills
# like `STAMP_RE` — it's the CLI's own shape — but just as literal.
SESSION_RE = re.compile(r'"session_id":"([0-9a-fA-F-]{36})"')

# The routing line the `brief` phase writes, naming which repos deserve a survey.
# Same treatment as `STAMP_RE` and for the same reason: the skill's own example
# carries the literal, so the LAST match is the decision and the earlier ones are
# prose. The keyword stays in Spanish because it's matched byte for byte.
SURVEY_RE = re.compile(r"^SONDEAR:(.*)$", re.MULTILINE)


def repos_to_survey(text: str, labels: list[str]) -> list[str]:
    """Which of the mounted repos the brief asked to survey, in mounting order.

    Every ambiguity widens to `labels`. Routing is an optimization — an irrelevant
    repo answers `not-touched` and costs one session — while skipping a repo that
    mattered costs the ticket, and nothing downstream detects it. So a parsing
    failure is a cost problem, never a correctness one, and there is no path by
    which this narrows the list on its own.

    A single unknown label voids the whole line instead of dropping just that one:
    a partially valid line looks like a decision and is usually a typo.
    """
    matches = SURVEY_RE.findall(text)
    if not matches:
        return list(labels)
    wanted = [p.strip().lower() for p in matches[-1].split(",") if p.strip()]
    known = {label.lower(): label for label in labels}
    if not wanted or any(w not in known for w in wanted):
        return list(labels)
    chosen = {known[w] for w in wanted}
    # Mounting order, not the order the agent typed: the log of a fan-out has to be
    # comparable between runs of the same ticket.
    return [label for label in labels if label in chosen]
LEGACY_STATES = {"validado": "ok", "sin-validar": "parcial", "no-escrito": "nada"}

# Separator between the path and the reserve in a `parcial` stamp: "HUELLA: parcial —
# <path> · <reserve>". Space, middle dot (U+00B7), space — that's what the two skills
# ask for in their closing rule.
RESERVE_SEP = " · "

NO_STAMP_REASON = "la corrida no declaró huella"
# The 5 historical runs from before this contract came out with status=success (the
# CLI exited 0) and no stamp: saying "failed" there would be lying about what happened.
LEGACY_NO_STAMP_REASON = "corrida anterior a este contrato: terminó bien, pero " + NO_STAMP_REASON


def split_reserve(state: str, rest: str) -> tuple[str, str | None]:
    """From a `parcial` stamp with a reserve, split the path (for `artifact_path`,
    which has to stay a clean path: it's the viewer's allowlist) from the reserve (for
    `artifact_note`). A `parcial` without ` · ` has no reserve and `rest` in full is the
    path, same as before this change."""
    if state == "parcial" and RESERVE_SEP in rest:
        path, note = rest.split(RESERVE_SEP, 1)
        return path.strip(), note.strip()
    return rest, None


def stamp_in(text: str) -> tuple[str, str] | None:
    """The stamp of ONE stretch of log. Split out from `read_stamp` because a fan-out
    run holds several children in a single file, and each one's verdict has to be read
    from its own stretch — the last stamp of the whole file is only the last child's."""
    hits = STAMP_RE.findall(text[-4000:])
    if not hits:
        return None
    state, rest = hits[-1]
    return LEGACY_STATES.get(state, state), rest.strip()


def read_stamp(log_path: Path) -> tuple[str, str] | None:
    """`(state, path-or-reason)` from the LAST match in the log, or None if there is none.

    The LAST one, not just presence: the SKILL.md body travels in the log (the
    tool_result from loading it) and contains the three stamps literally, so checking
    for presence makes the check find itself and pass a run that actually closed with
    `nada`. This has already been paid for once."""
    if not log_path.exists():
        return None
    # ponytail: reads the whole file just to keep the tail; with MB-sized logs this
    # would need a seek from the end. Today they weigh KB.
    return stamp_in(log_path.read_text(encoding="utf-8", errors="replace"))


def normalize_dirs(items: list) -> list[dict]:
    """Extra repos used to be a list of paths before carrying a label. Normalized on
    read so old rows don't break; they heal on the next save."""
    return [{"path": i, "label": ""} if isinstance(i, str)
            else {"path": i["path"], "label": i.get("label", "")} for i in items]


def project_out(row: sqlite3.Row) -> dict:
    """Outward a project has ONE list of repos, with one marked primary. Internally
    they're stored separately because the runner uses them differently: the primary one
    is the run's `cwd`, the rest travel as `--add-dir`."""
    repos = [{"path": row["repo_path"], "label": row["repo_label"], "primary": True}]
    repos += [{**d, "primary": False} for d in normalize_dirs(json.loads(row["extra_dirs"]))]
    return {"name": row["name"], "org": row["org"], "project": row["project"], "repos": repos}


def get_project(name: str) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()


def is_repo_dir(path: str) -> bool:
    """Whether a path from a form points at a real directory.

    `is_dir()` raises instead of returning False on a null byte or an absurdly long
    path, and this value comes straight from a text field the user pasted into.
    """
    try:
        return Path(path).is_dir()
    except (ValueError, OSError):
        return False


def check_dirs(*paths: str) -> None:
    """Paths arrive from a form and end up as cwd and --add-dir of a subprocess: a typo
    here blows up inside the CLI with an unreadable error."""
    bad = [p for p in paths if not is_repo_dir(p)]
    if bad:
        raise HTTPException(400, "No existen o no son directorios: " + ", ".join(bad))


def is_dirty(repo: str) -> bool:
    """Is there uncommitted work that a `git switch -c` would carry along?

    `??` entries are ignored **on purpose**: the main repo always has `openspec/`,
    `docs/tickets/` and whatever `openspec init` left untracked — those are the agent's
    own artifacts. Requiring a pristine tree would make the phase permanently
    unlaunchable. What matters is what's tracked: that's genuinely the user's work.
    """
    # The directory is checked BEFORE invoking `git`, instead of wrapping the call in a
    # `try/except OSError`: that also caught a missing `git` on the PATH (the same
    # `FileNotFoundError`/`NotADirectoryError` on Windows) and disguised it as "not a
    # git repository" — a 409 that lies about the cause. A real invocation failure
    # (git not installed, etc.) has to propagate, not turn into a 409.
    if not Path(repo).is_dir():
        raise HTTPException(409, f"No es un repositorio git: {repo}")
    r = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No es un repositorio git: {repo}")
    return any(not ln.startswith("??") for ln in r.stdout.splitlines() if ln.strip())


def check_clean(repos: list[str]) -> None:
    bad = [r for r in repos if is_dirty(r)]
    if bad:
        raise HTTPException(409, "Hay cambios sin commitear en: " + ", ".join(bad)
                            + ". La fase implement commitea, y no debe llevarse por "
                              "delante tu trabajo a medias.")


BRANCH_FMT = "ticket-agent/{ado_id}"


def prepare_branch(repo: str, ado_id: int) -> str:
    """Creates the phase's branch, or switches to it if it already exists.

    The runner creates it, not the skill, for the same reason the stamp exists: a limit
    that depends on the agent obeying a markdown file isn't a limit. `refs/heads/` in
    the `rev-parse` so the branch isn't confused with a tag or a sha.
    """
    name = BRANCH_FMT.format(ado_id=ado_id)
    exists = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"],
                            cwd=repo, capture_output=True).returncode == 0
    cmd = ["git", "switch", "-q", name] if exists else ["git", "switch", "-q", "-c", name]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise HTTPException(409, f"No se pudo preparar la rama en {repo}: {r.stderr.strip()}")
    return name


RESUME_STAMP_REMINDER = (
    "\n\nClose with the same HUELLA line as always, the last one of the message.")
NO_SESSION_TO_RESUME = (
    "[orchestrator] se pidió continuar, pero esta fase no tiene sesión previa "
    "registrada: corre en una sesión nueva.\n")


CONSOLIDATE_PROMPT = (
    "\n\nThe surveys are in `{dir}`, one file per surveyed repo. Read them all.\n"
    "Surveyed: {surveyed}.\n"
    "{missing}"
    "The mounted repos are readable if you need to check something a survey asserts, "
    "but the surveys are the interface: don't redo them.")
NO_SURVEYS_REASON = (
    "no hay surveys que consolidar; corre primero la fase «survey»")


def last_survey_dir(ticket_id: int) -> str | None:
    """Where the most recent survey fan-out left its files.

    A run whose stamp came back `nada` left nothing worth reading, so it doesn't count:
    otherwise a failed fan-out would hide the good one before it and consolidation
    would run against an empty directory.
    """
    with db() as c:
        r = c.execute(
            "SELECT artifact_path FROM runs WHERE ticket_id=? AND phase='survey' "
            "AND artifact_state IN ('ok','parcial') ORDER BY id DESC LIMIT 1",
            (ticket_id,)).fetchone()
    return r["artifact_path"] if r else None


def last_session(ticket_id: int, phase: str) -> str | None:
    """The CLI session of this phase's most recent run that had one.

    Not "the last run": one can die before the id shows up in the stream, and that
    shouldn't hide the session before it — a run that died halfway is precisely one
    worth continuing.

    No check that the directory matches: every run of a ticket shares its `repo_path`
    (copied when the ticket is created, and no endpoint edits it afterwards), and a
    session lives under the directory it ran in. If ticket editing ever appears, this
    stops holding.
    """
    with db() as c:
        r = c.execute(
            "SELECT session_id FROM runs WHERE ticket_id=? AND phase=? "
            "AND session_id IS NOT NULL ORDER BY id DESC LIMIT 1",
            (ticket_id, phase)).fetchone()
    return r["session_id"] if r else None


BRIEF_REL = "docs/tickets/{ado_id}-brief.md"
NO_BRIEF_REASON = (
    "no existe el brief de la fase anterior; corre primero la fase «brief»")
SURVEY_PROMPT = (
    "{command} {ado_id}\n\n"
    "You are rooted in the repo `{label}` ({path}), and this session is the only one "
    "that sees ITS rules, hooks and configuration. Answer only for this repo.\n\n"
    "Write the survey to `{out}` and nothing else: this repo is read-only for you.\n\n"
    "--- Ticket brief (the work item is NOT reachable from here; this is all of it) ---\n"
    "{brief}\n"
    "--- end of brief ---")


def ticket_labels(t) -> list[tuple[str, str]]:
    """`(label, path)` for every repo the ticket mounts, primary first.

    The label is what the routing line names, so an unlabelled repo falls back to its
    folder name rather than becoming un-nameable: a repo nobody can write on a
    `SONDEAR:` line is a repo that never gets surveyed.
    """
    out = [(t["repo_label"] or Path(t["repo_path"]).name, t["repo_path"])]
    for e in normalize_dirs(json.loads(t["extra_dirs"] or "[]")):
        out.append((e["label"] or Path(e["path"]).name, e["path"]))
    return out


def ticket_repos(t) -> list[str]:
    """The repos the ticket mounts: the primary one first, then the extras. That's the
    order they're checked and branched in, and it holds equally for a SQLite row and for
    the `dict` that travels to the background task."""
    return [t["repo_path"]] + [
        e["path"] for e in normalize_dirs(json.loads(t["extra_dirs"] or "[]"))]


def prepare_repos(repos: list[str], ado_id: int) -> str | None:
    """Clean-tree guard on ALL of them and, only if all pass, the branch on all of them.

    The two steps go in this order and not interleaved repo by repo: if one were
    checked and branched, then the next, a second dirty repo would leave the first one
    already switched to a branch with no run to explain it.

    All of them get branched, including ones the plan ends up not touching: the runner
    doesn't parse the plan, and a branch with no commits is noise that removes itself.
    """
    check_clean(repos)
    branch = None
    for r in repos:
        branch = prepare_branch(r, ado_id)
    return branch


def split_repos(repos: list) -> tuple:
    """Validates the list exactly as the UI sends it and splits it into (primary, rest)."""
    if not repos:
        raise HTTPException(400, "El proyecto necesita al menos un repo")
    primaries = [r for r in repos if r.primary]
    if len(primaries) != 1:
        raise HTTPException(400, "Marca exactamente un repo como principal")
    check_dirs(*[r.path for r in repos])
    return primaries[0], [r for r in repos if not r.primary]


def repos_columns(body) -> tuple:   # ProjectIn is defined further below; no annotation
    primary, rest = split_repos(body.repos)
    return (primary.path, primary.label,
            json.dumps([{"path": r.path, "label": r.label} for r in rest]))


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects(
              name TEXT PRIMARY KEY,
              org TEXT NOT NULL,
              project TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              repo_label TEXT NOT NULL DEFAULT '',
              extra_dirs TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS tickets(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ado_id INTEGER NOT NULL,
              org TEXT NOT NULL,
              project TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              extra_dirs TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'queued',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
              phase TEXT NOT NULL,
              instructions TEXT,
              status TEXT NOT NULL DEFAULT 'queued',
              log_path TEXT,
              artifact_state TEXT,
              artifact_path TEXT,
              started_at TEXT,
              finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS phase_config(
              phase TEXT PRIMARY KEY,
              model TEXT NOT NULL DEFAULT '',
              effort TEXT NOT NULL DEFAULT ''
            );
            """
        )
        # DBs created before extra repos existed. SQLite has no
        # ADD COLUMN IF NOT EXISTS, so it's attempted and ignored if it's already there.
        for alter in (
            "ALTER TABLE tickets ADD COLUMN extra_dirs TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE projects ADD COLUMN repo_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE runs ADD COLUMN artifact_state TEXT",
            "ALTER TABLE runs ADD COLUMN artifact_path TEXT",
            # The reserve of a `parcial` stamp (whatever follows ` · `), separate from
            # the path: `artifact_path` has to stay a clean path.
            "ALTER TABLE runs ADD COLUMN artifact_note TEXT",
            # The branch the runner prepared for an `implement` run. It's the only
            # piece of data the run produces that doesn't fit in `tasks.md`.
            "ALTER TABLE runs ADD COLUMN branch TEXT",
            # Existed since the first commit, was initialized to 'analyze' and nothing
            # ever wrote to it: a slot planned for this that only caused confusion.
            # Progress is computed from `runs`.
            "ALTER TABLE tickets DROP COLUMN current_phase",
            # The ticket's title, read from the analysis when `analyze` closes well.
            # It doesn't come from Azure DevOps: the backend has no ADO credentials —
            # the MCP only lives inside the agent's subprocess — and giving it some
            # would mean building a second authentication path to save a typo.
            "ALTER TABLE tickets ADD COLUMN title TEXT",
            # The CLI session this run drove. It's what `--resume` takes to continue a
            # phase instead of redoing it, and the only place it exists is the stream.
            "ALTER TABLE runs ADD COLUMN session_id TEXT",
            # And which session this one continued, when it did. Always with
            # `--fork-session`, so each run keeps its own id and the chain stays
            # walkable in both directions.
            "ALTER TABLE runs ADD COLUMN resumed_from TEXT",
            # The primary repo's label. It lived only on the project until the fan-out
            # needed to name every repo to the routing — an unlabelled primary can't be
            # written on a `SONDEAR:` line. Copied on creation like the rest.
            "ALTER TABLE tickets ADD COLUMN repo_label TEXT NOT NULL DEFAULT ''",
        ):
            try:
                c.execute(alter)
            except sqlite3.OperationalError:
                pass
        # Runs from before this contract have empty columns and would show up as "no
        # stamp declared" in the timeline. Their stamp is in their log: it's read once,
        # at migration time, instead of on every read.
        for r in c.execute(
            "SELECT id, log_path FROM runs WHERE artifact_state IS NULL AND log_path IS NOT NULL"
        ).fetchall():
            h = read_stamp(Path(r["log_path"]))
            if h:
                path, note = split_reserve(*h)
                c.execute(
                    "UPDATE runs SET artifact_state=?, artifact_path=?, artifact_note=? WHERE id=?",
                    (h[0], path, note, r["id"]))


app = FastAPI(title="ticket-orchestrator")
init_db()


class Repo(BaseModel):
    path: str
    label: str = ""       # "backend", "app de autenticación"… travels to the agent's prompt
    primary: bool = False  # exactly one: it's the cwd and where the analysis is written


class ProjectIn(BaseModel):
    name: str
    org: str
    project: str
    repos: list[Repo] = []


class RutaIn(BaseModel):
    ruta: str


class TicketIn(BaseModel):
    ado_id: int
    project: str


class RunIn(BaseModel):
    instructions: str | None = None
    phase: str = "analyze"  # default, so callers that don't pass it don't break
    # Continue the phase's previous CLI session instead of starting a fresh one. The
    # human decides, because only they know whether the adjustment ADDS scope (where
    # continuing saves the exploration) or CORRECTS what the agent understood (where a
    # fresh session keeps the correction from competing with the reasoning behind the
    # mistake). Defaults to False: the safe side.
    resume: bool = False


def ticket_row(tid: int) -> sqlite3.Row | None:
    with db() as c:
        return c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()


class PhaseConfig(BaseModel):
    model: str = ""
    effort: str = ""


@app.get("/modelos")
def get_models():
    return phase_configs()


@app.put("/modelos")
def put_models(body: dict[str, PhaseConfig]):
    """Validates EVERYTHING before writing ANYTHING: a half-saved write would leave some
    phases with the new model and others with the old one, and nobody would know which."""
    for phase, cfg in body.items():
        if phase not in PHASE_COMMANDS:
            raise HTTPException(400, f"La fase '{phase}' no es ejecutable")
        if cfg.model and not MODEL_RE.match(cfg.model):
            raise HTTPException(400, f"Modelo inválido: '{cfg.model}'")
        if cfg.effort not in EFFORTS:
            raise HTTPException(
                400, f"Effort inválido: '{cfg.effort}' (usa {', '.join(EFFORTS[1:])})")
    with db() as c:
        for phase, cfg in body.items():
            c.execute(
                "INSERT INTO phase_config(phase, model, effort) VALUES(?,?,?) "
                "ON CONFLICT(phase) DO UPDATE SET model=excluded.model, effort=excluded.effort",
                (phase, cfg.model, cfg.effort))
    return phase_configs()


@app.get("/projects")
def list_projects():
    with db() as c:
        return [project_out(r) for r in c.execute("SELECT * FROM projects ORDER BY name")]


@app.post("/projects", status_code=201)
def create_project(body: ProjectIn):
    cols = repos_columns(body)
    with db() as c:
        if c.execute("SELECT 1 FROM projects WHERE name=?", (body.name,)).fetchone():
            raise HTTPException(409, f"Ya existe un proyecto '{body.name}'")
        c.execute(
            "INSERT INTO projects(name, org, project, repo_path, repo_label, extra_dirs) "
            "VALUES(?,?,?,?,?,?)",
            (body.name, body.org, body.project, *cols),
        )
    return project_out(get_project(body.name))


@app.put("/projects/{name}")
def update_project(name: str, body: ProjectIn):
    # ponytail: full replace, no partial PATCH — the form sends everything.
    if not get_project(name):
        raise HTTPException(404)
    # Renaming is safe: tickets copy the project's data when they're created, so none
    # of them point here. All that matters is keeping the name unique.
    if body.name != name and get_project(body.name):
        raise HTTPException(409, f"Ya existe un proyecto '{body.name}'")
    cols = repos_columns(body)
    with db() as c:
        c.execute(
            "UPDATE projects SET name=?, org=?, project=?, repo_path=?, repo_label=?, "
            "extra_dirs=? WHERE name=?",
            (body.name, body.org, body.project, *cols, name),
        )
    return project_out(get_project(body.name))


@app.delete("/projects/{name}", status_code=204)
def delete_project(name: str):
    # Safe without checking tickets: each ticket saved its own copy when it was created.
    with db() as c:
        if not c.execute("DELETE FROM projects WHERE name=?", (name,)).rowcount:
            raise HTTPException(404)


@app.post("/rutas/validar")
def validar_ruta(body: RutaIn):
    """The same check `check_dirs` does, exposed on its own so the project form can
    answer at blur time instead of at save time.

    It does NOT replace `check_dirs`: saving keeps validating, and that one stays the
    authoritative check. This endpoint is a courtesy, so a failure here never blocks a
    save — see the frontend's `catch` in `ProjectForm`.
    """
    return {"existe": is_repo_dir(body.ruta)}


@app.post("/tickets", status_code=201)
def create_ticket(body: TicketIn):
    proj = get_project(body.project)
    if not proj:
        raise HTTPException(400, f"El proyecto '{body.project}' no está dado de alta")
    ts = now()
    with db() as c:
        cur = c.execute(
            "INSERT INTO tickets(ado_id, org, project, repo_path, repo_label, extra_dirs, "
            "created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (body.ado_id, proj["org"], proj["project"], proj["repo_path"],
             proj["repo_label"], proj["extra_dirs"], ts, ts),
        )
    t = ticket_row(cur.lastrowid)
    return ticket_out(t, phases_for(t, [], with_footprint=False))


def seconds(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    return int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def stamp_stat(repo: str, rel: str) -> dict:
    """Size and file count of what the run declared having written. A declared path
    that doesn't exist is NOT hidden: it's reported as `existe: False`. It's the golden
    rule of the skills applied to the orchestrator.

    Recursive: an OpenSpec change nests `specs/<capability>/spec.md`, so looking only at
    direct children would underrepresent the most common deliverable. `nombres` carries
    the path relative to the stamp's directory (not the basename) because it's exactly
    the list Task 4 will use as the viewer's allowlist — "under the declared
    directory", not "direct child" — and always with `/`, even on Windows: that value
    travels to the UI and from there to the viewer endpoint, which works with POSIX
    paths."""
    p = Path(repo) / rel
    if not p.exists():
        return {"ruta": rel, "existe": False, "archivos": 0, "bytes": 0, "nombres": []}
    if p.is_dir():
        children = sorted(x for x in p.rglob("*") if x.is_file())
        names = [x.relative_to(p).as_posix() for x in children]
    else:
        children = [p]
        names = [p.name]
    return {"ruta": rel, "existe": True, "archivos": len(children),
            "bytes": sum(x.stat().st_size for x in children),
            # ponytail: 12 names are enough for the timeline; a change has 4.
            "nombres": names[:12]}


# A checked box in `tasks.md`. The Phase 2b skill checks them off as it advances, so
# counting lines is the whole mechanism — no stream-json parsing, which is a CLI format
# that would have to be maintained when it changes.
# These are line-oriented and fence-blind: a literal `- [x]` inside a fenced code block
# in `tasks.md` would count as a real task. `tasks.md` is machine-generated today
# without such examples, so this is a lookup for a future surprise, not a live bug.
DONE_BOX = re.compile(r"^\s*- \[x\]", re.MULTILINE | re.IGNORECASE)
OPEN_BOX = re.compile(r"^\s*- \[ \]", re.MULTILINE)


def task_progress(t: sqlite3.Row, runs: list[dict]) -> dict | None:
    """`{hechas, total}` for a running `implement`, or None.

    Answers the question you actually have at minute 50 of an 83-minute run —how much is
    left— instead of "is it still alive". It's an estimate, not a truth: a big task
    counts the same as a small one, which is why the UI shows the count and never a
    percentage of time.

    None as soon as anything doesn't add up: no `design` run with a footprint, no
    `tasks.md`, no boxes. Then the UI shows the stopwatch it showed before.
    """
    design = next((r for r in runs
                   if r["phase"] == "design"
                   and r["artifact_state"] in ("ok", "parcial")
                   and r["artifact_path"]), None)
    if not design:
        return None
    # Same path guard as the viewer: this is a path declared by a run of THIS ticket, and
    # it goes through the predicate that took three rounds and 638 vectors.
    p = declared_file_or_none(t, design["artifact_path"].rstrip("/") + "/tasks.md")
    if not p:
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hechas = len(DONE_BOX.findall(text))
    total = hechas + len(OPEN_BOX.findall(text))
    return {"hechas": hechas, "total": total} if total else None


def read_title(t: sqlite3.Row, rel: str) -> str | None:
    """The analysis's first `# ` heading, or None.

    Soft contract: the skill's template writes that heading, but no plugin test protects
    it, so every failure path returns None and the UI falls back to `#<ado_id>`.

    Goes through `declared_file_or_none`, not straight to disk: a stamp that declares a
    traversal must not become a second, laxer door.
    """
    p = declared_file_or_none(t, rel)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            # The heading is at the top; a 28 KB analysis isn't read whole for a title.
            for _ in range(50):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("# "):
                    return line[2:].strip()[:200] or None
    except OSError:
        return None
    return None


# The markers a deliverable closes with, unticked. `- [x]` is an answered one and
# doesn't count. The keywords are contract literals, matched byte for byte, and they
# stay in Spanish like `HUELLA`.
DECISION_RE = re.compile(r"^\s*- \[ \]\s*\*\*(DECIDIR|BLOQUEA)\*\*", re.MULTILINE)


def open_decisions(t: sqlite3.Row, rel: str) -> dict | None:
    """How many decisions the phase left waiting for a human.

    Without this the `## Decisiones para ti` sections are read by nobody: today the
    only way to find them is to open an 8 KB document and go hunting. Goes through
    `declared_file_or_none` and not straight to disk, for the same reason the viewer
    does: a stamp that declares a traversal must not become a second, laxer door.
    """
    p = declared_file_or_none(t, rel)
    if not p:
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found = DECISION_RE.findall(text)
    if not found:
        return None
    return {"decidir": found.count("DECIDIR"), "bloquea": found.count("BLOQUEA")}


def phases_for(t: sqlite3.Row, runs: list[dict], with_footprint: bool = True) -> list[dict]:
    """A phase's progress IS its most recent run. `runs` arrives ordered by id DESC."""
    out = []
    extras = normalize_dirs(json.loads(t["extra_dirs"] or "[]"))
    for name in phase_names_for(extras):
        if name not in PHASE_COMMANDS:
            out.append({"fase": name, "disponible": False})
            continue
        rs = [r for r in runs if r["phase"] == name]
        e = {"fase": name, "disponible": True, "corridas": len(rs),
             "fallidas": sum(1 for r in rs if r["status"] == "error"),
             # What the UI enables the "continue" control with. Computed here and not
             # in the client on purpose: it's the same condition `execute_run` uses to
             # decide whether the resume applies or falls back to fresh, and two copies
             # of it drift.
             "puede_continuar": any(r["session_id"] for r in rs),
             # The CURRENT chain, not the historical total: a fresh run breaks it. It's
             # what says how much context has piled up in the session now in play, which
             # is the risk the human is weighing — nothing here caps it.
             "continuaciones": len(list(takewhile(lambda r: r["resumed_from"], rs)))}
        if not rs:
            e["estado"] = "pendiente"
            out.append(e)
            continue
        latest = rs[0]
        if latest["status"] in ("queued", "running"):
            e["estado"] = "corriendo"
        elif latest["status"] == "success" and latest["artifact_state"] in ("ok", "parcial"):
            e["estado"] = latest["artifact_state"]
        else:
            e["estado"] = "error"
        e["en"] = latest["finished_at"] or latest["started_at"]
        e["duracion_s"] = seconds(latest["started_at"], latest["finished_at"])
        if e["estado"] == "error":
            if latest["artifact_path"]:
                e["motivo"] = latest["artifact_path"]
            elif latest["status"] == "success":
                e["motivo"] = LEGACY_NO_STAMP_REASON
            else:
                e["motivo"] = NO_STAMP_REASON
        else:
            # Only while running, and only in the detail view: it's a disk read, and the
            # list turns the footprint off for exactly that reason. Once finished, "19 of
            # 19" says nothing the green check doesn't.
            if with_footprint and name == "implement" and e["estado"] == "corriendo":
                e["progreso"] = task_progress(t, runs)
            if e["estado"] == "parcial" and latest.get("artifact_note"):
                e["motivo"] = latest["artifact_note"]
            if e["estado"] in ("ok", "parcial") and latest["artifact_path"] and with_footprint:
                e["huella"] = stamp_stat(t["repo_path"], latest["artifact_path"])
                pend = open_decisions(t, latest["artifact_path"])
                if pend:
                    e["decisiones"] = pend
        out.append(e)
    return out


def folded_status(phases: list[dict]) -> str:
    """The list's label, folded from the same phases the detail view sees. Stops
    depending on a column that used to get overwritten on every run."""
    if any(f.get("estado") == "corriendo" for f in phases):
        return "running"
    done = [f for f in phases if f.get("estado") in ("ok", "parcial")]
    if done:
        return PHASE_DONE[done[-1]["fase"]]
    if any(f.get("estado") == "error" for f in phases):
        return "error"
    return "queued"


def ticket_out(t: sqlite3.Row, phases: list[dict]) -> dict:
    # `fases` travels here so every producer (POST /tickets, GET /tickets, and the
    # `.ticket` object inside GET /tickets/{tid}) agrees: the frontend's `Ticket` type
    # declares it required, and `json<T>()` never checks that at runtime.
    return {**dict(t), "status": folded_status(phases), "fases": phases}


@app.get("/tickets")
def list_tickets():
    with db() as c:
        ts = c.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
        runs = [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC")]
    # ponytail: all runs are fetched at once and grouped in memory; with thousands of
    # tickets this would need a per-ticket query or a GROUP BY. It's a local queue.
    out = []
    for t in ts:
        # The footprint stays off: it's the part that touches disk, and the list doesn't
        # show artifacts. The phases themselves are cheap and the stepper needs them —
        # the folded `status` says `error` without saying which phase failed.
        ph = phases_for(t, [r for r in runs if r["ticket_id"] == t["id"]], with_footprint=False)
        out.append(ticket_out(t, ph))
    return out


@app.get("/tickets/{tid}")
def get_ticket(tid: int):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    with db() as c:
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM runs WHERE ticket_id=? ORDER BY id DESC", (tid,))]
    tail = ""
    if runs and runs[0]["log_path"] and Path(runs[0]["log_path"]).exists():
        tail = Path(runs[0]["log_path"]).read_text(encoding="utf-8", errors="replace")[-8000:]
    phases = phases_for(t, runs)
    return {"ticket": ticket_out(t, phases), "fases": phases, "runs": runs, "log_tail": tail}


@app.delete("/tickets/{tid}", status_code=204)
def delete_ticket(tid: int):
    if not ticket_row(tid):
        raise HTTPException(404)
    with db() as c:
        for r in c.execute("SELECT log_path FROM runs WHERE ticket_id=?", (tid,)):
            if r["log_path"]:
                Path(r["log_path"]).unlink(missing_ok=True)
        c.execute("DELETE FROM tickets WHERE id=?", (tid,))


@app.get("/runs/active")
def active_run():
    """The run currently in flight, if there is one. The lock is global, so the UI
    needs this to explain why it can't launch a ticket from ANOTHER project."""
    with db() as c:
        r = c.execute(
            "SELECT r.id, r.ticket_id, r.started_at, t.ado_id, t.project "
            "FROM runs r JOIN tickets t ON t.id = r.ticket_id "
            "WHERE r.status IN ('queued','running') ORDER BY r.id LIMIT 1"
        ).fetchone()
    return dict(r) if r else None


async def spawn_cli(cmd, cwd, env, log, run_id: int | None) -> bool:
    """Runs one CLI child, streaming into the already-open log. True if it exited 0.

    `run_id` None means "don't record the session": a fan-out run drives several
    sessions and there is no single one to continue, so `puede_continuar` stays false
    for that phase on its own, with no special case anywhere else.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    assert proc.stdout is not None
    # In chunks, not lines: asyncio's line reader blows up with "Separator is found,
    # but chunk is longer than limit" at 64 KiB, and stream-json passes lines longer
    # than that as soon as the agent writes a large file. It really happened: a good
    # run from 3322 ended up marked as an error. The incremental decoder avoids
    # splitting a character across two chunks.
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    # The FIRST match wins, the opposite of `STAMP_RE`: the id is unique and stable for
    # the whole run, so waiting for the last one would mean waiting for the end — and a
    # run that dies halfway is precisely one worth continuing. `carry` covers the id
    # landing astride two chunks: untested on purpose, because a pipe read can return
    # short and that boundary can't be placed deterministically from a test.
    sid, carry = None, ""
    while chunk := await proc.stdout.read(65536):
        text = dec.decode(chunk)
        log.write(text)
        if run_id is not None and sid is None:
            m = SESSION_RE.search(carry + text)
            if m:
                sid = m.group(1)
                set_run(run_id, session_id=sid)
            else:
                carry = (carry + text)[-64:]
        log.flush()
    log.write(dec.decode(b"", True))
    return (await proc.wait()) == 0


async def run_fan_out(children, env, log, log_path: Path, scratch: Path) -> bool:
    """Runs one child per routed repo, in sequence, all into the same log.

    Sequential on purpose: the global lock keeps meaning something, one log preserves
    live progress in the UI, and one row in `runs` means no schema change. Running them
    in parallel is a later optimization, and it's when `runs` would need a parent.

    A child that fails does NOT abort the rest. What it must never do is disappear:
    `consolidate` receives which repos were surveyed and which failed, because an
    analysis that looks complete and isn't is this system's most expensive failure.
    """
    verdicts = []
    for label, cwd, cmd in children:
        log.write(f"\n\n===== survey: {label} ({cwd}) =====\n$ {' '.join(cmd)}\n\n")
        log.flush()
        start = log_path.stat().st_size
        try:
            exited_ok = await spawn_cli(cmd, cwd, env, log, None)
        except Exception as exc:
            log.write(f"\n[orchestrator] {label}: excepción: {exc}\n")
            exited_ok = False
        log.flush()
        # Each child's verdict is read from ITS stretch of the log. The last stamp of
        # the whole file is only the last child's — reading that would let one good
        # survey vouch for every failed one before it.
        with open(log_path, "rb") as fh:
            fh.seek(start)
            section = fh.read().decode("utf-8", errors="replace")
        stamp = stamp_in(section) if exited_ok else None
        verdicts.append((label, stamp[0] if stamp else "nada"))
    good = [label for label, state in verdicts if state in ("ok", "parcial")]
    failed = [label for label, state in verdicts if state not in ("ok", "parcial")]
    log.write("\n\n[orchestrator] sondeados: " + (", ".join(good) or "ninguno"))
    if failed:
        log.write(" · fallaron: " + ", ".join(failed))
    log.write("\n")
    # The run's own stamp, written by the runner and not by any child: the phase's
    # verdict is the set of them, and no single child can speak for it. It goes last so
    # `read_stamp`, which anchors on the final match, finds this one and not a child's.
    if not good:
        log.write(f"HUELLA: nada — ningún repo pudo sondearse ({', '.join(failed)})\n")
    elif failed:
        log.write(f"HUELLA: parcial — {scratch.as_posix()} · "
                  f"{len(good)}/{len(verdicts)} sondeados, falló {', '.join(failed)}\n")
    else:
        log.write(f"HUELLA: ok — {scratch.as_posix()}\n")
    log.flush()
    return bool(good)


RUN_LOCK = asyncio.Lock()


def claude_cmd() -> list[str]:
    raw = os.environ.get("ORCH_CLAUDE_CMD")
    if raw:
        return json.loads(raw)
    exe = shutil.which("claude")
    if not exe:
        raise HTTPException(500, "No se encontró el CLI 'claude' en el PATH")
    return [exe]


def model_for(phase: str) -> list[str]:
    cfg = phase_configs()[phase]
    return ([*(["--model", cfg["model"]] if cfg["model"] else []),
             *(["--effort", cfg["effort"]] if cfg["effort"] else [])])


def set_run(run_id: int, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def set_ticket(tid: int, **fields):
    """The `status` column is still in the table for old DBs, but it's no longer
    written or read: the ticket's state is folded from `runs` in `ticket_out`. A second
    source is a source that will lie someday."""
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE tickets SET {cols} WHERE id=?", (*fields.values(), tid))


async def execute_run(run_id: int, ticket: dict, instructions: str | None, phase: str,
                      resume: bool = False):
    async with RUN_LOCK:  # ponytail: global lock, could go per-repo if it ever hurts
        log_path = LOGS_DIR / f"{run_id}.log"
        set_run(run_id, status="running", log_path=str(log_path), started_at=now())
        set_ticket(ticket["id"])
        # Repo preparation goes HERE, under the lock and right before launching the
        # subprocess, and not only in the POST. The POST's still exists —it's the one
        # that gives the immediate 409 without spending anything— but it can't be the
        # authoritative one for two real reasons: (1) its active-run check filters by
        # `ticket_id`, so two different tickets over the SAME physical repo both pass it
        # and switch each other's branch while the first one's agent is working; (2)
        # between the POST and the launch up to half an hour can pass waiting for the
        # lock, and the user may have edited files in that gap.
        branch = None
        if phase == "implement":
            try:
                branch = prepare_repos(ticket_repos(ticket), ticket["ado_id"])
            except Exception as exc:
                # We're inside a background task: an exception here reaches nobody and
                # would leave the run stuck in `running` forever. It's closed as an
                # error with a readable reason, through the same path already used by a
                # run with no stamp (`artifact_state='nada'`, reason in `artifact_path`,
                # which is where `phases_for` pulls it from for the UI).
                reason = "no se pudo preparar el repositorio: " + str(
                    getattr(exc, "detail", None) or exc)
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write(f"[orchestrator] {reason}\n")
                set_run(run_id, status="error", finished_at=now(),
                        artifact_state="nada", artifact_path=reason)
                set_ticket(ticket["id"])
                return
            # The branch that gets saved is the one prepared under the lock, not one
            # the POST deduced before waiting.
            set_run(run_id, branch=branch)
        noun = PHASE_NOUN[phase]
        # Resolved before the prompt is built, because the prompt has to name it: the
        # only phase whose whole job is reading the surveys was being launched with them
        # neither mounted nor named (found on run 3320, 2026-08-13).
        surveys = None
        if phase == "consolidate":
            surveys = last_survey_dir(ticket["id"])
            if not surveys or not Path(surveys).is_dir():
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write(f"[orchestrator] {NO_SURVEYS_REASON}\n")
                set_run(run_id, status="error", finished_at=now(),
                        artifact_state="nada", artifact_path=NO_SURVEYS_REASON)
                set_ticket(ticket["id"])
                return
        extras = normalize_dirs(json.loads(ticket.get("extra_dirs") or "[]"))
        prev = last_session(ticket["id"], phase) if resume else None
        if prev:
            # NOT the slash command. The session already ran the skill; sending it
            # again restarts the procedure from step 1 — rereads the work item,
            # reexplores, rewrites the deliverable — which is what continuing was
            # meant to avoid, and it can duplicate the output. `repos_text` is
            # dropped too: it's already in that context.
            # The stamp reminder is not optional: the runner demands the stamp on
            # every run, and without it a good continuation is marked as an error.
            prompt = (instructions or "") + RESUME_STAMP_REMINDER
            set_run(run_id, resumed_from=prev)
        else:
            prompt = f"{PHASE_COMMANDS[phase]} {ticket['ado_id']}"
            prompt += repos_text(phase, extras, noun, ticket_labels(ticket)[0][0])
            if surveys:
                # The list of repos NOT surveyed is as much a part of the input as the
                # surveys themselves: without it the consolidation can't write the line
                # that keeps the analysis from looking complete when it isn't.
                done = {p.stem.removeprefix("survey-") for p in Path(surveys).glob("survey-*.md")}
                missing = [label for label, _ in ticket_labels(ticket) if label not in done]
                prompt += CONSOLIDATE_PROMPT.format(
                    dir=Path(surveys).as_posix(),
                    surveyed=", ".join(sorted(done)) or "ninguno",
                    missing=(f"Mounted but NOT surveyed: {', '.join(missing)} — say so in "
                             "the analysis.\n") if missing else "")
            prompt += adjustment_text(phase, noun, instructions)
        # The fan-out replaces the single child with one per routed repo. It's built
        # before argv because each child gets its own prompt, its own cwd and its own
        # mounts — nothing of the single-child path survives except the flags.
        children, scratch = None, None
        if phase == "survey":
            brief_path = Path(ticket["repo_path"]) / BRIEF_REL.format(ado_id=ticket["ado_id"])
            if not brief_path.exists():
                with open(log_path, "w", encoding="utf-8") as log:
                    log.write(f"[orchestrator] {NO_BRIEF_REASON}: {brief_path}\n")
                set_run(run_id, status="error", finished_at=now(),
                        artifact_state="nada", artifact_path=NO_BRIEF_REASON)
                set_ticket(ticket["id"])
                return
            brief = brief_path.read_text(encoding="utf-8", errors="replace")
            labels = ticket_labels(ticket)
            routed = repos_to_survey(brief, [label for label, _ in labels])
            scratch = LOGS_DIR / str(run_id)
            scratch.mkdir(parents=True, exist_ok=True)
            children = []
            for label, path in labels:
                if label not in routed:
                    continue
                out = (scratch / f"survey-{label}.md").as_posix()
                child_prompt = SURVEY_PROMPT.format(
                    command=PHASE_COMMANDS[phase], ado_id=ticket["ado_id"],
                    label=label, path=path, out=out, brief=brief)
                child_prompt += adjustment_text(phase, noun, instructions)
                children.append((label, path, claude_cmd() + [
                    "-p", child_prompt,
                    "--output-format", "stream-json", "--verbose",
                    "--permission-mode", "acceptEdits",
                    "--allowedTools", "Read", "Glob", "Grep", "Task", "Write", "Edit",
                    *model_for(phase),
                    # The scratch is the ONLY thing mounted: it's the child's outbox.
                    # It holds no `.claude/`, so mounting it leaks no configuration —
                    # and the sibling repos are deliberately absent, because the whole
                    # point is a session that sees only its own repo's rules.
                    "--add-dir", scratch.as_posix(),
                ]))
        cmd = claude_cmd() + [
            "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            "--permission-mode", "acceptEdits",
            # In headless mode, acceptEdits does NOT auto-approve MCP tools: they get
            # denied on their own and the agent is left unable to read the work item.
            # The rest of the tools per phase come from PHASE_ALLOWED_TOOLS (see above).
            "--allowedTools", *(["mcp__azure-devops"] if phase in PHASE_MCP else []),
            "Read", "Glob", "Grep", "Task", "Write", "Edit",
            *PHASE_ALLOWED_TOOLS[phase],
            *settings_for(phase),
            # Read at launch time, not at startup: changing the model in Settings has
            # to affect the next run without restarting the backend.
            *model_for(phase),
            # Always forked: the original run's transcript stays intact and every row
            # of `runs` keeps its own id, so the chain is walkable in both directions.
            *(["--resume", prev, "--fork-session"] if prev else []),
        ]
        for e in extras:
            cmd += ["--add-dir", e["path"]]
        if surveys:
            cmd += ["--add-dir", Path(surveys).as_posix()]
        # Guarantees the CLI uses the logged-in subscription, never API billing:
        # without these variables, the only credential available is the local /login one.
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        # `--add-dir` grants file access, not configuration discovery: from a mounted
        # repo it loads `.claude/skills/` and `.claude/agents/`, but NOT its CLAUDE.md
        # nor `.claude/rules/`. Without this the agent writes the extra repo's code
        # under the PRIMARY repo's conventions — and having the wrong rules is worse
        # than having none, because it applies them with confidence.
        # Only in `implement`: it's where obeying them while writing is what matters,
        # and in Phase 1 the surveys already put them into the analysis in writing.
        # Hooks and `.mcp.json` of a mounted repo are NOT recovered by this, or by
        # anything else — only a session rooted in that repo has them.
        if extras and phase == "implement":
            env["CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD"] = "1"
        ok = False
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                # Never in silence: a continuation that quietly turns into a fresh run
                # reads, from outside, like the agent ignored the adjustment.
                if resume and not prev:
                    log.write(NO_SESSION_TO_RESUME)
                if children is None:
                    log.write(f"$ {' '.join(cmd)}\n\n")
                    log.flush()
                    ok = await spawn_cli(cmd, ticket["repo_path"], env, log, run_id)
                else:
                    ok = await run_fan_out(children, env, log, log_path, scratch)
        except Exception as exc:  # the error stays in the log, never brings down the server
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"\n[orchestrator] excepción: {exc}\n")
        # The exit code isn't enough: `claude -p` exits 0 even if the agent stopped
        # without writing anything. The skill's closing stamp is the only reliable
        # contract, and now every phase honors it.
        stamp = read_stamp(log_path) if ok else None
        state, rest = stamp or ("nada", NO_STAMP_REASON)
        if state == "nada":
            ok = False
        path, note = split_reserve(state, rest)
        set_run(run_id, status="success" if ok else "error", finished_at=now(),
                artifact_state=state, artifact_path=path, artifact_note=note)
        # The title travels with the analysis, so it only gets read when that phase
        # closes with a footprint. `title` is only written when one is found: a re-run
        # that comes out worse must not erase the title the previous one left.
        if phase == "analyze" and state in ("ok", "parcial"):
            # `DELETE /tickets/{tid}` has no guard against an in-flight run: the row
            # can be gone by the time this runs. `t` is bound and checked before
            # `read_title` touches it — `declared_file` does `t["id"]` unconditionally,
            # and a `None` row would blow up this background task with a TypeError
            # nobody catches.
            t = ticket_row(ticket["id"])
            if t and (title := read_title(t, path)):
                set_ticket(ticket["id"], title=title)
        set_ticket(ticket["id"])   # only touches updated_at: the state is computed on read


@app.post("/tickets/{tid}/run", status_code=202)
def run_ticket(tid: int, body: RunIn, background: BackgroundTasks):
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    if body.phase not in PHASE_COMMANDS:
        raise HTTPException(400, f"La fase '{body.phase}' no es ejecutable todavía")
    with db() as c:
        active = c.execute(
            "SELECT 1 FROM runs WHERE ticket_id=? AND status IN ('queued','running')", (tid,)
        ).fetchone()
    if active:
        raise HTTPException(409, "Este ticket ya tiene una corrida activa")
    if body.phase == "implement":
        # The guard, here: it's the one that returns the immediate 409 without spending
        # a subprocess or leaving a run queued, and the design calls for that property.
        # What does NOT happen here is switching branches: that occurs in `execute_run`,
        # under the lock (see there for why). This check is an early filter, not the
        # authoritative one.
        check_clean(ticket_repos(t))
    with db() as c:
        cur = c.execute(
            "INSERT INTO runs(ticket_id, phase, instructions, status) "
            "VALUES(?,?,?,'queued')",
            (tid, body.phase, body.instructions),
        )
        run_id = cur.lastrowid
    set_ticket(tid)
    background.add_task(execute_run, run_id, dict(t), body.instructions, body.phase,
                        body.resume)
    with db() as c:
        return dict(c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())


def declared_file(t: sqlite3.Row, ruta: str) -> Path:
    """Resolves `ruta` against the ticket's main repo and enforces the three rules that
    make a path servable: declared by a run OF THIS ticket (or under a declared
    directory, at any depth), inside the ticket's repos, and a regular file.

    Extracted from `GET /tickets/{tid}/artefacto`, where it lived inline, because the
    ticket's title and the task-progress counter need the same check from outside the
    endpoint. **Moved, not rewritten**: same body, same order of checks, same messages.
    That code took three rounds of adversarial review and 638 vectors, and each round
    closed a hole the previous one had opened.

    The cap and the read stay in the endpoint: those are about serving a file, not about
    deciding whether it may be read.

    **`t` must be a row from `ticket_row`.** The extraction moved the ticket's scope out
    of a path parameter and onto the caller's row: the declared-paths query is filtered
    by `t["id"]`. A caller handing over a hand-built or partial mapping gets a `KeyError`
    if the column is missing, or — silently, which is worse — a query scoped to the wrong
    ticket if the `id` doesn't match the ticket whose files are being served.
    """
    with db() as c:
        declared = [r["artifact_path"] for r in c.execute(
            "SELECT artifact_path FROM runs WHERE ticket_id=? AND artifact_path IS NOT NULL "
            "AND artifact_path != '' AND artifact_state IN ('ok','parcial')", (t["id"],))]
            # ^ '' in addition to NULL as belt and suspenders — the real property that
            # discards wildcards lives further below, when building `real_declared`.

    # The ticket's roots: the main repo and the extras. Computed once and used
    # twice — to decide which declared paths count as a real footprint and,
    # further below, for rule 2.
    roots = [Path(t["repo_path"]).resolve()]
    roots += [Path(d["path"]).resolve() for d in normalize_dirs(json.loads(t["extra_dirs"] or "[]"))]

    # Resolved ONCE, BEFORE comparing anything: comparing over an unresolved
    # PurePosixPath (as rule 1 did before round 1 of the fixes) does NOT normalize
    # `..`, so "dir/../../../fuera" still had "dir" among its `.parents` and slipped
    # through as if it were a real descendant of a declared directory. Resolving first
    # closes that, the absolute/relative asymmetry, and Windows' case-insensitivity.
    #
    # `ruta` comes straight out of the query string: a null byte or an absurdly long
    # path makes `resolve()` blow up with `ValueError`/`OSError` uncaught, and without
    # catching it that was a 500 instead of the 400 that fits invalid client input.
    try:
        real = (Path(t["repo_path"]) / ruta).resolve()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, f"Ruta inválida: {exc}")

    # 1. Declared by a run OF THIS TICKET, or a file UNDER a declared directory — at
    #    any depth, not just a direct child: `stamp_stat` (Task 3) counts recursively
    #    because an OpenSpec change nests `specs/<capability>/spec.md`, and
    #    `huella.nombres` is exactly the allowlist the UI offers. Admitting only direct
    #    children would reject with 400 the very buttons the backend itself offered.
    #
    #    Filtering wildcards by SPELLING ('', '.', '..', 'docs/..', '   ') is a cat and
    #    mouse game: review round 2 found four more forms as soon as the comparison
    #    moved to resolved paths. The property that actually matters is different: a
    #    declared path only counts as a footprint if, ONCE RESOLVED, it lands STRICTLY
    #    inside some root of the ticket — it's neither the root itself (`..` resolves
    #    to the whole repo) nor above it. Whatever doesn't satisfy that isn't a
    #    footprint, it's a wildcard, and it's discarded here, before comparing against
    #    `real`.
    #
    #    Two questions, NOT one: `any(rd != r and r in rd.parents for r in roots)`
    #    (round 2) merged them into a single `any`, and with nested roots — an
    #    `extra_dir` that is an ANCESTOR of `repo_path`, the real monorepo case
    #    (primary `Tenant/src/Web`, extra `Tenant`; `check_dirs` accepts it without
    #    objection because it only checks `is_dir`) — it was enough for the declared
    #    path to land inside SOME root, even if THAT root was another root: `.`
    #    resolves to the primary repo, which sits strictly inside the extra, and it
    #    slipped through as a footprint again. First, whatever IS a root or sits ABOVE
    #    any of them gets discarded; only what survives that gets checked by
    #    containment. That order is what fixes the nested case: a declared path that
    #    resolves to the primary root gets discarded in the first step even if it's
    #    inside the extra.
    real_declared = []
    for d in declared:
        if not d:
            continue
        rd = (Path(t["repo_path"]) / d).resolve()
        if any(rd == r or rd in r.parents for r in roots):
            continue                      # it's a root, or contains one: wildcard, discard it
        if any(r in rd.parents for r in roots):
            real_declared.append(rd)  # strictly inside some root: valid
    if not any(real == d or d in real.parents for d in real_declared):
        raise HTTPException(400, "Esa ruta no la declaró ninguna corrida de este ticket")

    # 2. Falls inside the main repo or the ticket's extras. resolve() follows symlinks,
    #    so a symlink pointing outside dies here.
    if not any(real == r or r in real.parents for r in roots):
        raise HTTPException(400, "Esa ruta cae fuera de los repos del ticket")

    # 3. Regular file: neither a directory nor a device.
    if not real.is_file():
        raise HTTPException(400, "No es un archivo regular")

    return real


def declared_file_or_none(t: sqlite3.Row, ruta: str) -> Path | None:
    """The same check for internal consumers, which want `None` and not a 400.

    A separate door to disk is exactly what must NOT exist here: this is a wrapper, so
    a fix to `declared_file` reaches every caller at once.
    """
    try:
        return declared_file(t, ruta)
    except HTTPException:
        return None


ARTIFACT_CAP = 512 * 1024


@app.get("/tickets/{tid}/artefacto")
def artifact(tid: int, ruta: str):
    """Reads from disk starting from a request parameter, so validation can't be
    simplified. It's not a file explorer: it's "show me what THIS run said it wrote"."""
    t = ticket_row(tid)
    if not t:
        raise HTTPException(404)
    real = declared_file(t, ruta)

    # Cap, without loading the whole file into memory: reads at most CAP+4 bytes
    #    instead of the whole file, to avoid paying a memory peak equal to the full
    #    artifact size just to serve 0.5 KB of it. The real size (for the `bytes`
    #    field) comes from `stat()`, not from what was read — and that's why
    #    `truncated` ALSO requires that the read buffer exceed the cap: if the file
    #    shrinks between the `stat()` and the `read()` (a run rewriting the artifact
    #    while the UI is looking at it), the cut index can't go past the buffer that
    #    was actually read and blow up with `IndexError`. Backing off to a byte that
    #    isn't a continuation byte (0b10xxxxxx) still stands: cutting blindly splits a
    #    multibyte character in half.
    size = real.stat().st_size
    with open(real, "rb") as fh:
        raw = fh.read(ARTIFACT_CAP + 4)
    truncated = size > ARTIFACT_CAP and len(raw) > ARTIFACT_CAP
    cut = ARTIFACT_CAP
    while truncated and cut > 0 and (raw[cut] & 0xC0) == 0x80:
        cut -= 1
    text = (raw[:cut] if truncated else raw).decode("utf-8", "replace")
    return {"ruta": ruta, "texto": text, "bytes": size, "truncado": truncated}
