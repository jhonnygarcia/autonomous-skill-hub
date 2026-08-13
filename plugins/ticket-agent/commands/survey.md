---
description: Answers what a ticket demands of THIS repo, under THIS repo's rules
---

Survey this repo for Azure DevOps ticket "$ARGUMENTS".

Invoke the `ticket-agent:repo-survey` skill and follow it to the letter: the
eight sections of the survey, evidence marked `[verificado <file:line>]` or
`[asumido]`, and the `Espero de otros` / `Ofrezco a otros` pair that the
consolidation collates.

The ticket's brief travels in this prompt. **Azure DevOps is not reachable from
here**: whatever the brief doesn't say does not exist for you, and it goes under
`No pude determinar` rather than being filled in.

This repo is read-only. Write only the survey, at the path the prompt gives you.

Don't propose a solution — no tasks, no design. That's a later phase, and mixing
it in hands the consolidation N incompatible partial plans instead of N
observations.

If "$ARGUMENTS" is empty or not a work item number, ask for the ID and stop.
