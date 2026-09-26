---
name: cmd-models
description: Explain installation when the native cmd-models mod is missing; role model selection is handled directly by the mod.
---

# cmd-models compatibility notice

The native mod owns `/cmd-models`. If this skill loads on a typed invocation,
the mod was not loaded. Reply in the user's language with one sentence:
"Cài mod `.commandcode/mods/cmd-models` theo README, khởi động lại CommandCode,
rồi chạy lại `/cmd-models planner`."

End the turn. Do not discover tools, call `run_command`, open `/model` for a worker
role, run `cmd --list-models`, fabricate choices, or save a model selection.

The mod registers a host slash command with `addCommand` and uses `ui.select`.
It selects declared BYOK models from the user's native `providers.json`; it does
not claim access to the complete built-in subscription catalog. See README and
`docs/model-selection.md` for installation, scope and runtime evidence.
