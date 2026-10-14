# Dispatch Instructions — Victory Auditor

You are teamwork_preview_victory_auditor, the Independent Post-Victory Auditor.
Your working directory is:
/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_victory_auditor_2

The project root is:
/Users/krdeeksha/Ele-in

The original user request is recorded in:
/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md

The team has claimed completion for the user request:
Resolve Bug 1.1 in the Ele-in backend: Leads that hit a 'Wait For Reply' node are permanently orphaned and stuck in `waiting_for_reply` state because the orchestrator never re-queues them or times them out.

Working directory: /Users/krdeeksha/Ele-in
Integrity mode: benchmark

Requirements:
R1. Implement Re-queue Logic for `waiting_for_reply`
- Modify the orchestrator logic (`dequeue_due_leads` DB RPC or Python worker) to detect leads in `waiting_for_reply` that have either received a new inbound message OR exceeded a timeout threshold.
- Ensure these leads are successfully picked back up by the `job_processor` so the campaign DAG can continue executing.

Acceptance Criteria / Verification:
- [ ] A standalone Python script (`verify_bug_1_1.py`) is written that inserts a mock lead in the `waiting_for_reply` state and a mock inbound message.
- [ ] Running `verify_bug_1_1.py` successfully triggers the re-queue logic and asserts the lead's state transitions correctly to be picked up by the orchestrator.
- [ ] The backend compiles successfully (`python3 -m py_compile core/backend/workers/*.py`).

Orchestrator Handoff:
/Users/krdeeksha/Ele-in/.agents/teamwork/swe_5/handoff.md

Conduct your 3-phase audit:
Phase A: Timeline & Progress Audit
Phase B: Cheating / Anti-Pattern Detection (Benchmark Integrity Mode)
Phase C: Independent Test & Build Execution (run verify_bug_1_1.py, py_compile checks, and unit tests)

Report a structured verdict: VICTORY CONFIRMED or VICTORY REJECTED with full evidence chain in your report.md and handoff.md, and message parent with your verdict.


## 2026-10-02T15:16:06Z
[Message] sender=0161e112-7771-4578-a619-969e1cb40873 priority=MESSAGE_PRIORITY_HIGH
You are teamwork_preview_victory_auditor, the Independent Post-Victory Auditor.
Your working directory is: /Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_victory_auditor_2
The project root is: /Users/krdeeksha/Ele-in
The original user request is recorded in: /Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md
The orchestrator handoff is at: /Users/krdeeksha/Ele-in/.agents/teamwork/swe_5/handoff.md
Please read /Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_victory_auditor_2/DISPATCH.md and execute your 3-phase audit:
- Phase A: Timeline & Progress Audit
- Phase B: Cheating / Anti-Pattern Detection (Benchmark Integrity Mode)
- Phase C: Independent Test Execution (execute python3 verify_bug_1_1.py, verify backend workers python3 -m py_compile, and unit tests)
Output your findings in report.md and handoff.md, and send a message back to parent with your verdict: VICTORY CONFIRMED or VICTORY REJECTED.
