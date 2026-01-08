"""
Chat Service - RAG-powered chat with OpenAI

Supports federated search across local ChromaDB and Weaviate (in private mode).
Enhanced with:
- Cross-encoder reranking
- HyDE (Hypothetical Document Embeddings)
- Query decomposition for multi-hop queries
- Confidence scoring for out-of-domain detection
- BM25 hybrid search with Reciprocal Rank Fusion (RRF)
- Citation validation (CiteFix-inspired post-processing)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import config
from app.db import repository
from app.db.vector_store import query_documents
from app.core.embeddings import generate_embeddings
from app.lib.weaviate_client import query_weaviate
from app.services.rag_enhancements import (
    rerank_chunks,
    generate_hypothetical_answer,
    decompose_query,
    assess_retrieval_confidence,
    get_enhanced_system_prompt,
    merge_and_deduplicate_chunks,
    classify_query_complexity,
    get_retrieval_params,
    RetrievalConfidence,
    hybrid_search,
    bm25_search,
)
from app.services.citation_validator import validate_and_correct_citations

logger = logging.getLogger(__name__)

# Pattern to detect "Video {youtube_id}" titles
VIDEO_ID_PATTERN = re.compile(r'^Video\s+([a-zA-Z0-9_-]{11})(?:\s+\(Part.*\))?$')

# Cache for YouTube video titles (simple in-memory cache)
_youtube_title_cache: dict[str, str] = {}


async def get_youtube_title(video_id: str) -> str | None:
    """Fetch YouTube video title using yt-dlp. Returns None if fetch fails."""
    # Check cache first
    if video_id in _youtube_title_cache:
        return _youtube_title_cache[video_id]

    try:
        from app.core.youtube_processor import get_video_info
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        info = await get_video_info(video_url)
        if info and info.title:
            _youtube_title_cache[video_id] = info.title
            return info.title
    except Exception as e:
        logger.debug(f"Could not fetch YouTube title for {video_id}: {e}")

    return None


@dataclass
class Source:
    """A source citation from the knowledge base."""
    title: str
    source_type: str
    source_url: str | None
    channel_name: str | None
    published_date: str | None
    chunk_text: str
    similarity: float
    document_id: str | None = None  # For linking to book covers
    document_filename: str | None = None  # For cover image lookup (filename without .pdf)


@dataclass
class ChatResponse:
    """Response from the chat service."""
    content: str
    sources: list[Source]


def get_openai_client() -> AsyncOpenAI:
    """Get the OpenAI client."""
    return AsyncOpenAI(api_key=config.chat.openai_api_key)


async def _retrieve_raw_chunks(
    query_embedding: list[float],
    category_ids: list[int] | None = None,
    n_results: int = 8,
    include_weaviate: bool | None = None,
    query_text: str = "",
) -> list[dict]:
    """
    Low-level retrieval function that queries vector stores directly.

    Args:
        query_embedding: The embedding vector for the query
        category_ids: Optional list of category IDs to filter by
        n_results: Number of results to retrieve
        include_weaviate: Whether to include Weaviate results
        query_text: Original query text (needed for Weaviate hybrid search)

    Returns:
        List of raw chunks with metadata and similarity scores
    """
    all_results = []

    # Determine if we should search Weaviate
    search_weaviate = include_weaviate
    if search_weaviate is None:
        search_weaviate = config.weaviate.is_configured and config.mode.private_mode

    # Calculate results per source
    local_limit = n_results if not search_weaviate else (n_results * 2 // 3) + 1
    weaviate_limit = n_results - local_limit + 2 if search_weaviate else 0

    # Query local ChromaDB
    if category_ids:
        # Query specific categories
        for cat_id in category_ids:
            results = query_documents(
                query_embedding=query_embedding,
                category_ids=[cat_id],
                n_results=local_limit,
            )
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"]):
                    metadata = results["metadatas"][i] if results.get("metadatas") else {}
                    metadata["source"] = "local"
                    distance = results["distances"][i] if results.get("distances") else 0
                    all_results.append({
                        "text": doc,
                        "metadata": metadata,
                        "similarity": 1 - distance,
                        "category_id": cat_id,
                    })
    else:
        # Query all categories
        results = query_documents(
            query_embedding=query_embedding,
            category_ids=None,
            n_results=local_limit,
        )
        if results and results.get("documents"):
            for i, doc in enumerate(results["documents"]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                metadata["source"] = "local"
                distance = results["distances"][i] if results.get("distances") else 0
                all_results.append({
                    "text": doc,
                    "metadata": metadata,
                    "similarity": 1 - distance,
                    "category_id": None,
                })

    # Query Weaviate (private mode only)
    if search_weaviate and query_text:
        try:
            weaviate_results = await query_weaviate(
                query=query_text,
                limit=weaviate_limit,
                use_reranker=True,
            )
            for result in weaviate_results:
                all_results.append({
                    "text": result["text"],
                    "metadata": result["metadata"],
                    "similarity": result["score"],
                    "category_id": None,
                })
        except Exception as e:
            logger.warning(f"Weaviate query failed, using local results only: {e}")

    return all_results


async def retrieve_relevant_chunks(
    query: str,
    category_ids: list[int] | None = None,
    n_results: int = 8,
    include_weaviate: bool | None = None,
    use_enhancements: bool = True,
) -> list[dict]:
    """
    Retrieve relevant chunks from the knowledge base with optional RAG enhancements.

    Enhancements (when enabled):
    - HyDE: Generate hypothetical answer and embed it for better matching
    - Query decomposition: Break multi-hop queries into sub-queries
    - Cross-encoder reranking: Re-score chunks for better precision
    - Over-retrieval: Retrieve more chunks before reranking

    Args:
        query: The user's question
        category_ids: Optional list of category IDs to filter by
        n_results: Number of results to retrieve
        include_weaviate: Whether to include Weaviate results (None = auto based on config)
        use_enhancements: Whether to apply RAG enhancements (default: True)

    Returns:
        List of relevant chunks with metadata
    """
    client = get_openai_client()

    # Determine enhancement settings based on config and query complexity
    rag_config = config.rag
    use_hyde = use_enhancements and rag_config.hyde_enabled
    use_decomposition = use_enhancements and rag_config.decomposition_enabled
    use_reranking = use_enhancements and rag_config.reranking_enabled

    # Adaptive retrieval: adjust parameters based on query complexity
    if use_enhancements and rag_config.adaptive_retrieval:
        complexity = await classify_query_complexity(query)
        params = get_retrieval_params(complexity)
        n_results = params["n_results"]
        use_hyde = use_hyde and params["use_hyde"]
        use_decomposition = use_decomposition and params["use_decomposition"]
        over_retrieve_factor = params["over_retrieve_factor"]
        logger.debug(f"Query complexity: {complexity}, params: {params}")
    else:
        over_retrieve_factor = rag_config.over_retrieve_factor

    # Calculate how many chunks to retrieve before reranking
    retrieve_limit = n_results * over_retrieve_factor if use_reranking else n_results

    all_chunk_lists = []

    # ===== STEP 1: Query Decomposition (for multi-hop queries) =====
    is_multi_hop = False
    if use_decomposition:
        decomposed = await decompose_query(query, client)

        if decomposed.is_multi_hop and len(decomposed.sub_queries) > 1:
            is_multi_hop = True
            logger.info(
                f"Multi-hop query detected. Decomposed into {len(decomposed.sub_queries)} sub-queries: "
                f"{decomposed.sub_queries}"
            )

            # IMPROVED: More chunks per sub-query for multi-hop (was too low)
            # Each sub-query should get enough context independently
            per_query_limit = max(6, retrieve_limit // 2)  # At least 6 per sub-query

            for sub_query in decomposed.sub_queries:
                sub_embeddings = await generate_embeddings([sub_query])
                sub_embedding = sub_embeddings[0]

                sub_results = await _retrieve_raw_chunks(
                    query_embedding=sub_embedding,
                    category_ids=category_ids,
                    n_results=per_query_limit,
                    include_weaviate=include_weaviate,
                    query_text=sub_query,
                )
                all_chunk_lists.append(sub_results)

                # IMPROVED: Also do BM25 search for each sub-query
                # This helps find exact matches for sub-query terms
                if config.rag.bm25_enabled:
                    try:
                        sub_bm25_results = await bm25_search(sub_query, n_results=per_query_limit)
                        if sub_bm25_results:
                            all_chunk_lists.append(sub_bm25_results)
                    except Exception as e:
                        logger.debug(f"BM25 sub-query search failed: {e}")
        else:
            # Not multi-hop, proceed with normal retrieval
            use_decomposition = False  # Flag that we didn't actually decompose

    # ===== STEP 2: Standard retrieval (original query) =====
    query_embeddings = await generate_embeddings([query])
    query_embedding = query_embeddings[0]

    original_results = await _retrieve_raw_chunks(
        query_embedding=query_embedding,
        category_ids=category_ids,
        n_results=retrieve_limit,
        include_weaviate=include_weaviate,
        query_text=query,
    )
    all_chunk_lists.append(original_results)

    # ===== STEP 3: HyDE (Hypothetical Document Embeddings) =====
    if use_hyde:
        try:
            hypothetical = await generate_hypothetical_answer(query, client)

            if hypothetical and hypothetical != query:
                hyde_embeddings = await generate_embeddings([hypothetical])
                hyde_embedding = hyde_embeddings[0]

                hyde_results = await _retrieve_raw_chunks(
                    query_embedding=hyde_embedding,
                    category_ids=category_ids,
                    n_results=retrieve_limit // 2,  # Fewer results for HyDE
                    include_weaviate=False,  # HyDE only for local
                    query_text=hypothetical,
                )
                all_chunk_lists.append(hyde_results)
                logger.debug(f"HyDE retrieved {len(hyde_results)} additional chunks")
        except Exception as e:
            logger.warning(f"HyDE retrieval failed: {e}")

    # ===== STEP 4: Merge and deduplicate =====
    merged_chunks = merge_and_deduplicate_chunks(
        all_chunk_lists,
        max_results=retrieve_limit * 2,  # Keep more for reranking
    )

    logger.debug(
        f"Retrieval: {sum(len(c) for c in all_chunk_lists)} total chunks -> "
        f"{len(merged_chunks)} after dedup"
    )

    # ===== STEP 4.5: BM25 Hybrid Search (if enabled) =====
    use_bm25 = use_enhancements and config.rag.bm25_enabled
    if use_bm25:
        try:
            merged_chunks = await hybrid_search(
                query=query,
                dense_results=merged_chunks,
                n_results=retrieve_limit * 2,  # Keep more for reranking
                bm25_weight=config.rag.bm25_weight,
            )
            logger.debug(f"BM25 hybrid search applied, {len(merged_chunks)} chunks")
        except Exception as e:
            logger.warning(f"BM25 hybrid search failed: {e}, using dense only")

    # ===== STEP 5: Cross-encoder reranking =====
    # IMPROVED: Return more chunks for multi-hop queries
    final_n_results = n_results
    if is_multi_hop:
        # Multi-hop queries need more context from different sources
        final_n_results = min(n_results + 4, 12)  # Add 4 more chunks, max 12
        logger.debug(f"Multi-hop: increased final chunks from {n_results} to {final_n_results}")

    if use_reranking and len(merged_chunks) > final_n_results:
        try:
            final_chunks = await rerank_chunks(query, merged_chunks, top_k=final_n_results)
            logger.debug(f"Reranking: {len(merged_chunks)} -> {len(final_chunks)} chunks")
        except Exception as e:
            logger.warning(f"Reranking failed: {e}, using similarity ranking")
            merged_chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            final_chunks = merged_chunks[:final_n_results]
    else:
        # Just sort by similarity and take top results
        merged_chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        final_chunks = merged_chunks[:final_n_results]

    return final_chunks


async def retrieve_relevant_chunks_with_confidence(
    query: str,
    category_ids: list[int] | None = None,
    n_results: int = 8,
    include_weaviate: bool | None = None,
    use_enhancements: bool = True,
) -> tuple[list[dict], RetrievalConfidence]:
    """
    Retrieve chunks with confidence assessment for out-of-domain detection.

    Returns:
        Tuple of (chunks, confidence assessment)
    """
    chunks = await retrieve_relevant_chunks(
        query=query,
        category_ids=category_ids,
        n_results=n_results,
        include_weaviate=include_weaviate,
        use_enhancements=use_enhancements,
    )

    # Assess confidence
    confidence = assess_retrieval_confidence(
        chunks,
        similarity_threshold=config.rag.confidence_threshold,
        avg_threshold=config.rag.avg_confidence_threshold,
    )

    # Log all confidence assessments for debugging
    logger.info(
        f"Retrieval confidence for query: '{query[:60]}...' - "
        f"is_confident={confidence.is_confident}, "
        f"score={confidence.confidence_score:.3f}, "
        f"max_sim={confidence.max_similarity:.3f}, "
        f"avg_sim={confidence.avg_similarity:.3f}, "
        f"reason={confidence.reason}"
    )

    return chunks, confidence


async def format_context_with_sources(chunks: list[dict]) -> tuple[str, list[Source]]:
    """
    Format retrieved chunks into context string with source tracking.

    Returns:
        Tuple of (context_string, list of sources)
    """
    if not chunks:
        return "", []

    context_parts = []
    sources = []

    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        text = chunk.get("text", "")

        # Extract source information - handle both local ChromaDB and Weaviate metadata
        title = metadata.get("title", "Unknown")
        source_type = metadata.get("source_type", "document")
        source_url = metadata.get("source_url")

        # Channel name: check various field names (YouTube=channel_name, Weaviate=company_name)
        channel_name = (
            metadata.get("channel_name") or
            metadata.get("channel") or
            metadata.get("company_name")
        )

        # Published date: check various field names (YouTube=upload_date, Weaviate=datetime)
        published_date = (
            metadata.get("published_date") or
            metadata.get("upload_date") or
            metadata.get("datetime") or
            metadata.get("created_at")
        )

        # Check if title is a "Video {id}" pattern and fetch real title from YouTube
        video_match = VIDEO_ID_PATTERN.match(title)
        if video_match:
            video_id = video_match.group(1)
            real_title = await get_youtube_title(video_id)
            if real_title:
                title = real_title
            # Also construct URL from video_id
            if not source_url:
                source_url = f"https://www.youtube.com/watch?v={video_id}"

        # For YouTube sources, construct URL if missing
        video_id = metadata.get("video_id")
        if not source_url and video_id and source_type == "youtube_transcript":
            source_url = f"https://www.youtube.com/watch?v={video_id}"

        # Format published_date if it's in YYYYMMDD format
        if published_date and isinstance(published_date, str):
            if len(published_date) == 8 and published_date.isdigit():
                published_date = f"{published_date[:4]}-{published_date[4:6]}-{published_date[6:8]}"
            # Truncate ISO datetime to just the date
            elif "T" in published_date:
                published_date = published_date.split("T")[0]

        # Format context entry
        context_parts.append(f"[{i}] {text}")

        # Create source object
        sources.append(Source(
            title=title,
            source_type=source_type,
            source_url=source_url,
            channel_name=channel_name,
            published_date=published_date,
            chunk_text=text[:200] + "..." if len(text) > 200 else text,
            similarity=chunk.get("similarity", 0),
        ))

    context = "\n\n".join(context_parts)
    return context, sources


def build_messages(
    conversation_history: list[dict],
    user_message: str,
    context: str,
    system_prompt: str | None = None,
    confidence: RetrievalConfidence | None = None,
) -> list[dict]:
    """
    Build the messages array for the OpenAI API.

    Args:
        conversation_history: Previous messages in the conversation
        user_message: Current user message
        context: Retrieved context from knowledge base
        system_prompt: Optional custom system prompt (uses enhanced prompt if confidence provided)
        confidence: Optional retrieval confidence for dynamic prompt adjustment
    """
    # Use enhanced system prompt if confidence is provided
    if system_prompt is None:
        if confidence is not None and config.rag.confidence_enabled:
            system_prompt = get_enhanced_system_prompt(confidence)
        else:
            system_prompt = config.chat.system_prompt

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # Add conversation history (last 10 message pairs to stay within context limits)
    history_limit = 20  # 10 pairs of user/assistant messages
    recent_history = conversation_history[-history_limit:] if len(conversation_history) > history_limit else conversation_history

    for msg in recent_history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # Add current user message with context
    # CRITICAL: When there's conversation history, tell AI to use it alongside new context
    has_conversation_history = len(recent_history) > 0

    if context:
        if has_conversation_history:
            # With conversation history: Reference previous messages AND new context
            augmented_message = f"""Building on our previous conversation, please answer my new question using both what we've discussed and the following context from the current knowledge base.

