"""
PostgreSQL + pgvector Service for MAGICK PDFs Vector Database

This module provides:
- Connection pool management
- Document and chunk storage
- Vector similarity search
- Hybrid search (vector + keyword)
- OpenAI embedding integration

This is a NEW service that doesn't modify existing ChromaDB functionality.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import UUID

import os

import asyncpg

from app.config import config
from app.services.ssh_tunnel import (
    close_all_tunnels,
    get_bibliothek_tunnel,
    get_magick_tunnel,
    init_tunnels,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class DocumentRecord:
    """A document stored in the database."""
    id: UUID
    filename: str
    title: str | None
    author: str | None
    page_count: int | None
    file_size_bytes: int | None
    file_hash: str | None
    source_path: str | None
    processed_at: datetime | None
    created_at: datetime
    metadata: dict[str, Any]


@dataclass
class ChunkRecord:
    """A chunk stored in the database."""
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    chunk_type: str
    token_count: int | None
    metadata: dict[str, Any]


@dataclass
class SearchResult:
    """A search result with similarity score."""
    chunk_id: UUID
    document_id: UUID
    content: str
    similarity: float
    page_number: int | None
    document_title: str | None
    document_author: str | None
    document_filename: str | None = None  # For cover image lookup
    metadata: dict[str, Any] | None = None


@dataclass
class HybridSearchResult(SearchResult):
    """A hybrid search result with both vector and keyword scores."""
    vector_score: float = 0.0
    keyword_score: float = 0.0


# ============================================================================
# CONNECTION POOL MANAGEMENT
# ============================================================================


_pool: asyncpg.Pool | None = None
_bibliothek_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool for MAG-LIB (magick_knowledge database)."""
    global _pool

    if _pool is None:
        cfg = config.pgvector

        # Check if SSH tunneling is enabled
        use_ssh_tunnel = os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true"

        if use_ssh_tunnel:
            logger.info("SSH tunnel enabled for magick_knowledge database")
            tunnel = get_magick_tunnel()
            if not tunnel.is_active():
                tunnel.start()
            host, port = tunnel.local_bind_host, tunnel.local_bind_port
            logger.info(f"Using SSH tunnel: {host}:{port} -> {cfg.host}:{cfg.port}")
        else:
            host, port = cfg.host, cfg.port
            logger.info(f"Direct connection to {host}:{port}")

        logger.info(f"Creating pgvector connection pool to {host}:{port}/{cfg.database}")

        _pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=cfg.database,
            user=cfg.user,
            password=cfg.password,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("pgvector connection pool created successfully")

    return _pool


async def get_bibliothek_pool() -> asyncpg.Pool:
    """Get or create the connection pool for BIBLIOTHEK (bibliothek_knowledge database)."""
    global _bibliothek_pool

    if _bibliothek_pool is None:
        # Check if SSH tunneling is enabled
        use_ssh_tunnel = os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true"

        if use_ssh_tunnel:
            logger.info("SSH tunnel enabled for bibliothek_knowledge database")
            tunnel = get_bibliothek_tunnel()
            if not tunnel.is_active():
                tunnel.start()
            host = tunnel.local_bind_host
            port = tunnel.local_bind_port
            logger.info(f"Using SSH tunnel: {host}:{port} -> 127.0.0.1:5432")
        else:
            host = os.getenv("BIBLIOTHEK_HOST", "localhost")
            port = int(os.getenv("BIBLIOTHEK_PORT", "5432"))

        database = os.getenv("BIBLIOTHEK_DATABASE", "bibliothek_knowledge")
        user = os.getenv("BIBLIOTHEK_USER", "docling")
        password = os.getenv("BIBLIOTHEK_PASSWORD", "docling_secure_pwd_2024")

        logger.info(f"Creating BIBLIOTHEK connection pool to {host}:{port}/{database}")

        _bibliothek_pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("BIBLIOTHEK connection pool created successfully")

    return _bibliothek_pool


