"""
RAG Quality Metrics

Metrics for evaluating RAG system performance across retrieval and generation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureMode(Enum):
    """Categories of RAG failure modes."""

    RETRIEVAL_FAILURE = "retrieval_failure"  # Wrong chunks retrieved
    GENERATION_FAILURE = "generation_failure"  # Right chunks, bad answer
    MIXED_FAILURE = "mixed_failure"  # Partial retrieval + generation issues
    NO_FAILURE = "no_failure"  # Successful response


@dataclass
class RetrievalMetrics:
    """Metrics for evaluating chunk retrieval quality."""

    # How many retrieved chunks were relevant
    precision_at_k: float = 0.0

    # How many relevant chunks were retrieved (out of expected)
    recall: float = 0.0

    # Were the expected sources in the top results?
    source_hit_rate: float = 0.0

    # How many expected keywords appeared in retrieved chunks
    keyword_coverage: float = 0.0

    # Average similarity score of retrieved chunks
    avg_similarity: float = 0.0

    # Number of chunks retrieved
    chunks_retrieved: int = 0

    # NEW: Content-based relevance (does content actually answer the question?)
    content_relevance: float = 0.0

    # NEW: How many chunks contain relevant content
    relevant_chunk_count: int = 0

    # Details
    retrieved_sources: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    matched_sources: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class GenerationMetrics:
    """Metrics for evaluating answer generation quality."""

    # Does answer contain expected keywords/phrases
    answer_relevance: float = 0.0

    # Is answer grounded in retrieved context (not hallucinated)
    faithfulness: float = 0.0

    # For negative queries: did it correctly say "not found"
    negative_handling: float | None = None

    # Keywords found in answer
    keywords_found: list[str] = field(default_factory=list)

    # Answer length
    answer_length: int = 0


@dataclass
class EvaluationResult:
    """Complete evaluation result for a single query."""

    query_id: str
    query: str
    query_type: str
    difficulty: str

    retrieval: RetrievalMetrics
    generation: GenerationMetrics

    failure_mode: FailureMode = FailureMode.NO_FAILURE

    # Raw data
    retrieved_chunks: list[dict] = field(default_factory=list)
    answer: str = ""
    sources_cited: list[dict] = field(default_factory=list)

    # Timing
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Notes
    notes: str = ""


def calculate_precision_at_k(
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int | None = None,
) -> float:
    """
    Calculate precision@k - what fraction of retrieved sources are relevant.

    Args:
        retrieved_sources: List of source titles that were retrieved
        expected_sources: List of source titles we expected to retrieve
        k: Only consider top k results (None = all)

    Returns:
        Precision score between 0 and 1
    """
    if not retrieved_sources:
        return 0.0

    if k is not None:
        retrieved_sources = retrieved_sources[:k]

    if not expected_sources:
        # No expected sources - can't evaluate precision
        return 0.0

    relevant_count = sum(1 for s in retrieved_sources if s in expected_sources)
    return relevant_count / len(retrieved_sources)


def calculate_recall(
    retrieved_sources: list[str],
    expected_sources: list[str],
) -> float:
    """
    Calculate recall - what fraction of expected sources were retrieved.

    Args:
        retrieved_sources: List of source titles that were retrieved
        expected_sources: List of source titles we expected to retrieve

    Returns:
        Recall score between 0 and 1
    """
    if not expected_sources:
        return 1.0  # Nothing expected, nothing missed

    found_count = sum(1 for s in expected_sources if s in retrieved_sources)
    return found_count / len(expected_sources)


def calculate_keyword_coverage(
    text: str,
    expected_keywords: list[str],
) -> tuple[float, list[str]]:
    """
    Calculate what fraction of expected keywords appear in text.

    Args:
        text: Text to search in (chunks or answer)
        expected_keywords: Keywords we expect to find

    Returns:
        Tuple of (coverage score, list of matched keywords)
    """
    if not expected_keywords:
        return 1.0, []

    text_lower = text.lower()
    matched = [kw for kw in expected_keywords if kw.lower() in text_lower]
    coverage = len(matched) / len(expected_keywords)
    return coverage, matched


def _get_significant_words(text: str, min_length: int = 3) -> set[str]:
    """Extract significant words from text (excluding short words and stopwords)."""
    import re
    stopwords = {'the', 'and', 'for', 'with', 'are', 'was', 'has', 'have', 'how', 'what', 'why', 'when', 'who', 'this', 'that', 'from', 'your', 'our', 'its', 'you', 'can'}
    words = set(re.findall(r'\b[a-zA-Z]+\b', text.lower()))
    return {w for w in words if len(w) >= min_length and w not in stopwords}


def calculate_content_relevance(
    retrieved_chunks: list[dict],
    expected_keywords: list[str],
    query: str,
) -> tuple[float, list[str], list[dict]]:
    """
    Calculate content-based relevance score for retrieved chunks.

    This measures whether the retrieved CONTENT actually answers the question,
    regardless of source title matching.

    Args:
        retrieved_chunks: List of chunk dicts with 'text' field
        expected_keywords: Keywords expected to appear in relevant content
        query: The original query (for context)

    Returns:
        Tuple of (relevance_score, matched_keywords, relevant_chunks)
    """
    if not retrieved_chunks:
        return 0.0, [], []

    # Combine all chunk texts
    all_text = " ".join(chunk.get("text", "") for chunk in retrieved_chunks)
    all_text_lower = all_text.lower()

    # Check keyword coverage
    matched_keywords = [kw for kw in expected_keywords if kw.lower() in all_text_lower]
    keyword_score = len(matched_keywords) / len(expected_keywords) if expected_keywords else 0.0

    # Check query term coverage (do chunks contain query-relevant terms?)
    query_words = _get_significant_words(query)
    query_in_chunks = sum(1 for w in query_words if w in all_text_lower)
    query_coverage = query_in_chunks / len(query_words) if query_words else 0.0

    # Identify which chunks are actually relevant (contain keywords or query terms)
    relevant_chunks = []
    for chunk in retrieved_chunks:
        chunk_text = chunk.get("text", "").lower()
        has_keyword = any(kw.lower() in chunk_text for kw in expected_keywords)
        has_query_term = any(w in chunk_text for w in query_words)
        if has_keyword or has_query_term:
            relevant_chunks.append(chunk)

    # Combined relevance score (weighted)
    # 60% keyword coverage, 40% query term coverage
    relevance_score = (keyword_score * 0.6) + (query_coverage * 0.4)

    return relevance_score, matched_keywords, relevant_chunks


def calculate_chunk_topic_match(
    chunk_text: str,
    expected_topic: str,
    threshold: float = 0.3,
) -> bool:
    """
    Check if a chunk's content matches an expected topic.

    This is more robust than title matching - it checks if the chunk
    DISCUSSES the expected topic, not just if the source title matches.

    Args:
        chunk_text: The text content of the chunk
        expected_topic: The topic we expect (e.g., "Dandruff")
        threshold: Minimum word overlap for a match

    Returns:
        True if the chunk discusses the expected topic
    """
    chunk_lower = chunk_text.lower()
    topic_lower = expected_topic.lower()

    # Direct mention check
    if topic_lower in chunk_lower:
        return True

    # Word overlap check
    topic_words = _get_significant_words(expected_topic)
    chunk_words = _get_significant_words(chunk_text)

    if not topic_words:
        return False

    overlap = len(topic_words & chunk_words) / len(topic_words)
    return overlap >= threshold


def _fuzzy_title_match(expected: str, retrieved: str, threshold: float = 0.5) -> bool:
    """
    Check if two titles match using multiple strategies:
    1. Substring containment
    2. Significant word overlap (Jaccard similarity)
    """
    expected_lower = expected.lower()
    retrieved_lower = retrieved.lower()

    # Strategy 1: Substring match (either direction)
    if expected_lower in retrieved_lower or retrieved_lower in expected_lower:
        return True

    # Strategy 2: Significant word overlap
    expected_words = _get_significant_words(expected)
    retrieved_words = _get_significant_words(retrieved)

    if not expected_words:
        return False

    # Calculate Jaccard-like similarity (intersection / smaller set)
    intersection = expected_words & retrieved_words
    similarity = len(intersection) / min(len(expected_words), len(retrieved_words)) if expected_words and retrieved_words else 0

    return similarity >= threshold


def calculate_source_hit_rate(
    retrieved_sources: list[str],
    expected_sources: list[str],
) -> float:
    """
    Calculate what percentage of expected sources were found.
    Uses fuzzy matching with word overlap for better accuracy.
    """
    if not expected_sources:
        return 1.0

    hits = 0
    for expected in expected_sources:
        for retrieved in retrieved_sources:
            if _fuzzy_title_match(expected, retrieved):
                hits += 1
                break

    return hits / len(expected_sources)


def determine_failure_mode(
    retrieval: RetrievalMetrics,
    generation: GenerationMetrics,
    thresholds: dict[str, float] | None = None,
) -> FailureMode:
    """
    Determine the failure mode based on metrics.

    Uses CONTENT-BASED relevance as primary retrieval metric (not just source title matching).
    This gives a more accurate picture of whether retrieval actually found useful content.

    Args:
        retrieval: Retrieval metrics
        generation: Generation metrics
        thresholds: Custom thresholds (optional)

    Returns:
        FailureMode enum value
    """
    if thresholds is None:
        thresholds = {
            "retrieval_good": 0.5,  # At least 50% content relevance OR source hit
            "generation_good": 0.5,  # At least 50% expected keywords in answer
        }

    # PRIMARY: Use content_relevance (does content actually answer the question?)
    # FALLBACK: Use source_hit_rate or keyword_coverage
    # This fixes false negatives where content is relevant but source titles don't match
    retrieval_score = max(
        retrieval.content_relevance,
        retrieval.source_hit_rate,
        retrieval.keyword_coverage,
    )
    retrieval_good = retrieval_score >= thresholds["retrieval_good"]
    generation_good = generation.answer_relevance >= thresholds["generation_good"]

    if retrieval_good and generation_good:
        return FailureMode.NO_FAILURE
    elif not retrieval_good and generation_good:
        return FailureMode.RETRIEVAL_FAILURE
    elif retrieval_good and not generation_good:
        return FailureMode.GENERATION_FAILURE
    else:
        return FailureMode.MIXED_FAILURE


@dataclass
class BenchmarkSummary:
    """Summary statistics across all test queries."""

    total_queries: int = 0

    # Retrieval metrics averages
    avg_precision_at_k: float = 0.0
    avg_recall: float = 0.0
    avg_source_hit_rate: float = 0.0
    avg_keyword_coverage: float = 0.0
    avg_content_relevance: float = 0.0  # NEW: Content-based relevance

    # Generation metrics averages
    avg_answer_relevance: float = 0.0
    avg_faithfulness: float = 0.0

    # Failure mode breakdown
    failure_counts: dict[str, int] = field(default_factory=dict)
    failure_percentages: dict[str, float] = field(default_factory=dict)

    # By query type
    by_query_type: dict[str, dict[str, float]] = field(default_factory=dict)

    # By difficulty
    by_difficulty: dict[str, dict[str, float]] = field(default_factory=dict)

    # Timing
    avg_retrieval_time_ms: float = 0.0
    avg_generation_time_ms: float = 0.0
    avg_total_time_ms: float = 0.0


def aggregate_results(results: list[EvaluationResult]) -> BenchmarkSummary:
    """
    Aggregate individual evaluation results into summary statistics.

    Args:
        results: List of individual evaluation results

    Returns:
        BenchmarkSummary with aggregated statistics
    """
    if not results:
        return BenchmarkSummary()

    summary = BenchmarkSummary(total_queries=len(results))

    # Calculate averages
    summary.avg_precision_at_k = sum(r.retrieval.precision_at_k for r in results) / len(results)
    summary.avg_recall = sum(r.retrieval.recall for r in results) / len(results)
    summary.avg_source_hit_rate = sum(r.retrieval.source_hit_rate for r in results) / len(results)
    summary.avg_keyword_coverage = sum(r.retrieval.keyword_coverage for r in results) / len(results)
    summary.avg_content_relevance = sum(r.retrieval.content_relevance for r in results) / len(results)

    summary.avg_answer_relevance = sum(r.generation.answer_relevance for r in results) / len(results)

    # Count failure modes
    for mode in FailureMode:
        count = sum(1 for r in results if r.failure_mode == mode)
        summary.failure_counts[mode.value] = count
        summary.failure_percentages[mode.value] = count / len(results) * 100

    # By query type
    query_types = set(r.query_type for r in results)
    for qt in query_types:
        qt_results = [r for r in results if r.query_type == qt]
        if qt_results:
            summary.by_query_type[qt] = {
                "count": len(qt_results),
                "avg_source_hit_rate": sum(r.retrieval.source_hit_rate for r in qt_results) / len(qt_results),
                "avg_answer_relevance": sum(r.generation.answer_relevance for r in qt_results) / len(qt_results),
                "success_rate": sum(1 for r in qt_results if r.failure_mode == FailureMode.NO_FAILURE) / len(qt_results) * 100,
            }

    # By difficulty
    difficulties = set(r.difficulty for r in results)
    for diff in difficulties:
        diff_results = [r for r in results if r.difficulty == diff]
        if diff_results:
            summary.by_difficulty[diff] = {
                "count": len(diff_results),
                "avg_source_hit_rate": sum(r.retrieval.source_hit_rate for r in diff_results) / len(diff_results),
                "avg_answer_relevance": sum(r.generation.answer_relevance for r in diff_results) / len(diff_results),
                "success_rate": sum(1 for r in diff_results if r.failure_mode == FailureMode.NO_FAILURE) / len(diff_results) * 100,
            }

    # Timing
    summary.avg_retrieval_time_ms = sum(r.retrieval_time_ms for r in results) / len(results)
    summary.avg_generation_time_ms = sum(r.generation_time_ms for r in results) / len(results)
    summary.avg_total_time_ms = sum(r.total_time_ms for r in results) / len(results)

    return summary