CONTEXT:
{context}

MY NEW QUESTION:
{user_message}

Remember to cite sources using [1], [2], etc. based on the context numbers provided. Feel free to reference points from our earlier discussion if they're relevant."""
        else:
            # No conversation history: Just use new context
            augmented_message = f"""Based on the following context from the current knowledge base, please answer my question.

CONTEXT:
{context}

MY QUESTION:
{user_message}

Remember to cite sources using [1], [2], etc. based on the context numbers provided."""
    else:
        augmented_message = f"""{user_message}

Note: I couldn't find relevant information in the current knowledge base for this question. Please let me know if you need more specific information or if I should search differently."""

    messages.append({"role": "user", "content": augmented_message})

    return messages


async def chat(
    conversation_id: int,
    user_message: str,
    category_ids: list[int] | None = None,
) -> ChatResponse:
    """
    Process a chat message with RAG.

    Args:
        conversation_id: The conversation ID
        user_message: The user's message
        category_ids: Optional category filter

    Returns:
        ChatResponse with content and sources
    """
    # Get conversation history
    conversation = await repository.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Store user message
    await repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )

    # Retrieve relevant context with confidence assessment
    chunks, confidence = await retrieve_relevant_chunks_with_confidence(
        query=user_message,
        category_ids=category_ids,
        n_results=config.chat.context_chunks,
    )

    # Format context and track sources
    context, sources = await format_context_with_sources(chunks)

    # CRITICAL: Only include sources if retrieval confidence is high
    # If confidence is low (no relevant information found), clear sources
    # to prevent misleading citations in the response
    if not confidence.is_confident:
        logger.info(
            f"Clearing sources due to low confidence - "
            f"is_confident={confidence.is_confident}, "
            f"confidence_score={confidence.confidence_score:.2f}, "
            f"reason={confidence.reason}"
        )
        sources = []

    # Build messages for OpenAI (with confidence-aware system prompt)
    messages = build_messages(
        conversation_history=conversation.get("messages", []),
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Call OpenAI
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
        )

        assistant_content = response.choices[0].message.content

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        assistant_content = f"I'm sorry, I encountered an error while processing your request: {str(e)}"
        sources = []

    # Store assistant message with sources
    sources_data = [
        {
            "title": s.title,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "channel_name": s.channel_name,
            "published_date": s.published_date,
            "document_id": s.document_id,
            "document_filename": s.document_filename,
        }
        for s in sources
    ] if sources else None

    await repository.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        sources=sources_data,
    )

    # Update conversation title if it's the first message
    if len(conversation.get("messages", [])) == 0:
        # Generate a title from the first message
        title = user_message[:50] + "..." if len(user_message) > 50 else user_message
        await repository.update_conversation(conversation_id, title=title)

    return ChatResponse(content=assistant_content, sources=sources)


