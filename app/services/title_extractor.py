"""
Document Title Extraction Service

Hybrid regex + LLM system for extracting document titles and authors
from the first chunks of documents.

Features:
- Regex-based fast extraction (regex patterns for different document types)
- LLM-based accurate extraction (fallback for complex documents)
- Confidence scoring
- Configurable thresholds
- Comprehensive logging
"""

import logging
import json
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple
from enum import Enum

from openai import AsyncOpenAI
from app.config import config

logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Methods for title extraction"""
    REGEX = "regex"
    LLM = "llm"
    HYBRID = "hybrid"


@dataclass
class ExtractionResult:
    """Result of title extraction attempt"""
    document_id: str
    original_title: str
    extracted_title: str
    extracted_author: Optional[str] = None
    extracted_year: Optional[int] = None
    confidence: float = 0.0
    method: str = "regex"
    error: Optional[str] = None
    processing_time_ms: int = 0
    chunks_used: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    def __str__(self) -> str:
        """String representation"""
        return (
            f"{self.extracted_title or 'N/A'} "
            f"({self.method}, confidence: {self.confidence:.2f})"
        )


class RegexTitleExtractor:
    """Fast regex-based title extraction"""

    # Regex patterns for different document types
    # Order matters: more specific patterns first
    PATTERNS = [
        # Academic papers: Title on first line, Author on second
        {
            "name": "academic_paper",
            "title_pattern": r"^([A-Z][A-Za-z\s\d\-:'\(\)\.]+?)(?:\n|$)",
            "author_pattern": r"^(?:by|Author[s]?:?)\s+([A-Z][A-Za-z\s\-\.]+?)(?:\n|$)",
            "confidence_base": 0.95,
        },
        # Books: Often uppercase title
        {
            "name": "book",
            "title_pattern": r"^\s*([A-Z][A-Z\s\-:\']+?)(?:\n|$)",
            "author_pattern": r"^(?:by|[Aa]uthor[s]?:?)\s+([A-Z][A-Za-z\s\-\.]+?)(?:\n|$)",
            "confidence_base": 0.90,
        },
        # Reports: "Title" then "by Author"
        {
            "name": "report",
            "title_pattern": r"^([A-Z][A-Za-z\s\d\-:',\(\)\.]+?)(?:\n|$)",
            "author_pattern": (
                r"^(?:by|Author|Prepared by|Prepared)|(?:\nby\s+([A-Z][A-Za-z\s]+?))"
            ),
            "confidence_base": 0.88,
        },
        # Web articles: Headline with byline
        {
            "name": "article",
            "title_pattern": r"^(?:\*{2,}|##|###)?\s*([A-Z][A-Za-z\s\d\-:',\(\)]+?)(?:\*{2,}|##|###)?",
            "author_pattern": r"^by\s+([A-Z][A-Za-z\s]+?)\s+(?:•|-|\||on|,)",
            "confidence_base": 0.85,
        },
        # Generic fallback: First substantive line
        {
            "name": "generic",
            "title_pattern": r"^(?!\s*$)(?![\(\[])((?:[A-Z][a-z]+\s+){3,}[A-Z][a-z]*)",
            "author_pattern": r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s+(?:and|&|\d{4})",
            "confidence_base": 0.70,
        },
    ]

    def extract(self, text: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Extract title and author from text using regex patterns

        Args:
            text: Document text (first 1-2 chunks)

        Returns:
            Tuple of (title, author, confidence) or (None, None, 0) if not found
        """
        if not text or len(text.strip()) < 10:
            return None, None, 0.0

        text_lines = text.split("\n")[:5]  # Check first 5 lines
        text_section = "\n".join(text_lines)

        for pattern_set in self.PATTERNS:
            # Try title extraction
            title_match = re.search(
                pattern_set["title_pattern"],
                text_section,
                re.MULTILINE | re.IGNORECASE,
            )

            if title_match:
                title = title_match.group(1).strip()

                # Validate title
                if not self._is_valid_title(title):
                    continue

                # Try author extraction
                author = None
                author_match = re.search(
                    pattern_set["author_pattern"],
                    text_section,
                    re.MULTILINE | re.IGNORECASE,
                )
                if author_match:
                    try:
                        author = author_match.group(1).strip()
                    except IndexError:
                        author = None

                # Calculate confidence
                confidence = self._calculate_confidence(
                    title,
                    author,
                    pattern_set["confidence_base"],
                )

                logger.debug(
                    f"Regex extraction ({pattern_set['name']}): "
                    f"title='{title[:50]}', author='{author}', "
                    f"confidence={confidence:.2f}"
                )

                return title, author, confidence

        logger.debug("No regex pattern matched for title extraction")
        return None, None, 0.0

    @staticmethod
    def _is_valid_title(title: str) -> bool:
        """Check if extracted title seems valid"""
        if not title or len(title) < 5 or len(title) > 200:
            return False

        # Should have mostly letters/numbers, not too many special chars
        special_count = sum(1 for c in title if c in "|\\/:*?\"<>")
        if special_count > 2:
            return False

        # Should have at least 2 words (spaces)
        if title.count(" ") < 1:
            return False

        return True

    @staticmethod
    def _calculate_confidence(
        title: str, author: Optional[str], base_confidence: float
    ) -> float:
        """Calculate confidence score based on extraction quality"""
        confidence = base_confidence

        # Length validation
        if len(title) < 10 or len(title) > 150:
            confidence *= 0.8

        # Author bonus
        if author and len(author) > 3:
            confidence = min(1.0, confidence + 0.10)

        # Suspicious characters penalty
        suspicious = title.count("|") + title.count("\\") + title.count("/")
        confidence *= 1 - (suspicious * 0.15)

        # Capital letter ratio check
        capital_ratio = sum(1 for c in title if c.isupper()) / len(title)
        if capital_ratio < 0.15 or capital_ratio > 0.85:
            confidence *= 0.9

        return max(0.0, min(1.0, confidence))


