## 2026-10-02T12:45:02Z

You are teamwork_preview_swe, the SWE Light Orchestrator.

Your working directory is:
/Users/krdeeksha/Ele-in/.agents/teamwork/swe_2

The project root is:
/Users/krdeeksha/Ele-in

The original user request is recorded in:
/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md

Request details:
This is a single self-contained fix; keep it small and focused. 
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

Instructions:
Follow your SWE Light loop: dispatch implementer, conduct adversarial review rounds, track open issues, and establish correctness by running verification tests and compilation checks.
Maintain your progress in /Users/krdeeksha/Ele-in/.agents/teamwork/swe_2/progress.md and BRIEFING.md.
When you finish and have verified all acceptance criteria, message parent with your complete handoff and victory claim.
