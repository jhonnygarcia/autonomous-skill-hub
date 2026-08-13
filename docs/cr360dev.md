# cr360dev — a second Azure DevOps organization

Reference notes from wiring `ticket-agent` to a second org on 2026-08-12, kept
because the next org will raise the same questions. Everything below was executed,
not inferred.

**No credential lives in this file, and none should.** See "The token" for where it
belongs.

## The coordinates

| | |
|---|---|
| Browser URL | `https://cr360dev.visualstudio.com` |
| Org name (what the MCP wants) | `cr360dev` |
| Project | `CallRevu Development Lifecycle Management` |
| Verification ticket | `44647` — User Story, *SAV \| Insights Trend Report \| Excel Export Functionality* |

Two things that trip people up, both confirmed against the live API:

**The legacy URL is not a different system.** `cr360dev.visualstudio.com` and
`dev.azure.com/cr360dev` are the same account; the MCP builds the second from the
org name. Nothing special is needed for a `visualstudio.com` account.

**The project name carries spaces and travels verbatim.** The URL shows
`CallRevu%20Development%20Lifecycle%20Management`; the config takes
`"CallRevu Development Lifecycle Management"`, decoded. Percent-encoding is the
browser's, not the API's.

## Configuration in the target repo

```jsonc
// .claude/settings.json — committable
{ "env": { "ADO_ORG": "cr360dev", "ADO_AUTH": "envvar" } }

// .claude/settings.local.json — gitignored, never committed
{ "env": { "ADO_MCP_AUTH_TOKEN": "<pat>" } }

// .claude/ticket-agent.json — committable
{
  "organization": "cr360dev",
  "project": "CallRevu Development Lifecycle Management",
  "autonomy": "supervised"
}
```

Restart Claude Code afterwards: the MCP reads the org at startup.

`ADO_AUTH` is what `.mcp.json` expands as `${ADO_AUTH:-azcli}`. Unset, the plugin
behaves as it always did and authenticates through `az login`.

**Nothing validates that `ADO_ORG` and `organization` agree.** If they diverge, the
MCP connects to one org while the skill queries a project from another, and the
skill reports it as "MCP not connected" — which sends you to the wrong file.

## The token

A PAT with **Work Items (read)**, **Code (read)** and **Wiki (read)**. Phase 2b
never pushes, so Code (write) isn't needed.

Created at `https://cr360dev.visualstudio.com/_usersSettings/tokens`.

Where it goes, in order of preference:

1. A real environment variable on the machine — the secret never touches the repo.
2. `.claude/settings.local.json`, which is gitignored.

Never `.claude/settings.json`. A PAT there is a leaked credential the day someone
commits it.

PATs expire. A run that worked yesterday and fails today with a 401, with no config
change in between, is the expiry — not the setup.

> The PAT used for the 2026-08-12 verification was pasted into a session transcript
> and must be treated as burned. Rotate it; see `STATUS.md`.

## How it was verified

Three levels, each one proving something the previous one didn't:

**1 & 2 — the credential, both auth modes.** `GET /_apis/wit/workitems/44647` with
`Authorization: Basic base64(":" + pat)` (what `--authentication pat` does) and again
with `Authorization: Bearer <pat>` (what `envvar` does). Both returned the work item.
The second is the one that matters: it proves the mode we actually configured.

**3 — the MCP itself.** The server started with the real flags and driven over
stdio, which is exactly what the plugin does:

```powershell
$env:ADO_MCP_AUTH_TOKEN = '<pat>'
$lines = @(
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}',
  '{"jsonrpc":"2.0","method":"notifications/initialized"}',
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"wit_work_item","arguments":{"action":"get","id":44647,"project":"CallRevu Development Lifecycle Management"}}}'
)
$lines | npx -y '@azure-devops/mcp' cr360dev --authentication envvar -d core work-items
```

It returned work item 44647 with its fields. Levels 1 and 2 only prove the token is
valid; level 3 proves the whole chain the plugin depends on.

Quicker smoke test, when you only need to know whether a credential reaches an org:

```powershell
az account show
az devops project list --org https://dev.azure.com/cr360dev
```

If the second lists projects, the MCP will connect. If the org sits in a different
Entra tenant than your default, `az login --tenant <tenant-id>` is what fixes a
`TF400813 ... is not authorized`.

## The authentication modes, in full

Read from `src/auth.ts` of `@azure-devops/mcp`, because the README doesn't document
them:

| `--authentication` | Token variable | Format |
|---|---|---|
| `azcli` | — | the `az login` session |
| `envvar` | `ADO_MCP_AUTH_TOKEN` | the PAT, plain (sent as Bearer) |
| `pat` | `PERSONAL_ACCESS_TOKEN` | base64 of `email:pat` (sent as Basic) |
| `env` | `ADO_MCP_AUTH_TOKEN` | same as `envvar` |
| `interactive` | — | opens a browser; **cannot work headless** |

`interactive` is the package's own default outside GitHub Codespaces, which is why
`.mcp.json` always passes the flag explicitly. Under the orchestrator it would hang
until the timeout.

`--tenant <id>` applies to `interactive` and `azcli` only.
