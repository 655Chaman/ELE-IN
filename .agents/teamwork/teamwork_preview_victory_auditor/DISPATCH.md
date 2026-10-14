## 2026-10-02T15:07:03Z

<original_task>
This is a single self-contained fix; keep it small and focused. 
Resolve Bug 1.1 in the Ele-in backend: Leads that hit a 'Wait For Reply' node are permanently orphaned and stuck in `waiting_for_reply` state because the orchestrator never re-queues them or times them out.

Working directory: /Users/krdeeksha/Ele-in
Integrity mode: benchmark

## Requirements

### R1. Implement Re-queue Logic for `waiting_for_reply`
- Modify the orchestrator logic (`dequeue_due_leads` DB RPC or Python worker) to detect leads in `waiting_for_reply` that have either received a new inbound message OR exceeded a timeout threshold.
- Ensure these leads are successfully picked back up by the `job_processor` so the campaign DAG can continue executing.

## Acceptance Criteria

### Verification
- [ ] A standalone Python script (`verify_bug_1_1.py`) is written that inserts a mock lead in the `waiting_for_reply` state and a mock inbound message.
- [ ] Running `verify_bug_1_1.py` successfully triggers the re-queue logic and asserts the lead's state transitions correctly to be picked up by the orchestrator.
- [ ] The backend compiles successfully (`python3 -m py_compile core/backend/workers/*.py`).
</original_task>

Audit Instructions:
- Conduct an independent post-victory audit for Bug 1.1.
- Project root: /Users/krdeeksha/Ele-in
- Working directory: /Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_victory_auditor
- Report location: /Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_victory_auditor/report.md
- Conduct a 3-phase audit:
  1. Timeline & requirements compliance audit
  2. Cheating detection (check for mock tampering, trivial assertions, artificial passes in `verify_bug_1_1.py`)
  3. Independent test execution: run `python3 verify_bug_1_1.py` and compilation check `python3 -m py_compile core/backend/workers/*.py`
- Deliver a clear structured verdict (CONFIRMED or REJECTED) with evidence and rationale.
