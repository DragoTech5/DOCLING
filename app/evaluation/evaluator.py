"""
RAG Evaluation Harness

Runs test queries through the RAG system and calculates metrics.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.config import config
from app.core.embeddings import generate_embeddings
from app.db.vector_store import query_documents
from app.db import repository
from app.services.chat_service import (
    retrieve_relevant_chunks_with_confidence,
    format_context_with_sources,
    build_messages,
    get_openai_client,
)
from app.services.rag_enhancements import RetrievalConfidence

from .test_dataset import TestQuery, get_all_queries, QueryType
from .metrics import (
    RetrievalMetrics,
    GenerationMetrics,
    EvaluationResult,
    BenchmarkSummary,
    FailureMode,
    calculate_precision_at_k,
    calculate_recall,
    calculate_keyword_coverage,
    calculate_source_hit_rate,
    calculate_content_relevance,
    determine_failure_mode,
    aggregate_results,
    _fuzzy_title_match,
)

logger = logging.getLogger(__name__)


async def evaluate_single_query(
    test_query: TestQuery,
    n_chunks: int = 8,
    skip_generation: bool = False,
    use_enhancements: bool = True,
) -> EvaluationResult:
    """
    Evaluate a single test query through the RAG pipeline.

    Args:
        test_query: The test query to evaluate
        n_chunks: Number of chunks to retrieve
        skip_generation: If True, skip the LLM generation step (faster, retrieval-only eval)
        use_enhancements: If True, use RAG enhancements (HyDE, decomposition, reranking)

    Returns:
        EvaluationResult with all metrics
    """
    result = EvaluationResult(
        query_id=test_query.id,
        query=test_query.query,
        query_type=test_query.query_type.value,
        difficulty=test_query.difficulty.value,
        retrieval=RetrievalMetrics(),
        generation=GenerationMetrics(),
    )

    # ==================
    # RETRIEVAL PHASE
    # ==================
    start_time = time.time()

    try:
        chunks, confidence = await retrieve_relevant_chunks_with_confidence(
            query=test_query.query,
            n_results=n_chunks,
            use_enhancements=use_enhancements,
        )
        result.retrieved_chunks = chunks
        result.retrieval_time_ms = (time.time() - start_time) * 1000

        # Extract source titles from retrieved chunks
        retrieved_sources = []
        chunk_texts = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            title = metadata.get("title", "Unknown")
            retrieved_sources.append(title)
            chunk_texts.append(chunk.get("text", ""))

        combined_chunk_text = " ".join(chunk_texts)

        # Calculate retrieval metrics
        result.retrieval.retrieved_sources = retrieved_sources
        result.retrieval.expected_sources = test_query.expected_source_titles
        result.retrieval.chunks_retrieved = len(chunks)

        # Precision@K
        result.retrieval.precision_at_k = calculate_precision_at_k(
            retrieved_sources,
            test_query.expected_source_titles,
        )

        # Recall
        result.retrieval.recall = calculate_recall(
            retrieved_sources,
            test_query.expected_source_titles,
        )

        # Source hit rate (fuzzy matching)
        result.retrieval.source_hit_rate = calculate_source_hit_rate(
            retrieved_sources,
            test_query.expected_source_titles,
        )

        # Keyword coverage in retrieved chunks
        coverage, matched = calculate_keyword_coverage(
            combined_chunk_text,
            test_query.expected_keywords,
        )
        result.retrieval.keyword_coverage = coverage
        result.retrieval.matched_keywords = matched

        # Average similarity
        similarities = [c.get("similarity", 0) for c in chunks]
        result.retrieval.avg_similarity = sum(similarities) / len(similarities) if similarities else 0

        # Track matched sources using improved fuzzy matching
        result.retrieval.matched_sources = [
            s for s in test_query.expected_source_titles
            if any(_fuzzy_title_match(s, r) for r in retrieved_sources)
        ]

        # NEW: Calculate content-based relevance (the key fix!)
        # This measures if retrieved content actually answers the question,
        # regardless of whether source titles match
        content_rel, content_keywords, relevant_chunks = calculate_content_relevance(
            retrieved_chunks=chunks,
            expected_keywords=test_query.expected_keywords,
            query=test_query.query,
        )
        result.retrieval.content_relevance = content_rel
        result.retrieval.relevant_chunk_count = len(relevant_chunks)

        # Update matched_keywords to include content-based matches
        all_matched_keywords = list(set(matched + content_keywords))
        result.retrieval.matched_keywords = all_matched_keywords

    except Exception as e:
        logger.error(f"Retrieval failed for query {test_query.id}: {e}")
        result.notes = f"Retrieval error: {str(e)}"
        result.failure_mode = FailureMode.RETRIEVAL_FAILURE
        return result

    # ==================
    # GENERATION PHASE
    # ==================
    if not skip_generation:
        gen_start_time = time.time()

        try:
            # Format context
            context, sources = await format_context_with_sources(chunks)
            result.sources_cited = [
                {
                    "title": s.title,
                    "source_type": s.source_type,
                    "source_url": s.source_url,
                }
                for s in sources
            ]

            # Build messages (empty history for isolated test)
            # Pass confidence for enhanced system prompt on low-confidence queries
            messages = build_messages(
                conversation_history=[],
                user_message=test_query.query,
                context=context,
                confidence=confidence if use_enhancements else None,
            )

            # Call OpenAI
            client = get_openai_client()
            response = await client.chat.completions.create(
                model=config.chat.model,
                messages=messages,
                max_tokens=config.chat.max_tokens,
                temperature=0.3,  # Lower temperature for consistent eval
            )

            answer = response.choices[0].message.content or ""
            result.answer = answer
            result.generation_time_ms = (time.time() - gen_start_time) * 1000

            # Calculate generation metrics
            result.generation.answer_length = len(answer)

            # Answer relevance - check for expected content
            if test_query.should_not_find:
                # For negative queries, check if answer indicates "not found"
                not_found_phrases = [
                    "not found", "no information", "doesn't mention",
                    "not discussed", "no relevant", "cannot find",
                    "doesn't appear", "not in the knowledge base",
                    "couldn't find", "could not find", "don't have information",
                    "isn't covered", "is not covered", "no data",
                ]
                answer_lower = answer.lower()
                found_negative = any(phrase in answer_lower for phrase in not_found_phrases)
                result.generation.negative_handling = 1.0 if found_negative else 0.0
                result.generation.answer_relevance = result.generation.negative_handling
            else:
                # Check for expected answer content
                relevance, found_keywords = calculate_keyword_coverage(
                    answer,
                    test_query.expected_answer_contains,
                )
                result.generation.answer_relevance = relevance
                result.generation.keywords_found = found_keywords

        except Exception as e:
            logger.error(f"Generation failed for query {test_query.id}: {e}")
            result.notes += f" Generation error: {str(e)}"
            result.generation_time_ms = (time.time() - gen_start_time) * 1000

    # Calculate total time
    result.total_time_ms = result.retrieval_time_ms + result.generation_time_ms

    # Determine failure mode
    result.failure_mode = determine_failure_mode(result.retrieval, result.generation)

    return result


async def run_evaluation(
    queries: list[TestQuery] | None = None,
    n_chunks: int = 8,
    skip_generation: bool = False,
    parallel: bool = False,
    max_concurrent: int = 5,
    use_enhancements: bool = True,
) -> tuple[list[EvaluationResult], BenchmarkSummary]:
    """
    Run evaluation on a set of test queries.

    Args:
        queries: List of test queries (None = use all)
        n_chunks: Number of chunks to retrieve per query
        skip_generation: Skip LLM generation (retrieval-only eval)
        parallel: Run queries in parallel
        max_concurrent: Max concurrent queries if parallel
        use_enhancements: If True, use RAG enhancements (HyDE, decomposition, reranking)

    Returns:
        Tuple of (list of results, summary statistics)
    """
    if queries is None:
        queries = get_all_queries()

    mode = "enhanced" if use_enhancements else "baseline"
    logger.info(f"Starting {mode} evaluation of {len(queries)} queries...")

    results = []

    if parallel:
        # Run in parallel with semaphore
        semaphore = asyncio.Semaphore(max_concurrent)

        async def eval_with_semaphore(q: TestQuery) -> EvaluationResult:
            async with semaphore:
                return await evaluate_single_query(q, n_chunks, skip_generation, use_enhancements)

        tasks = [eval_with_semaphore(q) for q in queries]
        results = await asyncio.gather(*tasks)
    else:
        # Run sequentially
        for i, query in enumerate(queries):
            logger.info(f"Evaluating query {i+1}/{len(queries)}: {query.id}")
            result = await evaluate_single_query(query, n_chunks, skip_generation, use_enhancements)
            results.append(result)

    # Aggregate results
    summary = aggregate_results(results)

    logger.info(f"Evaluation complete. Success rate: {summary.failure_percentages.get('no_failure', 0):.1f}%")

    return results, summary


def save_results(
    results: list[EvaluationResult],
    summary: BenchmarkSummary,
    output_dir: str = "app/evaluation/results",
) -> str:
    """
    Save evaluation results to JSON files.

    Args:
        results: List of evaluation results
        summary: Benchmark summary
        output_dir: Directory to save results

    Returns:
        Path to the saved summary file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Save detailed results
    results_file = output_path / f"results_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2, default=str)

    # Save summary
    summary_file = output_path / f"summary_{timestamp}.json"
    with open(summary_file, "w") as f:
        json.dump(asdict(summary), f, indent=2, default=str)

    logger.info(f"Results saved to {output_path}")

    return str(summary_file)


