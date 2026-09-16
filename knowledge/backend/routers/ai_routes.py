from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import json
import asyncio

from core.backend.api.auth_dep import get_current_workspace
from inbox.backend.schemas.inbox import AISuggestRequest, IntentRequest

router = APIRouter(tags=["ai"])

@router.post("/ai-suggest")
async def ai_suggest_reply(req: AISuggestRequest, workspace_id: str = Depends(get_current_workspace)):
    """Stream a context-aware reply draft for a LinkedIn thread."""
    from knowledge.backend.services.elein_ai_service import stream_reply_draft

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
    return await classify_intent(req.message_text, workspace_id=workspace_id)
