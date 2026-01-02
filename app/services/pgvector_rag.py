"""
pgvector RAG Service for MAGICK PDFs

This module provides RAG functionality using PostgreSQL + pgvector as the backend.
It integrates with the existing RAG enhancements (HyDE, reranking, query decomposition)
while using pgvector for vector storage.

This is a NEW service that works alongside existing ChromaDB RAG.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.config import config
from app.services import pgvector_service as pgvector
from app.services.rag_enhancements import (
    rerank_chunks,
    generate_hypothetical_answer,
    decompose_query,
    assess_retrieval_confidence,
    get_enhanced_system_prompt,
    classify_query_complexity,
    get_retrieval_params,
    merge_and_deduplicate_chunks,
    DecomposedQuery,
    RetrievalConfidence,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class RAGResponse:
    """Response from RAG query."""
    answer: str
    sources: list[dict[str, Any]]
    confidence: RetrievalConfidence | None
    query_info: dict[str, Any]


@dataclass
class PgVectorRAGConfig:
    """Configuration for pgvector RAG."""
    use_hyde: bool = True
    use_reranking: bool = True
    use_decomposition: bool = True
    use_confidence: bool = True
    use_hybrid_search: bool = True
    n_results: int = 8
    vector_weight: float = 0.7


# ============================================================================
# RETRIEVAL FUNCTIONS
# ============================================================================


async def retrieve_chunks(
    query: str,
    n_results: int = 8,
    use_hybrid: bool = True,
    vector_weight: float = 0.7,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """
    Retrieve relevant chunks from pgvector.

    Args:
        query: Search query
        n_results: Number of results to return
        use_hybrid: Whether to use hybrid search (vector + keyword)
        vector_weight: Weight for vector similarity in hybrid search
        document_ids: Optional list of document IDs to filter by

    Returns:
        List of chunk dicts in RAG-compatible format
    """
    try:
        results = await pgvector.search(
            query=query,
            match_count=n_results,
            use_hybrid=use_hybrid,
            vector_weight=vector_weight,
            document_ids=document_ids,
        )
    except Exception as e:
        # Fall back to vector-only search if hybrid fails
        logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
        results = await pgvector.search(
            query=query,
            match_count=n_results,
            use_hybrid=False,
            document_ids=document_ids,
        )

    return pgvector.format_search_results_for_rag(results)


async def retrieve_with_hyde(
    query: str,
    client: AsyncOpenAI,
    n_results: int = 8,
    use_hybrid: bool = True,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """
    Retrieve using HyDE (Hypothetical Document Embeddings).

    Generates a hypothetical answer first, then embeds and retrieves
    using both the original query and the hypothetical answer.
    """
    # Generate hypothetical answer
    hypothetical = await generate_hypothetical_answer(query, client)

    # Retrieve for both original and hypothetical
    results_original = await retrieve_chunks(
        query=query,
        n_results=n_results,
        use_hybrid=use_hybrid,
        document_ids=document_ids,
    )

    results_hyde = await retrieve_chunks(
        query=hypothetical,
        n_results=n_results,
        use_hybrid=use_hybrid,
        document_ids=document_ids,
    )

    # Merge and deduplicate
    merged = merge_and_deduplicate_chunks(
        [results_original, results_hyde],
        max_results=n_results,
    )

    logger.info(f"[HYDE_RETRIEVAL] Original: {len(results_original)}, HyDE: {len(results_hyde)}, Merged: {len(merged)}, document_ids={document_ids}")

    # DEBUG: Log first chunk text if available
    if merged:
        first_chunk_text = merged[0].get("text", "")[:100]
        logger.debug(f"[HYDE_RETRIEVAL] First merged chunk text: {first_chunk_text}")
    else:
        logger.warning(f"[HYDE_RETRIEVAL] NO CHUNKS AFTER MERGE! original={len(results_original)}, hyde={len(results_hyde)}")

    return merged


async def retrieve_with_decomposition(
    query: str,
    client: AsyncOpenAI,
    n_results: int = 8,
    use_hybrid: bool = True,
    document_ids: list[int] | None = None,
) -> tuple[list[dict], DecomposedQuery]:
    """
    Retrieve using query decomposition for multi-hop queries.
    """
    # Decompose query
    decomposed = await decompose_query(query, client)

    if not decomposed.is_multi_hop:
        # Simple query, just retrieve directly
        results = await retrieve_chunks(
            query=query,
            n_results=n_results,
            use_hybrid=use_hybrid,
            document_ids=document_ids,
        )
        return results, decomposed

    # Retrieve for each sub-query
    all_results = []
    for sub_query in decomposed.sub_queries:
        sub_results = await retrieve_chunks(
            query=sub_query,
            n_results=n_results // len(decomposed.sub_queries) + 1,
            use_hybrid=use_hybrid,
            document_ids=document_ids,
        )
        all_results.append(sub_results)

    # Merge and deduplicate
    merged = merge_and_deduplicate_chunks(all_results, max_results=n_results)

    logger.debug(
        f"Decomposition retrieval: {len(decomposed.sub_queries)} sub-queries -> {len(merged)} chunks"
    )

    return merged, decomposed


# ============================================================================
# ENHANCED RAG PIPELINE
# ============================================================================


def _balance_reranked_chunks(
    reranked_chunks: list[dict],
    document_ids: list[int],
    target_count: int,
) -> list[dict]:
    """
    Re-balance chunks after reranking to ensure multi-document representation.

    When multiple documents are selected and reranking is applied, the global
    scoring often results in all top chunks coming from one high-relevance document.
    This function takes the reranked chunks and re-distributes them to ensure
    chunks from all selected documents are represented in the final results.

    Args:
        reranked_chunks: Chunks after reranking by relevance score
        document_ids: List of selected document IDs
        target_count: Target number of chunks to return

    Returns:
        Balanced list of chunks with representation from all documents
    """
    if not reranked_chunks or len(document_ids) <= 1:
        return reranked_chunks[:target_count]

    logger.debug(f"[BALANCE_RERANKED] Input: {len(reranked_chunks)} reranked chunks, target={target_count}, document_ids={document_ids}")
    if reranked_chunks:
        logger.debug(f"[BALANCE_RERANKED] First chunk structure: {list(reranked_chunks[0].keys())}")

    # Group reranked chunks by document
    chunks_by_doc = {}
    for i, chunk in enumerate(reranked_chunks):
        # Try multiple locations for document_id
        doc_id = chunk.get("metadata", {}).get("document_id") or chunk.get("document_id")
        if i == 0:
            logger.debug(f"[BALANCE_RERANKED] Chunk 0 full structure: {chunk}")
        logger.debug(f"[BALANCE_RERANKED] Chunk {i}: doc_id={doc_id}, has metadata={bool(chunk.get('metadata'))}, has document_id={bool(chunk.get('document_id'))}")
        if doc_id is None:
            # Skip chunks without document_id
            continue
        if doc_id not in chunks_by_doc:
            chunks_by_doc[doc_id] = []
        chunks_by_doc[doc_id].append(chunk)

    logger.debug(f"[BALANCE_RERANKED] Grouped into {len(chunks_by_doc)} documents: {list(chunks_by_doc.keys())}")

    # If no chunks have document_id, fall back to returning as-is
    if not chunks_by_doc:
        logger.warning(f"[BALANCE_RERANKED] No chunks have document_id, returning original {target_count} chunks")
        return reranked_chunks[:target_count]

    # Calculate target chunks per document
    chunks_per_doc = max(1, target_count // len(document_ids))
    remainder = target_count % len(document_ids)

    # Build balanced result from reranked chunks
    balanced = []
    for i, doc_id in enumerate(document_ids):
        # Document IDs might be stored as strings in metadata, so check both int and str
        doc_id_int = int(doc_id) if isinstance(doc_id, str) else doc_id
        doc_id_str = str(doc_id)
        found_doc_id = None

        if doc_id_int in chunks_by_doc:
            found_doc_id = doc_id_int
        elif doc_id_str in chunks_by_doc:
            found_doc_id = doc_id_str

        if found_doc_id is not None:
            # Take top N chunks from this document (already sorted by relevance)
            count = chunks_per_doc + (1 if i < remainder else 0)
            taken = len(chunks_by_doc[found_doc_id][:count])
            logger.debug(f"[BALANCE_RERANKED] Document {doc_id}: taking {taken} chunks (requested {count})")
            balanced.extend(chunks_by_doc[found_doc_id][:count])
        else:
            logger.warning(f"[BALANCE_RERANKED] Document {doc_id} not found in reranked chunks (tried {doc_id_int} and {doc_id_str})!")

    logger.debug(f"[BALANCE_RERANKED] Balanced result: {len(balanced)} chunks from {len(set(c.get('metadata', {}).get('document_id') or c.get('document_id') for c in balanced))} documents")

    # If balancing resulted in empty list, return original (unbalanced) top chunks
    if not balanced:
        logger.warning(f"[BALANCE_RERANKED] Balancing resulted in empty list, returning original {target_count} chunks")
        return reranked_chunks[:target_count]

    # Return balanced chunks (maintaining their reranking order within each document)
    return balanced[:target_count]


async def enhanced_retrieve(
    query: str,
    client: AsyncOpenAI | None = None,
    rag_config: PgVectorRAGConfig | None = None,
    document_ids: list[int] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Enhanced retrieval pipeline using pgvector with all RAG enhancements.

    Args:
        query: User's query
        client: Optional OpenAI client
        rag_config: Optional RAG configuration
        document_ids: Optional list of document IDs to filter by

    Returns:
        Tuple of (chunks, metadata about the retrieval)
    """
    if client is None:
        client = AsyncOpenAI(api_key=config.chat.openai_api_key)

    if rag_config is None:
        rag_config = PgVectorRAGConfig()

    retrieval_info = {
        "original_query": query,
        "methods_used": [],
        "document_filter": document_ids,
    }

    # Classify query complexity
    complexity = await classify_query_complexity(query)
    params = get_retrieval_params(complexity)
    retrieval_info["complexity"] = complexity

    # Adjust params based on config
    n_results = rag_config.n_results
    use_hyde = rag_config.use_hyde and params.get("use_hyde", False)
    use_decomposition = rag_config.use_decomposition and params.get("use_decomposition", False)

    # Decomposition first (for multi-hop queries)
    decomposed = None
    if use_decomposition:
        chunks, decomposed = await retrieve_with_decomposition(
            query=query,
            client=client,
            n_results=n_results * 2,  # Over-retrieve for reranking
            use_hybrid=rag_config.use_hybrid_search,
            document_ids=document_ids,
        )
        retrieval_info["methods_used"].append("decomposition")
        retrieval_info["decomposed"] = {
            "is_multi_hop": decomposed.is_multi_hop,
            "sub_queries": decomposed.sub_queries,
            "reasoning": decomposed.reasoning,
        }
    # HyDE for bridging vocabulary gaps
    elif use_hyde:
        chunks = await retrieve_with_hyde(
            query=query,
            client=client,
            n_results=n_results * 2,
            use_hybrid=rag_config.use_hybrid_search,
            document_ids=document_ids,
        )
        retrieval_info["methods_used"].append("hyde")
    # Simple retrieval
    else:
        chunks = await retrieve_chunks(
            query=query,
            n_results=n_results * 2,
            use_hybrid=rag_config.use_hybrid_search,
            document_ids=document_ids,
        )

    retrieval_info["initial_chunks"] = len(chunks)

    # Reranking
    if rag_config.use_reranking and chunks:
        # For multi-document queries, rerank per-document to ensure all docs are represented
        if document_ids and len(document_ids) > 1:
            logger.debug(f"[RERANKING] Multi-document mode: reranking {len(chunks)} chunks from {len(document_ids)} documents")

            # Group chunks by document
            chunks_by_doc = {}
            for chunk in chunks:
                doc_id = chunk.get("metadata", {}).get("document_id") or chunk.get("document_id")
                if doc_id:
                    if doc_id not in chunks_by_doc:
                        chunks_by_doc[doc_id] = []
                    chunks_by_doc[doc_id].append(chunk)

            # Rerank per-document and collect top chunks from each
            per_doc_count = max(1, n_results // len(document_ids))
            remainder = n_results % len(document_ids)
            reranked_chunks = []

            for i, doc_id in enumerate(document_ids):
                if str(doc_id) in chunks_by_doc or doc_id in chunks_by_doc:
                    doc_chunks = chunks_by_doc.get(str(doc_id)) or chunks_by_doc.get(doc_id)
                    if doc_chunks:
                        # Rerank chunks for this document
                        reranked_doc_chunks = await rerank_chunks(query, doc_chunks, top_k=len(doc_chunks))
                        # Take top N for this document
                        count = per_doc_count + (1 if i < remainder else 0)
                        reranked_chunks.extend(reranked_doc_chunks[:count])
                        logger.debug(f"[RERANKING] Document {doc_id}: took {len(reranked_doc_chunks[:count])} of {count} requested chunks")

            chunks = reranked_chunks
            logger.debug(f"[RERANKING] Multi-document reranking: {len(chunks)} chunks from multiple documents")
        else:
            # Single document or no document filter: use global reranking
            chunks = await rerank_chunks(query, chunks, top_k=n_results)

        retrieval_info["methods_used"].append("reranking")

    retrieval_info["final_chunks"] = len(chunks)

    # Confidence assessment
    confidence = None
    if rag_config.use_confidence:
        confidence = assess_retrieval_confidence(
            chunks,
            similarity_threshold=config.rag.confidence_threshold,
            avg_threshold=config.rag.avg_confidence_threshold,
        )
        retrieval_info["confidence"] = {
            "is_confident": confidence.is_confident,
            "score": confidence.confidence_score,
            "max_similarity": confidence.max_similarity,
            "avg_similarity": confidence.avg_similarity,
            "reason": confidence.reason,
        }

    return chunks, retrieval_info


# ============================================================================
# RAG CHAT
# ============================================================================


async def rag_chat(
    query: str,
    chat_history: list[dict] | None = None,
    rag_config: PgVectorRAGConfig | None = None,
) -> RAGResponse:
    """
    Full RAG chat using pgvector.

    Args:
        query: User's query
        chat_history: Optional conversation history
        rag_config: Optional RAG configuration

    Returns:
        RAGResponse with answer, sources, and metadata
    """
    client = AsyncOpenAI(api_key=config.chat.openai_api_key)

    # Retrieve relevant chunks
    chunks, retrieval_info = await enhanced_retrieve(
        query=query,
        client=client,
        rag_config=rag_config,
    )

    # Build context from chunks
    context_parts = []
    sources = []

    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[{i}] {chunk['text']}")

        source = {
            "index": i,
            "text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
            "similarity": chunk.get("similarity", 0),
        }

        metadata = chunk.get("metadata", {})
        if metadata:
            source["title"] = metadata.get("document_title")
            source["author"] = metadata.get("document_author")
            source["page"] = metadata.get("page_number")

        sources.append(source)

    context = "\n\n".join(context_parts)

    # Get confidence-aware system prompt
    confidence = None
    if retrieval_info.get("confidence"):
        confidence = RetrievalConfidence(
            is_confident=retrieval_info["confidence"]["is_confident"],
            confidence_score=retrieval_info["confidence"]["score"],
            max_similarity=retrieval_info["confidence"]["max_similarity"],
            avg_similarity=retrieval_info["confidence"]["avg_similarity"],
            reason=retrieval_info["confidence"]["reason"],
        )

    system_prompt = get_enhanced_system_prompt(confidence)

    # Customize system prompt for MAGICK collection
    system_prompt = system_prompt.replace(
        "health and wellness",
        "occult, magick, esoteric knowledge, and spiritual traditions"
    )

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]

    # Add chat history if provided
    if chat_history:
        messages.extend(chat_history[-10:])  # Last 10 messages

    # Add context and query
    user_message = f"""Context from the MAGICK PDFs knowledge base:

{context}

---

User Question: {query}

Please answer based on the context above. Cite sources using [1], [2], etc."""

    messages.append({"role": "user", "content": user_message})

    # Generate response
    response = await client.chat.completions.create(
        model=config.chat.model,
        messages=messages,
        max_tokens=config.chat.max_tokens,
        temperature=config.chat.temperature,
    )

    answer = response.choices[0].message.content or ""

    return RAGResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        query_info=retrieval_info,
    )


# ============================================================================
# SIMPLE SEARCH (for API)
# ============================================================================


async def simple_search(
    query: str,
    n_results: int = 10,
    use_hybrid: bool = True,
) -> list[dict]:
    """
    Simple search endpoint for external API use.

    Args:
        query: Search query
        n_results: Number of results
        use_hybrid: Whether to use hybrid search

    Returns:
        List of search results with metadata
    """
    results = await pgvector.search(
        query=query,
        match_count=n_results,
        use_hybrid=use_hybrid,
    )

    return [
        {
            "id": str(r.chunk_id),
            "document_id": str(r.document_id),
            "content": r.content,
            "similarity": r.similarity,
            "title": r.document_title,
            "author": r.document_author,
            "page": r.page_number,
        }
        for r in results
    ]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


async def get_stats() -> dict[str, Any]:
    """Get pgvector database statistics."""
    return await pgvector.get_database_stats()


async def health_check() -> bool:
    """Check if pgvector connection is healthy."""
    try:
        await pgvector.get_pool()
        return True
    except Exception as e:
        logger.error(f"pgvector health check failed: {e}")
        return False
