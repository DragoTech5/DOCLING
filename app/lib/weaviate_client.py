"""
Weaviate Vector Database Client

Provides integration with Weaviate for querying external knowledge bases
in private mode. Uses REST/GraphQL API for compatibility with various setups.
"""

from __future__ import annotations

from typing import Optional
import httpx

from app.config import config


def close_weaviate_client():
    """Close the Weaviate client connection (no-op for REST API)."""
    pass


async def check_weaviate_health() -> dict:
    """Check if Weaviate is healthy and accessible."""
    if not config.weaviate.is_configured:
        return {"status": "disabled", "message": "Weaviate is not enabled"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.weaviate.http_url}/v1/.well-known/ready",
                timeout=5.0
            )
            if response.status_code == 200:
                return {"status": "healthy", "message": "Weaviate is ready"}
            return {"status": "unhealthy", "message": f"Status code: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def query_weaviate(
    query: str,
    limit: int = 10,
    company_filter: Optional[str] = None,
    use_reranker: bool = True,
) -> list[dict]:
    """
    Query Weaviate for relevant content using hybrid search with reranking.
    Uses REST/GraphQL API for compatibility.

    Args:
        query: The search query
        limit: Maximum number of results
        company_filter: Optional filter by company_name
        use_reranker: Whether to use the cross-encoder reranker

    Returns:
        List of results with text, score, and metadata
    """
    if not config.weaviate.is_configured:
        return []

    try:
        # Escape query for GraphQL
        escaped_query = query.replace('\\', '\\\\').replace('"', '\\"')

        # Build company filter if specified
        where_clause = ""
        if company_filter:
            escaped_filter = company_filter.replace('\\', '\\\\').replace('"', '\\"')
            where_clause = f'where: {{ path: ["company_name"], operator: Equal, valueText: "{escaped_filter}" }}'

        # Build GraphQL query with hybrid search and optional reranking
        if use_reranker:
            graphql_query = {
                "query": f"""
                {{
                    Get {{
                        {config.weaviate.collection_name}(
                            hybrid: {{
                                query: "{escaped_query}"
                                alpha: 0.5
                            }}
                            {where_clause}
                            limit: {limit}
                        ) {{
                            content
                            title
                            company_name
                            industry
                            datetime
                            _additional {{
                                score
                                rerank(
                                    property: "content"
                                    query: "{escaped_query}"
                                ) {{
                                    score
                                }}
                            }}
                        }}
                    }}
                }}
                """
            }
        else:
            graphql_query = {
                "query": f"""
                {{
                    Get {{
                        {config.weaviate.collection_name}(
                            hybrid: {{
                                query: "{escaped_query}"
                                alpha: 0.5
                            }}
                            {where_clause}
                            limit: {limit}
                        ) {{
                            content
                            title
                            company_name
                            industry
                            datetime
                            _additional {{
                                score
                            }}
                        }}
                    }}
                }}
                """
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.weaviate.http_url}/v1/graphql",
                json=graphql_query,
                timeout=30.0
            )

            if response.status_code != 200:
                print(f"Weaviate query failed with status {response.status_code}")
                return []

            data = response.json()

            # Check for errors
            if data.get("errors"):
                print(f"Weaviate GraphQL errors: {data['errors']}")
                return []

            results = data.get("data", {}).get("Get", {}).get(config.weaviate.collection_name, [])

            # Process results
            processed_results = []
            for obj in results:
                additional = obj.get("_additional", {})

                # Get score - prefer rerank score if available
                # Rerank response is a list: [{"score": 0.5}]
                rerank_info = additional.get("rerank")
                if rerank_info and isinstance(rerank_info, list) and len(rerank_info) > 0:
                    score = rerank_info[0].get("score", 0)
                else:
                    score = additional.get("score", 0)
                score = float(score) if score else 0.0

                processed_results.append({
                    "text": obj.get("content", ""),
                    "score": score,
                    "metadata": {
                        "source": "weaviate",
                        "source_type": "discord_chat",
                        "company_name": obj.get("company_name", "Unknown"),
                        "industry": obj.get("industry", ""),
                        "title": obj.get("title", ""),
                        "datetime": str(obj.get("datetime", "")),
                    }
                })

            return processed_results

    except Exception as e:
        print(f"Weaviate query error: {e}")
        return []


async def get_weaviate_stats() -> dict:
    """Get statistics about the Weaviate collection."""
    if not config.weaviate.is_configured:
        return {"enabled": False}

    try:
        async with httpx.AsyncClient() as client:
            # Get aggregate count
            query = {
                "query": f"""
                {{
                    Aggregate {{
                        {config.weaviate.collection_name} {{
                            meta {{
                                count
                            }}
                        }}
                    }}
                }}
                """
            }

            response = await client.post(
                f"{config.weaviate.http_url}/v1/graphql",
                json=query,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                agg = data.get("data", {}).get("Aggregate", {}).get(config.weaviate.collection_name, [])
                count = agg[0].get("meta", {}).get("count", 0) if agg else 0

                return {
                    "enabled": True,
                    "collection": config.weaviate.collection_name,
                    "total_objects": count,
                    "host": config.weaviate.host,
                    "port": config.weaviate.port,
                }

    except Exception as e:
        return {"enabled": True, "error": str(e)}

    return {"enabled": True, "error": "Unknown error"}


async def get_weaviate_companies() -> list[dict]:
    """Get list of companies/sources in Weaviate."""
    if not config.weaviate.is_configured:
        return []

    try:
        async with httpx.AsyncClient() as client:
            query = {
                "query": f"""
                {{
                    Aggregate {{
                        {config.weaviate.collection_name}(groupBy: ["company_name"]) {{
                            groupedBy {{
                                value
                            }}
                            meta {{
                                count
                            }}
                        }}
                    }}
                }}
                """
            }

            response = await client.post(
                f"{config.weaviate.http_url}/v1/graphql",
                json=query,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                groups = data.get("data", {}).get("Aggregate", {}).get(config.weaviate.collection_name, [])

                companies = []
                for group in groups:
                    companies.append({
                        "name": group.get("groupedBy", {}).get("value", "Unknown"),
                        "count": group.get("meta", {}).get("count", 0),
                    })

                return sorted(companies, key=lambda x: x["count"], reverse=True)

    except Exception as e:
        print(f"Error fetching Weaviate companies: {e}")

    return []
