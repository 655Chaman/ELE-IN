# Dispatch for teamwork_preview_explorer_survey_2

## Task
You are Explorer 2 investigating the codebase for Requirements R2 and R3.
You are a read-only exploration agent. Do NOT modify source code. Produce a detailed handoff report in your working directory at `handoff.md`.

## Working Directory
`/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_2`

## Authoritative Request Reference
Read `/Users/krdeeksha/Ele-in/.agents/teamwork/ORIGINAL_REQUEST.md` (specifically `## Follow-up — 2026-10-02T08:00:47Z`).

## Scope & Instructions
1. **R2: Standardize `if_replied_*` sentiment variable mismatch**:
   - Inspect `campaigns/backend/services/elein_executor.py`: check `handle_if_replied_positive`, `handle_if_replied_negative`, `handle_if_replied_neutral`, `handle_ai_detect_sentiment`, and `_get_reply_sentiment()`.
   - Identify all variable keys used (`ai_sentiment`, `last_reply_sentiment`, etc.) and where they are set or accessed.
   - Check `core/frontend/lib/eiNodeDefs.ts` for any sentiment variable references or node configurations.
   - Propose a single, standardized key name (e.g. `last_reply_sentiment` or `ai_sentiment`), map out all occurrences across python files, docstrings, and frontend definitions that must be aligned.
2. **R3: Implement 5 advanced engagement node handlers & confirm enrichment nodes remain locked**:
   - Inspect `campaigns/backend/services/elein_executor.py` for how handlers are structured, how `self.worker` is invoked, how `try_consume_daily_action` is called, and how `action_log` entries are written.
   - For each of the 5 nodes:
     - `like_top_3_posts`
     - `endorse_3_skills`
     - `congratulate_new_job`
     - `congratulate_anniversary`
     - `view_profile_repeat`
     Check what methods exist on `self.worker` (inspect `core/backend/workers/` or wherever worker is implemented). If worker methods don't exist, see what worker API exists or how other actions (e.g. `like_post`, `view_profile`, `send_message`) are executed.
   - Inspect `core/frontend/lib/eiNodeDefs.ts` for the 5 engagement nodes and the enrichment nodes (`find_email`, `find_personal_email`, `find_phone`, etc.) to confirm their definitions, and verify enrichment nodes have `comingSoon: true`.

## Output
Write your findings and verified evidence chains to `/Users/krdeeksha/Ele-in/.agents/teamwork/teamwork_preview_explorer_survey_2/handoff.md`.
