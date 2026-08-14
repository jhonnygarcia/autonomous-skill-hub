---
description: Reads an Azure DevOps work item and decides which of the mounted repos deserve a survey
---

Write the brief for Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:ticket-brief` skill and follow it to the letter:
project configuration, read-only collection (work item, comments, 1-level
relations, attachments, wiki), the brief in `docs/tickets/<id>-brief.md` with
the acceptance criteria verbatim, the `SONDEAR:` routing line, and closing per
the configured autonomy level.

Don't analyze code. Each routed repo gets its own session, rooted in it, which
is the only one that sees that repo's rules — doing it from here would put the
primary repo's conventions in front of every repo.

If "$ARGUMENTS" is empty, or is neither a work item number nor an `R-` key
(`R-7`, `R-form-clientes`), ask for the ID and stop.
