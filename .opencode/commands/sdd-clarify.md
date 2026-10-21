---
description: Find ambiguities, ask the user, and record binding clarifications
agent: planner
---

Review the current spec and plan for ambiguities: $ARGUMENTS

For each ambiguity, ask one focused question with concrete options and a recommendation.
After the user answers, append the question and the binding resolution to
`docs/clarification.md` using stable `C1`, `C2`, ... IDs. Update the spec's resolved
clarifications section to reference them. Do not implement anything in this step.
