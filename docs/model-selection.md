# Model selection runtime contract

## Evidence inspected before implementation

Verified against installed `command-code` **1.66.0** on 2026-09-26 and:

- https://commandcode.ai/docs/reference/tools : `ask_user_question` supports
  structured choices; headless runs auto-answer the first option. `run_command`
  defers slash commands until the turn ends, with no role-selection callback.
- https://commandcode.ai/docs/mods and bundled `mod-builder/reference/api.md`,
  `ui.md`, `examples/slash-command.ts`: `addCommand` gets `{args, ui, cwd, exec}`;
  returning `{message}` avoids an LLM turn. `ui.select({title, options})` returns
  the selected **label**, or undefined on cancellation/headless hosts.
- https://commandcode.ai/docs/byok : custom provider declarations live in
  user-level `~/.commandcode/providers.json`, refreshed through `/connect`.
- Targeted installed bundle inspection: host command dispatch checks mods before
  skills. `buildUi` maps select labels through native `interaction.askQuestion`.
  `parseProvidersConfig` reads `provider` (or legacy `providers`), skips disabled
  providers; `buildCustomModelPickerGroups` qualifies IDs as `provider/model`.
  ModApi `buildApi` has no model-list getter. The agent tool's model parameter
  is a string, not a model catalog enum. These are version-specific observations.

The old skill incorrectly used controller `/model` as a role picker and required
an unspecified callback. A skill cannot guarantee a menu before an LLM turn.
The replacement is a host command, with no `search_tools`, agent invocation,
`run_command`, provider HTTP request or `cmd --list-models` subprocess.

## Supported boundary

The menu shows valid declared BYOK models, including AGY and custom GOAT endpoints
when actually configured. It does **not** list built-in subscription lanes or
claim complete parity with `/model`. No public ModApi accessor for that full
catalog was found in the inspected version. Adding full parity requires an
upstream catalog accessor; do not invent one, scrape credentials, patch the
installed bundle, or substitute the repository's example preferences.

The metadata reader follows the inspected declaration rules for provider/model
shape, disabled entries, connection URLs and wire types. It never reads auth.json,
resolves key references, executes credential commands or checks model health.
IDs are labels, so duplicate friendly names cannot select the wrong provider.
Future runtime contract changes require revalidation of this adapter.

The controller branch directs the user to `/model`; it never switches models as
a side effect of choosing planner/worker/verifier. With no argument the mod opens
a role menu. The compatibility skill only reports missing-mod installation.

## Persistence and checks

After selection, re-read declarations and require the chosen ID to remain present.
Then re-read `.cmd/model-overrides.json`, merge the chosen role, preserve unrelated
keys and write via a temporary file plus rename. Malformed state is not replaced.
Cancellation/headless selection is undefined and writes nothing. An in-process
busy guard prevents overlapping menus. External simultaneous writers are not
coordinated: the project's single-controller ownership rule still applies.

The mod itself does not refresh the router's normalized catalogs. Selection is a
manual preference; dispatch still requires fresh native/provider evidence and
verified policy metadata as specified in routing.md.

Validation:

```sh
node --test tests/test_models.mjs
python3 -m unittest discover -s tests -v
```

The Node tests call the registered handler with an injected native UI boundary
and temporary native declaration files. They cover each role, exact IDs, cancel,
headless, invalid replies/state/catalogs, provider filtering, changes during the
menu, status and auto. They do not prove real TUI rendering or account entitlement.
Manual acceptance after installation: run `/cmd-models planner`, select an ID,
verify the role in `status` and that the controller stayed unchanged; repeat for
worker/verifier and cancel a selection. No `SKILL loaded` or LLM narration should
precede the dialog when the mod is installed.

The installed jiti loader successfully loaded the TypeScript entry and registered
`cmd-models`. `cmd mods list` in the fresh, untrusted checkout reported no project
mods (its discovery is gated on project-session initialization); this is not an
interactive rendering test. Global installation avoids that project trust gate.
