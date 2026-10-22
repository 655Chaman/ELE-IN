import logging
import re
import math
import hashlib
import threading
from typing import Optional, List, Dict, Any, Tuple
from supabase import Client
from knowledge.backend.services.elein_ai_service import get_active_nvidia_keys, UsageLimitExceededError, _get_sync_client, _mark_key_failed, _get_async_client

logger = logging.getLogger(__name__)

# Paranoia Layer 1: Global in-memory vector store & pure-Python similarity fallback
_in_memory_chunks_lock = threading.RLock()
_IN_MEMORY_CHUNKS: List[Dict[str, Any]] = []


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Paranoia Layer 0 & 1: Safe cosine similarity between two float vectors.
    Guards against zero-division, mismatched lengths, NaN/Inf.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    try:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        val = dot / (norm_a * norm_b)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return max(0.0, min(1.0, float(val)))
    except Exception:
        return 0.0


class SemanticBrain:
    def __init__(self, supabase: Optional[Client] = None):
        self.supabase = supabase
        self.embed_model = "nvidia/nemotron-3-embed-1b"
        self._asset_name_cache = {}
        self._cache_lock = threading.RLock()

    def _fallback_embedding(self, text: str, dim: int = 2048) -> list:
        """
        Paranoia Layer 1: Deterministic normalized pseudo-embedding for zero-key offline resilience.
        Generates stable unit vector from text tokens matching the 2048-dim embedding space.
        """
        vec = [0.0] * dim
        words = re.findall(r'\w+', (text or "").lower())
        if not words:
            return [1.0 / math.sqrt(dim)] * dim
        for w in words:
            h = int(hashlib.md5(w.encode('utf-8')).hexdigest(), 16)
            idx = h % dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

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

    def _generate_embeddings_with_status(self, texts: list) -> Tuple[list, bool]:
        """
        Phase 2: Batch embedding calls to prevent API payload explosion.
        Paranoia Layer 1: Seamlessly falls back to deterministic pseudo-embeddings
        if NVIDIA API keys are missing, invalid, or exhausted.
        Returns: (embeddings_list, is_fallback: bool)
        """
        if not texts:
            return [], False
        try:
            keys = get_active_nvidia_keys()
        except Exception as e:
            logger.warning(f"[Embeddings] get_active_nvidia_keys failed: {e}")
            keys = []

        if not keys:
            logger.warning("[Embeddings] No active NVIDIA API keys available, using deterministic fallback embeddings.")
            return [self._fallback_embedding(t) for t in texts], True
            
        # Batch size for NVIDIA API
        batch_size = 50
        all_embeddings = []
        any_fallback = False
        
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
                    _mark_key_failed(k_obj.get("id"), str(e))
                    logger.warning(f"[Embeddings] Key {k_obj.get('id')} failed, trying next. Error: {e}")
                    continue
            
            if not batch_success:
                logger.warning(f"[Embeddings] All keys exhausted generating embeddings ({last_error}). Falling back to deterministic pseudo-embeddings for batch.")
                all_embeddings.extend([self._fallback_embedding(t) for t in batch])
                any_fallback = True
                
        return all_embeddings, any_fallback

    def _generate_embeddings(self, texts: list) -> list:
        """Backward-compatible wrapper returning only the embedding list."""
        embeddings, _ = self._generate_embeddings_with_status(texts)
        return embeddings

    def delete_by_asset_id(self, asset_id: str, workspace_id: str = None):
        try:
            # Layer 1 Paranoia (Flaw 20): Enforce multi-tenant workspace isolation on chunk deletion
            if self.supabase:
                query = self.supabase.table("knowledge_chunks").delete().eq("asset_id", asset_id)
                if workspace_id:
                    query = query.eq("workspace_id", workspace_id)
                query.execute()
        except Exception as e:
            logger.error(f"Error deleting chunks for asset_id {asset_id}: {e}")

        # Layer 1 Paranoia: Purge in-memory fallback chunks under lock
        with _in_memory_chunks_lock:
            _IN_MEMORY_CHUNKS[:] = [
                c for c in _IN_MEMORY_CHUNKS
                if not (str(c.get("asset_id")) == str(asset_id) and (workspace_id is None or c.get("workspace_id") == workspace_id))
            ]

        with self._cache_lock:
            self._asset_name_cache.pop(str(asset_id), None)
        logger.info(f"Successfully purged all chunks for asset_id: {asset_id} (workspace: {workspace_id or 'all'})")

    def invalidate_asset_cache(self, asset_id: Optional[str] = None):
        """Invalidate single asset or entire cache on rename/delete."""
        with self._cache_lock:
            if asset_id:
                self._asset_name_cache.pop(str(asset_id), None)
            else:
                self._asset_name_cache.clear()

    def index_document(self, content: str, source_name: str, workspace_id: str, doc_type: str = "text", asset_id: str = "legacy"):
        """Indexes a document using semantic chunking, batch embeddings, and replace-not-append."""
        if not content:
            return
            
        # Layer 2 Paranoia: Prevent Infinite Consumption of Vectors
        from core.backend.api.auth_dep import get_service_client
        import time, json
        
        if self.supabase:
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

            
        # Phase 1: Semantic chunking
        documents = self._chunk_content(content)
        if not documents:
            return

        try:
            # Phase 2: Batch embeddings (compute before deleting old chunks to prevent data loss)
            embeddings, is_fallback = self._generate_embeddings_with_status(documents)
            
            # Re-sync must replace, not append - delete old chunks only after new embeddings succeed
            self.delete_by_asset_id(asset_id, workspace_id)

            rows = []
            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                rows.append({
                    "id": f"chunk_{asset_id}_{i}",
                    "asset_id": asset_id,
                    "workspace_id": workspace_id,
                    "content": doc,
                    "embedding": emb,
                    "source": source_name,
                    "is_fallback": is_fallback
                })
                
            if self.supabase:
                db_batch_size = 100
                for i in range(0, len(rows), db_batch_size):
                    db_rows = [
                        {
                            "asset_id": r["asset_id"],
                            "workspace_id": r["workspace_id"],
                            "content": r["content"],
                            "embedding": r["embedding"]
                        }
                        for r in rows[i:i+db_batch_size]
                    ]
                    self.supabase.table("knowledge_chunks").insert(db_rows).execute()

                # Three-Layer Paranoia (Leak 2 Fix): If fallback pseudo-embeddings were generated,
                # explicitly flag knowledge_assets so the user knows vectors are degraded,
                # and enqueue automated re-indexing when keys recover!
                if is_fallback and asset_id and asset_id != "legacy":
                    try:
                        self.supabase.table("knowledge_assets").update({
                            "embedding_status": "degraded_fallback",
                            "reindex_required": True
                        }).eq("id", asset_id).execute()
                        logger.warning(f"[SemanticBrain] Asset {asset_id} indexed with fallback pseudo-embeddings. Flagged for re-indexing.")
                    except Exception as err:
                        logger.debug(f"[SemanticBrain] Failed flagging degraded asset in DB: {err}")

            # Paranoia Layer 1: Multi-tenant safe in-memory storage (Issue 3 resolution)
            with _in_memory_chunks_lock:
                # Purge prior chunks for this asset and workspace
                _IN_MEMORY_CHUNKS[:] = [
                    c for c in _IN_MEMORY_CHUNKS
                    if not (str(c.get("asset_id")) == str(asset_id) and (workspace_id is None or c.get("workspace_id") == workspace_id))
                ]
                # Enforce tenant isolation quota: prune oldest chunks of THIS workspace if exceeding tenant cap (1,000)
                this_ws_chunks = [c for c in _IN_MEMORY_CHUNKS if c.get("workspace_id") == workspace_id]
                if len(this_ws_chunks) + len(rows) > 1000:
                    excess = (len(this_ws_chunks) + len(rows)) - 1000
                    prune_ids = {c["id"] for c in this_ws_chunks[:excess] if "id" in c}
                    _IN_MEMORY_CHUNKS[:] = [c for c in _IN_MEMORY_CHUNKS if c.get("id") not in prune_ids]

                # Enforce global memory ceiling (5,000)
                if len(_IN_MEMORY_CHUNKS) + len(rows) > 5000:
                    excess_global = (len(_IN_MEMORY_CHUNKS) + len(rows)) - 5000
                    del _IN_MEMORY_CHUNKS[:excess_global]
                _IN_MEMORY_CHUNKS.extend(rows)
                
            logger.info(f"Indexed {len(documents)} chunks for asset {asset_id} using embeddings (fallback={is_fallback}).")
            
        except Exception as e:
            logger.error(f"Failed to index document to pgvector for asset {asset_id}: {e}")
            raise

    def _enrich_chunk_sources(self, rows: list, workspace_id: str) -> list:
        """Layer 0/1 Paranoia: Attaches real document titles to chunks and injects metadata dict."""
        if not rows:
            return []
        
        asset_ids_to_fetch = set()
        with self._cache_lock:
            for r in rows:
                aid = r.get("asset_id")
                if aid and str(aid) not in self._asset_name_cache:
                    asset_ids_to_fetch.add(str(aid))
                
        if asset_ids_to_fetch and self.supabase:
            try:
                res = self.supabase.table("knowledge_assets").select("id, name").in_("id", list(asset_ids_to_fetch)).execute()
                with self._cache_lock:
                    for item in (res.data or []):
                        # Paranoia Layer 1: Bound in-memory cache to 256 items with FIFO eviction to prevent memory leaks
                        if len(self._asset_name_cache) >= 256:
                            self._asset_name_cache.pop(next(iter(self._asset_name_cache)), None)
                        self._asset_name_cache[str(item["id"])] = item.get("name") or "Asset Document"
            except Exception as e:
                logger.debug(f"[SemanticBrain] Could not fetch asset names: {e}")
                
        enriched = []
        with self._cache_lock:
            for r in rows:
                aid = str(r.get("asset_id") or "")
                source_name = self._asset_name_cache.get(aid, r.get("source") or "Knowledge Base")
                r_copy = dict(r)
                r_copy["source"] = source_name
                if "metadata" not in r_copy or not isinstance(r_copy["metadata"], dict):
                    r_copy["metadata"] = {"source": source_name, "asset_id": aid}
                else:
                    r_copy["metadata"]["source"] = source_name
                enriched.append(r_copy)
        return enriched

    def _search_in_memory(self, query: str, workspace_id: str, top_k: int = 5, match_threshold: float = 0.38) -> list:
        """
        Paranoia Layer 1: In-memory fallback search across _IN_MEMORY_CHUNKS.
        Supports pure-Python cosine similarity and keyword matching when DB is offline or empty.
        """
        with _in_memory_chunks_lock:
            if not _IN_MEMORY_CHUNKS:
                return []
            
            # Filter chunks by workspace_id
            workspace_chunks = [
                c for c in _IN_MEMORY_CHUNKS
                if not workspace_id or c.get("workspace_id") == workspace_id
            ]
            if not workspace_chunks:
                return []

            # Try vector similarity first
            scored = []
            try:
                query_embeddings, query_is_fallback = self._generate_embeddings_with_status([query])
                query_embedding = query_embeddings[0] if query_embeddings else None
                if query_embedding:
                    for c in workspace_chunks:
                        emb = c.get("embedding")
                        chunk_is_fallback = c.get("is_fallback", False)
                        # Avoid comparing sparse pseudo-vectors with dense transformer vectors
                        if emb and (query_is_fallback == chunk_is_fallback):
                            sim = _cosine_similarity(query_embedding, emb)
                            if sim >= match_threshold:
                                scored.append({
                                    "id": c.get("id"),
                                    "asset_id": c.get("asset_id"),
                                    "content": c.get("content"),
                                    "similarity": round(sim, 4),
                                    "source": c.get("source") or "In-Memory Knowledge"
                                })
            except Exception as e:
                logger.debug(f"[SemanticBrain] In-memory vector similarity failed: {e}")

            if scored:
                scored.sort(key=lambda x: x["similarity"], reverse=True)
                return self._enrich_chunk_sources(scored[:top_k], workspace_id)

            # Keyword fallback in memory
            stop_words = {"what", "when", "where", "which", "who", "whom", "this", "that", "these", "those", "from", "with", "about", "into", "through", "during", "before", "after", "above", "below", "have", "has", "had", "having", "does", "did", "doing", "would", "should", "could", "ought"}
            tokens = [re.sub(r'[^\w]', '', w.lower()) for w in query.split() if len(w) > 3]
            keywords = [t for t in tokens if t and t not in stop_words][:4]

            if not keywords:
                return []

            kw_matches = []
            for c in workspace_chunks:
                content_lower = (c.get("content") or "").lower()
                matched_kws = [kw for kw in keywords if kw in content_lower]
                if matched_kws:
                    coverage = len(matched_kws) / float(len(keywords))
                    score = min(0.90, max(0.35, 0.40 + (0.40 * coverage)))
                    kw_matches.append({
                        "id": c.get("id"),
                        "asset_id": c.get("asset_id"),
                        "content": c.get("content"),
                        "similarity": round(score, 4),
                        "_coverage": coverage,
                        "source": c.get("source") or "In-Memory Knowledge"
                    })

            if kw_matches:
                kw_matches.sort(key=lambda x: (x["similarity"], x["_coverage"]), reverse=True)
                cleaned = [{
                    "id": c["id"],
                    "asset_id": c["asset_id"],
                    "content": c["content"],
                    "similarity": c["similarity"],
                    "source": c["source"]
                } for c in kw_matches[:top_k]]
                return self._enrich_chunk_sources(cleaned, workspace_id)

            return []

    def retrieve(self, query: str, workspace_id: str, top_k: int = 5, match_threshold: float = 0.38, filters: dict = None, rerank: bool = False) -> list:
        """
        Phase 3: Multi-layered semantic retrieval with:
        - Configurable & progressive threshold relaxation (solves the 0.5 cliff)
        - Keyword/text search fallback (survives RPC / extension degradation)
        - In-memory pure-Python cosine similarity fallback (survives database failure)
        - Chunk source attribution and metadata enrichment
        - Two-Stage Cross-Encoder Reciprocal Rank Fusion (RRF) Reranking (when rerank=True)
        Returns a list of dicts [{content, metadata, similarity, source}].
        """
        if not query or len(query.strip()) < 3:
            return []
            
        clean_query = query.strip()[:2000]

        def _finalize_results(raw_res: list) -> list:
            if not raw_res:
                return []
            if rerank:
                try:
                    from knowledge.backend.services.reranker_service import rerank_documents
                    return rerank_documents(clean_query, raw_res, top_k=top_k)
                except Exception as re_err:
                    logger.warning(f"[SemanticBrain] Reranking failed, using Stage 1 candidates: {re_err}")
            return raw_res[:top_k]

        # 1. Semantic Vector Search via RPC (if Supabase is available and neural embedding is active)
        query_embeddings, is_fallback = self._generate_embeddings_with_status([clean_query])
        query_embedding = query_embeddings[0] if query_embeddings else None

        if self.supabase and query_embedding and not is_fallback:
            try:
                # Pass 1: Standard threshold (default 0.38)
                response = self.supabase.rpc('match_knowledge', {
                    'query_embedding': query_embedding,
                    'match_threshold': match_threshold,
                    'match_count': top_k if not rerank else top_k * 3,
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
                        'match_count': top_k if not rerank else top_k * 3,
                        'p_workspace_id': workspace_id
                    }).execute()
                    rows = relaxed_resp.data or []
                    
                if rows:
                    enriched_candidates = self._enrich_chunk_sources(rows, workspace_id)
                    return _finalize_results(enriched_candidates)
                    
            except Exception as e:
                logger.warning(f"[SemanticBrain] RPC vector search failed or unavailable, triggering keyword fallback: {e}")
        elif is_fallback:
            logger.info(f"[SemanticBrain] Primary neural embedding API unavailable. Bypassing pgvector distance search to avoid pseudo-vector noise, routing directly to keyword fallback.")

            # Layer 1 Paranoia: Multi-keyword candidate retrieval and dynamic scoring
            try:
                stop_words = {"what", "when", "where", "which", "who", "whom", "this", "that", "these", "those", "from", "with", "about", "into", "through", "during", "before", "after", "above", "below", "have", "has", "had", "having", "does", "did", "doing", "would", "should", "could", "ought"}
                tokens = [re.sub(r'[^\w]', '', w.lower()) for w in clean_query.split() if len(w) > 3]
                keywords = [t for t in tokens if t and t not in stop_words][:4]
                
                if keywords:
                    candidate_map = {}
                    for kw in keywords:
                        try:
                            fb_res = self.supabase.table("knowledge_chunks")\
                                .select("id, asset_id, content")\
                                .eq("workspace_id", workspace_id)\
                                .ilike("content", f"%{kw}%")\
                                .limit(top_k * 2)\
                                .execute()
                            for item in (fb_res.data or []):
                                cid = item.get("id")
                                if cid and cid not in candidate_map:
                                    candidate_map[cid] = item
                        except Exception as q_err:
                            logger.debug(f"[SemanticBrain] Fallback query for keyword '{kw}' failed: {q_err}")

                    if candidate_map:
                        scored_candidates = []
                        for item in candidate_map.values():
                            content_text = item.get("content") or ""
                            content_lower = content_text.lower()
                            words = [w for w in re.findall(r'\w+', content_lower) if w]
                            total_words = max(1, len(words))

                            matched_kws = [kw for kw in keywords if kw in content_lower]
                            coverage = len(matched_kws) / float(len(keywords))

                            kw_hits = sum(content_lower.count(kw) for kw in keywords)
                            density = kw_hits / float(total_words)

                            # Dynamic multi-keyword scoring: base 0.40, coverage up to 0.40, density up to 0.10
                            score = min(0.90, max(0.35, 0.40 + (0.40 * coverage) + min(0.10, density * 2.0)))

                            scored_candidates.append({
                                "id": item.get("id"),
                                "asset_id": item.get("asset_id"),
                                "content": content_text,
                                "similarity": round(score, 4),
                                "_coverage": coverage,
                            })

                        # Sort by similarity descending, then coverage descending
                        scored_candidates.sort(key=lambda x: (x["similarity"], x["_coverage"]), reverse=True)
                        top_candidates = scored_candidates[:top_k]
                        cleaned_rows = [
                            {
                                "id": c["id"],
                                "asset_id": c["asset_id"],
                                "content": c["content"],
                                "similarity": c["similarity"]
                            }
                            for c in top_candidates
                        ]
                        logger.info(f"[SemanticBrain] Multi-keyword fallback rescued {len(cleaned_rows)} chunks across keywords {keywords}")
                        enriched_kw = self._enrich_chunk_sources(cleaned_rows, workspace_id)
                        return _finalize_results(enriched_kw)
            except Exception as fe:
                logger.error(f"[SemanticBrain] Keyword search fallback failed: {fe}")

        # Layer 1 Paranoia: In-memory fallback if Supabase RPC and keyword search returned nothing or if DB is offline
        in_memory_results = self._search_in_memory(clean_query, workspace_id, top_k, match_threshold)
        if in_memory_results:
            logger.info(f"[SemanticBrain] In-memory fallback rescued {len(in_memory_results)} chunks for query '{clean_query[:30]}'")
            return _finalize_results(in_memory_results)

        return []

        return []

# Module-level instance for simple imports
from core.backend.api.auth_dep import get_service_client
try:
    vector_store = SemanticBrain(get_service_client())
except Exception as e:
    logger.error(f"Failed to initialize vector_store: {e}")
    vector_store = SemanticBrain(None)

if vector_store is None:
    vector_store = SemanticBrain(None)
