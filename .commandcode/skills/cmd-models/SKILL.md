---
name: cmd-models
description: Change cmd-cmd models using Command Code's native interactive model picker; select controller/planner/worker/verifier roles or return a role to automatic routing.
---

# Change cmd-cmd models

Default scope is the main/controller. Arguments can name `planner`, `worker`,
`verifier`, `status`, or `auto [role]`. Speak the user's language.

## Native picker is authoritative

Do NOT run `cmd --list-models` merely to build a model-selection UI. Some Command
Code installations expose no useful output from that command, and duplicating the
native picker is brittle.

For every interactive model change, use Command Code's native `/model` picker as
the source of truth. Never invent model IDs, auto-select the first item, or replace
the picker with a shell-generated menu.

## Controller

1. Read `.cmd/model-overrides.json` if present. Preserve unrelated roles.
2. Set `roles.controller` to `"session"` using native file tools.
3. Invoke the native interactive command `/model` through the runtime mechanism
   that executes Command Code slash commands (not a shell command), then finish the
   turn so the picker can be displayed.
4. State only that the native picker was requested. Do not claim a selection until
   the runtime reports the selected active model.

Cancelling keeps the current session model. If the runtime cannot invoke slash
commands programmatically, tell the user to run `/model` directly; do not call a
shell command named `cmd` as a substitute.

## Planner, worker, verifier

These roles also use the native `/model` picker.

1. Remember the requested target role for this selection.
2. Invoke native `/model` and let the user choose from Command Code's live list.
3. After the picker returns a selected/active exact model ID, save that ID under
   `roles.<role>` in `.cmd/model-overrides.json`, preserving all unrelated roles.
4. Write `updated_at` with a seconds-resolution ISO timestamp including timezone.
5. Confirm the role and exact model actually reported by the native runtime.

Initial shape:

```json
{"roles": {}, "updated_at": "<current ISO timestamp>"}
```

If the runtime cannot return the selected model to the skill, do not guess it.
Explain that the current Command Code runtime cannot persist a role-specific pin
from an interactive picker automatically. Ask the user for the exact ID shown by
`/model`, then validate/use that explicit ID through native runtime information
when available. Do not fall back to `cmd --list-models` solely because the picker
result is unavailable.

A manual role pin supersedes automatic model preferences and authorizes that
model's escalation tier, but task capability, budget and health gates still apply.
If a selected model lacks verified policy metadata, record the choice and explain
that task execution needs metadata before routing. Never silently fall back from a
pin. Read `docs/routing.md` when adding metadata or explaining a blocked route.
Native agent calls must receive the pinned `model` explicitly; omitting it inherits
the controller and loses the user's choice.

## Explicit model IDs

When the user supplies an exact model ID, prefer validation against native runtime
model metadata/listing if that capability is available. A non-interactive listing
may be used for validation, but it MUST NOT be required for opening an interactive
selection and MUST NOT replace the native `/model` picker.

## Auto and status

`auto [role]` removes only that role's key (default controller). It takes effect at
the next safe dispatch boundary; do not interrupt running agents or switch the
current controller mid-turn. Empty/missing roles use automatic policy.

`status` shows saved role choices plus the actual native session model if known.
Manual controller mode follows `/model` changes immediately; pinned worker roles
persist until changed or reset. Malformed override JSON must be repaired visibly,
not overwritten as though it were empty.
