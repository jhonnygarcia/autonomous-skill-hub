# Installing ticket-agent

From nothing to `/ticket-agent:analyze 3311` running in a project of yours. Four
steps, ten minutes, and most of that is the Azure credential.

The plugin installs no dependencies and touches nothing global: it adds six slash
commands to Claude Code and reads two JSON files from *your* project. Everything
else on this page is a prerequisite it assumes is already there.

## The short version

If you have Claude Code, Node and an `az login` session, this is the entire install:

    # 1 — in any Claude Code session
    /plugin marketplace add jhonnygarcia/autonomous-skill-hub
    /plugin install ticket-agent@autonomous-skill-hub

    # 2 — in the project you want to use it in
    .claude/settings.json       →  { "env": { "ADO_ORG": "your-org" } }
    .claude/ticket-agent.json   →  { "organization": "your-org", "project": "Your Project" }

    # 3 — restart Claude Code, then
    /ticket-agent:analyze 3311

Step 2 is for running the plugin **standalone**. Driven through the orchestrator app
instead, both files are supplied for you — see Step 4's note.

The rest of the page is the same four steps with the reasons, the token
alternative, and what each failure actually means.

---

## Step 1 · Prerequisites

Check these first. Every one of them fails *later*, disguised as something else.

| What | Check it with | Why it's needed |
|---|---|---|
| **Claude Code** | `claude --version` | [install it](https://claude.com/claude-code) if missing |
| **Node 20+ with `npx`** | `npx --version` | the Azure DevOps MCP server and the OpenSpec CLI are both downloaded on demand — no npm access, no Phase 1 |
| **Git identity** | `git config user.name` | Phase 3 makes one commit per task |
| **Azure DevOps access** | an `az login` session **or** a PAT | either works — step 3 sets it up |

You do **not** need an Anthropic API key: everything runs on the Claude Code CLI
subscription. You do **not** need an `openspec/` folder in the target repo — Phase 2
creates it.

## Step 2 · Install the plugin

**Two lines in any Claude Code session, and you're installed:**

    /plugin marketplace add jhonnygarcia/autonomous-skill-hub
    /plugin install ticket-agent@autonomous-skill-hub

That's the whole step. The rest of this section is what those two lines mean.

**Why two.** A *marketplace* is just a git repo holding a catalog of plugins. The
first line registers this repo as one — it clones it and reads the catalog,
installing nothing. The second picks one plugin out of that catalog and installs it.
You add the marketplace once per machine; installing from it afterwards is one line.

**The `@autonomous-skill-hub` suffix isn't decoration.** `ticket-agent` is the
plugin, `autonomous-skill-hub` is the marketplace it came from. Two marketplaces can
offer the same plugin name, so the install — and later the update — wants both.

**From a terminal instead**, with no session open, the same words minus the slash —
and there you can chain them into one line:

    claude plugin marketplace add jhonnygarcia/autonomous-skill-hub && \
      claude plugin install ticket-agent@autonomous-skill-hub

There is no single command that does both: `install` only searches marketplaces that
are already registered, so `ticket-agent@jhonnygarcia/autonomous-skill-hub` fails
with *plugin not found* even though the syntax is accepted.

**This repo is a monorepo** — it also holds a FastAPI + React app you don't need. To
clone only what the plugin install requires:

    claude plugin marketplace add jhonnygarcia/autonomous-skill-hub \
      --sparse .claude-plugin plugins

**Three ways to name the marketplace.** `owner/repo` is the shorthand and the normal
case; the other two exist for what the shorthand can't reach:

| Form | Example | Use it when |
|---|---|---|
| `owner/repo` | `jhonnygarcia/autonomous-skill-hub` | it's on GitHub. The normal case |
| full URL | `https://github.com/jhonnygarcia/autonomous-skill-hub` | another git host, or a private repo over SSH |
| local path | `D:\code\autonomous-skill-hub` | you cloned it and want to edit the skills and try them without pushing |

**Check it landed** with `claude plugin list` — `ticket-agent` should be there with
its version. They won't *appear* as slash commands until you restart, which step 4
does anyway.

### Where it installs

**Not in your project.** By default everything goes under your user directory:

    ~/.claude/plugins/                  # Windows: C:\Users\<you>\.claude\plugins\
      known_marketplaces.json           # the marketplaces you added
      marketplaces/                     # their clones — this repo lands here
      installed_plugins.json            # what you installed, and from where
      cache/

Your project stays untouched by the install. The only files this plugin ever puts in
a repo of yours are the two you write yourself in step 4 — plus the deliverables it
produces later (`docs/tickets/`, `openspec/changes/`).

That's the `user` scope, the default, and it's what you want on your own machine:
install once, and the commands exist in **every** repo you open. `--scope` changes
that when you need it:

| `--scope` | Recorded in | Use it for |
|---|---|---|
| `user` *(default)* | `~/.claude/` | your machine. Every repo you open |
| `project` | the repo's `.claude/settings.json` — **committable** | putting the whole team on the same plugin: they get it when they clone |
| `local` | the repo's `.claude/settings.local.json` — gitignored | just you, just this repo, without touching your teammates |

The `project` scope is worth knowing about: it writes `extraKnownMarketplaces` and
`enabledPlugins` into the repo's settings, so a teammate who clones the repo gets the
marketplace and the plugin without following this page at all.

    claude plugin marketplace add jhonnygarcia/autonomous-skill-hub --scope project
    claude plugin install ticket-agent@autonomous-skill-hub --scope project

**Uninstalling** is symmetrical, and leaves your repos alone:

    claude plugin uninstall ticket-agent@autonomous-skill-hub
    claude plugin marketplace remove autonomous-skill-hub

## Step 3 · Pick how it authenticates

Two ways in. Decide now, because the answer changes what you write in step 4.

| | Option A — Azure CLI | Option B — token (PAT) |
|---|---|---|
| Credential lives in | your `az login` session | an environment variable or a gitignored file |
| Set up | nothing to configure | create a PAT, set two variables |
| Right for | your own machine | no Azure CLI, a build agent, unattended runs |

### Option A · the Azure CLI session (default)

Nothing to configure — with `ADO_AUTH` unset this is what happens. Just verify it,
because a missing credential looks *exactly* like a misconfigured org: the agent
reports "MCP not connected" and sends you to edit the wrong file.

    az login
    az account show
    az devops project list --org https://dev.azure.com/your-org

**If that third command lists projects, the plugin will connect.** If it returns
`TF400813 ... is not authorized`, the org lives in a different Entra tenant than
your default one — `az login --tenant <tenant-id>` is the fix.

### Option B · a personal access token

**Create the PAT** in Azure DevOps: *User settings → Personal access tokens → New
token*, scoped to **Work Items (read)**, **Code (read)** and **Wiki (read)**. Nothing
more: the plugin never writes to Azure DevOps, and Phase 3 doesn't push.

**Then two variables — and they go in different places on purpose.** `ADO_AUTH`
selects the mode and is safe to commit; the token is not:

    // .claude/settings.json — committable, next to ADO_ORG
    {
      "env": {
        "ADO_ORG": "cr360dev",
        "ADO_AUTH": "envvar"
      }
    }

    // .claude/settings.local.json — gitignored, NEVER committed
    {
      "env": {
        "ADO_MCP_AUTH_TOKEN": "abcd1234...your-pat"
      }
    }

Confirm the second file really is ignored before pasting a token into it:

    git check-ignore -v .claude/settings.local.json

**Or keep the secret out of the repo entirely** with a real environment variable —
the plugin reads it identically, and this is the better option on a shared machine:

    # PowerShell — this session
    $env:ADO_MCP_AUTH_TOKEN = "abcd1234..."
    # PowerShell — persistent, for your user
    [Environment]::SetEnvironmentVariable("ADO_MCP_AUTH_TOKEN", "abcd1234...", "User")

    # bash / zsh
    export ADO_MCP_AUTH_TOKEN="abcd1234..."

**The four modes**, for reference — `envvar` is the one to use:

| `ADO_AUTH` | Token variable | Format | Notes |
|---|---|---|---|
| *(unset)* / `azcli` | — | the `az login` session | the default; nothing stored anywhere |
| `envvar` | `ADO_MCP_AUTH_TOKEN` | the PAT, plain | **use this one** |
| `pat` | `PERSONAL_ACCESS_TOKEN` | base64 of `email:pat` | legacy; you encode it by hand |
| `interactive` | — | opens a browser | hangs when headless — never for automation |

Two things about PATs worth knowing before they surprise you: they **expire** (a run
that worked yesterday and 401s today is the expiry, not your config), and each one is
scoped to **one organization** — a second org needs a second token.

Leaving the token path is just removing `ADO_AUTH`: unset, you're back on `az login`.

## Step 4 · Point it at your project

The plugin is installed but knows nothing about your organization. It reads that from
**the repo you run it in**, not from a global config — which is what lets different
repos target different Azure DevOps organizations.

**This step is for running the plugin standalone.** If a repo is driven through the
orchestrator app (`apps/orchestrator/`), it supplies both of these for you at launch
time: `ADO_ORG` as a fallback (only when the repo doesn't already export one) and
`.claude/ticket-agent.json` created from the project's saved `org`/`project` when it's
missing — never overwriting a file you already committed. See `CLAUDE.md`'s
Orchestrator section ("the runner supplies what the target repo is missing") for the
mechanism. Standalone use (no orchestrator, just `claude` in a terminal) still needs
both set up by hand, exactly as below.

**`.claude/settings.json`** — what the MCP server connects with (add `ADO_AUTH` here
too if you chose Option B):

    {
      "env": { "ADO_ORG": "your-org" }
    }

**`.claude/ticket-agent.json`** — what the skills read. Committable, no secrets:

    {
      "organization": "your-org",
      "project": "Your Project Name",
      "autonomy": "supervised",
      "subagent_model": "sonnet"
    }

Three things that bite everyone once:

- **`organization` must equal `ADO_ORG`.** Nothing validates it. When they diverge,
  the MCP connects to one org while the skill queries a project in another — and the
  error, "MCP not connected", points you at the wrong file.
- **`project` is the display name: spaces, decoded.** Copy it from the work item URL
  and undo the escaping — `.../CallRevu%20Development%20Lifecycle%20Management/...`
  goes in as `"CallRevu Development Lifecycle Management"`.
- **The org is the subdomain.** A legacy `https://cr360dev.visualstudio.com` account
  is `"cr360dev"` — same account, modern alias.

The two optional keys: `autonomy` (`supervised` by default, and anything unrecognized
means `supervised`) decides whether an unanswered `DECIDIR` stops the next phase or
lets it proceed with the proposal on record; `subagent_model` picks the model for the
per-task subagents Phase 3 launches.

**Now restart Claude Code.** The slash commands and the MCP server — with your org
baked in — register at session start.

## Step 5 · The first run

    /ticket-agent:analyze 3311

Writes `docs/tickets/3311-analysis.md` in your repo, and stops. Read it, correct what
it got wrong, answer the `## Decisiones para ti` list at the bottom by ticking boxes.
Then, when you're happy with it:

    /ticket-agent:plan 3311        # → openspec/changes/3311-<slug>/
    /ticket-agent:implement 3311   # → commits on branch ticket-agent/3311

**Nothing chains itself.** Each command is its own run, with a file on disk in
between for you to read and correct. Phase 3 stops on a branch with commits — no
push, no PR; you decide what goes out.

From here on it's **[USAGE.md](USAGE.md)**: each stage with examples, how you answer
the open decisions, the multi-repo route, and every configuration key.

Optional, and separate: the hub also holds a **local app** that queues tickets and
presses these buttons for you. It isn't installed through the marketplace — you
download a release or clone the repo, and run it on your own machine. See
[RELEASE.md](RELEASE.md). The plugin doesn't need it.

## Updating

The plugin's `version` is the cache key: if it hasn't moved, `update` brings nothing.
Refresh the catalog first, then the plugin:

    claude plugin marketplace update autonomous-skill-hub
    claude plugin update ticket-agent@autonomous-skill-hub

## When it doesn't work

**Installing** (step 2):

| It says | What it actually is |
|---|---|
| marketplace not found / 404 | typo in `owner/repo` — it's case-sensitive — or no network |
| plugin not found | the `@autonomous-skill-hub` suffix is missing |
| marketplace already exists | it's added already; go straight to the install line |
| an update changes nothing | `version` didn't move, or you skipped `marketplace update` |

**Running** (steps 3–5):

| Symptom | Almost always |
|---|---|
| the `/ticket-agent:*` commands don't exist | Claude Code wasn't restarted |
| "MCP not connected" | the credential (step 3), or `organization` ≠ `ADO_ORG` |
| 401 on a run that worked yesterday | the PAT expired, or the variable isn't reaching the session |
| `TF400813 ... is not authorized` | wrong Entra tenant — `az login --tenant <id>` |
| `HUELLA: nada — npx unavailable` | no Node, or no access to the npm registry |
| works in one repo, not in another | the two files in step 4 are per-repo; the other repo has neither |

That last row is the one worth internalizing: **installing the plugin is not
configuring a repo.** The plugin is per-user, the configuration is per-project.
