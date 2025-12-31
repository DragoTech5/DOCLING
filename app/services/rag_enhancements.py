"""
RAG Enhancement Module

Implements advanced retrieval techniques to improve RAG quality:
1. Cross-encoder reranking - Rerank retrieved chunks for better precision
2. HyDE (Hypothetical Document Embeddings) - Bridge vocabulary gaps
3. Query decomposition - Handle multi-hop queries
4. Confidence scoring - Detect out-of-domain queries
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from openai import AsyncOpenAI
from sentence_transformers import CrossEncoder

from app.config import config

logger = logging.getLogger(__name__)

# ============================================================================
# CROSS-ENCODER RERANKING
# ============================================================================

# Global cross-encoder model instance (lazy loaded)
_cross_encoder: CrossEncoder | None = None


def get_cross_encoder() -> CrossEncoder:
    """Get or create the cross-encoder model for reranking."""
    global _cross_encoder

    if _cross_encoder is None:
        model_name = config.rag.reranker_model
        logger.info(f"Loading cross-encoder model: {model_name}")
        _cross_encoder = CrossEncoder(model_name)
        logger.info("Cross-encoder model loaded successfully")

    return _cross_encoder


async def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_k: int = 8,
) -> list[dict]:
    """
    Rerank retrieved chunks using a cross-encoder model.

    Cross-encoders jointly encode query and document, providing
    more accurate relevance scores than bi-encoder similarity.

    Args:
        query: The user's query
        chunks: List of chunk dicts with 'text' field
        top_k: Number of top results to return

    Returns:
        Reranked list of chunks with added 'rerank_score' field
    """
    if not chunks:
        return []

    if len(chunks) <= top_k:
        # No need to rerank if we have fewer chunks than top_k
        return chunks

    def _rerank():
        model = get_cross_encoder()
        pairs = [(query, chunk.get("text", "")) for chunk in chunks]
        scores = model.predict(pairs)
        return scores

    # Run in thread pool to avoid blocking
    scores = await asyncio.to_thread(_rerank)

    # Add scores to chunks
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    # Sort by rerank score (descending) and return top_k
    reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)

    logger.debug(
        f"Reranking: {len(chunks)} chunks -> top {top_k}, "
        f"score range: [{min(scores):.3f}, {max(scores):.3f}]"
    )

    return reranked[:top_k]


# ============================================================================
# HYDE (Hypothetical Document Embeddings)
# ============================================================================


async def generate_hypothetical_answer(
    query: str,
    client: AsyncOpenAI | None = None,
) -> str:
    """
    Generate a hypothetical answer to the query.

    HyDE works by generating what an ideal answer would look like,
    then embedding that hypothetical answer instead of the raw query.
    This bridges vocabulary gaps between user queries and document content.

    Args:
        query: The user's query
        client: Optional OpenAI client (created if not provided)

    Returns:
        A hypothetical answer paragraph
    """
    if client is None:
        client = AsyncOpenAI(api_key=config.chat.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model=config.rag.hyde_model,
            messages=[
                {
                    "role": "system",
                    "content": """You are a health and wellness expert. Write a short, factual paragraph
