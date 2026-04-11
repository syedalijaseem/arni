# WORKFLOW.md
# Autonomous Development Pipeline

---

## 1. Core Principle

Agents are individual contributors. Each agent owns specific files.
No two agents modify the same file at the same time.
Every layer completes and hands off before the next begins.

---

## 2. Repository Structure

```
docs/
  outline.md          ← YOU write this
  srs.md              ← planner owns
  architecture.md     ← architect owns
  constraints.md      ← architect owns

phases/
  phase1.md           ← planner owns
  phase2.md           ← planner owns
  phase3.md           ← planner owns
  status.md           ← loop-operator owns exclusively

tasks/
  phase1/
    task1.md          ← planner owns (initial)
    task2.md          ← loop-operator owns (dynamic)
  phase2/
  phase3/

src/                  ← tdd-guide owns
tests/                ← tdd-guide owns

CLAUDE.md             ← YOU maintain
WORKFLOW.md           ← YOU maintain
```

---

## 3. File Ownership

| File / Directory        | Owner               | Others                      |
|-------------------------|---------------------|-----------------------------|
| docs/outline.md         | Human               | READ ONLY                   |
| docs/srs.md             | planner             | READ ONLY                   |
| docs/architecture.md    | architect           | READ ONLY                   |
| docs/constraints.md     | architect           | READ ONLY                   |
| phases/*.md             | planner             | READ ONLY                   |
| phases/status.md        | loop-operator       | READ ONLY                   |
| tasks/phase*/ (initial) | planner             | READ ONLY during execution  |
| tasks/phase*/ (dynamic) | loop-operator       | created mid-execution only  |
| src/                    | tdd-guide           | READ ONLY                   |
| tests/                  | tdd-guide           | READ ONLY                   |

**Hard rules:**
- code-reviewer is READ ONLY across all files — never writes
- refactor-cleaner only touches src/ AFTER tdd-guide marks task complete
- architect never touches phases/, tasks/, src/, tests/
- planner never touches architecture.md, src/, tests/
- loop-operator reads docs/ freely but never writes to docs/

---

## 4. Planning Phase (Human-Triggered, Runs Once)

If planning documents already exist in docs/, skip to Step 5.

To update an existing doc, invoke the responsible agent explicitly and manually.

Sequential. Each step must complete before the next begins.

### Step 1 — Write the outline
Write your product idea in `docs/outline.md`. Plain English, no format required.

### Step 2 — Generate SRS
```
Use the planner agent to generate docs/srs.md from docs/outline.md
```

### Step 3 — Generate Architecture
```
Use the architect agent to generate docs/architecture.md from docs/srs.md
```

### Step 4 — Generate Phases and Tasks
```
Use the planner agent to generate phases and initial tasks from docs/architecture.md
```
Planner produces: `phases/phase1.md`, `phase2.md`, `phase3.md` and `tasks/phase1/task1.md`, etc.

Each task must contain:
- objective
- files: creates / modifies / reads
- implementation steps
- success criteria
- testing requirements
- status: pending

### Step 5 — Initialize Status File
Create `phases/status.md`:
```
current_phase: phase1
phase1: pending
phase2: pending
phase3: pending
last_updated: <timestamp>
loop_status: running
pause_reason:
```
This file is now owned exclusively by loop-operator. Do not edit manually.

---

## 5. Execution Phase (Autonomous Loop)

### Trigger
```
Use loop-operator to run the autonomous development loop defined in WORKFLOW.md.
All planning documents are ready in docs/, phases/, and tasks/.
```

### Loop Cycle

```
1.  Read phases/status.md → determine current phase
2.  Scan tasks/<current_phase>/ → find next incomplete task
3.  If no tasks found → create dynamic task file for missing work
4.  Read task specification
5.  Invoke tdd-guide → implement (owns src/, tests/)
6.  Invoke code-reviewer → review (READ ONLY)
7.  If PASS → invoke refactor-cleaner (owns src/ only)
8.  If FAIL → invoke tdd-guide again with review feedback
9.  Mark task complete in phases/status.md
9a. git add . && git commit -m "task: <task name>"
10. If all tasks in phase complete → advance phase in phases/status.md
10a. git push origin main
11. If all phases complete → write loop_status: complete → stop
11a. git push origin main
```

### Handoff Protocol

Each handoff is sequential. Next agent starts only after previous confirms completion.
tdd-guide signals completion by writing `status: complete` to the task file.
loop-operator reads this signal before invoking code-reviewer.

---

## 6. Architecture Change Protocol

If a task requires architectural changes:

1. loop-operator writes `loop_status: paused` and `pause_reason: architecture change required`
2. Human invokes architect to update `docs/architecture.md`
3. Human invokes planner to update affected phases/tasks if needed
4. Human resumes:
```
Resume the autonomous development loop from phases/status.md
```

Architecture changes are never made autonomously.

---

## 7. Stall Detection and Recovery

| Condition                              | Action                                      |
|----------------------------------------|---------------------------------------------|
| No progress across 2 consecutive tasks | Pause, reduce task scope                    |
| Same stack trace repeating 3+ times   | Pause, invoke build-error-resolver          |
| Merge conflict blocking task           | Pause, notify human                         |
| Architecture boundary hit              | Pause, invoke architecture change protocol  |

Recovery: pause → update status.md → fix → verify → resume.

---

## 8. Safety Constraints

Forbidden commands for all agents:
```
rm -rf
rm -r
sudo rm
git reset --hard
git clean -fd
```

Agents must never:
- Delete directories recursively
- Force reset git history
- Operate outside the project repository
- Modify WORKFLOW.md or CLAUDE.md
- Write to files outside their ownership boundary
