# Dynamic provider/model pool

## Scope and reuse decision

The starting repository at `bae0e9e6f09aedb039106ed321d5603ac6571689` contained
README.md and .gitignore only. There was no router, scheduler or inference client
to migrate. This implementation adds a Python 3.9+ standard-library policy CLI,
not a replacement agent runtime. `urllib`, `json`, `argparse` and `unittest` cover
the required transport, configuration and verification without another SDK.

Command Code remains the authority for provider registration, authentication,
allowed native model IDs, inference and agent lifecycle. Use `/connect` to refresh
its provider list. The optional `discover` command is a read-only policy adapter
for a complete OpenAI-compatible `/v1/models` response, not another registration
system. Existing native discovery output can instead supply the snapshot.

## Setup and saved manual choices

Run `/cmd-setup` once. It saves `.cmd/setup.json`, `.cmd/routing.json` and
`.cmd/model-overrides.json`; later sessions reuse them. No recurring model prompt.
These files are machine-local and ignored by Git. The bundled skills are project
skills; copying this policy into another project requires carrying over AGENTS.md,
the skills, policy code and its referenced docs/config (or keeping this repo as
the policy working directory). Native provider configuration stays user-global.

- `/cmd-models`: open the real native `/model` picker for the main/controller.
- `/cmd-models planner` (or worker/verifier): select an exact current native ID
  through paginated native questions without changing the controller.
- `/cmd-models status`: show saved choices.
- `/cmd-models auto [role]`: remove a saved override for that role.

Manual controller selection belongs to Command Code. While its menu is open,
`controller: "session"` suppresses automatic switching; the next native turn
records the actual selected ID. Cancellation retains the current model. Saved
exact IDs are restored at a safe turn boundary in future sessions. The skill
cannot synchronously read the result of a picker that opens after the turn ends.
Manual task pins bypass preference ordering and the automatic escalation tier
gate but still require verified capabilities, budget and health. Unavailable or
ineligible pins block; they never silently fall back. UI selection includes all
native models, even ones that need metadata before automated task execution.

## Automatic selection

`config/routing.example.json` contains preferences, not an availability catalog:

| Role | Preference / gate |
| --- | --- |
| Controller | AGY `gemini-3.8-flash-low` |
| Planner | AGY `gemini-3.8-flash-high`; medium for light work |
| Worker / verifier | Cheapest eligible model within the preferred pool |
| Escalation | AGY Gemini Pro / Claude only for difficulty 3 or verified failure |
| Supplemental pool | GOAT DeepSeek V4 Flash Fast, using its exact native ID |

Preference IDs never create candidates. Newly discovered models can participate
through metadata rules or an explicit profile. Pro/Claude family rules are gated
for escalation; unclassified models remain excluded. `owned_by`, a name suffix,
or mere presence in `/models` does not prove tool support, reasoning budget,
context size or price. No public price/benchmark claims are baked into code.

Metadata is joined from trusted local `rules` (in order), then exact `models`
overrides. Defaults deliberately have unknown costs, no capabilities and zero
limits: complete them from verified native/provider metadata before automatic
routing. Example profile below has **illustrative values only**:

```json
{
  "roles": ["controller", "planner", "worker", "verifier"],
  "capabilities": ["tools"],
  "max_difficulty": 2,
  "escalation_only": false,
  "context_window": 32000,
  "max_output": 4000,
  "cost": {"input": 0.2, "output": 0.5}
}
```

Attach under `providers.agy.models.<exact discovered ID>` or a narrowly verified
family rule. Cost units are USD per million input/output tokens, reflecting the
user's marginal cost. Zero is valid only when verified. Missing cost is never
zero. Quota-limited GOAT is disabled in the example until explicitly configured;
add a profile for the exact ID from `cmd --list-models`, with `native_id` if needed.
GOAT is a billing pool label here, not an invented native provider prefix.

Selection intersects fresh provider membership with a fresh native allowed list,
then filters role, difficulty capacity, required capabilities, context/output
limits, health exclusions, attempted identities, escalation and cost cap. Ranking
is lexicographic: provider priority, role preference, estimated request cost,
identity (deterministic tie break). Thus a configured role preference can win over
a cheaper model, but never over its budget/capability gates. Requests specify total
input estimate (including tools/history) and maximum output allowance. No cache
savings are assumed. This is an estimate, not a billing reservation; native usage
must be reconciled against the remaining task budget after every attempt.

## CLI and snapshot contract

From this repository root:

```sh
python3 -m cmd_cmd discover --provider agy --base-url http://localhost:PORT/v1
python3 -m cmd_cmd route --policy .cmd/routing.json --catalog .cmd/catalog.json \
  --native-catalog .cmd/native-models.json --request config/request.example.json
python3 -m unittest discover -s tests -v
```

Replace PORT with the configured endpoint port. `--key-env AGY_API_KEY` is optional
for authenticated discovery; use native discovery when credentials exist only in
Command Code's auth store. Do not extract/copy that store. HTTP is restricted to
loopback; remote discovery uses HTTPS. Redirects are refused, timeout is bounded,
response size is capped, and transport errors are redacted by the CLI.

`discover` prints one snapshot. `catalog.json` is an array of such snapshots:

```json
[{"provider":"agy","observed_at":1790399400,"data":[{"id":"gemini-3.8-flash-low"}]}]
```

`native-models.json` has `observed_at` plus `data:[{"id":"agy/..."}]` using exact
IDs observed from `cmd --list-models` at that timestamp. This is **our normalized
snapshot format**, not a claimed native JSON CLI flag. The native controller
normalizes its current listing, preserving every ID. Provider and native snapshots
expire after 300 seconds by default; refresh at dispatch when stale. An AGY snapshot
can contain models not registered in Command Code: the intersection excludes them.
Paginated endpoint responses are refused rather than silently treated as complete.
Use a complete native snapshot when provider pagination is required.

The CLI rereads override state each time. Manual `session` returns
`MANUAL_SESSION`, a directive to retain the real native controller, not a successful
inference or task verification. Only `ROUTED` contains a selected task model.
A `BLOCKED` decision or malformed input exits 2; it never launches a model.

## Fallback without loops

On an inference failure, native execution records its provider/model identity in
`attempted`, updates remaining cost allowance, and excludes unhealthy identities
or whole providers via `unavailable`. A missing snapshot represents discovery
failure. Selection moves to another eligible AGY model, then an enabled GOAT pool.
An outage alone does not authorize Pro/Claude escalation. Difficulty 3 must be
supported by planner evidence; `verified_failure` requires verifier evidence, not
self-reported inability. If the native runtime already retried, count those tries
in the task's total attempt budget too.

Maximum 3 attempts per work unit by default; the attempted list (including repeat
attempts) survives resume and is reset only for a new/revised work unit. Never retry
an attempted identity or recursively invoke the router. Exhaustion, unknown cost,
no capability match, or unavailable manual pin stops with an actionable decision.
No stale-cache fallback, background poller, inference retry loop, or auto-escalation
ladder is implemented here.