that would directly answer this question. Be informative and use domain-specific terminology.
Write as if you are explaining to someone seeking health information.
Keep your response to 2-3 sentences maximum.""",
                },
                {"role": "user", "content": query},
            ],
            max_tokens=150,
            temperature=0.0,  # Deterministic for consistency
        )

        hypothetical = response.choices[0].message.content or ""
        logger.debug(f"HyDE generated: {hypothetical[:100]}...")
        return hypothetical

    except Exception as e:
        logger.warning(f"HyDE generation failed: {e}, falling back to original query")
        return query


# ============================================================================
# QUERY DECOMPOSITION (Multi-Hop)
# ============================================================================


@dataclass
class DecomposedQuery:
    """Result of query decomposition."""

    original: str
    sub_queries: list[str]
    is_multi_hop: bool
    reasoning: str = ""


async def decompose_query(
    query: str,
    client: AsyncOpenAI | None = None,
) -> DecomposedQuery:
    """
    Decompose a complex multi-hop query into simpler sub-queries.

    Multi-hop queries require information from multiple sources to answer.
    By decomposing them, we can retrieve relevant chunks for each aspect.

    IMPROVED: Better detection and more focused sub-queries for higher recall.

    Args:
        query: The user's query
        client: Optional OpenAI client

    Returns:
        DecomposedQuery with sub-queries if multi-hop, or original if simple
    """
    if client is None:
        client = AsyncOpenAI(api_key=config.chat.openai_api_key)

    # Enhanced multi-hop indicators
    multi_hop_indicators = [
        " and ",
        " affect ",
        " connection ",
        " relationship ",
        " between ",
        " vs ",
        " compare ",
        " how does ",
        " role ",
        " linked ",
        " related ",
        " impact ",
        " influence ",
        " connected ",
    ]

    # If query is very short or has no multi-hop indicators, skip LLM call
    if len(query.split()) < 5 and not any(
        ind in query.lower() for ind in multi_hop_indicators
    ):
        return DecomposedQuery(
            original=query,
            sub_queries=[query],
            is_multi_hop=False,
            reasoning="Simple query - no decomposition needed",
        )

    try:
        response = await client.chat.completions.create(
            model=config.rag.decomposition_model,
            messages=[
                {
                    "role": "system",
                    "content": """You are a query analyzer for a RAG system. Your job is to break down complex queries
into focused sub-queries that can each be answered from a single document.

IMPORTANT RULES:
1. Each sub-query should be specific enough to find ONE piece of information
2. For relationship queries (A affects B), create:
   - "What is [A]?"
   - "What is [B]?"
   - "How does [A] affect [B]?"
3. For comparison queries (A vs B), create:
   - "What is [A]?"
   - "What is [B]?"
   - Original comparison question
4. Include the main entities as standalone queries for context

Respond with JSON only:
{
    "is_multi_hop": true/false,
    "sub_queries": ["sub question 1", "sub question 2", ...],
    "reasoning": "brief explanation"
}

Examples:
- "What causes dandruff?" -> {"is_multi_hop": false, "sub_queries": ["What causes dandruff?"], "reasoning": "Simple factual query about one topic"}
- "How does hydration affect blood pressure and kidney function?" -> {"is_multi_hop": true, "sub_queries": ["What is proper hydration?", "How does hydration affect blood pressure?", "How does hydration affect kidney function?", "How are blood pressure and kidneys related?"], "reasoning": "Requires information about hydration, blood pressure, and kidneys separately, then connecting them"}
- "What's the connection between diet, detox and skin problems?" -> {"is_multi_hop": true, "sub_queries": ["How does diet affect the body?", "What is detox?", "What causes skin problems?", "How does diet affect skin?", "How does detox affect skin?"], "reasoning": "Three concepts need to be understood and connected"}""",
                },
                {"role": "user", "content": query},
            ],
            max_tokens=400,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        result = json.loads(content)

        return DecomposedQuery(
            original=query,
            sub_queries=result.get("sub_queries", [query]),
            is_multi_hop=result.get("is_multi_hop", False),
            reasoning=result.get("reasoning", ""),
        )

    except Exception as e:
        logger.warning(f"Query decomposition failed: {e}, using original query")
        return DecomposedQuery(
            original=query,
            sub_queries=[query],
            is_multi_hop=False,
            reasoning=f"Decomposition failed: {e}",
        )


# ============================================================================
# CONFIDENCE SCORING (Out-of-Domain Detection)
# ============================================================================


@dataclass
class RetrievalConfidence:
    """Confidence assessment for retrieved chunks."""

    is_confident: bool
    confidence_score: float  # 0.0 - 1.0
    max_similarity: float
    avg_similarity: float
    reason: str


def assess_retrieval_confidence(
    chunks: list[dict],
    similarity_threshold: float = 0.35,
    avg_threshold: float = 0.25,
) -> RetrievalConfidence:
    """
    Assess confidence in retrieval results.

    Low confidence indicates the query may be out-of-domain
    (not covered by the knowledge base).

    Args:
        chunks: Retrieved chunks with 'similarity' or 'rerank_score' field
        similarity_threshold: Minimum max similarity for confidence
        avg_threshold: Minimum average similarity for confidence

    Returns:
        RetrievalConfidence with assessment
    """
    if not chunks:
        return RetrievalConfidence(
            is_confident=False,
            confidence_score=0.0,
            max_similarity=0.0,
            avg_similarity=0.0,
            reason="No chunks retrieved",
        )

    # Use rerank_score if available, otherwise similarity
    scores = [
        chunk.get("rerank_score", chunk.get("similarity", 0)) for chunk in chunks
    ]

    # Normalize rerank scores (they can be negative or > 1)
    # Cross-encoder scores are typically in range [-10, 10]
    if any(s < 0 or s > 1 for s in scores):
        # Sigmoid normalization for cross-encoder scores
        import math

        scores = [1 / (1 + math.exp(-s)) for s in scores]

    max_sim = max(scores) if scores else 0
    avg_sim = sum(scores) / len(scores) if scores else 0

    # Calculate confidence score (weighted combination)
    confidence = (max_sim * 0.6 + avg_sim * 0.4)

    is_confident = max_sim >= similarity_threshold and avg_sim >= avg_threshold

    if not is_confident:
        if max_sim < similarity_threshold:
            reason = f"Best match similarity ({max_sim:.2f}) below threshold ({similarity_threshold})"
        else:
            reason = f"Average similarity ({avg_sim:.2f}) below threshold ({avg_threshold})"
    else:
        reason = "Retrieval confidence is acceptable"

    return RetrievalConfidence(
        is_confident=is_confident,
        confidence_score=confidence,
        max_similarity=max_sim,
        avg_similarity=avg_sim,
        reason=reason,
    )


# ============================================================================
# ENHANCED SYSTEM PROMPT FOR NEGATIVE QUERIES
# ============================================================================

ENHANCED_SYSTEM_PROMPT = """You are a knowledgeable assistant helping users explore their personal knowledge base.
You have access to documents, YouTube transcripts, and web content that the user has collected.