async def close_pool():
    """Close the connection pool."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("pgvector connection pool closed")

    # Close SSH tunnel if enabled
    if os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true":
        close_all_tunnels()


async def close_bibliothek_pool():
    """Close the BIBLIOTHEK connection pool."""
    global _bibliothek_pool

    if _bibliothek_pool is not None:
        await _bibliothek_pool.close()
        _bibliothek_pool = None
        logger.info("BIBLIOTHEK connection pool closed")

    # Close SSH tunnel if enabled
    if os.getenv("SSH_TUNNEL_ENABLED", "false").lower() == "true":
        close_all_tunnels()


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def get_bibliothek_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the BIBLIOTHEK pool."""
    pool = await get_bibliothek_pool()
    async with pool.acquire() as conn:
        yield conn


# ============================================================================
# EMBEDDING GENERATION (Local BGE model for MAGICK PDFs)
# ============================================================================


_embedding_model = None


def get_embedding_model():
    """Get or create the local embedding model (BGE)."""
    global _embedding_model

    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = config.pgvector.embedding_model
        logger.info(f"Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded (dim={_embedding_model.get_sentence_embedding_dimension()})")

    return _embedding_model


async def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding for a single text using local BGE model.

    Args:
        text: The text to embed

    Returns:
        List of floats representing the embedding vector (1024 dims for BGE-large)
    """
    def _embed():
        model = get_embedding_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    return await asyncio.to_thread(_embed)


async def generate_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in batches using local BGE model.

    Args:
        texts: List of texts to embed
        batch_size: Texts per batch (lower for memory efficiency)

    Returns:
        List of embedding vectors
    """
    def _embed_batch():
        model = get_embedding_model()
        # Filter empty texts
        non_empty = [t if t.strip() else " " for t in texts]
        embeddings = model.encode(non_empty, convert_to_numpy=True, batch_size=batch_size)
        return embeddings.tolist()

    return await asyncio.to_thread(_embed_batch)


# ============================================================================
# DOCUMENT OPERATIONS
# ============================================================================


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


async def document_exists(file_hash: str) -> bool:
    """Check if a document with the given hash already exists."""
    async with get_connection() as conn:
        result = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM documents WHERE file_hash = $1)",
            file_hash
        )
        return result


async def get_document_by_hash(file_hash: str) -> DocumentRecord | None:
    """Get a document by its file hash."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM documents WHERE file_hash = $1",
            file_hash
        )

        if row:
            return DocumentRecord(
                id=row["id"],
                filename=row["filename"],
                title=row["title"],
                author=row["author"],
                page_count=row["page_count"],
                file_size_bytes=row["file_size_bytes"],
                file_hash=row["file_hash"],
                source_path=row["source_path"],
                processed_at=row["processed_at"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

        return None


async def insert_document(
    filename: str,
    file_hash: str,
    title: str | None = None,
    author: str | None = None,
    page_count: int | None = None,
    file_size_bytes: int | None = None,
    source_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    """
    Insert a new document into the database.

    Args:
        filename: Original filename
        file_hash: SHA256 hash of the file
        title: Document title (extracted or from filename)
        author: Document author
        page_count: Number of pages
        file_size_bytes: File size in bytes
        source_path: Original file path
        metadata: Additional metadata as JSON

    Returns:
        UUID of the inserted document
    """
    async with get_connection() as conn:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (
                filename, file_hash, title, author, page_count,
                file_size_bytes, source_path, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            filename,
            file_hash,
            title,
            author,
            page_count,
            file_size_bytes,
            source_path,
            json.dumps(metadata or {}),
        )

        logger.debug(f"Inserted document: {filename} ({doc_id})")
        return doc_id


async def get_document_count() -> int:
    """Get the total number of documents in the database."""
    async with get_connection() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM documents")


async def get_chunk_count() -> int:
    """Get the total number of chunks in the database."""
    async with get_connection() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM chunks")


async def get_embedded_chunk_count() -> int:
    """Get the number of chunks with embeddings."""
    async with get_connection() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
        )


# ============================================================================
# CHUNK OPERATIONS
# ============================================================================


async def insert_chunk(
    document_id: UUID,
    content: str,
    chunk_index: int,
    embedding: list[float] | None = None,
    page_number: int | None = None,
    section_title: str | None = None,
    chunk_type: str = "text",
    token_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> UUID:
    """
    Insert a chunk into the database.

    Args:
        document_id: ID of the parent document
        content: Chunk text content
        chunk_index: Index of the chunk within the document
        embedding: Optional pre-computed embedding vector
        page_number: Page number if known
        section_title: Section title if applicable
        chunk_type: Type of chunk (text, table, figure, heading)
        token_count: Number of tokens in the chunk
        metadata: Additional metadata as JSON

    Returns:
        UUID of the inserted chunk
    """
    async with get_connection() as conn:
        # Convert embedding to pgvector format if provided
        embedding_str = None
        if embedding:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        chunk_id = await conn.fetchval(
            """
            INSERT INTO chunks (
                document_id, content, chunk_index, embedding, page_number,
                section_title, chunk_type, token_count, metadata
            )
            VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            document_id,
            content,
            chunk_index,
            embedding_str,
            page_number,
            section_title,
            chunk_type,
            token_count,
            json.dumps(metadata or {}),
        )

        return chunk_id


