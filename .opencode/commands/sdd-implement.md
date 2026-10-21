---
description: Implement the next unchecked task with tests and quality gates
agent: implementer
---

Implement the next unchecked task in `specs/001-mov-shot-mvp/tasks.md`.

Scope hint: $ARGUMENTS

Read the constitution, spec, plan, and task first. Write or update tests for the pure DSP
functions before or alongside the implementation. Keep changes small and consistent with the
surrounding code. Record every fallback as a warning in the output JSON. Never modify the
input video, never add semantic AI to the core, and never make network calls.

Run the quality gates:

```bash
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

Mark the task complete only when both pass. Report the changed files, the requirements now
covered, and any follow-up work.
