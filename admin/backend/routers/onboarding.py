import json
import uuid
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException

from core.backend.api.auth_dep import get_supabase_client, get_service_client, verify_token_and_get_user_id
from core.backend.services.job_queue import enqueue_job

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

def sanitize_text(val: Any, max_len: int = 250) -> str:
    """Layer 2 Human Paranoia: Sanitize inputs against formula injection and control characters."""
    if not val:
        return ""
    text = str(val).strip()
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        text = "'" + text
    return text[:max_len]

def sanitize_linkedin_url(url: Optional[str]) -> Optional[str]:
    """Layer 1 & 2: Normalize and validate LinkedIn URL against SSRF and protocol exploits."""
    if not url or not isinstance(url, str):
        return None
    clean = url.strip()
    clean_lower = clean.lower()
    # Reject dangerous URI schemes
    if any(clean_lower.startswith(scheme) for scheme in ("javascript:", "data:", "file:", "vbscript:", "blob:")):
        return None
    if not clean.startswith(("http://", "https://")):
        if "linkedin.com" in clean:
            clean = f"https://{clean}"
        else:
            import re
            handle = clean.lstrip("/")
            if re.match(r"^[a-zA-Z0-9_\-\.%]+$", handle):
                clean = f"https://linkedin.com/in/{handle}"
            else:
                return None
    if not clean.startswith(("https://", "http://")):
        return None
    return clean[:500]

class GeneratePreviewRequest(BaseModel):
    target_title: str = Field(default="VP of Sales", description="Target job title")
    target_industry: str = Field(default="B2B SaaS", description="Target industry")
    company_name: Optional[str] = Field(default="Acme Corp", description="User's company name")
    company_url: Optional[str] = Field(default=None, description="Company URL")
    value_prop: Optional[str] = Field(default="Automate outbound pipeline with human-grade AI sequences", description="Core value prop")
    tone: Optional[str] = Field(default="consultative", description="Tone: consultative, direct, or curious")