async def insert_chunks_batch(
    document_id: UUID,
    chunks: list[dict[str, Any]],
) -> list[UUID]:
    """
    Insert multiple chunks in a batch.

    Args:
        document_id: ID of the parent document
        chunks: List of chunk dicts with keys: content, chunk_index, etc.

    Returns:
        List of inserted chunk UUIDs
    """
    if not chunks:
        return []

    async with get_connection() as conn:
        # Prepare values for batch insert
        values = []
        for chunk in chunks:
            embedding = chunk.get("embedding")
            embedding_str = None
            if embedding:
                embedding_str = f"[{','.join(str(x) for x in embedding)}]"

            values.append((
                document_id,
                chunk["content"],
                chunk["chunk_index"],
                embedding_str,
                chunk.get("page_number"),
                chunk.get("section_title"),
                chunk.get("chunk_type", "text"),
                chunk.get("token_count"),
                json.dumps(chunk.get("metadata", {})),
            ))

        # Batch insert using executemany
        chunk_ids = []
        for val in values:
            chunk_id = await conn.fetchval(
                """
                INSERT INTO chunks (
                    document_id, content, chunk_index, embedding, page_number,
                    section_title, chunk_type, token_count, metadata
                )
                VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                *val
            )
            chunk_ids.append(chunk_id)

        return chunk_ids


async def update_chunk_embedding(chunk_id: UUID, embedding: list[float]):
    """Update the embedding for a chunk."""
    async with get_connection() as conn:
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        await conn.execute(
            "UPDATE chunks SET embedding = $1::vector WHERE id = $2",
            embedding_str,
            chunk_id,
        )


async def get_chunks_without_embeddings(limit: int = 100) -> list[tuple[UUID, str]]:
    """Get chunks that don't have embeddings yet."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, content FROM chunks
            WHERE embedding IS NULL
            LIMIT $1
            """,
            limit
        )
        return [(row["id"], row["content"]) for row in rows]


# ============================================================================
# SEARCH OPERATIONS
# ============================================================================


async def vector_search(
    query_embedding: list[float],
    match_count: int = 10,
    document_ids: list[int] | None = None,
) -> list[SearchResult]:
    """
    Search for similar chunks using vector similarity.

    Args:
        query_embedding: Query embedding vector
        match_count: Maximum number of results
        document_ids: Optional list of document IDs to filter by

    Returns:
        List of SearchResult objects
    """
    import logging
    logger = logging.getLogger(__name__)

    async with get_connection() as conn:
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        logger.info(f"[VECTOR_SEARCH] document_ids={document_ids}, match_count={match_count}")

        # Query adapted for MAGICK PDFs schema (integer IDs, no page_number/author/metadata)
        if document_ids:
            rows = await conn.fetch(
                """
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.content,
                    1 - (c.embedding <=> $1::vector) AS similarity,
                    d.title AS document_title,
                    d.filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL
                  AND c.document_id = ANY($3::integer[])
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                embedding_str,
                match_count,
                document_ids,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.content,
                    1 - (c.embedding <=> $1::vector) AS similarity,
                    d.title AS document_title,
                    d.filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                embedding_str,
                match_count,
            )

        logger.info(f"[VECTOR_SEARCH] Returned {len(rows)} rows from database")

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                similarity=float(row["similarity"]),
                page_number=None,
                document_title=row["document_title"] or row["filename"],
                document_author=None,
                document_filename=row["filename"],
                metadata=None,
            )
            for row in rows
        ]