def print_summary(summary: BenchmarkSummary) -> None:
    """Print a formatted summary of the benchmark results."""
    print("\n" + "=" * 60)
    print("RAG EVALUATION SUMMARY")
    print("=" * 60)

    print(f"\nTotal Queries: {summary.total_queries}")

    print("\n--- RETRIEVAL METRICS ---")
    print(f"Avg Content Relevance: {summary.avg_content_relevance:.2%}  ← PRIMARY METRIC")
    print(f"Avg Keyword Coverage:  {summary.avg_keyword_coverage:.2%}")
    print(f"Avg Source Hit Rate:   {summary.avg_source_hit_rate:.2%}  (title matching)")
    print(f"Avg Precision@K:       {summary.avg_precision_at_k:.2%}")
    print(f"Avg Recall:            {summary.avg_recall:.2%}")

    print("\n--- GENERATION METRICS ---")
    print(f"Avg Answer Relevance: {summary.avg_answer_relevance:.2%}")

    print("\n--- FAILURE MODE BREAKDOWN ---")
    for mode, pct in summary.failure_percentages.items():
        count = summary.failure_counts[mode]
        print(f"  {mode}: {count} ({pct:.1f}%)")

    print("\n--- BY QUERY TYPE ---")
    for qt, stats in summary.by_query_type.items():
        print(f"  {qt}:")
        print(f"    Count: {stats['count']}")
        print(f"    Source Hit Rate: {stats['avg_source_hit_rate']:.2%}")
        print(f"    Answer Relevance: {stats['avg_answer_relevance']:.2%}")
        print(f"    Success Rate: {stats['success_rate']:.1f}%")

    print("\n--- BY DIFFICULTY ---")
    for diff, stats in summary.by_difficulty.items():
        print(f"  {diff}:")
        print(f"    Count: {stats['count']}")
        print(f"    Success Rate: {stats['success_rate']:.1f}%")

    print("\n--- TIMING ---")
    print(f"Avg Retrieval Time: {summary.avg_retrieval_time_ms:.0f}ms")
    print(f"Avg Generation Time: {summary.avg_generation_time_ms:.0f}ms")
    print(f"Avg Total Time: {summary.avg_total_time_ms:.0f}ms")

    print("\n" + "=" * 60)