class LLMTitleExtractor:
    """LLM-based title extraction using Claude"""

    EXTRACTION_PROMPT = """You are a document analysis system. Extract metadata from the provided text.

TEXT:
{text}

Extract the following information from the document:
1. Document title (the main title/heading at the beginning)
2. Author name(s) if available
3. Publication year if available
4. Document type (book, paper, report, article, etc.)

Respond ONLY with valid JSON, no other text:
{{
    "title": "Exact title from document, or null if not found",
    "author": "Author name(s), or null if not found",
    "year": 2025 or null,
    "document_type": "book|paper|report|article|other"
}}

If any field cannot be determined, use null.
The title should be the primary heading, not section titles.
Extract only what is explicitly shown in the text."""

    def __init__(self):
        """Initialize LLM extractor"""
        self.client = AsyncOpenAI()

    async def extract(self, text: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Extract title and author from text using Claude

        Args:
            text: Document text (first 2-3 chunks)

        Returns:
            Tuple of (title, author, confidence)
        """
        if not text or len(text.strip()) < 50:
            return None, None, 0.0

        try:
            prompt = self.EXTRACTION_PROMPT.format(text=text[:3000])  # Limit text

            response = await self.client.chat.completions.create(
                model=config.chat.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response - try multiple strategies
            result = None

            # Strategy 1: Direct JSON parsing
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                pass

            # Strategy 2: Strip markdown code block wrapper
            if not result:
                # Remove markdown code block wrapper if present
                cleaned_text = result_text
                if cleaned_text.startswith("```"):
                    # Remove opening ```json or ```
                    cleaned_text = cleaned_text.lstrip("`").lstrip("json").lstrip(" \n\t")
                if cleaned_text.endswith("```"):
                    # Remove closing ```
                    cleaned_text = cleaned_text.rstrip("`").rstrip(" \n\t")

                try:
                    result = json.loads(cleaned_text)
                except json.JSONDecodeError:
                    pass

            # Strategy 3: Extract JSON from response using regex
            if not result:
                # Try to find JSON object in the response
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result_text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

            if not result:
                logger.debug(f"Failed to parse JSON from LLM response: {result_text[:100]}")
                return None, None, 0.0

            title = result.get("title")
            author = result.get("author")

            # Validate extracted data
            if not title or len(title) < 5:
                return None, None, 0.0

            # Calculate confidence (LLM responses have higher base confidence)
            confidence = 0.92
            if author:
                confidence = min(1.0, confidence + 0.05)

            logger.debug(
                f"LLM extraction: title='{title[:50]}', author='{author}', "
                f"confidence={confidence:.2f}"
            )

            return title, author, confidence

        except Exception as e:
            import traceback
            logger.debug(f"LLM extraction exception: {type(e).__name__}: {str(e)}\nTraceback: {traceback.format_exc()}")
            return None, None, 0.0


class HybridTitleExtractor:
    """Hybrid extractor: regex-first, LLM-fallback"""

    def __init__(self, regex_threshold: float = 0.75, llm_enabled: bool = True):
        """
        Initialize hybrid extractor

        Args:
            regex_threshold: Confidence threshold for accepting regex results
            llm_enabled: Whether to use LLM for fallback
        """
        self.regex_extractor = RegexTitleExtractor()
        self.llm_extractor = LLMTitleExtractor() if llm_enabled else None
        self.regex_threshold = regex_threshold

    async def extract(
        self,
        document_id: str,
        original_title: str,
        text: str,
        method: ExtractionMethod = ExtractionMethod.HYBRID,
    ) -> ExtractionResult:
        """
        Extract title using hybrid approach

        Args:
            document_id: Document UUID
            original_title: Original title from database
            text: Document text (first chunks)
            method: Extraction method to use

        Returns:
            ExtractionResult with extracted metadata
        """
        start_time = time.time()

        try:
            if method == ExtractionMethod.REGEX or method == ExtractionMethod.HYBRID:
                # Try regex first
                title, author, confidence = self.regex_extractor.extract(text)
                logger.debug(f"Regex result for {document_id}: confidence={confidence:.2f}, title={title is not None}")

                if confidence >= self.regex_threshold:
                    processing_time = int((time.time() - start_time) * 1000)
                    logger.debug(f"Regex confidence >= threshold, returning regex result")
                    return ExtractionResult(
                        document_id=document_id,
                        original_title=original_title,
                        extracted_title=title or original_title,
                        extracted_author=author,
                        confidence=confidence,
                        method="regex",
                        processing_time_ms=processing_time,
                        chunks_used=1,
                    )

                # If regex not confident enough and LLM enabled, try LLM
                if method == ExtractionMethod.HYBRID and self.llm_extractor:
                    logger.debug(
                        f"Regex confidence {confidence:.2f} < threshold {self.regex_threshold}, "
                        f"trying LLM... (llm_extractor={self.llm_extractor is not None})"
                    )
                    title, author, confidence = await self.llm_extractor.extract(text)
                    logger.debug(f"LLM result for {document_id}: title={title}, confidence={confidence:.2f}")

                    if title:
                        processing_time = int((time.time() - start_time) * 1000)
                        return ExtractionResult(
                            document_id=document_id,
                            original_title=original_title,
                            extracted_title=title,
                            extracted_author=author,
                            confidence=confidence,
                            method="llm",
                            processing_time_ms=processing_time,
                            chunks_used=2,
                        )

            elif method == ExtractionMethod.LLM and self.llm_extractor:
                # Use only LLM
                title, author, confidence = await self.llm_extractor.extract(text)

                if title:
                    processing_time = int((time.time() - start_time) * 1000)
                    return ExtractionResult(
                        document_id=document_id,
                        original_title=original_title,
                        extracted_title=title,
                        extracted_author=author,
                        confidence=confidence,
                        method="llm",
                        processing_time_ms=processing_time,
                        chunks_used=2,
                    )

            # No extraction succeeded
            processing_time = int((time.time() - start_time) * 1000)
            return ExtractionResult(
                document_id=document_id,
                original_title=original_title,
                extracted_title=original_title,
                confidence=0.0,
                method="none",
                error="Extraction failed",
                processing_time_ms=processing_time,
            )

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            logger.error(f"Extraction error for {document_id}: {e}")
            return ExtractionResult(
                document_id=document_id,
                original_title=original_title,
                extracted_title=original_title,
                confidence=0.0,
                method="error",
                error=str(e),
                processing_time_ms=processing_time,
            )


def create_hybrid_extractor(
    regex_threshold: float = 0.75, llm_enabled: bool = True
) -> HybridTitleExtractor:
    """Factory function to create hybrid extractor"""
    return HybridTitleExtractor(
        regex_threshold=regex_threshold, llm_enabled=llm_enabled
    )
