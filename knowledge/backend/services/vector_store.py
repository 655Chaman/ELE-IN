import logging
import re
from supabase import Client
from knowledge.backend.services.elein_ai_service import get_active_nvidia_keys, UsageLimitExceededError, _get_sync_client, _mark_key_failed, _get_async_client

logger = logging.getLogger(__name__)

class SemanticBrain:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.embed_model = "nvidia/nemotron-3-embed-1b"
        self._asset_name_cache = {}

    def _chunk_content(self, text: str, target_tokens=400) -> list:
        """
        Phase 1: Semantic & structural chunking with strict token ceilings.
        Guarantees no chunk exceeds the embedding model context limit.
        (1 word ≈ 1.3 tokens -> 400 tokens ≈ 300 words).
        """
        if not text or not text.strip():
            return []

        target_words = max(100, int(target_tokens / 1.3))
        max_words = int(target_words * 1.3)  # Hard ceiling ~390 words (~500 tokens)
        overlap_words = int(target_words * 0.15)
        
        # 1. Split on natural structural boundaries
        raw_sections = re.split(r'\n(?=#+ )|\n\s*\n|\n(?=\- )|\n(?=\d+\.)', text)
        
        # 2. Layer 1 Paranoia: Decompose any oversized sections into sentence-bounded slices
        sections = []
        for sec in raw_sections:
            sec = sec.strip()
            if not sec:
                continue
            words = sec.split()
            if len(words) <= max_words:
                sections.append(sec)
            else:
                sentences = re.split(r'(?<=[.!?])\s+', sec)
                sec_buf = []
                for s in sentences:
                    s_words = s.split()
                    if len(sec_buf) + len(s_words) > target_words and sec_buf:
                        sections.append(" ".join(sec_buf))
                        sec_buf = sec_buf[-overlap_words:] if len(sec_buf) > overlap_words else sec_buf
                    sec_buf.extend(s_words)
                    
                    while len(sec_buf) > max_words:
                        sections.append(" ".join(sec_buf[:target_words]))
                        sec_buf = sec_buf[target_words - overlap_words:]
                if sec_buf:
                    sections.append(" ".join(sec_buf))
                    
        # 3. Assemble sections into target-sized chunks with overlap
        chunks = []
        buffer_words = []
        
        for sec in sections:
            sec_words = sec.split()
            if len(buffer_words) + len(sec_words) > target_words and buffer_words:
                chunks.append(" ".join(buffer_words).strip())
                tail = buffer_words[-overlap_words:] if len(buffer_words) > overlap_words else buffer_words
                buffer_words = tail + sec_words
            else:
                buffer_words.extend(sec_words)
                
            while len(buffer_words) > max_words:
                chunks.append(" ".join(buffer_words[:target_words]).strip())
                buffer_words = buffer_words[target_words - overlap_words:]
                
        if buffer_words:
            chunks.append(" ".join(buffer_words).strip())
            
        return [c for c in chunks if len(c.strip()) > 20]

    def _generate_embeddings(self, texts: list) -> list:
        """Phase 2: Batch embedding calls to prevent API payload explosion."""
        keys = get_active_nvidia_keys()
        if not keys:
            raise Exception("No active NVIDIA API keys available for embeddings.")
            
        # Batch size for NVIDIA API
        batch_size = 50
        all_embeddings = []
        
        last_error = None
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_success = False
            
            for k_obj in keys:
                try:
                    client = _get_sync_client(k_obj)
                    resp = client.embeddings.create(
                        model=self.embed_model,
                        input=batch,
                        encoding_format="float"
                    )
                    all_embeddings.extend([item.embedding for item in resp.data])
                    batch_success = True
                    break
                except Exception as e:
                    last_error = e
                    _mark_key_failed(k_obj["id"], str(e))
                    logger.warning(f"[Embeddings] Key {k_obj['id']} failed, trying next. Error: {e}")
                    continue
            
            if not batch_success:
                raise Exception(f"All keys exhausted generating embeddings. Last error: {last_error}")
                
        return all_embeddings

    def delete_by_asset_id(self, asset_id: str, workspace_id: str = None):
        try:
            self.supabase.table("knowledge_chunks").delete().eq("asset_id", asset_id).execute()
            logger.info(f"Successfully purged all chunks for asset_id: {asset_id}")
        except Exception as e:
            logger.error(f"Error deleting chunks for asset_id {asset_id}: {e}")
    def index_document(self, content: str, source_name: str, workspace_id: str, doc_type: str = "text", asset_id: str = "legacy"):
        """Indexes a document using semantic chunking, batch embeddings, and replace-not-append."""
        if not content:
            return
            
        # Layer 2 Paranoia: Prevent Infinite Consumption of Vectors
        from core.backend.api.auth_dep import get_service_client
        import time, json
        
        try:
            import hashlib
            content_digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:16]
            _deduct_res = self.supabase.rpc('deduct_credits_safely', {
                'p_workspace_id': workspace_id,
                'p_amount': 2,
                'p_action_type': 'rag_embed',
                'p_idempotency_key': f"embed_{workspace_id}_{asset_id}_{content_digest}",
                'p_metadata': json.dumps({"asset_id": asset_id})
            }).execute()
            if _deduct_res.data and not _deduct_res.data.get('success', False):
                reason = _deduct_res.data.get('reason')
                if reason == 'insufficient_credits':
                    raise UsageLimitExceededError("Insufficient credits for document indexing (2 credits required). Please top up your credits in Settings -> Billing.")
                else:
                    logger.warning(f"[SemanticBrain] Credit deduction non-success reason: {reason}")
        except UsageLimitExceededError:
            raise
        except Exception as e:
            logger.warning(f"[SemanticBrain] Credit deduction RPC execution non-fatal: {e}")

        try:
            # We charge 1 AI request per chunking operation/asset. Alternatively, charge by size.
            self.supabase.rpc('increment_usage', {
                'p_workspace_id': workspace_id,
                'p_type': 'ai',
                'p_amount': 1,
                'p_limit': 100000
            }).execute()
        except Exception as e:
            if 'UsageLimitExceededError' in str(e):
                logger.error(f"[SemanticBrain] CRITICAL: Workspace {workspace_id} exceeded monthly AI/Vector limit.")
                raise UsageLimitExceededError(f"Workspace {workspace_id} exceeded monthly AI limit.")
            else:
                logger.error(f"Error checking usage limits: {e}")

            
        # Phase 2: Re-sync must replace, not append
        self.delete_by_asset_id(asset_id, workspace_id)
        
        # Phase 1: Semantic chunking
        documents = self._chunk_content(content)
        if not documents:
            return

        try:
            # Phase 2: Batch embeddings
            embeddings = self._generate_embeddings(documents)
            
            rows = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                rows.append({
                    "asset_id": asset_id,
                    "workspace_id": workspace_id,
                    "content": doc,
                    "embedding": emb
                })
                
            db_batch_size = 100
            for i in range(0, len(rows), db_batch_size):
                self.supabase.table("knowledge_chunks").insert(rows[i:i+db_batch_size]).execute()
                
            logger.info(f"Indexed {len(documents)} chunks for asset {asset_id} using NVIDIA embeddings.")
            
            # Phase 2: Update chunk count is handled by the SQL Trigger we added earlier!
            
        except Exception as e:
            logger.error(f"Failed to index document to pgvector: {e}")

    def _enrich_chunk_sources(self, rows: list, workspace_id: str) -> list:
        """Layer 0/1 Paranoia: Attaches real document titles to chunks and injects metadata dict."""
        if not rows:
            return []
        
        asset_ids_to_fetch = set()
        for r in rows:
            aid = r.get("asset_id")
            if aid and aid not in self._asset_name_cache:
                asset_ids_to_fetch.add(str(aid))
                
        if asset_ids_to_fetch:
            try:
                res = self.supabase.table("knowledge_assets").select("id, name").in_("id", list(asset_ids_to_fetch)).execute()
                for item in (res.data or []):
                    self._asset_name_cache[str(item["id"])] = item.get("name") or "Asset Document"
            except Exception as e:
                logger.debug(f"[SemanticBrain] Could not fetch asset names: {e}")
                
        enriched = []
        for r in rows:
            aid = str(r.get("asset_id") or "")
            source_name = self._asset_name_cache.get(aid, "Knowledge Base")
            r_copy = dict(r)
            r_copy["source"] = source_name
            if "metadata" not in r_copy or not isinstance(r_copy["metadata"], dict):
                r_copy["metadata"] = {"source": source_name, "asset_id": aid}
            else:
                r_copy["metadata"]["source"] = source_name
            enriched.append(r_copy)
        return enriched

    def retrieve(self, query: str, workspace_id: str, top_k: int = 5, match_threshold: float = 0.38, filters: dict = None) -> list:
        """
        Phase 3: Multi-layered semantic retrieval with:
        - Configurable & progressive threshold relaxation (solves the 0.5 cliff)
        - Keyword/text search fallback (survives RPC / extension degradation)
        - Chunk source attribution and metadata enrichment
        Returns a list of dicts [{content, metadata, similarity, source}].
        """
        if not query or len(query.strip()) < 3:
            return []
            
        clean_query = query.strip()[:2000]
        
        # 1. Semantic Vector Search via RPC
        try:
            query_embedding = self._generate_embeddings([clean_query])[0]
            
            # Pass 1: Standard threshold (default 0.38)
            response = self.supabase.rpc('match_knowledge', {
                'query_embedding': query_embedding,
                'match_threshold': match_threshold,
                'match_count': top_k,
                'p_workspace_id': workspace_id
            }).execute()
            
            rows = response.data or []
            
            # Layer 1 Paranoia: Progressive threshold relaxation if 0 results
            if not rows and match_threshold > 0.28:
                relaxed_thresh = max(0.22, match_threshold - 0.12)
                logger.debug(f"[SemanticBrain] 0 results at {match_threshold}, relaxing to {relaxed_thresh}")
                relaxed_resp = self.supabase.rpc('match_knowledge', {
                    'query_embedding': query_embedding,
                    'match_threshold': relaxed_thresh,
                    'match_count': top_k,
                    'p_workspace_id': workspace_id
                }).execute()
                rows = relaxed_resp.data or []
                
            if rows:
                return self._enrich_chunk_sources(rows, workspace_id)
                
        except Exception as e:
            logger.warning(f"[SemanticBrain] RPC vector search failed or unavailable, triggering keyword fallback: {e}")

        # Layer 1 Paranoia: Text/keyword fallback on knowledge_chunks
        try:
            stop_words = {"what", "when", "where", "which", "who", "whom", "this", "that", "these", "those", "from", "with", "about", "into", "through", "during", "before", "after", "above", "below", "have", "has", "had", "having", "does", "did", "doing", "would", "should", "could", "ought"}
            tokens = [re.sub(r'[^\w]', '', w.lower()) for w in clean_query.split() if len(w) > 3]
            keywords = [t for t in tokens if t and t not in stop_words][:4]
            
            if keywords:
                search_term = max(keywords, key=len)
                fb_res = self.supabase.table("knowledge_chunks").select("id, asset_id, content").eq("workspace_id", workspace_id).ilike("content", f"%{search_term}%").limit(top_k).execute()
                if fb_res.data:
                    synthetic_rows = []
                    for item in fb_res.data:
                        synthetic_rows.append({
                            "id": item.get("id"),
                            "asset_id": item.get("asset_id"),
                            "content": item.get("content"),
                            "similarity": 0.35
                        })
                    logger.info(f"[SemanticBrain] Keyword fallback rescued {len(synthetic_rows)} chunks for query: '{search_term}'")
                    return self._enrich_chunk_sources(synthetic_rows, workspace_id)
        except Exception as fe:
            logger.error(f"[SemanticBrain] Keyword search fallback failed: {fe}")

        return []

# Module-level instance for simple imports
from core.backend.api.auth_dep import get_service_client
try:
    vector_store = SemanticBrain(get_service_client())
except Exception as e:
    logger.error(f"Failed to initialize vector_store: {e}")
    vector_store = None
