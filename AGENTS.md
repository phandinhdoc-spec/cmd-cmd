# cmd-cmd project policy

For code changes, read README.md and docs/routing.md. Keep the Python policy layer
separate from Command Code's execution runtime; tests run with
`python3 -m unittest discover -s tests -v`.

When running cmd-cmd orchestration inside Command Code:

- Read `.cmd/setup.json`, `.cmd/routing.json` and `.cmd/model-overrides.json` at
  startup/resume and before dispatch. If setup is missing/incomplete, use
  `/cmd-setup`. Completed setup is reused without showing another model picker.
- Respect saved manual choices until `/cmd-models` changes them or resets to auto.
  Direct `/model` changes are user overrides too: persist the exact active native
  controller ID when observable. A `controller: "session"` value is a pending
  picker choice; on the next turn, persist the actual active ID once verified.
  If the active ID is unavailable, retain session mode and do not guess.
- Restore a saved controller ID using native `/model <id>` only when it differs
  from the active model, and end the turn for the native switch. A saved ID absent
  from the native list blocks restoration and asks for an explicit replacement.
- Follow docs/native-runtime.md for plan reread, DAG readiness, file locks,
  native agent dispatch, verification and bounded recovery. Route decisions
  never authorize bypassing native permissions.