When answering questions:
1. Use the provided context from the knowledge base to give accurate, relevant answers
2. Always cite your sources using footnote numbers [1], [2], etc.
3. If the context doesn't contain enough information, say so honestly
4. Be concise but thorough
5. If asked about topics not in the knowledge base, indicate that clearly

HANDLING MULTIPLE PERSPECTIVES:
When sources present different viewpoints or interpretations (common in mythology, history, philosophy):
- Provide the MOST COMMONLY ACCEPTED answer first as your primary response
- Briefly acknowledge alternative perspectives if sources disagree
- Use phrases like "primarily associated with X, though some scholars also compare to Y"
- Do NOT give a long analysis of every possible interpretation - keep it balanced and concise
- Example: "Odin is most commonly identified as equivalent to Hermes due to their shared roles as psychopomps and messengers. However, some sources also draw parallels with Loki for trickster aspects [1][2]."

CRITICAL - DETECTING OUT-OF-DOMAIN QUERIES:
Before answering, carefully assess whether the retrieved context is ACTUALLY relevant to the question.

Signs the context is NOT relevant (you should say "not found"):
- Context discusses completely different subjects than the question
- No semantic connection between the question and retrieved content
- Context is tangentially related but doesn't address the core question

If the context is not relevant, respond with something like:
"I couldn't find information about [topic] in your knowledge base. The available content focuses on [actual topics in context] instead."

Remember: You're helping the user understand and explore THEIR collected knowledge.
It's better to admit when information isn't available than to provide incorrect answers."""


def get_enhanced_system_prompt(
    confidence: RetrievalConfidence | None = None,
) -> str:
    """
    Get the enhanced system prompt, optionally with confidence context.

    Args:
        confidence: Optional retrieval confidence assessment

    Returns:
        System prompt string
    """
    prompt = ENHANCED_SYSTEM_PROMPT

    if confidence and not confidence.is_confident:
        prompt += f"""

