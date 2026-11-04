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


# Common consumer freemail domains exempt from corporate account exclusivity
_FREEMAIL_EXEMPT_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "zoho.com", "mail.com", "gmx.com"
})


def check_company_domain_exclusivity(
    supabase_client,
    workspace_id: str,
    company_domain: str,
    exclude_campaign_id: Optional[str] = None,
    strict_account_exclusivity: bool = True,
    active_statuses: Optional[List[str]] = None,
    enterprise_workspace_ids: Optional[List[str]] = None,
) -> dict:
    """
    Paranoia Layer 0, 1 & 2:
    Strict Account Exclusivity Guard & Multi-Workspace Enterprise Collision Shield.
    Prevents cross-campaign and cross-workspace friendly fire at the corporate account level.
    If Campaign A or Sister Workspace A is actively engaging Acme Corp (acme.com), Campaign B
    is prohibited from simultaneously reaching out to another prospect at acme.com.
    
    - Layer 0: Identifies sibling leads belonging to the same company domain across all specified
               workspaces and detects if any have in-flight execution states in another active campaign.
    - Layer 1: Excludes consumer freemail domains (gmail.com, etc.) so B2C/freemail leads aren't blocked.
               Fails closed gracefully on database/network timeout.
               Searches both exact domain column and email domain patterns (@company.com) for un-normalized leads.
    - Layer 2: Sanitizes domain string, strips protocol/www/paths, and prevents unauthorized cross-tenant leaks.
    """
    if not supabase_client or not workspace_id or not company_domain:
        return {"collision_detected": False, "company_domain": "", "reason": "MISSING_PARAMETERS"}

    clean_ws = str(workspace_id).strip()
    clean_domain = str(company_domain).strip().lower()
    
    # Strip URL schemes and path prefixes if a full URL was passed
    if "://" in clean_domain:
        clean_domain = clean_domain.split("://", 1)[1]
    if "/" in clean_domain:
        clean_domain = clean_domain.split("/", 1)[0]
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]
    clean_domain = clean_domain.strip()

    if not clean_domain:
        return {"collision_detected": False, "company_domain": "", "reason": "EMPTY_DOMAIN"}

    if not strict_account_exclusivity:
        return {"collision_detected": False, "company_domain": clean_domain, "reason": "EXCLUSIVITY_DISABLED"}

    if clean_domain in _FREEMAIL_EXEMPT_DOMAINS:
        return {"collision_detected": False, "company_domain": clean_domain, "reason": "FREEMAIL_DOMAIN_EXEMPT"}

    # Determine target workspaces for enterprise scope
    target_workspaces = [clean_ws]
    if enterprise_workspace_ids and isinstance(enterprise_workspace_ids, list):
        for e_ws in enterprise_workspace_ids:
            s_ws = str(e_ws).strip()
            if s_ws and s_ws not in target_workspaces:
                target_workspaces.append(s_ws)

    try:
        domain_leads: List[str] = []
        for target_ws in target_workspaces:
            # 1. Fetch leads by domain column
            leads_res = supabase_client.table("leads").select("id").eq("workspace_id", target_ws).eq("domain", clean_domain).limit(500).execute()
            l_data = getattr(leads_res, "data", None) or []
            if isinstance(l_data, list):
                for r in l_data:
                    if isinstance(r, dict) and "id" in r:
                        domain_leads.append(str(r["id"]).strip())

            # 2. Un-normalized email domain fallback (e.g. leads where domain was not yet indexed)
            if len(domain_leads) < 50:
                try:
                    email_pattern = f"%@{clean_domain}"
                    email_leads_res = supabase_client.table("leads").select("id").eq("workspace_id", target_ws).ilike("email", email_pattern).limit(200).execute()
                    e_data = getattr(email_leads_res, "data", None) or []
                    if isinstance(e_data, list):
                        for r in e_data:
                            if isinstance(r, dict) and "id" in r:
                                lid = str(r["id"]).strip()
                                if lid not in domain_leads:
                                    domain_leads.append(lid)
                except Exception as _email_fallback_err:
                    logger.debug(f"[CollisionGuard] Email pattern fallback notice: {_email_fallback_err}")

        if not domain_leads:
            return {"collision_detected": False, "company_domain": clean_domain, "reason": "NO_SIBLING_LEADS_FOUND"}

        # 3. Check if any sibling lead is actively in-flight in another active campaign across target workspaces
        for target_ws in target_workspaces:
            colliding_ids = get_conflicting_active_leads(
                supabase_client=supabase_client,
                workspace_id=target_ws,
                lead_ids=domain_leads,
                exclude_campaign_id=exclude_campaign_id,
                active_statuses=active_statuses,
            )

            if colliding_ids:
                conflicting_lid = next(iter(colliding_ids))
                logger.info(
                    f"[CollisionGuard] Account exclusivity collision detected for domain '{clean_domain}' "
                    f"in workspace '{target_ws}' (conflicting lead: {conflicting_lid})"
                )
                return {
                    "collision_detected": True,
                    "company_domain": clean_domain,
                    "conflicting_lead_id": conflicting_lid,
                    "colliding_workspace_id": target_ws,
                    "reason": "ACCOUNT_EXCLUSIVITY_COLLISION",
                }

        return {"collision_detected": False, "company_domain": clean_domain}

    except Exception as exc:
        logger.error(f"[CollisionGuard] check_company_domain_exclusivity error for domain {clean_domain}: {exc}", exc_info=True)
        # Paranoia Layer 1: Fail closed on unexpected exception
        return {
            "collision_detected": True,
            "company_domain": clean_domain,
            "reason": f"FAIL_CLOSED_ERROR: {str(exc)}",
        }
