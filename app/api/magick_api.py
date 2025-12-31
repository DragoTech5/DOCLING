"""
MAGICK PDFs REST API

REST API endpoints for querying the MAGICK PDFs vector database.
This API can be used by external applications to search and chat with the collection.

Endpoints:
- POST /magick/search - Vector similarity search
- POST /magick/chat - RAG-powered chat
- GET /magick/documents - List/filter documents
- GET /magick/stats - Database statistics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from app.config import config
from app.services import pgvector_service as pgvector
from app.services import pgvector_rag

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/magick", tags=["MAGICK PDFs"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class SearchRequest(BaseModel):
    """Search request body."""
    query: str = Field(..., description="Search query text")
    n_results: int = Field(default=10, ge=1, le=100, description="Number of results")
    use_hybrid: bool = Field(default=True, description="Use hybrid search (vector + keyword)")
    vector_weight: float = Field(default=0.7, ge=0, le=1, description="Weight for vector search")


class SearchResult(BaseModel):
    """A single search result."""
    id: str
    document_id: str
    content: str
    similarity: float
    title: str | None = None
    author: str | None = None
    page: int | None = None


class SearchResponse(BaseModel):
    """Search response."""
    query: str
    results: list[SearchResult]
    total: int


class ChatRequest(BaseModel):
    """Chat request body."""
    query: str = Field(..., description="User's question")
    chat_history: list[dict] | None = Field(default=None, description="Previous messages")
    use_hyde: bool = Field(default=True, description="Use HyDE enhancement")
    use_reranking: bool = Field(default=True, description="Use cross-encoder reranking")
    use_decomposition: bool = Field(default=True, description="Use query decomposition")
    n_results: int = Field(default=8, ge=1, le=20, description="Context chunks to use")


class ChatSource(BaseModel):
    """A source citation."""
    index: int
    text: str
    similarity: float
    title: str | None = None
    author: str | None = None
    page: int | None = None


class ChatResponse(BaseModel):
    """Chat response."""
    answer: str
    sources: list[ChatSource]
    is_confident: bool
    confidence_score: float
    query_info: dict[str, Any]


class DocumentInfo(BaseModel):
    """Document information."""
    id: str
    filename: str
    title: str | None
    author: str | None
    page_count: int | None
    file_size_bytes: int | None


class StatsResponse(BaseModel):
    """Database statistics."""
    total_documents: int
    total_chunks: int
    embedded_chunks: int
    embedding_coverage: float
    documents_size: str
    chunks_size: str


# ============================================================================
# API KEY AUTHENTICATION (Optional)
# ============================================================================


def verify_api_key(api_key: str | None = Query(default=None, alias="api_key")):
    """
    Optional API key verification.

    For now, this is disabled. Enable by setting MAGICK_API_KEY env variable.
    """
    required_key = config.pgvector.password  # Reuse for now
    # To enable: uncomment below
    # if required_key and api_key != required_key:
    #     raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/health")
async def health_check():
    """Check if the MAGICK API is healthy and pgvector is connected."""
    if not config.pgvector.enabled:
        return {
            "status": "disabled",
            "message": "pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        }

    try:
        healthy = await pgvector_rag.health_check()
        if healthy:
            return {"status": "healthy", "database": "connected"}
        else:
            return {"status": "unhealthy", "database": "disconnected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    _auth: bool = Depends(verify_api_key),
):
    """
    Search the MAGICK PDFs collection.

    Uses vector similarity search with optional keyword matching.
    """
    if not config.pgvector.enabled:
        raise HTTPException(
            status_code=503,
            detail="pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        )

    try:
        results = await pgvector_rag.simple_search(
            query=request.query,
            n_results=request.n_results,
            use_hybrid=request.use_hybrid,
        )

        return SearchResponse(
            query=request.query,
            results=[SearchResult(**r) for r in results],
            total=len(results),
        )

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    _auth: bool = Depends(verify_api_key),
):
    """
    Chat with the MAGICK PDFs collection using RAG.

    Retrieves relevant context and generates an answer with citations.
    """
    if not config.pgvector.enabled:
        raise HTTPException(
            status_code=503,
            detail="pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        )

    try:
        rag_config = pgvector_rag.PgVectorRAGConfig(
            use_hyde=request.use_hyde,
            use_reranking=request.use_reranking,
            use_decomposition=request.use_decomposition,
            n_results=request.n_results,
        )

        response = await pgvector_rag.rag_chat(
            query=request.query,
            chat_history=request.chat_history,
            rag_config=rag_config,
        )

        return ChatResponse(
            answer=response.answer,
            sources=[ChatSource(**s) for s in response.sources],
            is_confident=response.confidence.is_confident if response.confidence else True,
            confidence_score=response.confidence.confidence_score if response.confidence else 1.0,
            query_info=response.query_info,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents")
async def list_documents(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    title_search: str | None = Query(default=None, description="Search in titles"),
    author_search: str | None = Query(default=None, description="Search by author"),
    _auth: bool = Depends(verify_api_key),
):
    """
    List documents in the collection.

    Supports pagination and filtering by title/author.
    """
    if not config.pgvector.enabled:
        raise HTTPException(
            status_code=503,
            detail="pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        )

    try:
        async with pgvector.get_connection() as conn:
            # Build query
            where_clauses = []
            params = []
            param_idx = 1

            if title_search:
                where_clauses.append(f"title ILIKE ${param_idx}")
                params.append(f"%{title_search}%")
                param_idx += 1

            if author_search:
                where_clauses.append(f"author ILIKE ${param_idx}")
                params.append(f"%{author_search}%")
                param_idx += 1

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            # Count total
            count_query = f"SELECT COUNT(*) FROM documents {where_sql}"
            total = await conn.fetchval(count_query, *params)

            # Fetch documents
            params.extend([limit, offset])
            query = f"""
                SELECT id, filename, title, author, page_count, file_size_bytes
                FROM documents
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """

            rows = await conn.fetch(query, *params)

            documents = [
                {
                    "id": str(row["id"]),
                    "filename": row["filename"],
                    "title": row["title"],
                    "author": row["author"],
                    "page_count": row["page_count"],
                    "file_size_bytes": row["file_size_bytes"],
                }
                for row in rows
            ]

            return {
                "documents": documents,
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    except Exception as e:
        logger.error(f"List documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    include_chunks: bool = Query(default=False),
    _auth: bool = Depends(verify_api_key),
):
    """
    Get a specific document by ID.

    Optionally includes all chunks for the document.
    """
    if not config.pgvector.enabled:
        raise HTTPException(
            status_code=503,
            detail="pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        )

    try:
        async with pgvector.get_connection() as conn:
            # Fetch document
            doc = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1",
                document_id,
            )

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            result = {
                "id": str(doc["id"]),
                "filename": doc["filename"],
                "title": doc["title"],
                "author": doc["author"],
                "page_count": doc["page_count"],
                "file_size_bytes": doc["file_size_bytes"],
                "file_hash": doc["file_hash"],
                "source_path": doc["source_path"],
                "processed_at": doc["processed_at"].isoformat() if doc["processed_at"] else None,
                "created_at": doc["created_at"].isoformat() if doc["created_at"] else None,
                "metadata": doc["metadata"],
            }

            if include_chunks:
                chunks = await conn.fetch(
                    """
                    SELECT id, content, chunk_index, page_number, section_title, chunk_type
                    FROM chunks
                    WHERE document_id = $1
                    ORDER BY chunk_index
                    """,
                    document_id,
                )

                result["chunks"] = [
                    {
                        "id": str(c["id"]),
                        "content": c["content"],
                        "chunk_index": c["chunk_index"],
                        "page_number": c["page_number"],
                        "section_title": c["section_title"],
                        "chunk_type": c["chunk_type"],
                    }
                    for c in chunks
                ]
                result["chunk_count"] = len(chunks)

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=StatsResponse)
async def get_stats(_auth: bool = Depends(verify_api_key)):
    """Get database statistics."""
    if not config.pgvector.enabled:
        raise HTTPException(
            status_code=503,
            detail="pgvector is not enabled. Set PGVECTOR_ENABLED=true",
        )

    try:
        stats = await pgvector_rag.get_stats()
        return StatsResponse(**stats)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