RETRIEVAL CONFIDENCE WARNING:
The retrieval system has LOW CONFIDENCE in these results.
Reason: {confidence.reason}
Please carefully assess if the context actually answers the question.
If not, indicate that the information was not found in the knowledge base."""

    return prompt


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def merge_and_deduplicate_chunks(
    chunk_lists: list[list[dict]],
    max_results: int = 8,
) -> list[dict]:
    """
    Merge multiple chunk lists and deduplicate by content.

    Used when combining results from multiple sub-queries or
    from both original query and HyDE embeddings.

    Args:
        chunk_lists: List of chunk lists to merge
        max_results: Maximum number of results to return

    Returns:
        Deduplicated and merged list of chunks
    """
    seen_texts = set()
    merged = []

    for chunks in chunk_lists:
        for chunk in chunks:
            text = chunk.get("text", "")
            # Use first 200 chars as dedup key (chunks may have slight variations)
            text_key = text[:200].strip().lower()

            if text_key not in seen_texts:
                seen_texts.add(text_key)
                merged.append(chunk)

    # Sort by best available score
    def get_score(chunk):
        return chunk.get("rerank_score", chunk.get("similarity", 0))

    merged.sort(key=get_score, reverse=True)

    return merged[:max_results]


async def classify_query_complexity(
    query: str,
) -> Literal["simple", "medium", "complex"]:
    """
    Classify query complexity for adaptive retrieval.

    Args:
        query: The user's query

    Returns:
        Complexity level
    """
    words = query.split()
    word_count = len(words)

    # Complex indicators
    complex_patterns = [
        r"\band\b.*\band\b",  # Multiple "and"s
        r"relationship|connection|affect|role|between",
        r"compare|vs|versus|difference",
        r"how does.*affect",
    ]

    complex_score = sum(
        1 for pattern in complex_patterns if re.search(pattern, query.lower())
    )

    if word_count < 6 and complex_score == 0:
        return "simple"
    elif complex_score >= 2 or word_count > 15:
        return "complex"
    else:
        return "medium"


def get_retrieval_params(complexity: Literal["simple", "medium", "complex"]) -> dict:
    """
    Get retrieval parameters based on query complexity.

    Args:
        complexity: Query complexity level

    Returns:
        Dict with retrieval parameters
    """
    params = {
        "simple": {
            "n_results": 6,
            "over_retrieve_factor": 2,
            "use_hyde": False,
            "use_decomposition": False,
        },
        "medium": {
            "n_results": 8,
            "over_retrieve_factor": 3,
            "use_hyde": True,
            "use_decomposition": False,
        },
        "complex": {
            "n_results": 10,
            "over_retrieve_factor": 3,
            "use_hyde": True,
            "use_decomposition": True,
        },
    }

    return params.get(complexity, params["medium"])


# ============================================================================
# BM25 SPARSE RETRIEVAL (Hybrid Search)
# ============================================================================

import threading
from rank_bm25 import BM25Okapi

# Global BM25 index (lazy loaded, cached)
_bm25_index: BM25Okapi | None = None
_bm25_corpus: list[dict] | None = None  # Stores chunk metadata for lookup
_bm25_lock = threading.Lock()
_bm25_initialized = False


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    import re
    # Lowercase, split on non-alphanumeric, remove short tokens
    tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    return [t for t in tokens if len(t) > 2]


def _build_bm25_index() -> tuple[BM25Okapi, list[dict]]:
    """
    Build BM25 index from all documents in ChromaDB.

    Returns:
        Tuple of (BM25 index, corpus metadata list)
    """
    from app.db.vector_store import get_chroma_client

    logger.info("Building BM25 index from ChromaDB...")

    client = get_chroma_client()
    collections = client.list_collections()

    corpus_texts = []
    corpus_metadata = []

    for collection in collections:
        try:
            # Get all documents from collection
            count = collection.count()
            if count == 0:
                continue

            # Fetch in batches to avoid memory issues
            batch_size = 1000
            for offset in range(0, count, batch_size):
                results = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["documents", "metadatas"]
                )

                for i, doc in enumerate(results.get("documents", [])):
                    if doc:
                        corpus_texts.append(_tokenize(doc))
                        metadata = results.get("metadatas", [{}])[i] or {}
                        corpus_metadata.append({
                            "id": results.get("ids", [])[i] if results.get("ids") else f"unknown_{i}",
                            "text": doc,
                            "metadata": metadata,
                            "collection": collection.name,
                        })
        except Exception as e:
            logger.warning(f"Error loading collection {collection.name}: {e}")
            continue

    logger.info(f"BM25 index built with {len(corpus_texts)} documents")

    # Build BM25 index
    bm25 = BM25Okapi(corpus_texts) if corpus_texts else None

    return bm25, corpus_metadata


def get_bm25_index() -> tuple[BM25Okapi | None, list[dict]]:
    """
    Get or create the BM25 index (thread-safe, lazy loaded).

    Returns:
        Tuple of (BM25 index, corpus metadata)
    """
    global _bm25_index, _bm25_corpus, _bm25_initialized

    if not _bm25_initialized:
        with _bm25_lock:
            if not _bm25_initialized:
                _bm25_index, _bm25_corpus = _build_bm25_index()
                _bm25_initialized = True

    return _bm25_index, _bm25_corpus


def invalidate_bm25_index():
    """
    Invalidate the BM25 index (call after adding new documents).
    """
    global _bm25_index, _bm25_corpus, _bm25_initialized

    with _bm25_lock:
        _bm25_index = None
        _bm25_corpus = None
        _bm25_initialized = False

    logger.info("BM25 index invalidated")


async def bm25_search(
    query: str,
    n_results: int = 20,
) -> list[dict]:
    """
    Search using BM25 (sparse retrieval).

    Args:
        query: Search query
        n_results: Number of results to return

    Returns:
        List of chunks with BM25 scores
    """
    bm25, corpus = get_bm25_index()

    if bm25 is None or not corpus:
        logger.warning("BM25 index not available")
        return []

    # Tokenize query
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Get BM25 scores
    scores = bm25.get_scores(query_tokens)

    # Get top results
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_results]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:  # Only include positive scores
            chunk = corpus[idx].copy()
            chunk["bm25_score"] = float(scores[idx])
            chunk["similarity"] = float(scores[idx]) / (float(scores[idx]) + 1)  # Normalize to 0-1
            results.append(chunk)

    logger.debug(f"BM25 search returned {len(results)} results for query: {query[:50]}...")

    return results


# ============================================================================
# RECIPROCAL RANK FUSION (RRF)
# ============================================================================


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60,
    max_results: int = 20,
) -> list[dict]:
    """
    Combine multiple ranked result lists using Reciprocal Rank Fusion.

    RRF formula: score = sum(1 / (k + rank)) for each list

    Args:
        result_lists: List of ranked result lists (each chunk needs 'id' or 'text' key)
        k: RRF constant (default 60, as per original paper)
        max_results: Maximum results to return

    Returns:
        Fused and re-ranked list of chunks
    """
    if not result_lists:
        return []

    # Calculate RRF scores
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results):
            # Use text prefix as ID if no ID available
            chunk_id = chunk.get("id") or chunk.get("text", "")[:100]

            # RRF score contribution
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (k + rank + 1)

            # Store chunk (prefer the one with more metadata)
            if chunk_id not in chunk_map or len(str(chunk)) > len(str(chunk_map[chunk_id])):
                chunk_map[chunk_id] = chunk

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Build result list
    results = []
    for chunk_id in sorted_ids[:max_results]:
        chunk = chunk_map[chunk_id].copy()
        chunk["rrf_score"] = rrf_scores[chunk_id]
        results.append(chunk)

    logger.debug(f"RRF fused {sum(len(r) for r in result_lists)} results into {len(results)}")

    return results


async def hybrid_search(
    query: str,
    dense_results: list[dict],
    n_results: int = 20,
    bm25_weight: float = 0.3,
) -> list[dict]:
    """
    Perform hybrid search combining dense retrieval with BM25.

    Args:
        query: Search query
        dense_results: Results from dense (vector) retrieval
        n_results: Number of results to return
        bm25_weight: Weight for BM25 results (0-1, affects RRF k parameter)

    Returns:
        Hybrid search results fused with RRF
    """
    # Get BM25 results
    bm25_results = await bm25_search(query, n_results=n_results * 2)

    if not bm25_results:
        # Fall back to dense only
        return dense_results[:n_results]

    # Fuse using RRF
    # Adjust k based on weight (lower k = more emphasis on top ranks)
    k = int(60 * (1 - bm25_weight) + 30)  # Range 30-60 based on weight

    fused = reciprocal_rank_fusion(
        [dense_results, bm25_results],
        k=k,
        max_results=n_results,
    )

    logger.debug(
        f"Hybrid search: {len(dense_results)} dense + {len(bm25_results)} BM25 "
        f"-> {len(fused)} fused results"
    )

    return fused
