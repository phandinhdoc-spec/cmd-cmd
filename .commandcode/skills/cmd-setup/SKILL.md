---
name: cmd-setup
description: Set up cmd-cmd once, save routing and model preferences for later sessions, or explicitly reconfigure an existing installation.
---

# Set up cmd-cmd once

Read `docs/routing.md` and `docs/native-runtime.md` from the cmd-cmd repository.
Operate on the user's target project, preserving existing configuration.

If `.cmd/setup.json` has `completed: true`, report that setup is already saved and
reuse it. Do not show model selection again unless the user asks to reconfigure.

For first setup:

1. Inspect the native Command Code provider/model list. If AGY is missing, use
   native `/connect` to let the user configure it. Keys stay in native storage.
   Do not copy credentials into this project.
2. Offer a single choice: automatic routing (recommended), or customize models.
   Automatic means the defaults in `config/routing.example.json`; it never requires
   the user to choose a model on each run. Use `/cmd-models` only for customization.
3. Copy `config/routing.example.json` to `.cmd/routing.json` only if absent. Fill
   verified capabilities, context/output limits and actual marginal cost from
   native configuration or user-confirmed provider metadata. BYOK does not mean
   free. Leave unknown entries blocked. Enable GOAT fallback only if available
   and the user wants to spend its quota; record the exact native model ID.
4. Create `.cmd/model-overrides.json` with `roles: {}` and current ISO `updated_at`
   only if absent. An empty map means auto for every role. Preserve saved choices.
5. Save `.cmd/setup.json` with `version: 1`, `completed: true`, current ISO
   `updated_at`, and routing/override file paths after at least one valid route or
   a verified manual native selection is available. Otherwise save
   `completed: false` and the concrete missing metadata/provider condition.

Future sessions read these files automatically through the project instructions.
Setup completion is not model-health evidence: refresh catalogs before routing.
A provider outage blocks/falls back under policy; it does not reopen onboarding.
Use `/cmd-models` to change a saved choice and `/cmd-models auto [role]` to reset it.
