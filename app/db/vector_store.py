"""
ChromaDB Vector Store for Docling Knowledge Hub
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings
from typing import Any
import json

from app.config import config


# Global ChromaDB client
_chroma_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create the ChromaDB client with persistent storage."""
    global _chroma_client

    if _chroma_client is None:
        config.database.chromadb_path.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=str(config.database.chromadb_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

    return _chroma_client


def get_collection_name(category_id: int | None = None) -> str:
    """Generate collection name for a category."""
    if category_id is None:
        return "knowledge_hub_general"
    return f"knowledge_hub_cat_{category_id}"


def get_or_create_collection(
    category_id: int | None = None,
    embedding_function: Any = None,
) -> chromadb.Collection:
    """Get or create a ChromaDB collection for a category."""
    client = get_chroma_client()
    collection_name = get_collection_name(category_id)

    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(
    documents: list[str],
    metadatas: list[dict[str, Any]],
    ids: list[str],
    category_id: int | None = None,
    embeddings: list[list[float]] | None = None,
) -> None:
    """Add documents to a category's collection."""
    collection = get_or_create_collection(category_id)

    if embeddings:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )
    else:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )


def query_documents(
    query_text: str | None = None,
    query_embedding: list[float] | None = None,
    category_ids: list[int] | None = None,
    n_results: int = 10,
    where: dict | None = None,
    include: list[str] | None = None,
) -> dict[str, Any]:
    """
    Query documents across one or more category collections.

    Args:
        query_text: Text query (will be embedded)
        query_embedding: Pre-computed embedding
        category_ids: List of category IDs to search (None = all)
        n_results: Number of results per collection
        where: Metadata filter
        include: What to include in results

    Returns:
        Combined results from all queried collections
    """
    client = get_chroma_client()

    if include is None:
        include = ["documents", "metadatas", "distances"]

    # Determine which collections to query
    if category_ids is None:
        # Query all collections
        collections = client.list_collections()
    else:
        collections = [
            get_or_create_collection(cat_id) for cat_id in category_ids
        ]

    all_results = {
        "ids": [],
        "documents": [],
        "metadatas": [],
        "distances": [],
    }

    for collection in collections:
        try:
            if query_embedding:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where,
                    include=include,
                )
            elif query_text:
                results = collection.query(
                    query_texts=[query_text],
                    n_results=n_results,
                    where=where,
                    include=include,
                )
            else:
                continue

            # Flatten results (remove the outer list from single query)
            if results.get("ids"):
                all_results["ids"].extend(results["ids"][0])
            if results.get("documents"):
                all_results["documents"].extend(results["documents"][0])
            if results.get("metadatas"):
                all_results["metadatas"].extend(results["metadatas"][0])
            if results.get("distances"):
                all_results["distances"].extend(results["distances"][0])

        except Exception:
            # Skip empty or problematic collections
            continue

    # Sort by distance (similarity) and limit to n_results
    if all_results["distances"]:
        combined = list(zip(
            all_results["distances"],
            all_results["ids"],
            all_results["documents"],
            all_results["metadatas"],
        ))
        combined.sort(key=lambda x: x[0])
        combined = combined[:n_results]

        all_results = {
            "distances": [x[0] for x in combined],
            "ids": [x[1] for x in combined],
            "documents": [x[2] for x in combined],
            "metadatas": [x[3] for x in combined],
        }

    return all_results


def delete_documents(
    ids: list[str],
    category_id: int | None = None,
) -> None:
    """Delete documents from a collection by ID."""
    collection = get_or_create_collection(category_id)
    collection.delete(ids=ids)


def delete_collection(category_id: int | None = None) -> None:
    """Delete an entire collection."""
    client = get_chroma_client()
    collection_name = get_collection_name(category_id)

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass  # Collection doesn't exist


def get_collection_stats(category_id: int | None = None) -> dict[str, Any]:
    """Get statistics for a collection."""
    collection = get_or_create_collection(category_id)

    return {
        "name": collection.name,
        "count": collection.count(),
        "metadata": collection.metadata,
    }


def get_all_collection_stats() -> list[dict[str, Any]]:
    """Get statistics for all collections."""
    client = get_chroma_client()
    stats = []

    for collection in client.list_collections():
        stats.append({
            "name": collection.name,
            "count": collection.count(),
            "metadata": collection.metadata,
        })

    return stats
