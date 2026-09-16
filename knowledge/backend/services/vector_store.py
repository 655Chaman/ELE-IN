import logging
import re
from supabase import Client
from knowledge.backend.services.elein_ai_service import get_active_nvidia_keys, UsageLimitExceededError, _get_sync_client, _mark_key_failed, _get_async_client

logger = logging.getLogger(__name__)

class SemanticBrain:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.embed_model = "nvidia/nemotron-3-embed-1b"

    def _chunk_content(self, text: str, target_tokens=400) -> list:
        """
        Phase 1: Semantic/structural chunking with overlap.
        (Using a rough heuristic: 1 word ≈ 1.3 tokens).
        """
        target_words = int(target_tokens / 1.3)
        overlap_words = int(target_words * 0.15)
        
        # Split on natural boundaries (headers, paragraphs, list items)
        sections = re.split(r'\n(?=#+ )|\n\s*\n|\n(?=\- )|\n(?=\d+\.)', text)
        
        chunks = []
        buffer = ""
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            current_words = len((buffer + " " + section).split())
            if current_words > target_words and buffer:
                chunks.append(buffer.strip())
                
                # Overlap tail
                buffer_words = buffer.split()
                tail = " ".join(buffer_words[-overlap_words:]) if len(buffer_words) > overlap_words else buffer
                buffer = tail + "\n\n" + section
            else:
                buffer += "\n\n" + section if buffer else section
                
        if buffer.strip():
            chunks.append(buffer.strip())
            
        return [c for c in chunks if len(c) > 20]

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
                    client = _get_sync_client(k_obj["key"])
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

    def retrieve(self, query: str, workspace_id: str, top_k: int = 5, filters: dict = None) -> list:
        """
        Phase 3: Semantic retrieval with similarity threshold and filters.
        Returns a list of dicts [{content, metadata, similarity}].
        """
        if not query or len(query.strip()) < 5:
            return []
            
        try:
            query_embedding = self._generate_embeddings([query])[0]
            
            # We use match_threshold = 0.5 to prevent hallucinating from irrelevant chunks
            response = self.supabase.rpc('match_knowledge', {
                'query_embedding': query_embedding,
                'match_threshold': 0.5,
                'match_count': top_k,
                'p_workspace_id': workspace_id
            }).execute()
            
            if not response.data:
                return []
                
            results = []
            for row in response.data:
                results.append(row)
                
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

# Module-level instance for simple imports
from core.backend.api.auth_dep import get_service_client
try:
    vector_store = SemanticBrain(get_service_client())
except Exception as e:
    logger.error(f"Failed to initialize vector_store: {e}")
    vector_store = None
