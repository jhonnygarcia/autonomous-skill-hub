---
description: Fully analyzes and understands an Azure DevOps work item by its ID, producing a structured analysis in docs/tickets/
---

Analyze Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:ticket-comprehension` skill and follow it to the
letter: project configuration, read-only collection (work item, comments,
1-level relations, attachments, wiki, project rules, affected code), structured
analysis in `docs/tickets/<id>-analysis.md`, and closing per the configured
autonomy level.

If "$ARGUMENTS" is empty or not a work item number, ask for the ID and stop.
