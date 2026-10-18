from typing import List, Set, Optional
import logging

logger = logging.getLogger(__name__)

def get_conflicting_active_leads(
    supabase_client,
    workspace_id: str,
    lead_ids: List[str],
    exclude_campaign_id: Optional[str] = None,
    active_statuses: Optional[List[str]] = None
) -> Set[str]:
    """
    Paranoia Layer 0 & 1: Queries active enrollments in the workspace to identify leads
    that currently have in-flight execution states ('pending', 'running', 'waiting_for_reply', 'awaiting_approval')
    in other active campaigns.
    """
    if not supabase_client or not workspace_id or not lead_ids:
        return set()

    clean_ws = str(workspace_id).strip()
    if not clean_ws:
        return set()

    clean_exclude = str(exclude_campaign_id).strip() if exclude_campaign_id else None

    # Layer 2 Paranoia: Sanitize and deduplicate lead IDs
    clean_lead_ids = []
    seen = set()
    for lid in lead_ids:
        if lid is not None:
            s_lid = str(lid).strip()
            if s_lid and s_lid not in seen:
                seen.add(s_lid)
                clean_lead_ids.append(s_lid)

    if not clean_lead_ids:
        return set()

    # Determine active statuses (defaulting to canonical in-flight states)
    if active_statuses:
        in_flight_statuses = [str(st).strip().lower() for st in active_statuses if str(st).strip()]
    else:
        in_flight_statuses = ["pending", "processing", "running", "waiting_for_reply", "awaiting_approval"]

    if not in_flight_statuses:
        return set()

    colliding_lead_ids = set()
    batch_size = 100

    for i in range(0, len(clean_lead_ids), batch_size):
        chunk = clean_lead_ids[i:i + batch_size]
        try:
            # 1. Query campaign_enrollments for the workspace and chunk of lead_ids
            query = supabase_client.table("campaign_enrollments").select("id, campaign_id, lead_id").eq("workspace_id", clean_ws).in_("lead_id", chunk)
            if clean_exclude:
                query = query.neq("campaign_id", clean_exclude)
            
            enrollments_res = query.execute()
            enrollments = enrollments_res.data or []
            if not enrollments:
                continue

            enrollment_map = {e["id"]: (e["campaign_id"], str(e["lead_id"]).strip()) for e in enrollments if e.get("id") and e.get("campaign_id") and e.get("lead_id")}
            if not enrollment_map:
                continue

            # Fetch corresponding campaigns to check if they are ACTIVE
            campaign_ids = list(set(e[0] for e in enrollment_map.values()))
            active_campaign_ids = set()
            for c_i in range(0, len(campaign_ids), batch_size):
                c_chunk = campaign_ids[c_i:c_i + batch_size]
                camp_res = supabase_client.table("campaigns").select("id, status").in_("id", c_chunk).execute()
                for c in (camp_res.data or []):
                    status = str(c.get("status", "")).upper()
                    if status == "ACTIVE":
                        active_campaign_ids.add(c["id"])

            if not active_campaign_ids:
                continue

            # Filter enrollments whose campaign is ACTIVE
            valid_enrollment_ids = [eid for eid, (cid, lid) in enrollment_map.items() if cid in active_campaign_ids]
            if not valid_enrollment_ids:
                continue

            # 2. Query campaign_execution_states for in-flight statuses
            for e_i in range(0, len(valid_enrollment_ids), batch_size):
                e_chunk = valid_enrollment_ids[e_i:e_i + batch_size]
                states_res = supabase_client.table("campaign_execution_states").select("enrollment_id, status").in_("enrollment_id", e_chunk).in_("status", in_flight_statuses).execute()
                for state in (states_res.data or []):
                    eid = state.get("enrollment_id")
                    st = str(state.get("status", "")).lower()
                    if eid in enrollment_map and st in in_flight_statuses:
                        cid, lid = enrollment_map[eid]
                        # ENG-07 Paranoia Layer 1: Deterministic priority ordering to eliminate mutual livelock.
                        if st == "pending":
                            # Both campaigns have the lead in pending state.
                            # Deterministic tie-breaker: lower-priority campaign (lexicographically greater UUID) yields,
                            # allowing higher-priority campaign to execute without mutual standoff.
                            if clean_exclude:
                                if str(clean_exclude) > str(cid):
                                    colliding_lead_ids.add(lid)
                            else:
                                colliding_lead_ids.add(lid)
                        else:
                            # Any active/in-flight status (running, waiting_for_reply, custom_in_flight, etc.) yields unconditionally.
                            colliding_lead_ids.add(lid)

        except Exception as e:
            logger.error(f"[CollisionGuard] Error checking conflicting active leads (failing closed): {e}", exc_info=True)
            # Paranoia Layer 1: Fail closed on DB/network error.
            # Mark all queried leads in chunk as potentially colliding to prevent duplicate outreach.
            for lid in chunk:
                colliding_lead_ids.add(lid)

    return colliding_lead_ids


def is_lead_active_in_other_campaign(
    supabase_client,
    workspace_id: str,
    lead_id: str,
    exclude_campaign_id: str,
    active_statuses: Optional[List[str]] = None
) -> bool:
    """
    Runtime preflight helper used by the orchestrator to check if a single lead
    has an active in-flight state in another campaign.
    Fails closed (returns True) if the database query fails.
    """
    if not lead_id:
        return False
    clean_lid = str(lead_id).strip()
    try:
        colliding = get_conflicting_active_leads(
            supabase_client,
            workspace_id,
            [clean_lid],
            exclude_campaign_id=exclude_campaign_id,
            active_statuses=active_statuses
        )
        return clean_lid in colliding
    except Exception as e:
        logger.error(f"[CollisionGuard] Preflight query failed for lead {clean_lid}: {e}. Failing closed.", exc_info=True)
        return True