async def hybrid_search(
    query_embedding: list[float],
    query_text: str,
    match_count: int = 10,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
    document_ids: list[int] | None = None,
) -> list[HybridSearchResult]:
    """
    Search using both vector similarity and keyword matching.
    MULTI-DOC FIX v2: Per-document search with balancing to ensure ALL documents contribute.

    Args:
        query_embedding: Query embedding vector
        query_text: Query text for keyword search
        match_count: Maximum number of results
        vector_weight: Weight for vector similarity (0-1)
        keyword_weight: Weight for keyword matching (0-1)
        document_ids: Optional list of document IDs to filter by

    Returns:
        List of HybridSearchResult objects
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[HYBRID_SEARCH] document_ids={document_ids}, match_count={match_count}")

    # MULTI-DOC FIX v2: For multiple documents, search each document separately
    # This ensures we get results from ALL documents, not just the most similar one
    if document_ids and len(document_ids) > 1:
        logger.info(f"[HYBRID_SEARCH] Multi-document mode: searching {len(document_ids)} documents separately")
        return await _hybrid_search_per_document(
            query_embedding, query_text, match_count, vector_weight, keyword_weight, document_ids, logger
        )
    else:
        # Single document or no filter: use standard search
        return await _hybrid_search_single(
            query_embedding, query_text, match_count, vector_weight, keyword_weight, document_ids, logger
        )


async def _hybrid_search_single(
    query_embedding: list[float],
    query_text: str,
    match_count: int,
    vector_weight: float,
    keyword_weight: float,
    document_ids: list[int] | None,
    logger,
) -> list[HybridSearchResult]:
    """Single document or unfiltered search."""
    async with get_connection() as conn:
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        rows = await conn.fetch(
            """
            SELECT * FROM hybrid_search($1::vector, $2, $3, $4, $5, $6::integer[])
            """,
            embedding_str,
            query_text,
            match_count,
            vector_weight,
            keyword_weight,
            document_ids,
        )

        logger.info(f"[HYBRID_SEARCH] Returned {len(rows)} rows from database")

        # Convert to HybridSearchResult objects immediately (eager evaluation)
        # This ensures the database connection is fully consumed before returning
        results = []
        for row in rows:
            results.append(HybridSearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                similarity=float(row["combined_score"]),
                vector_score=float(row["vector_score"]),
                keyword_score=float(row["keyword_score"]),
                page_number=None,
                document_title=row["document_title"],
                document_author=None,
                document_filename=row["document_filename"],
            ))
        return results


async def _hybrid_search_per_document(
    query_embedding: list[float],
    query_text: str,
    match_count: int,
    vector_weight: float,
    keyword_weight: float,
    document_ids: list[int],
    logger,
) -> list[HybridSearchResult]:
    """
    Search each document separately and merge results.
    Ensures balanced representation from all documents.
    """
    chunks_per_doc = max(1, match_count // len(document_ids))
    all_results = []

    async with get_connection() as conn:
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        # Search each document separately
        for doc_id in document_ids:
            rows = await conn.fetch(
                """
                SELECT * FROM hybrid_search($1::vector, $2, $3, $4, $5, $6::integer[])
                """,
                embedding_str,
                query_text,
                chunks_per_doc * 2,  # Get 2x per doc to allow for scoring variations
                vector_weight,
                keyword_weight,
                [doc_id],  # Search this document only
            )

            logger.info(f"[HYBRID_SEARCH] Document {doc_id}: Found {len(rows)} chunks")

            # Convert to HybridSearchResult objects
            for row in rows:
                all_results.append(
                    HybridSearchResult(
                        chunk_id=row["chunk_id"],
                        document_id=row["document_id"],
                        content=row["content"],
                        similarity=float(row["combined_score"]),
                        vector_score=float(row["vector_score"]),
                        keyword_score=float(row["keyword_score"]),
                        page_number=None,
                        document_title=row["document_title"],
                        document_author=None,
                        document_filename=row["document_filename"],
                    )
                )

    # BALANCE RESULTS: Don't sort globally - distribute proportionally across documents
    # Group by document_id
    results_by_doc = {}
    for result in all_results:
        doc_id = result.document_id
        if doc_id not in results_by_doc:
            results_by_doc[doc_id] = []
        results_by_doc[doc_id].append(result)

    # Sort each document's results by similarity
    for doc_id in results_by_doc:
        results_by_doc[doc_id].sort(key=lambda x: x.similarity, reverse=True)

    # FORCED MULTI-DOCUMENT: If any document has no results, fetch fallback chunks
    async def fetch_fallback_chunks(doc_id: int, min_chunks: int = 3) -> list:
        """Fetch fallback chunks from a document that had no query matches."""
        async with get_connection() as conn:
            # Get any chunks from this document sorted by vector similarity to query
            try:
                rows = await conn.fetch(
                    f"""
                    SELECT c.id AS chunk_id, c.document_id, c.content,
                           1 - (c.embedding <=> $1::vector) as similarity,
                           0 as vector_score, 0 as keyword_score,
                           NULL as page_number, d.title AS document_title, d.filename AS document_filename
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE c.document_id = $2 AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> $1::vector
                    LIMIT $3
                    """,
                    embedding_str,
                    doc_id,
                    min_chunks
                )
                logger.info(f"[FALLBACK_DEBUG] Query returned {len(rows)} rows for doc_id={doc_id}")
                result = [
                    HybridSearchResult(
                        chunk_id=row["chunk_id"],
                        document_id=row["document_id"],
                        content=row["content"],
                        similarity=float(row["similarity"]),
                        vector_score=float(row["vector_score"]),
                        keyword_score=float(row["keyword_score"]),
                        page_number=None,
                        document_title=row["document_title"],
                        document_author=None,
                        document_filename=row["document_filename"],
                    )
                    for row in rows
                ]
                logger.info(f"[FALLBACK_DEBUG] Returning {len(result)} chunks for doc_id={doc_id}")
                return result
            except Exception as e:
                logger.error(f"[FALLBACK_DEBUG] Error fetching fallback for doc_id={doc_id}: {e}")
                return []

    # Fetch fallback chunks for documents with no results
    for doc_id in document_ids:
        if doc_id not in results_by_doc or len(results_by_doc[doc_id]) == 0:
            logger.info(f"[HYBRID_SEARCH] No chunks found for document {doc_id}, fetching fallback...")
            fallback = await fetch_fallback_chunks(doc_id, min_chunks=3)
            if fallback:
                results_by_doc[doc_id] = fallback
                logger.info(f"[HYBRID_SEARCH] Fallback found {len(fallback)} chunks for document {doc_id}")
            else:
                # No chunks or fallback found - don't add metadata placeholders
                # (Metadata placeholders break source-aware citation numbering)
                logger.warning(f"[HYBRID_SEARCH] No chunks found for document {doc_id}")

    # Distribute chunks proportionally - take top N from each document
    chunks_per_doc = max(1, match_count // len(document_ids))
    remainder = match_count % len(document_ids)

    final_results = []
    for i, doc_id in enumerate(document_ids):
        # First doc(s) get remainder chunks
        to_take = chunks_per_doc + (1 if i < remainder else 0)
        if doc_id in results_by_doc and len(results_by_doc[doc_id]) > 0:
            final_results.extend(results_by_doc[doc_id][:to_take])
        else:
            logger.warning(f"[HYBRID_SEARCH] Document {doc_id} has no chunks even after fallback and metadata attempt")

    logger.info(
        f"[HYBRID_SEARCH] Per-document search complete: {len(final_results)} results from "
        f"{len(set(r.document_id for r in final_results))} documents"
    )

    return final_results


def _balance_results_across_documents(rows: list, document_ids: list[int], target_count: int, logger) -> list:
    """
    MULTI-DOC FIX: Balance search results across multiple documents.

    When multiple documents are selected, ensure chunks from ALL documents
    are represented in the results, not just the most similar document.

    Args:
        rows: Raw results from hybrid_search (already sorted by combined_score)
        document_ids: List of document IDs being filtered by
        target_count: Target number of results to return
        logger: Logger instance

    Returns:
        Rebalanced list of rows with representation from all documents
    """
    if not rows or len(document_ids) <= 1:
        return rows[:target_count]

    # Group rows by document
    docs_chunks = {}
    for row in rows:
        doc_id = row["document_id"]
        if doc_id not in docs_chunks:
            docs_chunks[doc_id] = []
        docs_chunks[doc_id].append(row)

    logger.info(f"[BALANCE] Found chunks from {len(docs_chunks)} documents: {list(docs_chunks.keys())}")

    # Calculate chunks per document
    chunks_per_doc = target_count // len(document_ids)
    remainder = target_count % len(document_ids)

    # Build balanced result: take top N chunks from each document
    balanced = []
    for i, doc_id in enumerate(document_ids):
        if doc_id in docs_chunks:
            # Get chunks for this document, take top (chunks_per_doc + 1 if has remainder)
            count = chunks_per_doc + (1 if i < remainder else 0)
            balanced.extend(docs_chunks[doc_id][:count])
            logger.info(f"[BALANCE] Document {doc_id}: taking {count} chunks")
        else:
            logger.warning(f"[BALANCE] Document {doc_id}: NO CHUNKS FOUND")

    # Re-sort by combined_score to maintain relevance ranking
    balanced.sort(key=lambda x: float(x["combined_score"]), reverse=True)

    return balanced[:target_count]


async def search(
    query: str,
    match_count: int = 10,
    use_hybrid: bool = True,
    vector_weight: float = 0.7,
    document_ids: list[int] | None = None,
) -> list[SearchResult]:
    """
    High-level search function that handles embedding generation.

    Args:
        query: Search query text
        match_count: Maximum number of results
        use_hybrid: Whether to use hybrid search (vector + keyword)
        vector_weight: Weight for vector similarity in hybrid search
        document_ids: Optional list of document IDs to filter by

    Returns:
        List of SearchResult objects
    """
    # Generate query embedding
    query_embedding = await generate_embedding(query)

    if use_hybrid:
        return await hybrid_search(
            query_embedding=query_embedding,
            query_text=query,
            match_count=match_count,
            vector_weight=vector_weight,
            keyword_weight=1 - vector_weight,
            document_ids=document_ids,
        )
    else:
        return await vector_search(
            query_embedding=query_embedding,
            match_count=match_count,
            document_ids=document_ids,
        )


async def search_bibliothek(
    query: str,
    match_count: int = 10,
    use_hybrid: bool = False,  # Disabled by default for BIBLIOTHEK (1.8M chunks - too slow)
    vector_weight: float = 0.7,
    document_ids: list[int] | None = None,
) -> list[SearchResult]:
    """
    Search the BIBLIOTHEK collection (bibliothek_knowledge database).

    Uses the same embedding model and search approach as MAG-LIB but
    queries the separate BIBLIOTHEK database.

    Note: Hybrid search is disabled by default for BIBLIOTHEK due to the
    large collection size (1.8M chunks). Vector-only search is more efficient.

    Args:
        query: Search query text
        match_count: Maximum number of results
        use_hybrid: Whether to use hybrid search (vector + keyword) - disabled by default
        vector_weight: Weight for vector similarity in hybrid search
        document_ids: Optional list of document IDs to filter by

    Returns:
        List of SearchResult objects
    """
    # Generate query embedding (same model as MAG-LIB)
    query_embedding = await generate_embedding(query)
    # Convert embedding to string format for pgvector
    embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

    async with get_bibliothek_connection() as conn:
        if use_hybrid:
            # Hybrid search: combine vector similarity with keyword matching
            keyword_weight = 1 - vector_weight
            doc_filter = ""
            params = [embedding_str, query, vector_weight, keyword_weight, match_count]
            if document_ids:
                doc_filter = "AND c.document_id = ANY($6)"
                params.append(document_ids)

            sql = f"""
            WITH vector_results AS (
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.content,
                    1 - (c.embedding <=> $1::vector) AS vector_score,
                    d.title AS document_title,
                    d.filename AS document_filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL {doc_filter}
                ORDER BY c.embedding <=> $1::vector
                LIMIT $5 * 2
            ),
            keyword_results AS (
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.content,
                    ts_rank_cd(to_tsvector('english', c.content), plainto_tsquery('english', $2)) AS keyword_score,
                    d.title AS document_title,
                    d.filename AS document_filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', $2)
                {doc_filter.replace('$6', '$6') if document_ids else ''}
                LIMIT $5 * 2
            )
            SELECT DISTINCT ON (combined.chunk_id)
                combined.chunk_id,
                combined.document_id,
                combined.content,
                combined.document_title,
                combined.document_filename,
                COALESCE(v.vector_score, 0) AS vector_score,
                COALESCE(k.keyword_score, 0) AS keyword_score,
                COALESCE(v.vector_score, 0) * $3 + COALESCE(k.keyword_score, 0) * $4 AS combined_score
            FROM (
                SELECT chunk_id, document_id, content, document_title, document_filename FROM vector_results
                UNION
                SELECT chunk_id, document_id, content, document_title, document_filename FROM keyword_results
            ) combined
            LEFT JOIN vector_results v ON combined.chunk_id = v.chunk_id
            LEFT JOIN keyword_results k ON combined.chunk_id = k.chunk_id
            ORDER BY combined.chunk_id, combined_score DESC
            """

            # Get top results
            rows = await conn.fetch(f"""
                SELECT * FROM ({sql}) sub
                ORDER BY combined_score DESC
                LIMIT $5
            """, *params)
        else:
            # Vector-only search
            doc_filter = ""
            params = [embedding_str, match_count]
            if document_ids:
                doc_filter = "AND c.document_id = ANY($3)"
                params.append(document_ids)

            rows = await conn.fetch(f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.content,
                    1 - (c.embedding <=> $1::vector) AS similarity,
                    d.title AS document_title,
                    d.filename AS document_filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL {doc_filter}
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
            """, *params)

            return [
                SearchResult(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    similarity=float(row["similarity"]),
                    page_number=None,
                    document_title=row["document_title"],
                    document_author=None,
                    document_filename=row["document_filename"],
                )
                for row in rows
            ]

        # Return hybrid results
        return [
            HybridSearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                similarity=float(row["combined_score"]),
                vector_score=float(row["vector_score"]),
                keyword_score=float(row["keyword_score"]),
                page_number=None,
                document_title=row["document_title"],
                document_author=None,
                document_filename=row["document_filename"],
            )
            for row in rows
        ]


