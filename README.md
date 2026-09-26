# cmd-cmd

CommandCode-native CMD control/policy layer.

This repository intentionally reuses Command Code's native planning, agents, skills, MCP, checkpoints/worktrees, and other runtime capabilities instead of reimplementing them.

## Setup once, change models when needed

Inside Command Code, run `/cmd-setup` once. Saved project configuration is reused
on later runs; model selection is not repeated. To change it, use `/cmd-models`:

| Command | Action |
| --- | --- |
| `/cmd-models` | Open the native `/model` picker for main/controller |
| `/cmd-models planner` | Choose a saved planner model from the current native list |
| `/cmd-models worker` or `verifier` | Save the model for that role |
| `/cmd-models auto [role]` | Return that role to automatic routing |
| `/cmd-models status` | Show saved choices |

Manual choices take precedence and persist; unavailable pins ask for a replacement
instead of silently changing model. The built-in picker remains the authority for
which models the user can select. Role-specific selection uses the same live native
list through paginated questions. See [routing and setup](docs/routing.md).

## Dynamic pools and defaults

AGY is a provider pool discovered through OpenAI-compatible `/v1/models`, intersected
with the models currently allowed by Command Code. Model names below are configurable
preferences, never a hard-coded catalog:

- Controller: `agy/gemini-3.8-flash-low`.
- Planner: `agy/gemini-3.8-flash-high`; medium for light tasks.
- Escalation: Gemini 3.1 Pro High or Claude Sonnet/Opus via AGY only when difficulty
  or verified failure warrants it (or the user explicitly pins that model).
- GOAT / DeepSeek V4 Flash Fast: supplemental/fallback pool, not default controller.

The router checks role, difficulty, capabilities, context, cost budget, freshness
and health. Unknown metadata fails closed. Configure verified prices/limits during
setup; the example deliberately does not assume AGY is free. See
[policy configuration](config/routing.example.json) and [routing design](docs/routing.md).

## Implementation boundary and validation

Python 3.9+, standard library only. `python3 -m cmd_cmd --help` exposes read-only
catalog discovery and policy evaluation. Run `python3 -m unittest discover -s tests -v`.
The CLI emits a decision; Command Code executes it using native tools. It does not
install providers, launch inference, run agents, or replace the native scheduler.

[Native execution contract](docs/native-runtime.md) covers function/method work
units, dependency DAG, file-conflict locking, library-first discovery and native
plan review. The supplied skills and controller instructions are the integration
surface; end-to-end behavior still depends on the installed native runtime.

## Plan-as-Markdown contract

Every orchestrated plan MUST be persisted as a human-editable Markdown file. A plan that exists only in model context or terminal output is not a valid CMD plan.

### Naming and ordering

Plan files use a monotonically increasing sequence plus a detailed local timestamp:

```text
.cmd/plans/0001_2026-09-26_10-45-32_plan.md
.cmd/plans/0002_2026-09-26_11-08-05_plan.md
```

- Sequence is zero-padded and never reused inside a project.
- Timestamp records creation time to seconds.
- Revisions preserve the original plan ID and record revision timestamps inside the file.
- The Markdown file is the human-editable source of truth for plan review.

### Required Markdown structure

CMD MUST use native Markdown constructs wherever possible:

- headings for plan/task/work-unit hierarchy;
- numbered lists for execution order;
- task lists: `- [ ]`, `- [x]`;
- nested checklists for steps and verification;
- tables for routing/dependencies when useful;
- blockquotes or explicit `COMMENT:` sections for detailed planning comments;
- fenced blocks only for contracts, commands, pseudocode, or schemas.

Each plan records at minimum:

- plan ID and sequence;
- created/updated timestamps;
- original objective;
- current status;
- task/work-unit IDs;
- dependencies;
- selected agent/model and reason;
- files/write scope;
- library/package/API reuse decision;
- acceptance criteria;
- verification checklist;
- detailed planner comments explaining WHY the task exists, assumptions, risks, handoff expectations, and what must not be changed.

### Example

```markdown
# PLAN 0007 — Add telemetry parser

> Created: 2026-09-26 10:45:32 +07:00
> Updated: 2026-09-26 10:52:11 +07:00
> Status: REVIEW
> Objective: Parse BLE telemetry without duplicating an existing library.

## 1. [ ] T1 — Dependency/library discovery

**Agent/model:** Scout / ...
**Depends on:** none
**Write scope:** none

### Planner comment

Explain in detail what must be searched, why reuse is preferred, assumptions,
expected evidence, known risks, and the exact condition that permits custom code.

### Checklist

- [ ] Inspect current dependencies.
- [ ] Check standard/framework APIs.
- [ ] Check maintained packages.
- [ ] Record reuse/reject evidence.

### Acceptance / verification

- [ ] Reuse decision is documented with evidence.
- [ ] No suitable existing component is reimplemented.

## 2. [ ] T2 — Implement parser

**Depends on:** T1

### Planner comment

Detailed implementation intent and constraints...

- [ ] W2.1 — Implement one independently changeable function.
  - [ ] Preserve frozen interface.
  - [ ] Run focused tests.
  - [ ] Record result and touched files.
```

### Editing semantics

Humans are expected to edit these Markdown plans directly. Before execution/resume, CMD MUST reread and validate the latest Markdown plan rather than relying on stale in-memory plan text. Checkbox state is meaningful but is not trusted blindly: completion still requires verification evidence.

CMD must preserve detailed planner comments during automatic status updates. It may update timestamps, status, checkbox state, evidence, and execution notes without erasing human edits.

### History

Do not overwrite old plans merely to make the directory tidy. Plan history is part of the project journal. Cleanup may remove only artifacts explicitly classified as disposable; final/current plans and meaningful historical plans are retained.
