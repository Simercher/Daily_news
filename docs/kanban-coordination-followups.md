# Kanban Coordination Follow-Ups

## Context
During the `article-search-v2` Kanban run (`t_7b2b06c3` root task), the implementation and review work completed successfully, but the monitoring layer detected workflow coordination issues that should be fixed in the orchestration system to avoid future stalls.

Relevant tasks:
- root: `t_7b2b06c3`
- implementation: `t_c84a1a8c`
- review: `t_cb492335`

## Observed Issues

### Issue 1: Implementation task ended in `blocked` for review handoff
**Observed behavior**
- `coding-worker` finished implementation and test verification.
- Instead of completing its task, it blocked the task with a `review-required` reason.

**Why this is a problem**
- The downstream `code-reviewer` task depended on the implementation task.
- A blocked parent prevented the dependent review task from proceeding normally.
- This created an execution deadlock even though the implementation work was already complete.

**How it was resolved this time**
- Monitoring detected the mismatch between task state and task content.
- The monitor first attempted to promote the child review task.
- That first attempt failed with `claim_rejected(parents_not_done)`.
- The implementation task was then corrected to `done`, after which review proceeded successfully.

**Follow-up action**
- Standardize worker handoff semantics so completed implementation with downstream review uses `complete`, not `block`.
- If a worker wants to indicate "ready for review", that should be metadata/comment/result text on a completed task, not a terminal blocked state.

---

### Issue 2: Review promotion before parent correction produced a recoverable claim rejection
**Observed behavior**
- The monitor force-promoted the review task while its parent was still blocked.
- Dispatcher correctly rejected the claim because parents were not done.

**Why this matters**
- This is not a correctness bug in the dispatcher; it is evidence that the recovery sequence should be improved.
- The safer recovery order is:
  1. confirm implementation truly finished,
  2. correct the parent state,
  3. let the child promote naturally or promote afterward.

**Follow-up action**
- Update monitoring/recovery logic to repair the parent task first when a review child is stranded by a review-required blocked implementation.
- Avoid force-promoting a child before parent state is made consistent.

---

## Recommended Backlog Items

### 1. Worker completion contract: implementation-to-review handoff
**Priority:** high

Define and document a single expected behavior for implementation workers when downstream review exists:
- implementation task completes as `done`
- worker leaves structured handoff content in summary/comment
- review task consumes that handoff

### 2. Monitor auto-recovery rule for blocked implementation parents
**Priority:** high

Add a specific recovery rule:
- if a coding-worker task is blocked only because it says review-required and its body/results show implementation + verification are complete,
- convert/complete parent first,
- then allow the child review task to run.

### 3. Review workflow regression test for Kanban orchestration
**Priority:** medium

Add a regression scenario covering:
- implementation task finished with review handoff
- downstream reviewer depends only on implementation task
- workflow continues without manual intervention

### 4. Distinguish human-input blocked vs workflow-handoff states
**Priority:** medium

Clarify and enforce semantics for:
- true blocked: requires human input or external dependency
- scheduled/todo/ready: waiting in workflow
- done: work complete, downstream tasks may proceed

A review handoff should not reuse `blocked` unless actual human input is required before any automation can continue.

## Suggested Ownership
- orchestration semantics / profile behavior: `orchestrator` + worker prompt/skill maintainers
- automated recovery logic: monitoring / controller layer
- regression coverage: Kanban orchestration test suite

## Desired Outcome
Future code workflows should behave as:
1. orchestrator creates implementation + review tasks
2. coding-worker completes implementation task with a review-ready summary
3. review task becomes ready automatically
4. code-reviewer runs without monitor intervention
5. root orchestrator summarizes completion