# ============================================================================
# DATABASE STATS
# ============================================================================


async def get_database_stats() -> dict[str, Any]:
    """Get database statistics."""
    async with get_connection() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM documents) AS total_documents,
                (SELECT COUNT(*) FROM chunks) AS total_chunks,
                (SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL) AS embedded_chunks,
                (SELECT pg_size_pretty(pg_total_relation_size('documents'))) AS documents_size,
                (SELECT pg_size_pretty(pg_total_relation_size('chunks'))) AS chunks_size
            """
        )

        return {
            "total_documents": stats["total_documents"],
            "total_chunks": stats["total_chunks"],
            "embedded_chunks": stats["embedded_chunks"],
            "documents_size": stats["documents_size"],
            "chunks_size": stats["chunks_size"],
            "embedding_coverage": (
                stats["embedded_chunks"] / stats["total_chunks"] * 100
                if stats["total_chunks"] > 0 else 0
            ),
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def format_search_results_for_rag(results: list[SearchResult]) -> list[dict]:
    """
    Format search results for use with RAG chat service.

    Converts pgvector SearchResult objects to the dict format expected
    by the existing RAG pipeline.
    """
    return [
        {
            "id": str(result.chunk_id),
            "text": result.content,
            "similarity": result.similarity,
            "metadata": {
                "document_id": str(result.document_id),
                "document_title": result.document_title,
                "document_author": result.document_author,
                "document_filename": result.document_filename,  # For cover image lookup
                "page_number": result.page_number,
                **(result.metadata or {}),
            },
        }
        for result in results
    ]
