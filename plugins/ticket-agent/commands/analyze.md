---
description: Fully analyzes and understands an Azure DevOps work item by its ID, producing a structured analysis in docs/tickets/
---

Analyze Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:ticket-comprehension` skill and follow it to the
letter: project configuration, read-only collection (work item, comments,
1-level relations, attachments, wiki, project rules, affected code), structured
analysis in `docs/tickets/<id>-analysis.md`, and closing per the configured
autonomy level.

If "$ARGUMENTS" is a work item number or an `R-` key (`R-7`, `R-form-clientes`),
analyze that id. If it is prose — a described need, not an id — derive a short
kebab-case slug from it, write the prose verbatim to
`docs/tickets/R-<slug>-request.md` (pick a different slug if that file already
exists; never overwrite), and continue as if you had been given `R-<slug>`. If
"$ARGUMENTS" is empty, ask for the ID or the request and stop.