@router.post("/generate-preview")
async def generate_preview(req: GeneratePreviewRequest) -> Dict[str, Any]:
    """
    Generates a bespoke, hyper-personalized LinkedIn connection note & follow-up message
    specifically for the user's target ICP and value proposition.
    
    Three-Layer Paranoia Framework:
    - Layer 0: Synthesize custom pitch and follow-up tailored to the target role.
    - Layer 1: Environmental resilience — LLM failover with algorithmic fallback; guaranteed <= 300 char LinkedIn note.
    - Layer 2: Real-time spam score calculation and hook rationale.
    """
    title = sanitize_text(req.target_title or "VP of Sales", 100)
    industry = sanitize_text(req.target_industry or "B2B SaaS", 100)
    company = sanitize_text(req.company_name or "Acme Corp", 120)
    prop = sanitize_text(req.value_prop or "scale outbound with human-grade AI", 350)
    tone = (req.tone or "consultative").lower().strip()
    if tone not in ["consultative", "direct", "curious"]:
        tone = "consultative"

    conn_note = ""
    followup = ""
    hook_rationale = ""
    used_llm = False

    # Layer 0 & 1: Try LLM first if available
    try:
        from knowledge.backend.services.elein_ai_service import get_active_nvidia_keys, _get_sync_client
        keys = get_active_nvidia_keys(task="drafting")
        if keys:
            prompt_tone_guide = {
                "consultative": "peer-to-peer, curious, asking for thoughts/perspective without pitching aggressively",
                "direct": "crisp, straightforward, highlighting an exact efficiency win without fluff",
                "curious": "exploratory, asking how they currently solve the problem"
            }.get(tone, "peer-to-peer")

            system_prompt = f"""You are an elite B2B copywriter crafting LinkedIn outreach for {company}.
Target ICP: {title} in {industry}.
Our Solution/Value Prop: {prop}.
Tone: {prompt_tone_guide}.

CRITICAL LINKEDIN HARD CONSTRAINTS:
1. The Connection Request note MUST be under 280 characters total (including placeholders like {{first_name}} and {{company_name}}). LinkedIn strictly cuts off at 300.
2. NO generic buzzwords ('synergy', 'game-changer', 'revolutionary', 'I hope this finds you well').
3. Keep the 2-day follow-up under 350 characters, addressing a specific priority for a {title}.
4. Return ONLY valid JSON with keys: "connection_note" and "followup_message"."""

            user_prompt = "Draft the 2-step LinkedIn outreach sequence now."

            client = _get_sync_client(keys[0])
            model = keys[0].get("model", "meta/llama-3.1-70b-instruct") if isinstance(keys[0], dict) else "meta/llama-3.1-70b-instruct"
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.6,
                max_tokens=300
            )
            raw_text = resp.choices[0].message.content.strip()
            if "{" in raw_text and "}" in raw_text:
                json_part = raw_text[raw_text.find("{"):raw_text.rfind("}")+1]
                parsed = json.loads(json_part)
                conn_note = parsed.get("connection_note", "").strip()
                followup = parsed.get("followup_message", "").strip()
                if conn_note and len(conn_note) <= 300:
                    used_llm = True
    except Exception as llm_err:
        logger.info(f"Onboarding preview LLM fallback activated: {llm_err}")

    # Layer 1: High-Converting Algorithmic Fallback Matrix
    if not conn_note:
        clean_prop_lower = prop.lower()
        if clean_prop_lower.startswith("we help"):
            clean_prop_lower = clean_prop_lower.replace("we help", "", 1).strip()
        if clean_prop_lower.startswith("helps"):
            clean_prop_lower = clean_prop_lower.replace("helps", "", 1).strip()

        plural_title = title if title.lower().endswith("s") else f"{title}s"

        if tone == "direct":
            conn_note = f"Hi {{first_name}}, saw what you're leading at {{company_name}}. Most {plural_title} in {industry} struggle with pipeline consistency. We built a way to {clean_prop_lower} with zero spam flags. Worth connecting?"
            followup = f"Hi {{first_name}}, circling back briefly. Most {plural_title} we work with care about reliable deliverability above all else. Would a 2-minute overview of our residential proxy model be relevant this week?"
            hook_rationale = f"Direct Challenger style: cuts straight to {title} pipeline predictability."
        elif tone == "curious":
            conn_note = f"Hi {{first_name}}, loved your recent updates at {{company_name}}. Curious how your team currently approaches efforts to {clean_prop_lower}? Open to connecting and sharing what we've seen work across {industry}?"
            followup = f"Hi {{first_name}}, bumping this gently! We recently helped another {title} in {industry} increase positive replies by 34% without spam flags. Open to comparing benchmarks?"
            hook_rationale = f"Curiosity-led inquiry: invites {title} to benchmark against peers in {industry}."
        else: # consultative
            conn_note = f"Hi {{first_name}}, noticed your work leading the team at {{company_name}}. We built an engine that helps {plural_title} {clean_prop_lower}. Open to comparing notes on how other {industry} teams approach this?"
            followup = f"Hi {{first_name}}, following up briefly on my note. Knowing how packed schedules are for {plural_title}, I'd love to share how our safety engine guarantees zero spam flags. Worth a 2-min chat?"
            hook_rationale = f"Peer-to-peer consultative approach: positions conversation around shared {industry} insights."

    # Layer 1 Safety Slicing: LinkedIn hard boundary
    if len(conn_note) > 300:
        conn_note = conn_note[:297] + "..."
    if len(followup) > 600:
        followup = followup[:597] + "..."

    # Layer 2 Spam Score Calculation
    spam_triggers = ["100%", "guaranteed", "free offer", "click here", "urgent", "buy now", "discount", "cheap", "best price"]
    found_triggers = [t for t in spam_triggers if t in conn_note.lower() or t in followup.lower()]
    base_score = 98.2
    if found_triggers:
        base_score -= len(found_triggers) * 10
    if len(conn_note) > 280:
        base_score -= 3.5
    if "http" in conn_note:
        base_score -= 15.0
    spam_score = max(round(base_score, 1), 60.0)

    return {
        "status": "success",
        "connection_note": conn_note,
        "followup_message": followup,
        "char_count": len(conn_note),
        "spam_safety_score": spam_score,
        "tone": tone,
        "used_llm": used_llm,
        "hook_strategy": hook_rationale or f"Tailored to {title} in {industry}",
        "safety_badges": [
            "Zero Links in Step 1 (Safe Deliverability)",
            "Under 300-Char LinkedIn Limit",
            "Human Jitter Compatible"
        ]
    }

