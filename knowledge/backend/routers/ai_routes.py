from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
import asyncio

from core.backend.api.auth_dep import get_current_workspace
from inbox.backend.schemas.inbox import AISuggestRequest, IntentRequest
from core.backend.services.credit_service import get_credit_balance

router = APIRouter(tags=["ai"])

@router.post("/ai-suggest")
async def ai_suggest_reply(req: AISuggestRequest, workspace_id: str = Depends(get_current_workspace)):
    """Stream a context-aware reply draft for a LinkedIn thread."""
    from knowledge.backend.services.elein_ai_service import stream_reply_draft

    # Paranoia Layer 1: Fast credit balance check before initializing stream (bypassed in sandbox simulation)
    if not req.is_simulation:
        bal = get_credit_balance(workspace_id)
        # Determine plan tier overdraft limit:
        # Free tier cannot overdraft: requires bal >= 5.
        # Paid tiers (PRO, GROWTH, ENTERPRISE, AGENCY) can overdraft down to -500: requires bal >= -495.
        from core.backend.api.auth_dep import get_service_client
        try:
            supabase = get_service_client()
            res = supabase.table("workspaces").select("tier, plan").eq("id", workspace_id).execute()
            raw_tier = "FREE"
            if res.data:
                raw_tier = res.data[0].get("tier") or res.data[0].get("plan") or "FREE"
            tier = str(raw_tier).strip().upper()
        except Exception:
            tier = "FREE"

        from core.backend.services.credit_service import get_workspace_overdraft_floor
        min_floor = get_workspace_overdraft_floor(tier)
        min_required = min_floor + 5
        if bal < min_required:
            raise HTTPException(
                status_code=402,
                detail="Insufficient credits for AI Ghostwriter. Please top up your balance."
            )

    async def generate():
        yield " "
        try:
            gen = stream_reply_draft(
                sender_name=req.sender_name,
                thread_messages=req.thread_messages,
                intent=req.intent,
                lead_profile=req.lead_profile or None,
                campaign_context=req.campaign_context or None,
                workspace_id=workspace_id,
                idempotency_key=req.idempotency_key or None,
                is_simulation=bool(req.is_simulation),
            )
            while True:
                try:
                    token = await asyncio.wait_for(gen.__anext__(), timeout=45.0)
                    yield token
                except StopAsyncIteration:
                    break
        except asyncio.TimeoutError:
            yield "ERROR: AI response timed out. Please try again."
        except Exception as e:
            yield f"ERROR: {str(e) if 'rate' not in str(e).lower() else 'AI Temporarily Unavailable due to rate limits.'}"

    return StreamingResponse(generate(), media_type="text/plain")

@router.post("/classify-intent", response_model=dict)
async def classify_message_intent(req: IntentRequest, workspace_id: str = Depends(get_current_workspace)):
    """Classify a single message into an intent bucket."""
    from knowledge.backend.services.elein_ai_service import classify_intent
    return await classify_intent(req.message_text, workspace_id=workspace_id, idempotency_key=req.idempotency_key or None)
