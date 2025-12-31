"""
Query API Routes - RAG queries

Supports both local ChromaDB and Weaviate (in private mode) for federated search.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Literal

from app.config import config
from app.db.vector_store import query_documents
from app.core.embeddings import generate_embedding
from app.lib.weaviate_client import (
    query_weaviate,
    get_weaviate_stats,
    get_weaviate_companies,
    check_weaviate_health,
)

router = APIRouter(prefix="/api/query", tags=["query"])


class QueryRequest(BaseModel):
    """Request for RAG query."""
    query: str = Field(min_length=1, description="Search query")
    category_ids: list[int] | None = Field(default=None, description="Categories to search")
    limit: int = Field(default=10, ge=1, le=100, description="Max results")
    sources: list[Literal["local", "weaviate"]] | None = Field(
        default=None,
        description="Sources to search. None means all available sources."
    )
    weaviate_company: str | None = Field(
        default=None,
        description="Filter Weaviate results by company name"
    )


class QueryResult(BaseModel):
    """A single query result."""
    text: str
    score: float
    metadata: dict


class QueryResponse(BaseModel):
    """Response for RAG query."""
    query: str
    results: list[QueryResult]
    total: int
    sources_searched: list[str]


@router.post("", response_model=QueryResponse)
async def search_knowledge_base(data: QueryRequest):
    """
    Search the knowledge base using RAG.

    In private mode with Weaviate enabled, searches both local ChromaDB
    and Weaviate, merging and ranking results.
    """
    all_results = []
    sources_searched = []

    # Determine which sources to search
    search_local = data.sources is None or "local" in data.sources
    search_weaviate = (
        config.weaviate.is_configured
        and config.mode.private_mode
        and (data.sources is None or "weaviate" in data.sources)
    )

    # Search local ChromaDB
    if search_local:
        sources_searched.append("local")
        query_embedding = await generate_embedding(data.query)

        results = query_documents(
            query_embedding=query_embedding,
            category_ids=data.category_ids,
            n_results=data.limit,
        )

        # Format local results
        for i in range(len(results.get("ids", []))):
            distance = results["distances"][i] if results.get("distances") else 0
            score = 1 - distance

            metadata = results["metadatas"][i] if results.get("metadatas") else {}
            metadata["source"] = "local"

            all_results.append(QueryResult(
                text=results["documents"][i] if results.get("documents") else "",
                score=score,
                metadata=metadata,
            ))

    # Search Weaviate (private mode only)
    if search_weaviate:
        sources_searched.append("weaviate")

        weaviate_results = await query_weaviate(
            query=data.query,
            limit=data.limit,
            company_filter=data.weaviate_company,
            use_reranker=True,
        )

        for result in weaviate_results:
            all_results.append(QueryResult(
                text=result["text"],
                score=result["score"],
                metadata=result["metadata"],
            ))

    # Merge and sort by score
    all_results.sort(key=lambda x: x.score, reverse=True)

    # Limit total results
    final_results = all_results[:data.limit]

    return QueryResponse(
        query=data.query,
        results=final_results,
        total=len(final_results),
        sources_searched=sources_searched,
    )


@router.get("/sources")
async def get_available_sources():
    """Get information about available search sources."""
    sources = {
        "local": {
            "enabled": True,
            "name": "Local Knowledge Base",
            "description": "Documents, YouTube transcripts, and web content",
        }
    }

    # Add Weaviate if configured and in private mode
    if config.weaviate.is_configured and config.mode.private_mode:
        weaviate_health = await check_weaviate_health()
        weaviate_stats = await get_weaviate_stats()
        weaviate_companies = await get_weaviate_companies()

        sources["weaviate"] = {
            "enabled": True,
            "name": "Weaviate Knowledge Base",
            "description": "Discord chat and external data sources",
            "health": weaviate_health,
            "stats": weaviate_stats,
            "companies": weaviate_companies,
        }

    return {
        "private_mode": config.mode.private_mode,
        "sources": sources,
    }
