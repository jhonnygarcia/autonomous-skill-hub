---
description: Converts a work item's analysis into an executable change plan, in OpenSpec format
---

Plan the changes for Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:change-planning` skill and follow it to the letter:
preconditions (Phase 1's analysis and the `openspec/` folder), reading the
analysis, studying the pattern in the code, writing the change in
`openspec/changes/<id>-<slug>/`, validating the change with the OpenSpec CLI,
and closing per the configured autonomy level (the exact validation command
lives in the skill, not here).

Don't write product code — not implementation, not tests: this phase's deliverable
is the plan.

If "$ARGUMENTS" is empty or not a work item number, ask for the ID and stop.
