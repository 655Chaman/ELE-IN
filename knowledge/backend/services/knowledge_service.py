import requests
import os
import io
import json
import logging
import uuid
import re
import httpx
from typing import Dict, List, Optional
from datetime import datetime

from knowledge.backend.services.elein_ai_service import (
    HAS_LLM, get_active_nvidia_keys, _get_async_client, ROUTING_CONFIG, _mark_key_failed
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_vector_store():
    """Lazy-import to avoid circular dependencies."""
    from knowledge.backend.services.vector_store import SemanticBrain
    from core.backend.api.auth_dep import get_service_client
    return SemanticBrain(get_service_client())


def _get_service_client():
    from core.backend.api.auth_dep import get_service_client
    return get_service_client()


# ---------------------------------------------------------------------------
# KnowledgeService
# ---------------------------------------------------------------------------

class KnowledgeService:

    # ───────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _finalize_asset_processing(
        supabase,
        asset_id: str,
        workspace_id: str,
        status: str,
        chunk_count: int = 0,
        error_msg: str = "",
    ):
        """Update asset row to final state and kick off synthesis if success."""
        update_payload: dict = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if error_msg:
            update_payload["error_msg"] = error_msg

        try:
            supabase.table("knowledge_assets") \
                .update(update_payload) \
                .eq("id", asset_id) \
                .execute()
        except Exception as e:
            logger.error(f"[KB] _finalize_asset_processing update failed: {e}")

        # Layer 1 Paranoia: Reconcile chunk_count from DB ground truth in case trigger misfired
        if status == "synced":
            try:
                count_res = supabase.table("knowledge_chunks").select("id", count="exact").eq("asset_id", asset_id).execute()
                real_count = count_res.count if count_res.count is not None else 0
                if real_count == 0:
                    try:
                        count_legacy = supabase.table("knowledge_vectors").select("id", count="exact").eq("asset_id", asset_id).execute()
                        real_count = count_legacy.count if count_legacy.count is not None else 0
                    except Exception:
                        pass
                supabase.table("knowledge_assets").update({"chunk_count": real_count}).eq("id", asset_id).execute()
            except Exception as ce:
                logger.warning(f"[KB] chunk_count reconciliation failed for {asset_id}: {ce}")

        if status == "synced":
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(KnowledgeService.update_synthesis(supabase, workspace_id))
                else:
                    loop.run_until_complete(KnowledgeService.update_synthesis(supabase, workspace_id))
            except Exception as e:
                logger.error(f"[KB] Could not schedule synthesis after finalize: {e}")

    # ───────────────────────────────────────────────────────────────────────
    # URL processing
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _scrape_url_resilient(url: str) -> str:
        """
        Layer 0 & 1 Paranoia: Multi-tiered resilient URL scraper.
        Tier 1: Jina.ai Reader with redirects followed
        Tier 2: Direct HTTP fetch with desktop browser headers + HTML text extraction
        """
        # Tier 1: Try Jina Reader
        try:
            jina_url = f"https://r.jina.ai/{url}"
            async with httpx.AsyncClient(timeout=18.0, follow_redirects=True) as client:
                resp = await client.get(
                    jina_url, 
                    headers={"Accept": "text/plain", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
            if resp.status_code == 200:
                text = resp.text.strip()
                if not text.startswith("<!DOCTYPE") and not text.startswith("<html") and len(text) >= 50:
                    logger.info(f"[KB] Tier 1 (Jina) scraped {len(text)} chars from {url}")
                    return text
        except Exception as j_err:
            logger.warning(f"[KB] Tier 1 Jina scraping failed for {url}: {j_err}")

        # Tier 2: Direct HTTP request with realistic desktop headers
        try:
            logger.info(f"[KB] Tier 2: Attempting direct HTTP extraction for {url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            async def _safe_redirect_hook(response):
                if response.is_redirect:
                    loc = response.headers.get("location")
                    if loc:
                        from urllib.parse import urljoin
                        from core.backend.core.validators import is_safe_ssrf_url
                        target = urljoin(str(response.url), loc)
                        if not is_safe_ssrf_url(target):
                            raise ValueError(f"SSRF Violation: redirect targets disallowed address: {target}")

            async with httpx.AsyncClient(
                timeout=20.0, 
                follow_redirects=True, 
                verify=False,
                event_hooks={"response": [_safe_redirect_hook]}
            ) as client:
                resp = await client.get(url, headers=headers)
                
            if resp.status_code == 200:
                html = resp.text
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe", "button"]):
                        tag.extract()
                    main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup
                    text = main_content.get_text(separator="\n", strip=True)
                except ImportError:
                    clean = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'<style.*?</style>', '', clean, flags=re.DOTALL | re.IGNORECASE)
                    clean = re.sub(r'<[^>]+>', ' ', clean)
                    text = re.sub(r'\s+', ' ', clean).strip()

                text = re.sub(r'\n{3,}', '\n\n', text).strip()
                if len(text) >= 50:
                    logger.info(f"[KB] Tier 2 (Direct HTTP) successfully extracted {len(text)} chars from {url}")
                    return text
        except Exception as d_err:
            logger.warning(f"[KB] Tier 2 Direct HTTP scraping failed for {url}: {d_err}")

        return ""

    @staticmethod
    async def process_url_bg(supabase, workspace_id: str, url: str, asset_id: str):
        """Background task: scrape a URL using multi-tier fallback and index into vector store."""
        logger.info(f"[KB] Starting URL processing for asset {asset_id}: {url}")
        try:
            from core.backend.core.validators import is_safe_ssrf_url
            if not is_safe_ssrf_url(url):
                raise ValueError("URL rejected due to security safety constraints (private or loopback IP).")

            text = await KnowledgeService._scrape_url_resilient(url)

            if not text or len(text.strip()) < 50:
                raise ValueError("Website could not be extracted (it may be blocked by anti-bot verification or require JavaScript). Please paste the text snippet directly.")

            logger.info(f"[KB] Successfully extracted {len(text)} chars for {url}")

            vs = _get_vector_store()
            vs.index_document(
                content=text,
                source_name=url,
                workspace_id=workspace_id,
                doc_type="url",
                asset_id=asset_id,
            )
            KnowledgeService._finalize_asset_processing(supabase, asset_id, workspace_id, "synced")
            logger.info(f"[KB] URL asset {asset_id} synced")

        except Exception as e:
            logger.error(f"[KB] process_url_bg failed for {asset_id}: {e}")
            try:
                KnowledgeService._finalize_asset_processing(
                    supabase, asset_id, workspace_id, "failed", error_msg=str(e)
                )
            except Exception as fe:
                logger.error(f"[KB] Could not mark asset as failed: {fe}")
            raise

    # ───────────────────────────────────────────────────────────────────────
    # Text processing
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    async def process_text_bg(
        supabase, workspace_id: str, name: str, text: str, asset_id: str
    ):
        """Background task: index raw text into vector store."""
        logger.info(f"[KB] Starting text processing for asset {asset_id}")
        try:
            if not text or len(text.strip()) < 20:
                raise ValueError("Text content is too short to be useful")

            vs = _get_vector_store()
            vs.index_document(
                content=text,
                source_name=name,
                workspace_id=workspace_id,
                doc_type="text",
                asset_id=asset_id,
            )
            KnowledgeService._finalize_asset_processing(supabase, asset_id, workspace_id, "synced")
            logger.info(f"[KB] Text asset {asset_id} synced")

        except Exception as e:
            logger.error(f"[KB] process_text_bg failed for {asset_id}: {e}")
            try:
                KnowledgeService._finalize_asset_processing(
                    supabase, asset_id, workspace_id, "failed", error_msg=str(e)
                )
            except Exception as fe:
                logger.error(f"[KB] Could not mark asset as failed: {fe}")
            raise

    # ───────────────────────────────────────────────────────────────────────
    # PDF processing
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    async def process_pdf_bg(
        supabase, workspace_id: str, filename: str, file_bytes: bytes, asset_id: str
    ):
        """Background task: extract text from a PDF and index into vector store."""
        logger.info(f"[KB] Starting PDF processing for asset {asset_id}: {filename}")
        try:
            if not file_bytes or len(file_bytes) == 0:
                raise ValueError("PDF file is empty (0 bytes).")

            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                text = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                ).strip()
            except ImportError:
                # Fallback: try pdfminer
                from pdfminer.high_level import extract_text_to_fp
                from pdfminer.layout import LAParams
                output = io.StringIO()
                extract_text_to_fp(io.BytesIO(file_bytes), output, laparams=LAParams())
                text = output.getvalue().strip()

            if not text or len(text.strip()) < 50:
                raise ValueError("This PDF contains scanned images or no selectable text. Please upload a text-searchable PDF or paste the text directly into the Text tab.")

            logger.info(f"[KB] Extracted {len(text)} chars from PDF {filename}")

            vs = _get_vector_store()
            vs.index_document(
                content=text,
                source_name=filename,
                workspace_id=workspace_id,
                doc_type="pdf",
                asset_id=asset_id,
            )
            KnowledgeService._finalize_asset_processing(supabase, asset_id, workspace_id, "synced")
            logger.info(f"[KB] PDF asset {asset_id} synced")

        except Exception as e:
            logger.error(f"[KB] process_pdf_bg failed for {asset_id}: {e}")
            try:
                KnowledgeService._finalize_asset_processing(
                    supabase, asset_id, workspace_id, "failed", error_msg=str(e)
                )
            except Exception as fe:
                logger.error(f"[KB] Could not mark asset as failed: {fe}")
            raise

    # ───────────────────────────────────────────────────────────────────────
    # Asset CRUD
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def delete_asset(supabase, workspace_id: str, asset_id: str) -> bool:
        """Delete an asset from DB, vector store, and Supabase storage."""
        # Layer 1 Paranoia: Purge physical file from Supabase Storage to prevent orphan accumulation
        try:
            storage_path = f"{workspace_id}/{asset_id}.pdf"
            supabase.storage.from_("knowledge-files").remove([storage_path])
        except Exception as se:
            logger.debug(f"[KB] Storage cleanup skipped or non-fatal for {asset_id}: {se}")

        try:
            vs = _get_vector_store()
            vs.delete_by_asset_id(asset_id, workspace_id)
        except Exception as e:
            logger.warning(f"[KB] Vector store delete failed for {asset_id}: {e}")

        try:
            supabase.table("knowledge_assets") \
                .delete() \
                .eq("id", asset_id) \
                .eq("workspace_id", workspace_id) \
                .execute()
            return True
        except Exception as e:
            logger.error(f"[KB] DB delete failed for {asset_id}: {e}")
            return False

    @staticmethod
    def get_assets(supabase, workspace_id: str) -> List[Dict]:
        """Return all knowledge assets for this workspace."""
        try:
            res = supabase.table("knowledge_assets") \
                .select("*") \
                .eq("workspace_id", workspace_id) \
                .order("created_at", desc=True) \
                .execute()
            return res.data or []
        except Exception as e:
            logger.error(f"[KB] get_assets failed: {e}")
            return []

    # ───────────────────────────────────────────────────────────────────────
    # Synthesis
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def get_synthesis(supabase, workspace_id: str) -> Optional[Dict]:
        """Return the current synthesis record for this workspace (with draft fallback)."""
        try:
            res = supabase.table("knowledge_synthesis") \
                .select("*") \
                .eq("workspace_id", workspace_id) \
                .limit(1) \
                .execute()
            synthesis = res.data[0] if res.data else None

            # Layer 1 Paranoia: Fallback to draft synthesis if live is pending review or empty
            if not synthesis or not synthesis.get("core_value_prop"):
                try:
                    draft_res = supabase.table("knowledge_synthesis_drafts") \
                        .select("*") \
                        .eq("workspace_id", workspace_id) \
                        .limit(1) \
                        .execute()
                    if draft_res.data and draft_res.data[0].get("core_value_prop"):
                        synthesis = draft_res.data[0]
                        synthesis["is_draft"] = True
                except Exception as de:
                    logger.warning(f"[KB] Draft synthesis fallback failed for {workspace_id}: {de}")

            return synthesis
        except Exception as e:
            logger.error(f"[KB] get_synthesis failed: {e}")
            return None

    @staticmethod
    async def update_synthesis(supabase, workspace_id: str):
        """
        Re-run LLM synthesis over the top KB chunks for this workspace and
        upsert the 6-field result into knowledge_synthesis.
        """
        if not HAS_LLM:
            logger.warning("[KB] update_synthesis skipped — no LLM configured")
            return

        import time
        window_id = int(time.time()) // 300  # 5-minute debounce window
        idemp_key = f"ai_synthesis_{workspace_id}_{window_id}"
        
        try:
            from core.backend.api.auth_dep import get_service_client
            _svc = get_service_client()
            _deduct_res = _svc.rpc('deduct_credits_safely', {
                'p_workspace_id': workspace_id,
                'p_amount': 3,
                'p_action_type': 'ai_synthesis',
                'p_idempotency_key': idemp_key,
                'p_metadata': json.dumps({"reason": "knowledge_synthesis"})
            }).execute()
            
            if _deduct_res.data:
                if not _deduct_res.data.get('success'):
                    logger.warning(f"[KB] Insufficient credits for synthesis in workspace {workspace_id}")
                    return
                if _deduct_res.data.get('reason') == 'already_processed':
                    logger.info(f"[KB] Synthesis already ran recently for workspace {workspace_id} (debounced).")
                    return
        except Exception as e:
            logger.error(f"[KB] Failed to deduct credits for synthesis: {e}")
            return

        logger.info(f"[KB] Running synthesis for workspace {workspace_id}")

        try:
            gathered_chunks = []
            seen_contents = set()
            
            # Layer 0 Paranoia: Multi-thematic extraction across core business dimensions
            thematic_queries = [
                "core product offering, primary value proposition, solutions and features",
                "ideal customer profile, target industries, buyer personas, pains solved",
                "proof points, statistics, metrics, ROI, case studies, customer results",
                "key differentiators, competitive advantages, pricing model, guarantees"
            ]
            
            vs = _get_vector_store()
            if vs:
                for q in thematic_queries:
                    try:
                        q_res = vs.retrieve(query=q, workspace_id=workspace_id, top_k=5, match_threshold=0.32)
                        for r in (q_res or []):
                            cnt = r.get("content", "").strip()
                            if cnt and cnt not in seen_contents:
                                seen_contents.add(cnt)
                                gathered_chunks.append(r)
                    except Exception as q_err:
                        logger.debug(f"[KB] Thematic retrieval for '{q[:30]}' failed: {q_err}")

            # Layer 1 Paranoia: If vector search gathered few chunks, sample directly from knowledge_chunks table
            if len(gathered_chunks) < 5:
                try:
                    db_res = supabase.table("knowledge_chunks").select("id, asset_id, content").eq("workspace_id", workspace_id).order("created_at", desc=True).limit(20).execute()
                    for r in (db_res.data or []):
                        cnt = r.get("content", "").strip()
                        if cnt and cnt not in seen_contents:
                            seen_contents.add(cnt)
                            gathered_chunks.append({
                                "id": r.get("id"),
                                "asset_id": r.get("asset_id"),
                                "content": cnt,
                                "source": "Uploaded Asset"
                            })
                except Exception as dbe:
                    logger.debug(f"[KB] Direct chunk fallback failed: {dbe}")

            # Format context with enriched source attribution (up to 25 representative chunks)
            context_parts = []
            for row in gathered_chunks[:25]:
                source = row.get("source") or row.get("metadata", {}).get("source") or "Document"
                context_parts.append(f"--- Document Context [{source}] ---\n{row['content']}")
            context = "\n\n".join(context_parts)
        except Exception as e:
            logger.error(f"[KB] Multi-thematic retrieval for synthesis failed: {e}")
            return

        if not context or len(context.strip()) < 100:
            # Layer 1 Paranoia: Only clear synthesis if all assets have truly been deleted from workspace.
            existing_assets = KnowledgeService.get_assets(supabase, workspace_id)
            if not existing_assets:
                logger.info(f"[KB] 0 assets remaining in workspace {workspace_id}. Purging synthesis cache.")
                supabase.table("knowledge_synthesis").delete().eq("workspace_id", workspace_id).execute()
                supabase.table("knowledge_synthesis_drafts").delete().eq("workspace_id", workspace_id).execute()
            else:
                logger.warning(f"[KB] Insufficient text extracted ({len(context)} chars), but workspace still has {len(existing_assets)} assets. Preserving existing synthesis to prevent data loss.")
            return

        prompt = f"""You are an expert B2B sales intelligence analyst.

Analyze the following company knowledge base content and extract structured intelligence for an AI-powered outreach system.

KNOWLEDGE BASE CONTENT:
{context}

Return ONLY a valid JSON object with exactly these 6 keys:

{{
  "core_value_prop": "<1-2 sentence summary of the company's primary value proposition — what they do and for whom>",
  "identified_tone": ["<tone adjective 1>", "<tone adjective 2>", "<tone adjective 3>"],
  "target_customer_profile": "<2-3 sentence description of the ideal customer — their role, company size, industry, and key pain points>",
  "key_differentiators": ["<differentiator 1>", "<differentiator 2>", "<differentiator 3>"],
  "proof_points": ["<specific stat or result 1>", "<specific case study or outcome 2>"],
  "primary_pain_points_solved": ["<pain point 1>", "<pain point 2>", "<pain point 3>"]
}}

Rules:
- Base EVERY field strictly on the documents above. Do NOT hallucinate.
- If a field cannot be determined from the content, use an empty string "" or empty array [].
- identified_tone: choose from [Professional, Friendly, Technical, Bold, Empathetic, Direct, Conversational, Authoritative, Innovative, Data-driven]
- key_differentiators: specific concrete claims (not generic marketing phrases like "best in class")
- proof_points: ONLY include if there are actual numbers, case studies, or named results in the documents
- Return ONLY the JSON. No markdown, no explanation, no preamble."""

        keys = get_active_nvidia_keys("synthesis")
        if not keys:
            logger.error("[KB] No NVIDIA API keys available for synthesis")
            return

        result = None
        for current_model in ROUTING_CONFIG["synthesis"]:
            for k_obj in keys:
                try:
                    response = await _get_async_client(k_obj).chat.completions.create(
                        model=current_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=600,
                    )
                    raw = response.choices[0].message.content.strip()
                    from knowledge.backend.services.elein_ai_service import _extract_json_from_slop
                    result = _extract_json_from_slop(raw)
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"[KB] Synthesis JSON parse error with key {k_obj['id']}: {e} | Raw: {raw[:200]}")
                    # Layer 0 Paranoia: Do not rotate API keys for a JSON hallucination.
                    # It's a model fault, not an auth/network fault. Break to next model.
                    break
                except Exception as e:
                    err_str = str(e)
                    logger.error(f"[KB] Synthesis LLM call failed with key {k_obj['id']}: {err_str}")
                    _mark_key_failed(k_obj["id"], err_str)
                    
                    if "400" in err_str or "Bad Request" in err_str:
                        logger.error(f"[KB] Fatal 400 Bad Request in synthesis. Aborting immediately.")
                        return
                    continue
            if result:
                break

        if not result:
            logger.error("[KB] All keys exhausted — synthesis could not complete")
            return

        vector_count = 0
        try:
            vec_res = supabase.table("knowledge_chunks").select("id", count="exact").eq("workspace_id", workspace_id).limit(1).execute()
            vector_count = vec_res.count if vec_res.count else 0
        except Exception:
            pass
        if not vector_count:
            try:
                vec_res_legacy = supabase.table("knowledge_vectors").select("id", count="exact").eq("workspace_id", workspace_id).limit(1).execute()
                vector_count = vec_res_legacy.count if vec_res_legacy.count else 0
            except Exception:
                pass

        upsert_payload = {
            "workspace_id": workspace_id,
            "core_value_prop": result.get("core_value_prop", ""),
            "identified_tone": result.get("identified_tone", []),
            "target_customer_profile": result.get("target_customer_profile", ""),
            "key_differentiators": result.get("key_differentiators", []),
            "proof_points": result.get("proof_points", []),
            "primary_pain_points_solved": result.get("primary_pain_points_solved", []),
            "updated_at": datetime.utcnow().isoformat(),
            "generated_from_vector_count": vector_count,
        }

        # Phase 4: Route synthesis output through Curation Review.
        # Also auto-seed live knowledge_synthesis if currently empty so new users aren't left in a blank state.
        try:
            upsert_payload["status"] = "pending_review"
            supabase.table("knowledge_synthesis_drafts") \
                .upsert(upsert_payload, on_conflict="workspace_id") \
                .execute()
            logger.info(f"[KB] Synthesis routed to drafts (pending_review) for workspace {workspace_id}")

            # Check if live synthesis has data; if not, promote immediately
            live_check = supabase.table("knowledge_synthesis").select("core_value_prop").eq("workspace_id", workspace_id).limit(1).execute()
            if not live_check.data or not live_check.data[0].get("core_value_prop"):
                live_payload = dict(upsert_payload)
                live_payload.pop("status", None)
                supabase.table("knowledge_synthesis").upsert(live_payload, on_conflict="workspace_id").execute()
                logger.info(f"[KB] Live synthesis auto-seeded for workspace {workspace_id}")
        except Exception as e:
            logger.error(f"[KB] Synthesis draft upsert failed: {e}")

    # ───────────────────────────────────────────────────────────────────────
    # Dynamic docs
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    async def generate_dynamic_docs(ui_state: dict) -> str:
        """Generates context-aware, state-driven documentation for the Knowledge Base with full key failover."""
        if not HAS_LLM:
            return "### Knowledge Base Guide\n\nPlease configure your NVIDIA API keys to enable AI guidance."

        asset_count = ui_state.get("assets", 0)
        persona_count = ui_state.get("personas", 0)
        objection_count = ui_state.get("objections", 0)
        has_synthesis = ui_state.get("has_synthesis", False)

        if asset_count == 0:
            next_step = "add_assets"
        elif not has_synthesis:
            next_step = "wait_synthesis"
        elif persona_count == 0:
            next_step = "add_personas"
        elif objection_count == 0:
            next_step = "add_objections"
        else:
            next_step = "complete"

        prompt = f"""You are the intelligent onboarding assistant embedded inside Ele-in, an AI-powered LinkedIn outreach platform.

The user just clicked 'How it works?' inside the Knowledge Base module. Their current state is:
- Data Sources uploaded: {asset_count}
- AI Synthesis complete: {has_synthesis}
- Buyer Personas defined: {persona_count}
- Objection playbooks mapped: {objection_count}
- Next action needed: {next_step}

Write a concise, actionable markdown guide (150-250 words) that tells them EXACTLY what to do next, and WHY it matters for their AI-powered outreach.

For each next_step value, follow this guidance:
- add_assets: Explain that without uploading company content (website URL, PDF, or text), the AI will write generic emails. Tell them to upload their homepage URL first. Explain what Jina.ai scraping does in simple terms.
- wait_synthesis: Their content is uploaded but the AI is still analyzing it. Tell them to wait 30-60 seconds and refresh.
- add_personas: Data is in. Now they must tell the AI WHO they're selling to. Without a persona, the AI writes for everyone — which means no one.
- add_objections: Almost done. They need to map out the 3-5 objections they hear most from prospects and how to handle them. This trains the AI to handle objections in outreach automatically.
- complete: Celebrate! Their Knowledge Base is fully operational. Tell them the AI will now write personalized, knowledge-aware emails for every lead in their campaigns.

Tone: Direct, confident, zero corporate jargon. Think 'senior product engineer giving you a pre-flight checklist'.
Output: ONLY valid Markdown. No preamble."""

        keys = get_active_nvidia_keys("synthesis")
        if not keys:
            return "### No API Keys Configured\n\nPlease add your NVIDIA API key in the backend `.env` file to enable AI guidance."

        last_error = None
        for current_model in ROUTING_CONFIG["synthesis"]:
            for k_obj in keys:
                try:
                    response = await _get_async_client(k_obj).chat.completions.create(
                        model=current_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.6,
                        max_tokens=500,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    last_error = e
                    _mark_key_failed(k_obj["id"], str(e))
                    continue

        return "### AI Temporarily Unavailable\n\nAll API keys are rate-limited. Please try again in 60 seconds."