# CLI entry point
async def main():
    """Run evaluation from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="RAG Evaluation Harness")
    parser.add_argument("--queries", type=str, help="Comma-separated query IDs to run (default: all)")
    parser.add_argument("--chunks", type=int, default=8, help="Number of chunks to retrieve")
    parser.add_argument("--skip-generation", action="store_true", help="Skip LLM generation")
    parser.add_argument("--parallel", action="store_true", help="Run queries in parallel")
    parser.add_argument("--save", action="store_true", help="Save results to file")
    parser.add_argument("--type", type=str, help="Filter by query type")

    args = parser.parse_args()

    # Filter queries if specified
    queries = get_all_queries()

    if args.queries:
        query_ids = args.queries.split(",")
        queries = [q for q in queries if q.id in query_ids]

    if args.type:
        try:
            query_type = QueryType(args.type)
            queries = [q for q in queries if q.query_type == query_type]
        except ValueError:
            print(f"Invalid query type: {args.type}")
            return

    # Run evaluation
    results, summary = await run_evaluation(
        queries=queries,
        n_chunks=args.chunks,
        skip_generation=args.skip_generation,
        parallel=args.parallel,
    )

    # Print summary
    print_summary(summary)

    # Save if requested
    if args.save:
        save_results(results, summary)


if __name__ == "__main__":
    asyncio.run(main())
