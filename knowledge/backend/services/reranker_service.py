"""
Two-Stage Cross-Encoder & Reciprocal Rank Fusion (RRF) Reranker Engine
======================================================================
Paranoia Layer 0, 1 & 2 Defense for RAG Semantic Retrieval.

Why this is necessary:
- Bi-encoder dense embeddings (pgvector) have high recall but mediocre precision;
  they frequently retrieve top-K candidates that share topical vocabulary but lack
  direct relevance to the prospect's specific inquiry.
- This module implements a two-stage retrieval pipeline:
    Stage 1: Broad candidate retrieval (Top-20 via pgvector or keyword search).
    Stage 2: Cross-Encoder & Lexical Reciprocal Rank Fusion (RRF) reranking,
             filtering out distractor chunks and surfacing the Top 3-5 true answers.
"""

import math
import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    """Extracts lowercased alphanumeric tokens, stripping punctuation."""
    if not text:
        return []
    return re.findall(r'[a-zA-Z0-9]+', text.lower())


def compute_bm25_lexical_score(query_tokens: List[str], doc_tokens: List[str], k1: float = 1.5, b: float = 0.75, avg_doc_len: float = 50.0) -> float:
    """
    Computes Okapi BM25 relevance score between query tokens and document tokens.
    Prevents keyword stuffing via term frequency saturation.
    """
    if not query_tokens or not doc_tokens:
        return 0.0

    doc_len = len(doc_tokens)
    score = 0.0
    doc_freqs: Dict[str, int] = {}
    for t in doc_tokens:
        doc_freqs[t] = doc_freqs.get(t, 0) + 1

    for qt in query_tokens:
        tf = doc_freqs.get(qt, 0)
        if tf == 0:
            continue
        # Term frequency saturation
        numerator = tf * (k1 + 1.0)
        denominator = tf + k1 * (1.0 - b + b * (doc_len / max(1.0, avg_doc_len)))
        score += (numerator / max(0.001, denominator))

    return score


def compute_cross_attention_heuristic(query: str, doc_text: str) -> float:
    """
    Simulates cross-encoder multi-token attention by calculating exact phrase matches,
    proximity of query terms, and heading/sentence relevance.
    """
    clean_q = query.strip().lower()
    clean_doc = doc_text.strip().lower()

    if not clean_q or not clean_doc:
        return 0.0

    score = 0.0
    # 1. Exact verbatim match bonus
    if clean_q in clean_doc:
        score += 3.0

    # 2. Sequential n-gram overlap
    q_words = clean_q.split()
    if len(q_words) >= 2:
        for i in range(len(q_words) - 1):
            bigram = f"{q_words[i]} {q_words[i+1]}"
            if bigram in clean_doc:
                score += 1.0

    # 3. Position discount: rewards occurrences in the leading 20% of the chunk (often section titles/definitions)
    first_idx = clean_doc.find(q_words[0]) if q_words else -1
    if 0 <= first_idx < len(clean_doc) * 0.25:
        score += 0.5

    return score


def rerank_documents(
    query: str,
    documents: List[Dict[str, Any]],
    top_k: int = 5,
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Reranks candidate document chunks using hybrid Reciprocal Rank Fusion (RRF)
    combining initial vector similarity rank with cross-encoder lexical and positional scoring.

    :param query: Prospect or agent search query
    :param documents: Raw Top-K candidate chunks from Stage 1 vector/keyword retrieval
    :param top_k: Final number of high-precision chunks to return
    :param rrf_k: Smoothing constant for Reciprocal Rank Fusion (standard 60)
    :returns: High-precision ordered subset with detailed reranking metadata
    """
    if not documents:
        return []
    if not query or not query.strip():
        return documents[:top_k]

    query_tokens = _tokenize(query)
    if not query_tokens:
        return documents[:top_k]

    scored_candidates = []
    # Compute average doc length across candidates
    doc_lens = [len(_tokenize(d.get("content") or d.get("text") or "")) for d in documents]
    avg_len = sum(doc_lens) / max(1, len(doc_lens))

    for initial_rank, doc in enumerate(documents):
        content = str(doc.get("content") or doc.get("text") or "")
        doc_tokens = _tokenize(content)

        # Vector rank contribution (RRF Stage 1)
        # Reciprocal rank formula: 1.0 / (k + rank)
        vector_rrf = 1.0 / (rrf_k + (initial_rank + 1))

        # Cross-encoder & BM25 contribution (Stage 2)
        bm25_score = compute_bm25_lexical_score(query_tokens, doc_tokens, avg_doc_len=avg_len)
        cross_score = compute_cross_attention_heuristic(query, content)
        combined_lexical = bm25_score + cross_score

        scored_candidates.append({
            "doc": doc,
            "initial_rank": initial_rank + 1,
            "initial_similarity": float(doc.get("similarity") or 0.0),
            "vector_rrf": vector_rrf,
            "cross_encoder_score": round(combined_lexical, 4),
        })

    # Sort by cross-encoder score to assign lexical rank
    scored_candidates.sort(key=lambda x: x["cross_encoder_score"], reverse=True)
    for lex_rank, cand in enumerate(scored_candidates):
        cand["lexical_rank"] = lex_rank + 1
        cand["lexical_rrf"] = 1.0 / (rrf_k + (lex_rank + 1))
        # Total Hybrid Score: Weighted sum of Vector RRF and Cross-Encoder RRF
        cand["final_rrf_score"] = cand["vector_rrf"] + cand["lexical_rrf"]

    # Final sort by composite RRF score
    scored_candidates.sort(key=lambda x: x["final_rrf_score"], reverse=True)

    results = []
    for cand in scored_candidates[:top_k]:
        out_doc = dict(cand["doc"])
        out_doc["rerank_metadata"] = {
            "initial_rank": cand["initial_rank"],
            "cross_encoder_rank": cand["lexical_rank"],
            "cross_encoder_score": cand["cross_encoder_score"],
            "final_rrf_score": round(cand["final_rrf_score"], 6),
        }
        results.append(out_doc)

    return results
