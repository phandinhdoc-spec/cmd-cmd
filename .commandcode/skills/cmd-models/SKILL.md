---
name: cmd-models
description: Change cmd-cmd models using Command Code's current model list; open the native controller picker, select a planner/worker/verifier model, or return a role to automatic routing.
---

# Change cmd-cmd models

Default scope is the main/controller. Arguments can name `planner`, `worker`,
`verifier`, `status`, or `auto [role]`. Speak the user's language.

## Controller: native picker

1. Read `.cmd/model-overrides.json` if present. Preserve unrelated roles.
2. Set `roles.controller` to `"session"` using native file tools. This disables
   automatic controller replacement and follows the actual native session choice.
3. Call native `run_command` with `command: "/model"`, then finish the turn so
   Command Code can open its picker. The user selects directly from the native
   list. For an explicit model ID, first verify it against `cmd --list-models`,
   then use `/model <exact-id>`.
4. State only that the picker has been requested; do not claim a model was selected.
   Cancelling the picker keeps the current session model and manual-session mode.
   On the next turn, use the active native model as the authority; never infer it
   from a stale list or the recommended defaults.

If `run_command` is unavailable (including headless mode), explain that the user
can open `/model` in an interactive session. Never auto-select the first menu item.
If plan mode prevents writing the override, open the picker if available and
report that persisting manual mode still needs a writable turn; do not claim it saved.

## Planner, worker or verifier: choose from the live native list

Run `cmd --list-models`. Use its exact IDs and provider labels, including all
providers available to this user. Do not substitute the AGY endpoint list for
Command Code's allowed list, invent IDs, or filter the UI down to router defaults.

Use native `ask_user_question` to offer provider, then model choices. Respect the
live tool's option limits; paginate large lists with Next/Previous and retain the
original IDs. Support searching or pasting an exact ID from the list. In headless
mode, require an explicit ID instead of a menu that might auto-answer.

Save the selected exact native ID in `roles.<role>` in
`.cmd/model-overrides.json` with a seconds-resolution `updated_at` including timezone.
Use native editing tools, preserving other roles. Initial shape:

```json
{"roles": {}, "updated_at": "<current ISO timestamp>"}
```

A manual role pin supersedes automatic model preferences and authorizes that
model's escalation tier, but task capability, budget and health gates still apply.
If a selected model lacks verified policy metadata, record the choice and explain
that task execution needs metadata before routing. Never silently fall back from
a pin. Read `docs/routing.md` when adding metadata or explaining a blocked route.
Native agent calls must receive the pinned `model` explicitly; omitting it inherits
the controller and loses the user's choice.

## Auto and status

`auto [role]` removes only that role's key (default controller). It takes effect at
the next safe dispatch boundary; do not interrupt running agents or switch the
current controller mid-turn. Empty/missing roles use automatic policy.

`status` shows saved role choices plus the actual native session model if known.
Manual controller mode follows `/model` changes immediately; pinned worker roles
persist until changed or reset. Malformed override JSON must be repaired visibly,
not overwritten as though it were empty.
