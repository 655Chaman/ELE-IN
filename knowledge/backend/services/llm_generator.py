from knowledge.backend.services.prompt_safety import sanitize_for_prompt, truncate_to_context_limit, truncate_to_tokens
from knowledge.backend.services.ai_output_guard import PREAMBLE_PATTERNS, REFUSAL_PATTERN
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from knowledge.backend.services.vector_store import vector_store

# Attempt to import openai, fail gracefully if not installed/configured
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

class LLMGenerator:
    def __init__(self):
        self.doctrine_text = ""
        self.client = None
        self.model_name = "gpt-4o-mini"
        self._load_doctrine()
        self._init_client()

    def _load_doctrine(self):
        """Loads the sales_call_rules.md doctrine into memory."""
        # Adjust path relative to the backend app
        doctrine_path = Path(__file__).parent.parent.parent.parent / "ELEMEET" / "sales_call_rules.md"
        try:
            if doctrine_path.exists():
                with open(doctrine_path, encoding="utf-8") as f:
                    self.doctrine_text = f.read()
                logger.info(f"Loaded Elemeet Doctrine from {doctrine_path} ({len(self.doctrine_text)} chars)")
            else:
                logger.warning(f"Doctrine file not found at {doctrine_path}")
        except Exception as e:
            logger.error(f"Failed to load doctrine: {e}")

    def _init_client(self):
        """Initialize the OpenAI async client. Uses NVIDIA if key is provided (priority), falls back to OpenAI if available."""
        if not HAS_OPENAI:
            logger.error("OpenAI package not available! Cannot initialize LLMGenerator.")
            return

        nvidia_api_key = os.environ.get("NVIDIA_API_KEY")
        openai_api_key = os.environ.get("OPENAI_API_KEY")

        if not (nvidia_api_key or openai_api_key):
            try:
                from core.backend.services.key_service import get_current_keys
                keys = get_current_keys()
                nvidia_api_key = keys.get("api_key_nvidia")
                openai_api_key = keys.get("api_key_openai") or keys.get("api_key_llm")
            except Exception as e:
                logger.debug(f"Could not load keys from key_service: {e}")

        if nvidia_api_key:
            self.client = AsyncOpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=str(nvidia_api_key).strip().strip("'\"")
            )
            self.model_name = "meta/llama-3.1-8b-instruct"
            logger.info("NVIDIA client initialized for LLM Generator.")
        elif openai_api_key:
            self.client = AsyncOpenAI(api_key=str(openai_api_key).strip().strip("'\""))
            self.model_name = "gpt-4o-mini"
            logger.info("OpenAI client initialized for LLM Generator.")
        else:
            logger.warning("No API keys (NVIDIA or OPENAI) found in environment or system keys. LLM generation will fail until keys are provided.")

    def _get_system_prompt(self, rag_context: str = "") -> str:
        base_prompt = f"""You are 'Elemeet', an elite sales meeting co-pilot for a Market Maker / Connector business.
You are listening to a live sales call transcript. You will receive the rolling history of the conversation.
Your job is to act as a teleprompter for the salesperson.

CRITICAL INSTRUCTIONS:
1. Analyze the rolling conversation memory. Generate a word-for-word response for the salesperson to read *right now*.
2. The response MUST strictly adhere to the business rules, frameworks, and tone defined in the "HQ Doctrine" below.
3. If the prospect raises an objection, immediately deploy the exact framework from the doctrine or the relevant context.
4. Output ONLY the raw text that the salesperson should say. Do not output JSON.
5. NEVER apologize, hedge, or act subservient. Maintain high status and frame control.

--- HQ DOCTRINE (BASE RULES) ---
{self.doctrine_text}
--- HQ DOCTRINE END ---
"""
        if rag_context:
            base_prompt += f"\n--- SPECIFIC SITUATION PROTOCOLS (PRIORITIZE THESE) ---\n{rag_context}\n--- END PROTOCOLS ---\n"
            
        return base_prompt

    async def generate_response(self, recent_transcript: str, session_memory: str, workspace_id: str):
        """
        Generates a streaming teleprompter response based on the conversation memory.
        Yields text chunks as they arrive.
        """
        from core.backend.api.auth_dep import get_service_client
        import time
        import json
        
        if not recent_transcript or len(recent_transcript.strip()) < 5:
            yield ""
            return

        import hashlib
        digest = hashlib.sha256(recent_transcript.encode("utf-8")).hexdigest()[:16]
        p_idempotency_key = f"coach_{workspace_id}_{digest}"

        try:
            _svc = get_service_client()
            _deduct_res = _svc.rpc('deduct_credits_safely', {
                'p_workspace_id': workspace_id,
                'p_amount': 1,
                'p_action_type': 'ai_coaching',
                'p_idempotency_key': p_idempotency_key,
                'p_metadata': json.dumps({"model": self.model_name})
            }).execute()
            if _deduct_res.data and not _deduct_res.data.get('success', False):
                yield "[System Error: Insufficient credits for AI coaching]"
                return
        except Exception as e:
            logger.error(f"Credit deduction failed: {e}")
            yield f"[System Error: Credit check failed - {e!s}]"
            return

        if self.client is None:
            self._init_client()

        if self.client:
            try:
                # 1. Retrieve specific protocols via Vector Semantic RAG using the latest phrase
                rag_text = ""
                if vector_store is not None:
                    try:
                        rag_context = vector_store.retrieve(recent_transcript, workspace_id)
                        if isinstance(rag_context, list):
                            rag_text = "\n\n".join([c.get("content", "") for c in rag_context if isinstance(c, dict) and c.get("content")])
                        elif isinstance(rag_context, str):
                            rag_text = rag_context
                    except Exception as rag_err:
                        logger.warning(f"Vector store retrieval failed: {rag_err}")

                if rag_text:
                    logger.info(f"RAG triggered! Injected {len(rag_text)} chars of context.")

                bounded_session = truncate_to_tokens(session_memory, 1500)
                bounded_recent = truncate_to_tokens(recent_transcript, 500)

                # Using selected model
                msgs = [
                        {"role": "system", "content": self._get_system_prompt(sanitize_for_prompt(rag_text, "rag_context"))},
                        {"role": "user", "content": f"Rolling Conversation Memory:\n{sanitize_for_prompt(bounded_session, 'session_memory')}\n\nLatest Prospect Input: {sanitize_for_prompt(bounded_recent, 'recent_transcript')}"}
                    ]
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=truncate_to_context_limit(msgs, max_tokens=2000),
                    temperature=0.3,
                    max_tokens=200,
                    stream=True,
                    stream_options={"include_usage": True}
                )
                
                final_usage = None
                full_output = []
                buffer = ""
                preamble_checked = False

                async for chunk in response:
                    if hasattr(chunk, 'usage') and chunk.usage:
                        final_usage = chunk.usage
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_output.append(token)

                        # Paranoia Layer 0 & 1: Buffer initial tokens to neutralize AI conversational preambles
                        if not preamble_checked:
                            buffer += token
                            if len(buffer) >= 60 or "\n" in buffer:
                                cleaned_buf = buffer
                                for p in PREAMBLE_PATTERNS:
                                    cleaned_buf = p.sub("", cleaned_buf).lstrip()
                                if REFUSAL_PATTERN.search(cleaned_buf):
                                    cleaned_buf = "[Address objection directly based on value proposition]"
                                buffer = ""
                                preamble_checked = True
                                if cleaned_buf:
                                    yield cleaned_buf
                        else:
                            yield token

                if buffer and not preamble_checked:
                    cleaned_buf = buffer
                    for p in PREAMBLE_PATTERNS:
                        cleaned_buf = p.sub("", cleaned_buf).lstrip()
                    if cleaned_buf:
                        yield cleaned_buf
                        
                if final_usage:
                    p_toks = getattr(final_usage, 'prompt_tokens', 0)
                    c_toks = getattr(final_usage, 'completion_tokens', 0)
                    t_toks = getattr(final_usage, 'total_tokens', p_toks + c_toks)
                    logger.info(f"Stream completed. prompt_tokens={p_toks} completion_tokens={c_toks}")
                    try:
                        from knowledge.backend.services.elein_ai_service import _log_ai_generation
                        from core.backend.api.auth_dep import get_service_client
                        _log_ai_generation(
                            supabase=get_service_client(),
                            workspace_id=workspace_id,
                            lead_id="00000000-0000-0000-0000-000000000000",
                            node_id="teleprompter",
                            prompt="[System Prompt Hidden for Teleprompter]",
                            output="".join(full_output),
                            model=self.model_name,
                            tokens_used=t_toks,
                            prompt_tokens=p_toks,
                            completion_tokens=c_toks
                        )
                    except Exception as e:
                        logger.error(f"Failed to log LLM generation usage: {e}")
                return
            except Exception as e:
                logger.error(f"Coaching generation failed: {e}")
                try:
                    # Paranoia Layer 0 & 1: Prevent multi-tenant refund collision by explicitly embedding workspace_id
                    _svc.rpc('add_credits_safely', {
                        'p_workspace_id': workspace_id,
                        'p_credits': 1,
                        'p_event_id': f"refund_coach_{workspace_id}_{digest}",
                        'p_provider': 'system_refund'
                    }).execute()
                except Exception:
                    pass
                yield f"[System Error: {e!s}]"
                return
                
        else:
            error_msg = "[System Error: LLM Client not initialized. Please configure API keys.]"
            logger.error(error_msg)
            yield error_msg
            return

llm_generator = LLMGenerator()
