# Backend Workspace Audit Report

This report outlines all instances in `app/api/routers/elein.py` where `supabase.table(...).insert(...)` is called without providing a `workspace_id`. Adding `workspace_id` is essential for proper Row Level Security (RLS) and multi-tenant isolation.

## Missing `workspace_id` in Inserts

| Line | Table | One-Line Fix / Note |
|---|---|---|
| 44 | `campaigns` | Add `"workspace_id": workspace_id` to `campaign_data` dict before insert |
| 125 | `lead_states` | Add `"workspace_id": workspace_id` to the inserted dict |
| 246 | `lead_lists` | Add `"workspace_id": workspace_id` to the inserted dict |
| 291 | `leads` | Ensure each dict in `leads_to_insert` has `"workspace_id": workspace_id` |
| 292 | `list_members` | Ensure each dict in `members_to_insert` has `"workspace_id": workspace_id` |
| 317 | `lead_lists` | Add `"workspace_id": workspace_id` to the inserted dict |
| 346 | `leads` | Ensure each dict in `leads_to_insert` has `"workspace_id": workspace_id` |
| 347 | `list_members` | Ensure each dict in `members_to_insert` has `"workspace_id": workspace_id` |
| 395 | `leads` | Ensure each dict in `leads_to_insert` has `"workspace_id": workspace_id` |
| 396 | `list_members` | Ensure each dict in `members_to_insert` has `"workspace_id": workspace_id` |
| 406 | `lead_lists` | Add `"workspace_id": workspace_id` to the inserted dict |
| 532 | `accounts` | Add `"workspace_id": workspace_id` to the inserted dict |
| 684 | `lead_states` | Ensure each dict in `states_to_insert` has `"workspace_id": workspace_id` |
| 950 | `messages` | Add `"workspace_id": workspace_id` to the inserted dict |
| 1323 | `messages` | Add `"workspace_id": workspace_id` to the inserted dict |
| 1388 | `messages` | Add `"workspace_id": workspace_id` to the inserted dict |
| 1410 | `approval_queue` | Add `"workspace_id": workspace_id` to the inserted dict |

## Required Action
To resolve these issues, the router methods need to resolve the user's `workspace_id` (likely via the new `get_workspace_id` helper in `app/core/workspace.py`) and include it in all of the above inserts.
