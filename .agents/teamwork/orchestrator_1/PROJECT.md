# Project: Ele-in Bug Remediation & Architectural Gap Closure

## Architecture
- **Backend Core & Database (Track 1)**:
  - `backend/migrations/033_fix_manual_mode_column.sql`: Corrected `dequeue_due_leads` RPC replacing `manual_mode_enabled` with `manual_send_suspected`.
  - `admin/backend/routers/workspaces.py`: Align notification preferences response shape to `{"preferences": res.data or []}`.
  - `core/frontend/pages/settings/NotificationSettings.tsx`: Defensive extraction supporting array or wrapped shape.
  - `campaigns/backend/services/elein_orchestrator.py`: `_normalize_to_utc_iso` datetime normalization for reply detection.
- **Campaign Execution & Worker (Track 2)**:
  - `campaigns/backend/services/elein_executor.py`: Sentiment standardization on canonical `ai_sentiment`, dual-write, output branches `"Other"`, `_log_action` helper, and 5 advanced engagement handlers (`like_top_3_posts`, `endorse_3_skills`, `congratulate_new_job`, `congratulate_anniversary`, `view_profile_repeat`) with limit checking and `action_log` writes.
  - `integrations/backend/services/linkedin_worker.py`: Playwright implementations for `like_top_3_posts` and `endorse_3_skills`.
  - `core/frontend/lib/eiNodeDefs.ts`: Verified all 12 enrichment nodes remain locked (`comingSoon: true`).
- **Approvals & Job Queue (Track 3)**:
  - `core/backend/api/routers/approvals.py`: `approve_reply` with account/workspace in job payload, `reject_reply` unblocking `campaign_execution_states` to `exited`, dual support for `approval_queue` and `ai_reply_approvals`.
  - `core/backend/workers/job_processor.py`: Account fallback to `job.get('asset_id')`.
  - `core/frontend/lib/apiClient.ts`: URL normalization for `fetchWithAuth`.
- **Frontend State, Autosave & Edit Hydration (Track 4)**:
  - `campaigns/frontend/eiTreeStore.ts`: Removal of module-level subscription to prevent autosave scope leaks.
  - `campaigns/frontend/EleInCreateCampaign.tsx`: Scoped subscription lifecycle, `isSavingRef` protection against draft resurrection, route param `:id` support, store hydration via `loadTree`, loading barrier.
  - `campaigns/backend/routers/elein.py`: Direct persistence of `nodes_json`/`edges_json` in `create_campaign` and `update_campaign`, fallback reconstruction in `get_campaign_detail`.
  - `core/frontend/App.tsx`: Routes for `/campaigns/:id/edit` and `/elein/campaigns/:id/edit`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R1: Fix `manual_mode_enabled` column mismatch | Migration 033 replaces `manual_mode_enabled` with `manual_send_suspected` in `dequeue_due_leads` | M1 | survey |
| 2 | R2: Standardize `if_replied_*` sentiment variable | Standardize on canonical `ai_sentiment`, dual-write, align branches to `"Other"` | M2 | survey |
| 3 | R3: Implement 5 advanced engagement node handlers | Real handlers in executor & worker with `_check_limit` and `action_log`; verify enrichment locked | M3 | survey |
| 4 | R4: Fix notification settings route & schema mismatch | Align payload shape `{preferences: []}` in `workspaces.py` and defensive parsing in frontend | M4 | survey |
| 5 | R5: Fix draft autosave subscription scope leak | Scope Zustand subscription to `EleInCreateCampaign` lifecycle with `isSavingRef` | M5 | survey |
| 6 | R6: Campaign reply detection UTC timezone comparison | UTC timezone normalization in `elein_orchestrator.py` for `enrollment_created_at` | M6 | survey |
| 7 | R7: Verify approval queue frontend-to-backend integration | Ensure LinkedIn job delivery in `approve_reply`, unblock execution states in `reject_reply` | M7 | survey |
| 8 | R8: Treestore state reset bug on campaign edit | Persist `nodes_json` on campaigns, reconstruct fallback in detail API, hydrate store on edit | M8 | survey |

## Milestones & Work Tracks
| Track | Name | Requirements | Exclusive File Boundaries | Status |
|-------|------|--------------|---------------------------|--------|
| Track 1 | Backend Infra & Migrations | R1, R4, R6 | `backend/migrations/033_fix_manual_mode_column.sql`, `admin/backend/routers/workspaces.py`, `core/frontend/pages/settings/NotificationSettings.tsx`, `campaigns/backend/services/elein_orchestrator.py` | PLANNED |
| Track 2 | Campaign Execution & Worker Handlers | R2, R3 | `campaigns/backend/services/elein_executor.py`, `integrations/backend/services/linkedin_worker.py`, `core/frontend/lib/eiNodeDefs.ts` | PLANNED |
| Track 3 | Approvals & LinkedIn Job Queue | R7 | `core/backend/api/routers/approvals.py`, `core/backend/workers/job_processor.py`, `core/frontend/lib/apiClient.ts` | PLANNED |
| Track 4 | Campaign Store & Edit Hydration | R5, R8 | `campaigns/frontend/eiTreeStore.ts`, `campaigns/frontend/EleInCreateCampaign.tsx`, `campaigns/backend/routers/elein.py`, `core/frontend/App.tsx` | PLANNED |

## Code Layout & Ownership Boundaries
- **Worker 1 owns exclusively**:
  - `backend/migrations/033_fix_manual_mode_column.sql`
  - `admin/backend/routers/workspaces.py`
  - `core/frontend/pages/settings/NotificationSettings.tsx`
  - `campaigns/backend/services/elein_orchestrator.py`
- **Worker 2 owns exclusively**:
  - `campaigns/backend/services/elein_executor.py`
  - `integrations/backend/services/linkedin_worker.py`
  - `core/frontend/lib/eiNodeDefs.ts`
- **Worker 3 owns exclusively**:
  - `core/backend/api/routers/approvals.py`
  - `core/backend/workers/job_processor.py`
  - `core/frontend/lib/apiClient.ts`
- **Worker 4 owns exclusively**:
  - `campaigns/frontend/eiTreeStore.ts`
  - `campaigns/frontend/EleInCreateCampaign.tsx`
  - `campaigns/backend/routers/elein.py`
  - `core/frontend/App.tsx`
