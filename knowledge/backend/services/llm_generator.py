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

        if nvidia_api_key:
            self.client = AsyncOpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=nvidia_api_key
            )
            self.model_name = "meta/llama-3.1-8b-instruct"
            logger.info("NVIDIA client initialized for LLM Generator.")
        elif openai_api_key:
            self.client = AsyncOpenAI(api_key=openai_api_key)
            self.model_name = "gpt-4o-mini"
            logger.info("OpenAI client initialized for LLM Generator.")
        else:
            logger.error("No API keys (NVIDIA or OPENAI) found in environment. LLM generation will fail.")

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
        if not recent_transcript or len(recent_transcript.strip()) < 5:
            yield ""
            return

        if self.client:
            try:
                # 1. Retrieve specific protocols via Vector Semantic RAG using the latest phrase
                rag_context = vector_store.retrieve(recent_transcript, workspace_id)
                if rag_context:
                    logger.info(f"RAG triggered! Injected {len(rag_context)} chars of context.")

                # Using selected model
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(rag_context)},
                        {"role": "user", "content": f"Rolling Conversation Memory:\n{session_memory}\n\nLatest Prospect Input: '{recent_transcript}'"}
                    ],
                    temperature=0.3,
                    max_tokens=200,
                    stream=True
                )
                
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                logger.error(f"LLM Generation Error: {e}")
                yield f"[System Error: LLM Generation failed - {e!s}]"
                return
                
        else:
            error_msg = "[System Error: LLM Client not initialized. Please configure API keys.]"
            logger.error(error_msg)
            yield error_msg
            return

llm_generator = LLMGenerator()
