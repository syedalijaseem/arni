# CLAUDE.md
# Project Configuration for Autonomous Development Pipeline

---

## Project Overview

This project uses an autonomous multi-agent development pipeline built on
Everything Claude Code (ECC). Agents operate as individual contributors in a
structured engineering team. Read WORKFLOW.md before doing anything.

---

## Critical Rules (All Agents Must Follow)

1. Read WORKFLOW.md before taking any action
2. Respect file ownership boundaries — never write to files you do not own
3. Complete your task fully before signaling handoff
4. Never run forbidden commands (see WORKFLOW.md Section 9)
5. Never modify WORKFLOW.md or CLAUDE.md
6. Never make architectural decisions autonomously — pause and escalate
7. Update phases/status.md only if you are loop-operator

---

## Agent Roster and Responsibilities

### planner
- Reads: docs/outline.md, docs/srs.md, docs/architecture.md
- Writes: docs/srs.md, phases/*.md, tasks/**/*.md (initial only)
- Never touches: docs/architecture.md, src/, tests/, phases/status.md

### architect
- Reads: docs/srs.md, docs/architecture.md
- Writes: docs/architecture.md, docs/constraints.md
- Never touches: docs/srs.md, phases/, tasks/, src/, tests/

### loop-operator
- Reads: phases/status.md, tasks/**/*.md, all docs/
- Writes: phases/status.md, tasks/**/*.md (dynamic tasks only)
- Never touches: src/, tests/, docs/architecture.md, docs/srs.md
- Delegates to: tdd-guide, code-reviewer, refactor-cleaner, build-error-resolver

### tdd-guide
- Reads: tasks/**/*.md, docs/architecture.md, docs/constraints.md
- Writes: src/, tests/
- Never touches: docs/, phases/, tasks/ (except reading own task spec)
- Always writes failing tests before implementation (TDD)

### code-reviewer
- Reads: src/, tests/, tasks/**/*.md, docs/architecture.md
- Writes: NOTHING — strictly read only
- Reports findings to loop-operator

### refactor-cleaner
- Reads: src/, tests/
- Writes: src/ only
- Only activated AFTER tdd-guide marks task complete
- Never touches: tests/ structure, docs/, phases/, tasks/

### architect (change protocol)
- Only invoked by human during architecture change protocol
- Never invoked autonomously by loop-operator

---

## Knowledge Hierarchy

Information flows strictly downward. Never skip a layer.

```
docs/outline.md       ← human input
      ↓
docs/srs.md           ← planner output
      ↓
docs/architecture.md  ← architect output
      ↓
phases/*.md           ← planner output
      ↓
tasks/**/*.md         ← planner output (+ loop-operator dynamic)
      ↓
src/ + tests/         ← tdd-guide output
```

---

## Task File Format

Every task file must follow this format:

```markdown
# Task: [task name]

## Objective
[What this task accomplishes]

## Files
- Creates: [list of files]
- Modifies: [list of files]
- Reads: [list of files]

## Implementation Steps
1. [Step 1]
2. [Step 2]

## Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Testing Requirements
- Unit tests for: [list]
- Integration tests for: [list]

## Status
pending | in_progress | complete | failed
```

---

## phases/status.md Format

```
current_phase: phase1
phase1: pending | in_progress | complete
phase2: pending | in_progress | complete
phase3: pending | in_progress | complete
last_updated: <timestamp>
loop_status: running | paused | complete
pause_reason: <reason if paused>
```

Only loop-operator writes this file.

---

## Escalation and Pausing

loop-operator must pause and notify human when:
- Architecture change is required
- Same failure repeats 3+ times
- Merge conflict cannot be auto-resolved
- Task scope is unclear or contradicts architecture

When paused, loop-operator writes to phases/status.md:
```
loop_status: paused
pause_reason: <clear description>
```

Human reads this, resolves the blocker, then resumes:
```
Resume the autonomous development loop from phases/status.md
```

---

## Tech Stack

To be filled in at hackathon start based on the project idea.
Architect will define this in docs/architecture.md.

---

## Security

- No hardcoded secrets or API keys in source files
- Use environment variables for all credentials
- security-reviewer agent runs before project completion
- Forbidden commands listed in WORKFLOW.md Section 9 apply to all agents

---

## How to Start a New Project

1. Write your idea in docs/outline.md
2. Run: `Use the planner agent to generate docs/srs.md from docs/outline.md`
3. Run: `Use the architect agent to generate docs/architecture.md from docs/srs.md`
4. Run: `Use the planner agent to generate phases and tasks from docs/architecture.md`
5. Initialize phases/status.md (see WORKFLOW.md Section 4 Step 5)
6. Run: `Use loop-operator to run the autonomous development loop defined in WORKFLOW.md`
7. Supervise. Check phases/status.md for progress. Intervene when paused.
