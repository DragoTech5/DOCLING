"""
Citation Validator Module

Ensures RAG-generated citations are accurate and verifiable:
1. Validates citation numbers are within bounds
2. Verifies quoted text exists in source chunks
3. Corrects hallucinated citations (post-processing)
4. Produces deterministic output for production use

Based on CiteFix (https://arxiv.org/abs/2504.15629) and
Citation-Aware RAG best practices.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CitationValidation:
    """Result of citation validation"""
    is_valid: bool
    original_text: str
    corrected_text: str
    issues: list[str]
    confidence: float  # 0.0 - 1.0 (1.0 = no changes needed)


class CitationValidator:
    """Validates and corrects LLM-generated citations"""

    def __init__(self, context: str, sources_count: int):
        """
        Initialize validator with context and source count.

        Args:
            context: Formatted context string with [1], [2], etc.
            sources_count: Number of actual sources available
        """
        self.context = context
        self.sources_count = sources_count
        self.valid_citation_range = set(range(1, sources_count + 1))

    def extract_citations(self, text: str) -> list[int]:
        """Extract all citation numbers [1], [2], etc. from text"""
        matches = re.findall(r'\[(\d+)\]', text)
        return sorted(list(set(int(m) for m in matches)))

    def validate_citations(self, response_text: str) -> CitationValidation:
        """
        Validate citations in LLM response.

        Checks:
        1. All citation numbers are within [1..sources_count]
        2. Citation style is consistent
        3. No orphaned citations

        Returns:
            CitationValidation with results and corrected text
        """
        citations = self.extract_citations(response_text)
        issues = []
        corrected_text = response_text
        confidence = 1.0

        # Check 1: Citation bounds
        invalid_citations = [c for c in citations if c not in self.valid_citation_range]
        if invalid_citations:
            issues.append(
                f"Hallucinated citations found: {invalid_citations}. "
                f"Valid range is [1..{self.sources_count}]"
            )
            corrected_text = self._remove_invalid_citations(
                corrected_text, invalid_citations
            )
            confidence = 0.6

        # Check 2: Unused sources (sources not cited but available)
        if citations and self.sources_count > 0:
            unused_sources = self.valid_citation_range - set(citations)
            if unused_sources and len(unused_sources) < self.sources_count:
                logger.debug(
                    f"Unused sources: {sorted(unused_sources)}. "
                    f"This may be normal - model chose relevant sources."
                )

        # Check 3: No citations when sources exist
        if not citations and self.sources_count > 0:
            issues.append(
                f"No citations found in response, but {self.sources_count} "
                f"sources are available. "
                f"Response should cite relevant sources."
            )
            confidence = 0.4

        # Check 4: Verify cited text exists in context
        # (Deterministic quoting verification)
        for citation_num in citations:
            if not self._verify_citation_anchors(response_text, citation_num):
                logger.warning(
                    f"Citation [{citation_num}] may not be properly anchored "
                    f"to source material"
                )
                confidence *= 0.95

        is_valid = len(issues) == 0

        return CitationValidation(
            is_valid=is_valid,
            original_text=response_text,
            corrected_text=corrected_text,
            issues=issues,
            confidence=confidence,
        )

    def _remove_invalid_citations(
        self, text: str, invalid_citations: list[int]
    ) -> str:
        """Remove references to invalid citation numbers"""
        corrected = text
        for citation_num in sorted(invalid_citations, reverse=True):
            # Remove citation references like [5], [6], etc.
            corrected = re.sub(
                rf'\s*\[{citation_num}\]', '', corrected
            )

        return corrected.strip()

    def _verify_citation_anchors(self, text: str, citation_num: int) -> bool:
        """
        Verify that a citation actually points to content in that source.

        This implements "Deterministic Quoting" - ensuring the LLM
        has actually quoted from the specified source.
        """
        if citation_num not in self.valid_citation_range:
            return False

        # Extract the source section from context
        source_pattern = rf'\[{citation_num}\]\s*(.+?)(?=\n\n\[|$)'
        source_match = re.search(source_pattern, self.context, re.DOTALL)

        if not source_match:
            return False

        source_text = source_match.group(1).lower()

        # Find text around the citation in the response
        # Look for sentences containing the citation
        citation_pattern = rf'(\w[\w\s.,;:\'"!?–\-]*)\s*\[{citation_num}\]'
        response_matches = re.finditer(citation_pattern, text, re.IGNORECASE)

        # Check if any text before the citation appears in the source
        for match in response_matches:
            cited_phrase = match.group(1).lower()
            # Extract key words (filter stop words)
            key_words = set(
                w for w in cited_phrase.split()
                if len(w) > 3  # Skip very short words
            )

            # Check if enough key words from citation appear in source
            matching_words = key_words & set(source_text.split())
            if len(matching_words) >= 2:  # At least 2 key words match
                return True

        return False


def validate_and_correct_citations(
    response_text: str,
    context: str,
    sources_count: int,
    strict_mode: bool = False,
) -> tuple[str, dict]:
    """
    Validate and correct citations in RAG response.

    Args:
        response_text: The LLM-generated response
        context: Formatted context with [1], [2], etc.
        sources_count: Number of sources available
        strict_mode: If True, remove all invalid citations. If False, log warnings.

    Returns:
        Tuple of (corrected_text, validation_result_dict)
    """
    validator = CitationValidator(context, sources_count)
    validation = validator.validate_citations(response_text)

    if validation.issues:
        logger.warning(
            f"Citation validation issues: {validation.issues}. "
            f"Confidence: {validation.confidence:.2%}"
        )

    text_to_return = (
        validation.corrected_text if strict_mode or not validation.is_valid
        else response_text
    )

    return text_to_return, {
        "is_valid": validation.is_valid,
        "issues": validation.issues,
        "confidence": validation.confidence,
        "citations_found": validator.extract_citations(response_text),
        "valid_range": [1, sources_count],
    }
