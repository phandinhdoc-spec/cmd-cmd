# Native execution contract

This is the controller playbook, not a second scheduler implementation. The Python
CLI only makes routing decisions. A Command Code agent must follow this contract;
cmd-cmd does not claim enforcement inside the closed native runtime.

## Native ownership (verified 2026-09-26)

| Concern | Owner | cmd-cmd contribution |
| --- | --- | --- |
| Provider setup and model picker | native `/connect`, `/model` | saved role policy and `/cmd-models` mod |
| Planning and review | native Plan/review | durable Markdown contract |
| Tasks and agents | native task tools and `agent(model=...)` | dependency/write-scope policy |
| Skills and MCP | native catalogs | reuse/discovery evidence before custom code |
| Isolation and recovery | native worktrees/checkpoints | ownership and verification rules |

Sources: [BYOK](https://commandcode.ai/docs/byok),
[tools](https://commandcode.ai/docs/reference/tools),
[agents](https://commandcode.ai/docs/agents),
[skills](https://commandcode.ai/docs/skills),
[plan mode](https://commandcode.ai/docs/plan-mode),
[worktrees](https://commandcode.ai/docs/worktrees).
Verify the installed tool schema before invoking it; availability depends on mode.
For model selection, see [the verified ModApi boundary](model-selection.md).
The role picker runs directly as a host command, not as an agent tool call.

Native BYOK discovery, credentials and inference are reused. Native `agent` accepts
a per-run model override; the controller supplies `native_model` from the decision.
Agent lifecycle, waiting and cancellation remain native. There is no subprocess
agent runner here. Model picker switching occurs after the native turn, so record
a pending controller change and yield; never loop on a switch within that turn.

## Plan persistence and reread

Keep the README's numbered, seconds-timestamped Markdown plan as authoritative
project history. Native Plan mode writes its reviewable file in the native plans
directory. When project writes are unavailable there, record the intended project
plan ID in that native document; copy the reviewed content into `.cmd/plans/` once
native permissions allow it. This bridge is explicit, not two independent plans.
Record source path, revision and digest. If either version is edited, reconcile
and review it before execution; conflicting edits block execution rather than
choosing the newer timestamp blindly. Native inline review comments may live in a
sidecar: incorporate accepted substantive comments into the durable Markdown.

Immediately before execute/resume, reread the full latest Markdown and saved model
policy from disk. Revalidate task IDs, dependency references/cycles, scope, acceptance
criteria, library decisions and completion evidence. A checkbox alone never proves
completion. Preserve human comments and historical plans. On scope or contract
changes, revise the same plan ID with an updated timestamp and re-review as needed.

## DAG and file-conflict locking

1. Discover existing libraries, standard/framework APIs, installed skills and MCP
   capabilities before implementation. Record reuse/reject evidence in the plan.
2. Split independently changeable functions/methods into work units with stable
   IDs, frozen signatures, inputs/outputs, dependencies, acceptance checks and
   explicit repository-relative read/write sets. Shared interfaces or tightly
   coupled edits remain one unit; granularity is not a reason to duplicate code.
3. Validate the dependency graph is acyclic and complete. Dispatch only tasks whose
   prerequisites have verified evidence. Mirror status into native tasks.
4. The single native controller owns a lock ledger in the Markdown plan. Before
   dispatch, canonicalize write paths (including symlink aliases, directory scopes,
   generated files and shared config) and atomically assign all scopes to a work
   unit. Overlapping file/directory writes serialize, even for different functions.
   Read-dependent tasks wait for pending writers where their evidence would stale.
5. Independent tasks with disjoint write scopes may run as native background agents.
   Use native worktrees for isolation when needed; merges into a shared target still
   require that target's write lock. Multiple independent controllers on the same
   checkout are unsupported: use separate native worktrees and a single integrator.
6. Record native agent IDs and model decisions; await native completion. Verify
   actual changed files and tests before marking done and releasing scopes. A
   cancelled/failed agent retains its lock until native termination and recovery
   are confirmed. On resume, reconcile live native agents and the ledger first.

This deliberately avoids a custom task database, file-lock daemon, worktree manager
or checkpoint engine. Locks are a controller protocol, not an OS mutex. If a host
needs cross-process locking, use its native coordination capability or serialize.

## Handoff and verification

Pass the native agent the exact plan revision, function contract, allowed files,
reuse evidence, dependencies, tests and model decision. Record actual model/provider,
remaining budget, attempted identities, touched files and verifier evidence back in
the plan. Re-read before each resumed dispatch. Escalation uses the same routing
entrypoint with evidence; it does not start a recursive planner/worker loop.