async def chat_stream(
    conversation_id: int,
    user_message: str,
    category_ids: list[int] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Process a chat message with RAG and stream the response.

    Yields:
        Chunks of the response as they're generated
    """
    # Get conversation history
    conversation = await repository.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Store user message
    await repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )

    # Retrieve relevant context with confidence assessment
    chunks, confidence = await retrieve_relevant_chunks_with_confidence(
        query=user_message,
        category_ids=category_ids,
        n_results=config.chat.context_chunks,
    )

    # Format context and track sources
    context, sources = await format_context_with_sources(chunks)

    # CRITICAL: Only include sources if retrieval confidence is high
    # If confidence is low (no relevant information found), clear sources
    # to prevent misleading citations in the response
    if not confidence.is_confident:
        logger.info(
            f"Clearing sources due to low confidence - "
            f"is_confident={confidence.is_confident}, "
            f"confidence_score={confidence.confidence_score:.2f}, "
            f"reason={confidence.reason}"
        )
        sources = []

    # Build messages for OpenAI (with confidence-aware system prompt)
    messages = build_messages(
        conversation_history=conversation.get("messages", []),
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Call OpenAI with streaming
    client = get_openai_client()

    full_content = ""

    try:
        stream = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                yield json.dumps({"type": "content", "data": content}) + "\n"

        # VALIDATE CITATIONS: Ensure citations are accurate before sending sources
        if sources:
            corrected_content, validation_result = validate_and_correct_citations(
                response_text=full_content,
                context=context,
                sources_count=len(sources),
                strict_mode=True,  # Remove invalid citations in production
            )

            if validation_result["issues"]:
                logger.warning(
                    f"Citation validation issues: {validation_result['issues']}, "
                    f"Confidence: {validation_result['confidence']:.2%}"
                )

            # If citations were corrected, use corrected version
            if corrected_content != full_content:
                logger.info(
                    f"Citations corrected. Original: {validation_result['citations_found']}, "
                    f"Valid range: {validation_result['valid_range']}"
                )
                full_content = corrected_content

        # Send sources at the end
        sources_data = [
            {
                "title": s.title,
                "source_type": s.source_type,
                "source_url": s.source_url,
                "channel_name": s.channel_name,
                "published_date": s.published_date,
                "document_id": s.document_id,
                "document_filename": s.document_filename,
            }
            for s in sources
        ]
        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        full_content = f"I'm sorry, I encountered an error: {str(e)}"
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"
        sources = []
        sources_data = None

    # Store assistant message
    sources_data = [
        {
            "title": s.title,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "channel_name": s.channel_name,
            "published_date": s.published_date,
            "document_id": s.document_id,
            "document_filename": s.document_filename,
        }
        for s in sources
    ] if sources else None

    await repository.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        sources=sources_data,
    )

    # Update conversation title if first message
    if len(conversation.get("messages", [])) == 0:
        title = user_message[:50] + "..." if len(user_message) > 50 else user_message
        await repository.update_conversation(conversation_id, title=title)


# ============================================================================
# MAG-LIB Chat Functions (using pgvector)
# ============================================================================


async def chat_maglib(
    conversation_id: int,
    user_message: str,
) -> ChatResponse:
    """
    Process a chat message using MAG-LIB pgvector collection.

    Uses the full RAG pipeline from pgvector_rag service with:
    - HyDE (Hypothetical Document Embeddings)
    - Query decomposition for multi-hop queries
    - Cross-encoder reranking
    - Hybrid search (vector + keyword)

    Args:
        conversation_id: The conversation ID
        user_message: The user's message

    Returns:
        ChatResponse with content and sources
    """
    from app.services import pgvector_rag
    from app.services.pgvector_rag import PgVectorRAGConfig

    # Get conversation history
    conversation = await repository.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Store user message
    await repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )

    # Configure RAG
    rag_config = PgVectorRAGConfig(
        use_hyde=config.rag.hyde_enabled,
        use_reranking=config.rag.reranking_enabled,
        use_decomposition=config.rag.decomposition_enabled,
        use_confidence=config.rag.confidence_enabled,
        use_hybrid_search=True,
        n_results=config.chat.context_chunks,
    )

    # Retrieve relevant chunks from pgvector
    chunks, retrieval_info = await pgvector_rag.enhanced_retrieve(
        query=user_message,
        rag_config=rag_config,
    )

    # Format context and track sources (adapted for pgvector format)
    context_parts = []
    sources = []

    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        text = chunk.get("text", "")

        title = metadata.get("document_title") or metadata.get("title") or "MAG-LIB Document"
        context_parts.append(f"[{i}] {text}")

        document_id = metadata.get("document_id")
        document_filename = metadata.get("document_filename")
        # Remove .pdf extension for cover image lookup
        if document_filename and document_filename.lower().endswith('.pdf'):
            document_filename = document_filename[:-4]
        sources.append(Source(
            title=title,
            source_type="magick_pdf",
            source_url=None,
            channel_name=metadata.get("document_author"),
            published_date=None,
            chunk_text=text[:200] + "..." if len(text) > 200 else text,
            similarity=chunk.get("similarity", 0),
            document_id=str(document_id) if document_id else None,
            document_filename=document_filename,
        ))

    context = "\n\n".join(context_parts)

    # Get confidence info
    confidence = None
    if retrieval_info.get("confidence"):
        conf = retrieval_info["confidence"]
        confidence = RetrievalConfidence(
            is_confident=conf["is_confident"],
            confidence_score=conf["score"],
            max_similarity=conf["max_similarity"],
            avg_similarity=conf["avg_similarity"],
            reason=conf["reason"],
        )

    # Build messages for OpenAI
    messages = build_messages(
        conversation_history=conversation.get("messages", []),
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Customize system prompt for MAGICK collection
    if messages and messages[0]["role"] == "system":
        messages[0]["content"] = messages[0]["content"].replace(
            "health and wellness",
            "occult, magick, esoteric knowledge, and spiritual traditions"
        )

    # Call OpenAI
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
        )

        assistant_content = response.choices[0].message.content

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        assistant_content = f"I'm sorry, I encountered an error while processing your request: {str(e)}"
        sources = []

    # Store assistant message with sources
    sources_data = [
        {
            "title": s.title,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "channel_name": s.channel_name,
            "published_date": s.published_date,
            "document_id": s.document_id,
            "document_filename": s.document_filename,
        }
        for s in sources
    ] if sources else None

    await repository.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        sources=sources_data,
    )

    # Update conversation title if it's the first message
    if len(conversation.get("messages", [])) == 0:
        title = user_message[:50] + "..." if len(user_message) > 50 else user_message
        await repository.update_conversation(conversation_id, title=title)

    return ChatResponse(content=assistant_content, sources=sources)


def _remove_invalid_citations(response_text: str, valid_source_count: int) -> str:
    """
    Remove or replace invalid citations in the response text.

    If the response contains citations like [6] but only 5 sources exist,
    remove those invalid citations to prevent source mismatch.

    Args:
        response_text: The LLM response text
        valid_source_count: Number of valid sources (max citation number)

    Returns:
        Response text with invalid citations removed
    """
    import re

    if valid_source_count == 0:
        # Remove all citations if no sources
        return re.sub(r'\s*\[\d+\]\s*', '', response_text)

    # Find all citations
    citation_pattern = r'\[(\d+)\]'
    matches = list(re.finditer(citation_pattern, response_text))

    # Process matches in reverse order to preserve positions
    cleaned_text = response_text
    for match in reversed(matches):
        citation_num = int(match.group(1))
        if citation_num > valid_source_count:
            # Remove invalid citation (including surrounding spaces)
            start, end = match.span()
            # Try to remove surrounding spaces for cleaner output
            if start > 0 and cleaned_text[start-1] == ' ':
                start -= 1
            if end < len(cleaned_text) and cleaned_text[end] == ' ':
                end += 1
            cleaned_text = cleaned_text[:start] + cleaned_text[end:]

    return cleaned_text


def _extract_cited_sources(response_text: str, all_sources: list[Source]) -> tuple[str, list[Source]]:
    """
    Extract only the sources that are actually cited in the response.

    With SOURCE-AWARE NUMBERING:
    - Context chunks are numbered by SOURCE ([1], [2], etc.), not by chunk position
    - All chunks from the same source get the same number
    - [1] always refers to the first unique source, [2] to the second, etc.
    - This ensures AI citations perfectly match the sources list in the frontend

    This function:
    1. Deduplicates sources by document title (preserving order)
    2. Parses the response text to find which citations are actually used (e.g., [1], [3], [7])
    3. Removes invalid citations from response text
    4. Returns ONLY the sources that are referenced in the response

    Args:
        response_text: The LLM response text (parsed for citations)
        all_sources: List of all retrieved sources (possibly with duplicates for multi-chunk sources)

    Returns:
        Tuple of (cleaned_response_text, list of sources that are actually cited)
    """
    import re

    if not all_sources:
        return response_text, []

    # Step 1: Deduplicate sources by document title (case-insensitive)
    # Preserves order of first appearance
    seen_titles = {}
    unique_sources = []

    for source in all_sources:
        # Normalize title for deduplication
        title_key = source.title.lower().strip()

        # Keep only the first occurrence of each document
        # (later chunks from same document won't add new entries)
        if title_key not in seen_titles:
            seen_titles[title_key] = True
            unique_sources.append(source)

    # Step 2: Extract citation numbers from response text
    # Pattern: [1], [2], [123], etc. (standalone citations)
    citation_pattern = r'\[(\d+)\]'
    citations = re.findall(citation_pattern, response_text)

    # Convert to integers and get unique citation numbers in order of appearance
    cited_indices = []
    seen_citations = set()
    for citation_str in citations:
        citation_num = int(citation_str)
        if citation_num not in seen_citations:
            cited_indices.append(citation_num)
            seen_citations.add(citation_num)

    # Step 3: Return only the sources that are cited
    # Citation numbers are 1-based, array indices are 0-based
    cited_sources = []
    valid_citations = []
    for citation_num in cited_indices:
        source_index = citation_num - 1  # Convert 1-based to 0-based
        if 0 <= source_index < len(unique_sources):
            cited_sources.append(unique_sources[source_index])
            valid_citations.append(citation_num)

    # CRITICAL FIX: Remove invalid citations from response text
    # If AI cited [6] but only 5 sources exist, clean that up
    invalid_citations = [c for c in cited_indices if c > len(unique_sources) or c <= 0]
    if invalid_citations:
        logger.warning(f"[SOURCES] Found {len(invalid_citations)} invalid citations in response: {invalid_citations}. Max valid citation: {len(unique_sources)}")
        cleaned_text = _remove_invalid_citations(response_text, len(unique_sources))
    else:
        cleaned_text = response_text

    # Fallback: if no valid citations found, return all unique sources
    # This prevents hallucinated sources by showing what was actually retrieved
    if not cited_sources and unique_sources:
        logger.warning(f"[SOURCES] No valid citations found in response (citations: {cited_indices}, sources: {len(unique_sources)}). Returning all retrieved sources as fallback.")
        return cleaned_text, unique_sources

    logger.info(f"[SOURCES] Extracted {len(cited_sources)} cited sources from response with valid citations: {valid_citations}")
    return cleaned_text, cited_sources


async def telegram_chat_stream_maglib(
    conversation_id: int,
    user_message: str,
    conversation_history: list[dict] | None = None,
    document_ids: list[int] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Process a chat message using MAG-LIB pgvector for Telegram Mini App.

    This uses the pgvector database with 534k embedded chunks from 6,377 MAGICK PDFs.

    Args:
        conversation_id: The Telegram conversation ID
        user_message: The user's message
        conversation_history: Pre-fetched conversation history (from tg_messages table)
        document_ids: Optional list of document IDs to filter search results

    Yields:
        Chunks of the response as they're generated
    """
    from app.services import pgvector_rag
    from app.services.pgvector_rag import PgVectorRAGConfig

    logger.info(f"[STREAM_MAGLIB] Starting chat stream for conversation_id={conversation_id}, document_ids={document_ids}")

    # Configure RAG for pgvector
    rag_config = PgVectorRAGConfig(
        use_hyde=config.rag.hyde_enabled,
        use_reranking=config.rag.reranking_enabled,
        use_decomposition=config.rag.decomposition_enabled,
        use_confidence=config.rag.confidence_enabled,
        use_hybrid_search=True,
        n_results=config.chat.context_chunks,
    )

    # Retrieve relevant chunks from pgvector (MAG-LIB collection)
    # If document_ids provided, filter to only those documents
    logger.info(f"[STREAM_MAGLIB] Calling enhanced_retrieve with query length={len(user_message)}")
    try:
        chunks, retrieval_info = await pgvector_rag.enhanced_retrieve(
            query=user_message,
            rag_config=rag_config,
            document_ids=document_ids if document_ids else None,
        )
        logger.info(f"[STREAM_MAGLIB] enhanced_retrieve returned {len(chunks)} chunks")
    except Exception as e:
        logger.error(f"[STREAM_MAGLIB] enhanced_retrieve failed: {e}", exc_info=True)
        yield json.dumps({"type": "error", "data": f"Retrieval failed: {str(e)}"}) + "\n"
        return

    # Format context with SOURCE-AWARE numbering (not chunk numbering)
    # This ensures citations [1], [2] etc. match the sources list exactly
    from collections import OrderedDict

    source_map = OrderedDict()  # Maps (title, doc_id) -> source_number
    unique_sources_ordered = []  # Ordered list of unique sources
    context_parts = []
    all_sources = []

    # If no chunks found for selected documents, proceed with empty context
    # (Do NOT use metadata fallback - it breaks source-aware citation numbering)
    if document_ids and len(chunks) == 0:
        logger.warning(f"No relevant chunks found in selected documents {document_ids}. AI will respond with general knowledge.")

    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        text = chunk.get("text", "")

        title = metadata.get("document_title") or metadata.get("title") or "MAG-LIB Document"
        document_id = metadata.get("document_id")
        document_filename = metadata.get("document_filename")

        # Create a unique key for this source (title + ID)
        # Use normalized title for matching
        source_key = (title.lower().strip(), document_id)

        # If this is the first chunk from this source, assign it a source number
        if source_key not in source_map:
            source_number = len(source_map) + 1
            source_map[source_key] = source_number

            # Remove .pdf extension for cover image lookup
            if document_filename and document_filename.lower().endswith('.pdf'):
                document_filename = document_filename[:-4]

            # Create the source object
            source = Source(
                title=title,
                source_type="magick_pdf",
                source_url=None,
                channel_name=metadata.get("document_author"),
                published_date=None,
                chunk_text=text[:200] + "..." if len(text) > 200 else text,
                similarity=chunk.get("similarity", 0),
                document_id=str(document_id) if document_id else None,
                document_filename=document_filename,
            )
            unique_sources_ordered.append(source)

        # Add source to all_sources in order (for logging)
        all_sources.append(unique_sources_ordered[source_map[source_key] - 1])

        # Use the SOURCE number in context (so [1] always means first unique source)
        # This aligns with how citations will be displayed in the frontend
        source_number = source_map[source_key]
        context_parts.append(f"[{source_number}] {text}")

    context = "\n\n".join(context_parts)

    # DEBUG: Log actual chunks being sent to OpenAI for content validation
    logger.info(f"[CHUNK_CONTENT_DEBUG] Sending {len(context_parts)} chunks to OpenAI:")
    for i, part in enumerate(context_parts, 1):
        chunk_preview = part[:300] + "..." if len(part) > 300 else part
        logger.info(f"[CHUNK_CONTENT_DEBUG] Chunk {i}: {chunk_preview}")

    # Get confidence info
    confidence = None
    if retrieval_info.get("confidence"):
        conf = retrieval_info["confidence"]
        confidence = RetrievalConfidence(
            is_confident=conf["is_confident"],
            confidence_score=conf["score"],
            max_similarity=conf["max_similarity"],
            avg_similarity=conf["avg_similarity"],
            reason=conf["reason"],
        )

    # Build messages for OpenAI
    messages = build_messages(
        conversation_history=conversation_history or [],
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Customize system prompt for MAGICK collection
    if messages and messages[0]["role"] == "system":
        messages[0]["content"] = messages[0]["content"].replace(
            "health and wellness",
            "occult, magick, esoteric knowledge, and spiritual traditions"
        )

    # Call OpenAI with streaming
    client = get_openai_client()

    full_content = ""

    logger.info(f"[STREAM_MAGLIB] Prepared {len(messages)} messages for OpenAI, context size={len(context)}")
    logger.info(f"[STREAM_MAGLIB] Starting OpenAI streaming call with model={config.chat.model}")

    try:
        stream = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
            stream=True,
        )

        logger.info(f"[STREAM_MAGLIB] OpenAI stream object created, starting to read chunks")
        chunk_count = 0
        total_loop_iterations = 0
        try:
            async for chunk in stream:
                total_loop_iterations += 1
                logger.debug(f"[STREAM_MAGLIB] Loop iteration #{total_loop_iterations}, chunk type={type(chunk)}")
                try:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        logger.debug(f"[STREAM_MAGLIB] delta={delta}, has content={hasattr(delta, 'content')}, content={getattr(delta, 'content', None)}")
                        if delta.content:
                            content = delta.content
                            full_content += content
                            chunk_count += 1
                            logger.debug(f"[STREAM_MAGLIB] Yielding content chunk #{chunk_count}, length={len(content)}")
                            yield json.dumps({"type": "content", "data": content}) + "\n"
                except Exception as e:
                    logger.error(f"[STREAM_MAGLIB] Error processing chunk in loop iteration #{total_loop_iterations}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[STREAM_MAGLIB] Error in OpenAI streaming loop: {e}", exc_info=True)

        logger.info(f"[STREAM_MAGLIB] Finished reading OpenAI chunks, total_loop_iterations={total_loop_iterations}, chunks_yielded={chunk_count}, full_content_length={len(full_content)}")

        # Extract and deduplicate sources from all retrieved chunks
        # CRITICAL FIX: _extract_cited_sources now returns (cleaned_text, cited_sources) tuple
        full_content, cited_sources = _extract_cited_sources(full_content, all_sources)

        # CRITICAL: Only include sources if retrieval confidence is high
        # If confidence is low (no relevant information found), clear sources
        # to prevent misleading citations in the response
        if confidence and not confidence.is_confident:
            logger.info(
                f"[STREAM_MAGLIB] Clearing sources due to low confidence - "
                f"is_confident={confidence.is_confident}, "
                f"confidence_score={confidence.confidence_score:.2f}, "
                f"reason={confidence.reason}"
            )
            cited_sources = []

        # Log sources for debugging with SOURCE-AWARE NUMBERING
        logger.info(f"[STREAM_MAGLIB] SOURCE-AWARE NUMBERING: {len(all_sources)} chunks from {len(cited_sources)} unique documents")
        for idx, s in enumerate(cited_sources, 1):
            logger.info(f"[STREAM_MAGLIB]   [{idx}] {s.title} (doc_id: {s.document_id})")
        logger.info(f"[STREAM_MAGLIB] Citations in AI response should be [1], [2], etc. matching the sources above")

        # Send the deduplicated sources
        sources_data = [
            {
                "title": s.title,
                "source_type": s.source_type,
                "source_url": s.source_url,
                "channel_name": s.channel_name,
                "published_date": s.published_date,
                "document_id": s.document_id,
                "document_filename": s.document_filename,
            }
            for s in cited_sources
        ]
        logger.info(f"[STREAM_MAGLIB] Sending {len(cited_sources)} sources")
        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        logger.info(f"[STREAM_MAGLIB] Sending done message")
        yield json.dumps({"type": "done"}) + "\n"
        logger.info(f"[STREAM_MAGLIB] Stream complete")

    except Exception as e:
        logger.error(f"[STREAM_MAGLIB] OpenAI API error: {e}", exc_info=True)
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"


async def telegram_chat_stream_bibliothek(
    conversation_id: int,
    user_message: str,
    conversation_history: list[dict] | None = None,
    document_ids: list[int] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Process a chat message using BIBLIOTHEK pgvector for Telegram Mini App.

    This uses the bibliothek_knowledge database with 1.8M chunks from 2,701 BIBLIOTHEK PDFs.

    Args:
        conversation_id: The Telegram conversation ID
        user_message: The user's message
        conversation_history: Pre-fetched conversation history (from tg_messages table)
        document_ids: Optional list of document IDs to filter search results

    Yields:
        Chunks of the response as they're generated
    """
    from app.services import pgvector_service as pgvector
    from app.services.rag_enhancements import (
        get_enhanced_system_prompt,
        assess_retrieval_confidence,
    )

    # Retrieve relevant chunks from BIBLIOTHEK database
    # Note: use_hybrid=False for BIBLIOTHEK due to large collection (1.8M chunks)
    results = await pgvector.search_bibliothek(
        query=user_message,
        match_count=config.chat.context_chunks,
        use_hybrid=False,  # Vector-only search for performance
        document_ids=document_ids if document_ids else None,
    )

    # FALLBACK: If document_ids provided but no results found, fetch document metadata
    if document_ids and len(results) == 0:
        logger.info(f"No chunks found for selected BIBLIOTHEK documents {document_ids}. Fetching document metadata as fallback...")

        try:
            # Query BIBLIOTHEK documents table for metadata using asyncpg
            import asyncpg
            # BIBLIOTHEK uses port 5433
            conn = await asyncpg.connect(
                host="localhost",
                port=5433,
                user="docling",
                password="docling",
                database="bibliothek_knowledge"
            )

            try:
                # Build parameterized query for document metadata
                # asyncpg uses $1, $2 etc. for placeholders
                placeholders = ','.join(f'${i}' for i in range(1, len(document_ids) + 1))
                rows = await conn.fetch(
                    f"SELECT id, title, filename FROM documents WHERE id = ANY($1::integer[]) LIMIT {len(document_ids)}",
                    document_ids
                )

                # Build results-like objects from metadata
                class MetadataResult:
                    def __init__(self, doc_id, title, filename):
                        self.document_id = doc_id
                        self.document_title = title
                        self.document_filename = filename
                        self.document_author = None
                        self.content = f"Document: {title}"
                        self.similarity = 1.0

                for row in rows:
                    results.append(MetadataResult(
                        doc_id=row["id"],
                        title=row["title"] or f"Document {row['id']}",
                        filename=row["filename"]
                    ))

                if results:
                    logger.info(f"Retrieved metadata for {len(results)} selected BIBLIOTHEK documents")
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Failed to fetch BIBLIOTHEK document metadata: {e}")

    # Format context with SOURCE-AWARE numbering (not chunk numbering)
    # This ensures citations [1], [2] etc. match the sources list exactly
    from collections import OrderedDict

    source_map = OrderedDict()  # Maps (title, doc_id) -> source_number
    unique_sources_ordered = []  # Ordered list of unique sources
    context_parts = []
    all_sources = []

    for result in results:
        title = result.document_title or "BIBLIOTHEK Document"
        document_id = result.document_id

        # Create a unique key for this source (title + ID)
        source_key = (title.lower().strip(), document_id)

        # If this is the first chunk from this source, assign it a source number
        if source_key not in source_map:
            source_number = len(source_map) + 1
            source_map[source_key] = source_number

            document_filename = result.document_filename
            if document_filename and document_filename.lower().endswith('.pdf'):
                document_filename = document_filename[:-4]

            # Create the source object
            source = Source(
                title=title,
                source_type="bibliothek_pdf",
                source_url=None,
                channel_name=result.document_author,
                published_date=None,
                chunk_text=result.content[:200] + "..." if len(result.content) > 200 else result.content,
                similarity=result.similarity,
                document_id=str(document_id) if document_id else None,
                document_filename=document_filename,
            )
            unique_sources_ordered.append(source)

        # Add source to all_sources in order (for logging)
        all_sources.append(unique_sources_ordered[source_map[source_key] - 1])

        # Use the SOURCE number in context (so [1] always means first unique source)
        source_number = source_map[source_key]
        context_parts.append(f"[{source_number}] {result.content}")

    context = "\n\n".join(context_parts)

    # Assess retrieval confidence
    confidence = None
    if config.rag.confidence_enabled and results:
        # assess_retrieval_confidence returns a RetrievalConfidence object directly
        confidence = assess_retrieval_confidence(
            chunks=[{"text": r.content, "similarity": r.similarity} for r in results],
        )

    # Build messages for OpenAI
    messages = build_messages(
        conversation_history=conversation_history or [],
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Stream the response
    try:
        client = AsyncOpenAI(api_key=config.chat.openai_api_key)
        full_response = ""

        async for chunk in await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            temperature=config.chat.temperature,
            max_tokens=config.chat.max_tokens,
            stream=True,
        ):
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield json.dumps({"type": "content", "data": content}) + "\n"

        # Extract only cited sources and deduplicate
        # CRITICAL FIX: _extract_cited_sources now returns (cleaned_text, cited_sources) tuple
        full_response, cited_sources = _extract_cited_sources(full_response, all_sources)

        # CRITICAL: Only include sources if retrieval confidence is high
        # If confidence is low (no relevant information found), clear sources
        # to prevent misleading citations in the response
        if confidence and not confidence.is_confident:
            logger.info(
                f"[STREAM_BIBLIOTHEK] Clearing sources due to low confidence - "
                f"is_confident={confidence.is_confident}, "
                f"confidence_score={confidence.confidence_score:.2f}, "
                f"reason={confidence.reason}"
            )
            cited_sources = []

        # Send only the cited, deduplicated sources
        sources_data = [
            {
                "title": s.title,
                "source_type": s.source_type,
                "source_url": s.source_url,
                "channel_name": s.channel_name,
                "published_date": s.published_date,
                "document_id": s.document_id,
                "document_filename": s.document_filename,
            }
            for s in cited_sources
        ]
        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    except Exception as e:
        logger.error(f"OpenAI API error in BIBLIOTHEK chat: {e}")
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"


async def telegram_chat_stream(
    conversation_id: int,
    user_message: str,
    category_ids: list[int] | None = None,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Process a chat message with RAG for Telegram Mini App and stream the response.

    This is a simplified version that doesn't manage conversation state -
    the caller (telegram.py) handles storing messages in tg_messages table.

    Args:
        conversation_id: The Telegram conversation ID
        user_message: The user's message
        category_ids: Optional category IDs to filter by
        conversation_history: Pre-fetched conversation history (from tg_messages table)

    Yields:
        Chunks of the response as they're generated
    """
    # Retrieve relevant context with confidence assessment
    chunks, confidence = await retrieve_relevant_chunks_with_confidence(
        query=user_message,
        category_ids=category_ids,
        n_results=config.chat.context_chunks,
    )

    # Format context and track sources
    context, sources = await format_context_with_sources(chunks)

    # Build messages for OpenAI (with confidence-aware system prompt)
    messages = build_messages(
        conversation_history=conversation_history or [],
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Call OpenAI with streaming
    client = get_openai_client()

    full_content = ""

    try:
        stream = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                yield json.dumps({"type": "content", "data": content}) + "\n"

        # VALIDATE CITATIONS: Ensure citations are accurate before sending sources
        if sources:
            corrected_content, validation_result = validate_and_correct_citations(
                response_text=full_content,
                context=context,
                sources_count=len(sources),
                strict_mode=True,  # Remove invalid citations in production
            )

            if validation_result["issues"]:
                logger.warning(
                    f"Citation validation issues: {validation_result['issues']}, "
                    f"Confidence: {validation_result['confidence']:.2%}"
                )

            # If citations were corrected, use corrected version
            if corrected_content != full_content:
                logger.info(
                    f"Citations corrected. Original: {validation_result['citations_found']}, "
                    f"Valid range: {validation_result['valid_range']}"
                )
                full_content = corrected_content

        # Send sources at the end
        sources_data = [
            {
                "title": s.title,
                "source_type": s.source_type,
                "source_url": s.source_url,
                "channel_name": s.channel_name,
                "published_date": s.published_date,
                "document_id": s.document_id,
                "document_filename": s.document_filename,
            }
            for s in sources
        ]
        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"


async def chat_stream_maglib(
    conversation_id: int,
    user_message: str,
) -> AsyncGenerator[str, None]:
    """
    Process a chat message using MAG-LIB pgvector and stream the response.

    Yields:
        Chunks of the response as they're generated
    """
    from app.services import pgvector_rag
    from app.services.pgvector_rag import PgVectorRAGConfig

    # Get conversation history
    conversation = await repository.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Store user message
    await repository.create_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
    )

    # Configure RAG
    rag_config = PgVectorRAGConfig(
        use_hyde=config.rag.hyde_enabled,
        use_reranking=config.rag.reranking_enabled,
        use_decomposition=config.rag.decomposition_enabled,
        use_confidence=config.rag.confidence_enabled,
        use_hybrid_search=True,
        n_results=config.chat.context_chunks,
    )

    # Retrieve relevant chunks from pgvector
    chunks, retrieval_info = await pgvector_rag.enhanced_retrieve(
        query=user_message,
        rag_config=rag_config,
    )

    # Format context and track sources (adapted for pgvector format)
    context_parts = []
    sources = []

    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata", {})
        text = chunk.get("text", "")

        title = metadata.get("document_title") or metadata.get("title") or "MAG-LIB Document"
        context_parts.append(f"[{i}] {text}")

        document_id = metadata.get("document_id")
        document_filename = metadata.get("document_filename")
        # Remove .pdf extension for cover image lookup
        if document_filename and document_filename.lower().endswith('.pdf'):
            document_filename = document_filename[:-4]
        sources.append(Source(
            title=title,
            source_type="magick_pdf",
            source_url=None,
            channel_name=metadata.get("document_author"),
            published_date=None,
            chunk_text=text[:200] + "..." if len(text) > 200 else text,
            similarity=chunk.get("similarity", 0),
            document_id=str(document_id) if document_id else None,
            document_filename=document_filename,
        ))

    context = "\n\n".join(context_parts)

    # Get confidence info
    confidence = None
    if retrieval_info.get("confidence"):
        conf = retrieval_info["confidence"]
        confidence = RetrievalConfidence(
            is_confident=conf["is_confident"],
            confidence_score=conf["score"],
            max_similarity=conf["max_similarity"],
            avg_similarity=conf["avg_similarity"],
            reason=conf["reason"],
        )

    # Build messages for OpenAI
    messages = build_messages(
        conversation_history=conversation.get("messages", []),
        user_message=user_message,
        context=context,
        confidence=confidence,
    )

    # Customize system prompt for MAGICK collection
    if messages and messages[0]["role"] == "system":
        messages[0]["content"] = messages[0]["content"].replace(
            "health and wellness",
            "occult, magick, esoteric knowledge, and spiritual traditions"
        )

    # Call OpenAI with streaming
    client = get_openai_client()

    full_content = ""

    try:
        stream = await client.chat.completions.create(
            model=config.chat.model,
            messages=messages,
            max_tokens=config.chat.max_tokens,
            temperature=config.chat.temperature,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                yield json.dumps({"type": "content", "data": content}) + "\n"

        # VALIDATE CITATIONS: Ensure citations are accurate before sending sources
        if sources:
            corrected_content, validation_result = validate_and_correct_citations(
                response_text=full_content,
                context=context,
                sources_count=len(sources),
                strict_mode=True,  # Remove invalid citations in production
            )

            if validation_result["issues"]:
                logger.warning(
                    f"Citation validation issues: {validation_result['issues']}, "
                    f"Confidence: {validation_result['confidence']:.2%}"
                )

            # If citations were corrected, use corrected version
            if corrected_content != full_content:
                logger.info(
                    f"Citations corrected. Original: {validation_result['citations_found']}, "
                    f"Valid range: {validation_result['valid_range']}"
                )
                full_content = corrected_content

        # Send sources at the end
        sources_data = [
            {
                "title": s.title,
                "source_type": s.source_type,
                "source_url": s.source_url,
                "channel_name": s.channel_name,
                "published_date": s.published_date,
                "document_id": s.document_id,
                "document_filename": s.document_filename,
            }
            for s in sources
        ]
        yield json.dumps({"type": "sources", "data": sources_data}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        full_content = f"I'm sorry, I encountered an error: {str(e)}"
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"
        sources = []

    # Store assistant message
    sources_data = [
        {
            "title": s.title,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "channel_name": s.channel_name,
            "published_date": s.published_date,
            "document_id": s.document_id,
            "document_filename": s.document_filename,
        }
        for s in sources
    ] if sources else None

    await repository.create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        sources=sources_data,
    )

    # Update conversation title if first message
    if len(conversation.get("messages", [])) == 0:
        title = user_message[:50] + "..." if len(user_message) > 50 else user_message
        await repository.update_conversation(conversation_id, title=title)