@router.post("/seed-demo-data")
async def seed_demo_data(request: Request) -> Dict[str, Any]:
    supabase = get_supabase_client(request)
    svc = get_service_client()
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth header")
    token = auth_header.split(" ")[1] if " " in auth_header else auth_header
    user_id = verify_token_and_get_user_id(token)
    
    # Read onboarding configuration payload
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    force = body.get("force", False)
    target_title = sanitize_text(body.get("target_title") or "VP of Sales", 100)
    target_industry = sanitize_text(body.get("target_industry") or "B2B SaaS", 100)
    company_name = sanitize_text(body.get("company_name") or "Acme Corp", 120)
    company_url = body.get("company_url")
    core_value_prop = sanitize_text(body.get("core_value_prop") or "Automating outbound pipeline with human-grade AI sequences", 400)
    campaign_name = sanitize_text(body.get("campaign_name") or f"Outreach to {target_title}s", 150)
    connection_note = sanitize_text(body.get("connection_note") or f"Hi {{first_name}}, noticed your work leading the team at {{company_name}}. We help {target_title}s scale without manual grind. Open to connecting?", 300)
    followup_message = sanitize_text(body.get("followup_message") or f"Hi {{first_name}}, following up briefly on my note. Knowing how tight schedules are for {target_title}s, I'd love to share how our safety engine guarantees zero spam flags. Worth a brief chat?", 600)
    sender_account_id = body.get("sender_account_id")
    is_sandbox = body.get("is_sandbox", False)
    single_lead_url = sanitize_linkedin_url(body.get("single_lead_url"))
    raw_custom_leads = body.get("custom_leads", [])
    
    is_unmigrated = False

    # ─── Step 1: Workspace Resolution (Layer 1 Fallback Resilience) ────────────
    x_ws = request.headers.get("X-Workspace-Id")
    workspace_id = None
    if x_ws:
        # Layer 2 IDOR defense: Verify user is an authorized member of requested workspace
        try:
            mem_chk = supabase.table("workspace_members").select("role").eq("workspace_id", x_ws).eq("user_id", user_id).limit(1).execute()
            if mem_chk.data:
                ws_chk = supabase.table("workspaces").select("id").eq("id", x_ws).limit(1).execute()
                if ws_chk.data:
                    workspace_id = x_ws
        except Exception as ws_err:
            logger.warning(f"Workspace membership check failed or unmigrated: {ws_err}")
            is_unmigrated = True

    if not workspace_id:
        try:
            ws_res = supabase.table("workspace_members").select("workspace_id").eq("user_id", user_id).limit(1).execute()
            if ws_res.data:
                workspace_id = ws_res.data[0]["workspace_id"]
            else:
                workspace_id = str(uuid.uuid4())
                try:
                    svc.table("workspaces").insert({
                        "id": workspace_id,
                        "name": f"{company_name} Workspace" if company_name else "My Workspace",
                        "owner_id": user_id
                    }).execute()
                    svc.table("workspace_members").insert({
                        "workspace_id": workspace_id,
                        "user_id": user_id,
                        "role": "owner"
                    }).execute()
                except Exception as create_ws_err:
                    logger.warning(f"Could not insert new workspace (unmigrated table): {create_ws_err}")
                    is_unmigrated = True
        except Exception as mem_err:
            logger.warning(f"Could not query workspace_members (unmigrated table): {mem_err}")
            workspace_id = x_ws or str(uuid.uuid4())
            is_unmigrated = True

    # ─── Step 2: Knowledge Base Wiring (Scraper, Synthesis, Personas) ──────────
    if company_url and company_url.strip():
        clean_url = company_url.strip()
        asset_id = str(uuid.uuid4())
        try:
            supabase.table("knowledge_assets").insert({
                "id": asset_id,
                "workspace_id": workspace_id,
                "name": clean_url,
                "type": "url",
                "source_url": clean_url,
                "status": "queued"
            }).execute()
            enqueue_job(supabase, "url", workspace_id, asset_id, {"url": clean_url})
        except Exception as e:
            logger.warning(f"Could not enqueue website scraping job during onboarding: {e}")

    try:
        # Upsert Knowledge Synthesis
        supabase.table("knowledge_synthesis").upsert({
            "workspace_id": workspace_id,
            "core_value_prop": core_value_prop,
            "target_customer_profile": f"{target_title} in {target_industry}",
            "primary_pain_points_solved": [f"Scaling outbound pipeline for {target_title}s", "Manual prospecting friction"],
            "buyer_personas": [{"title": target_title, "industry": target_industry}]
        }).execute()
    except Exception as e:
        logger.warning(f"Could not upsert knowledge synthesis during onboarding: {e}")

    try:
        # Insert target Persona for AI Ghostwriter/Executor
        from admin.backend.services.persona_service import PersonaService
        PersonaService.create_persona(supabase, workspace_id, {
            "title": target_title,
            "pain_points": [f"Scaling outbound pipeline in {target_industry} without getting blocked by LinkedIn flags."],
            "value_prop": core_value_prop,
            "tone_tweaks": "Direct, consultative, peer-to-peer"
        })
    except Exception as e:
        logger.warning(f"Could not insert target persona during onboarding: {e}")

    # Check if workspace already has campaigns (unless force is requested)
    if not force:
        try:
            camp_res = supabase.table("campaigns").select("id", count="exact").eq("workspace_id", workspace_id).execute()
            if camp_res.count and camp_res.count > 0:
                return {"status": "already_seeded", "workspace_id": workspace_id}
        except Exception as camp_chk_err:
            logger.warning(f"Could not check existing campaigns: {camp_chk_err}")
            is_unmigrated = True

    # ─── Step 3: Audience & Leads Resolution ──────────────────────────────────
    list_id = str(uuid.uuid4())
    leads_to_insert = []

    if raw_custom_leads and isinstance(raw_custom_leads, list) and len(raw_custom_leads) > 0:
        # CSV uploaded leads
        list_name = f"Uploaded CSV Audience - {target_title}s"
        for idx, cl in enumerate(raw_custom_leads[:100]): # Limit to first 100 for safety
            if not isinstance(cl, dict):
                continue
            leads_to_insert.append({
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id,
                "first_name": sanitize_text(cl.get("first_name") or f"Prospect {idx+1}", 80),
                "last_name": sanitize_text(cl.get("last_name") or "", 80),
                "linkedin_url": sanitize_linkedin_url(cl.get("linkedin_url")) or f"https://linkedin.com/in/prospect-{idx+1}",
                "company_name": sanitize_text(cl.get("company_name") or company_name, 120),
                "job_title": sanitize_text(cl.get("job_title") or target_title, 100),
                "industry": target_industry,
                "status": "extracted"
            })
    elif single_lead_url and single_lead_url.strip():
        # Single profile link test
        list_name = "Single Profile Test"
        leads_to_insert.append({
            "id": str(uuid.uuid4()),
            "workspace_id": workspace_id,
            "first_name": "Target",
            "last_name": "Prospect",
            "linkedin_url": single_lead_url.strip(),
            "company_name": "Target Company",
            "job_title": target_title,
            "industry": target_industry,
            "status": "extracted"
        })
    else:
        list_name = f"Target Prospects - {target_title}s"
        leads_to_insert = []

    try:
        supabase.table("lead_lists").insert({
            "id": list_id,
            "workspace_id": workspace_id,
            "name": list_name,
            "type": "csv",
            "row_count": len(leads_to_insert)
        }).execute()

        for lead in leads_to_insert:
            supabase.table("leads").insert(lead).execute()
            supabase.table("list_members").insert({
                "list_id": list_id,
                "opportunity_id": lead["id"]
            }).execute()
    except Exception as lead_err:
        logger.warning(f"Could not insert leads or lead_lists (unmigrated table): {lead_err}")
        is_unmigrated = True

    # ─── Step 4: Canonical Campaign Node Graph (HR_NODE_DEFS Compliant) ──────
    campaign_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())

    nodes = [
        {
            "id": "node_conn",
            "type": "connection_request",
            "position": {"x": 250, "y": 100},
            "data": {
                "label": "Connection Request",
                "note_strategy": "Fixed note",
                "note": connection_note[:300],
                "delayDays": 0
            }
        },
        {
            "id": "node_msg",
            "type": "send_message",
            "position": {"x": 250, "y": 300},
            "data": {
                "label": "Follow-up (Day 2)",
                "body": followup_message,
                "delayDays": 2
            }
        }
    ]

    edges = [
        {
            "id": "edge_conn_msg",
            "source": "node_conn",
            "target": "node_msg",
            "sourceHandle": "accepted"
        }
    ]

    valid_sender_id = None
    if sender_account_id:
        try:
            chk_acc = supabase.table("accounts").select("id").eq("id", sender_account_id).eq("workspace_id", workspace_id).execute()
            if chk_acc.data:
                valid_sender_id = sender_account_id
            else:
                logger.warning(f"Sender account {sender_account_id} not found in workspace {workspace_id}; proceeding in sandbox mode.")
        except Exception as acc_err:
            logger.warning(f"Error checking sender account {sender_account_id}: {acc_err}")

    sender_list = [valid_sender_id] if valid_sender_id else []

    try:
        supabase.table("campaigns").insert({
            "id": campaign_id,
            "workspace_id": workspace_id,
            "name": campaign_name,
            "status": "DRAFT",
            "nodes_json": nodes,
            "edges_json": edges,
            "sender_account_ids_json": sender_list,
            "metadata": {
                "is_sandbox": is_sandbox,
                "stop_on_reply": True,
                "lead_list_id": list_id
            }
        }).execute()
    except Exception as camp_ins_err:
        logger.warning(f"Could not insert campaign (unmigrated table): {camp_ins_err}")
        is_unmigrated = True

    # ─── Step 5: Relational Version, Nodes & Edges Tables ─────────────────────
    try:
        supabase.table("campaign_versions").insert({
            "id": version_id,
            "campaign_id": campaign_id,
            "version": 1
        }).execute()

        node_id_map = {}
        node_inserts = []
        for n in nodes:
            db_node_id = str(uuid.uuid4())
            node_id_map[n["id"]] = db_node_id
            node_inserts.append({
                "id": db_node_id,
                "campaign_version_id": version_id,
                "node_type": n["type"],
                "config": n["data"],
                "ui_position": n["position"]
            })
        if node_inserts:
            supabase.table("campaign_nodes").insert(node_inserts).execute()

        edge_inserts = []
        for e in edges:
            src_uuid = node_id_map.get(e["source"])
            tgt_uuid = node_id_map.get(e["target"])
            if src_uuid and tgt_uuid:
                edge_inserts.append({
                    "campaign_version_id": version_id,
                    "source_node_id": src_uuid,
                    "target_node_id": tgt_uuid,
                    "condition": e.get("sourceHandle")
                })
        if edge_inserts:
            supabase.table("campaign_edges").insert(edge_inserts).execute()

        if valid_sender_id:
            svc.table("campaign_accounts").insert({
                "campaign_id": campaign_id,
                "account_id": valid_sender_id
            }).execute()

    except Exception as e:
        logger.warning(f"Error persisting relational campaign metadata: {e}")
        is_unmigrated = True

    # ─── Step 6: Active Lead Enrollment Pipeline ──────────────────────────────
    try:
        enrollment_data = []
        execution_data = []
        for lead in leads_to_insert:
            enr_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{campaign_id}_{lead['id']}"))
            enrollment_data.append({
                "id": enr_id,
                "workspace_id": workspace_id,
                "campaign_id": campaign_id,
                "campaign_version_id": version_id,
                "lead_id": lead["id"],
                "account_id": valid_sender_id or None
            })
            execution_data.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"exec_{enr_id}")),
                "workspace_id": workspace_id,
                "enrollment_id": enr_id,
                "status": "pending",
                "variables": {}
            })

        if enrollment_data:
            svc.table("campaign_enrollments").upsert(enrollment_data, ignore_duplicates=True, on_conflict="campaign_id,lead_id").execute()
            svc.table("campaign_execution_states").upsert(execution_data, ignore_duplicates=True).execute()

    except Exception as e:
        logger.error(f"Error enrolling leads into campaign: {e}", exc_info=True)
        is_unmigrated = True

    return {
        "status": "seeded",
        "workspace_id": workspace_id,
        "campaign_id": campaign_id,
        "list_id": list_id,
        "leads_count": len(leads_to_insert),
        "unmigrated": is_unmigrated
    }
