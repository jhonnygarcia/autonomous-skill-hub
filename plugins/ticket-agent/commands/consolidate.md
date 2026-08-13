---
description: Merges the per-repo surveys into a single analysis, with the contract between them
---

Consolidate the surveys for Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:analysis-consolidation` skill and follow it to the
letter: read the brief and every survey, collate `Espero de otros` against
`Ofrezco a otros`, and write `docs/tickets/<id>-analysis.md` with the contract
table, the surveys as an appendix, and the open decisions.

**The contract table is the deliverable.** It's the only thing no repo could
write on its own, and it's what justifies having run one session per repo. If
you can't produce it, close `parcial` — never `ok`.

Name every mounted repo that wasn't surveyed. An analysis that looks complete
and isn't is this system's most expensive failure: the next phase consumes it
without knowing.

If "$ARGUMENTS" is empty or not a work item number, ask for the ID and stop.
