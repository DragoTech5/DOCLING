"""
RAG Evaluation Test Dataset

A diverse set of test queries for evaluating RAG quality across different
query types and complexity levels. Based on analysis of the Docling Knowledge Hub
content (1,457 YouTube transcripts from health/wellness channels).

Query Categories:
1. Simple factual lookups - Direct topic questions
2. Complex multi-hop - Require connecting info from multiple sources
3. Ambiguous queries - Vague or could have multiple interpretations
4. Domain-specific terminology - Technical/specialized terms
5. Comparison queries - Compare concepts or approaches
6. Negative queries - Topics NOT in knowledge base (should yield "not found")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QueryType(Enum):
    SIMPLE_FACTUAL = "simple_factual"
    MULTI_HOP = "multi_hop"
    AMBIGUOUS = "ambiguous"
    DOMAIN_SPECIFIC = "domain_specific"
    COMPARISON = "comparison"
    NEGATIVE = "negative"  # Not in knowledge base


class DifficultyLevel(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class TestQuery:
    """A single test query with ground truth for evaluation."""

    id: str
    query: str
    query_type: QueryType
    difficulty: DifficultyLevel

    # Ground truth for retrieval evaluation
    expected_source_titles: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)

    # For answer quality evaluation
    expected_answer_contains: list[str] = field(default_factory=list)
    expected_answer_not_contains: list[str] = field(default_factory=list)

    # Whether answer should indicate "not found" / "no information"
    should_not_find: bool = False

    notes: Optional[str] = None


# Test Dataset - 30 queries covering all categories
TEST_QUERIES: list[TestQuery] = [
    # ============================================
    # SIMPLE FACTUAL QUERIES (6 queries)
    # ============================================
    TestQuery(
        id="sf_001",
        query="What causes dandruff?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["Dandruff"],
        expected_keywords=["shampoo", "scalp", "inflammation"],
        expected_answer_contains=["shampoo", "scalp"],
    ),
    TestQuery(
        id="sf_002",
        query="What is the self-healing protocol?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["How strict we have to be with the SHP", "Explaining the Self Healer's Protocol", "How to start the SHP safely"],
        expected_keywords=["SHP", "protocol", "healing", "plasma"],
        expected_answer_contains=["protocol", "plasma"],
    ),
    TestQuery(
        id="sf_003",
        query="What does he say about salt?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["Kidneys and salt", "Hypertension and salt", "Hypertension, arrhythmia & salt"],
        expected_keywords=["salt", "minerals", "blood", "hydration"],
        expected_answer_contains=["salt"],
    ),
    TestQuery(
        id="sf_004",
        query="How to deal with parasites?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["How to deal with parasites?"],
        expected_keywords=["parasites", "cleanse", "detox"],
        expected_answer_contains=["parasites"],
    ),
    TestQuery(
        id="sf_005",
        query="What causes hair loss?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["Male Pattern Baldness and Alopecia-An alternative theory", "Why so many young men bald today and suffer from Male Pattern Baldness"],
        expected_keywords=["hair", "loss", "bald", "natural"],
        expected_answer_contains=["hair"],
    ),
    TestQuery(
        id="sf_006",
        query="What is plasma water?",
        query_type=QueryType.SIMPLE_FACTUAL,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=["Natural Healing Part 3  Water and Plasma", "Plasma and water retention"],
        expected_keywords=["plasma", "water", "minerals", "salt"],
        expected_answer_contains=["plasma", "water"],
    ),

    # ============================================
    # COMPLEX MULTI-HOP QUERIES (5 queries)
    # ============================================
    TestQuery(
        id="mh_001",
        query="How does hydration affect blood pressure and kidney function?",
        query_type=QueryType.MULTI_HOP,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Hypertension and salt", "Kidneys and salt", "Natural Health Part 4 Hydration and cleansing"],
        expected_keywords=["hydration", "blood pressure", "kidney", "plasma", "salt"],
        expected_answer_contains=["hydration", "kidney"],
    ),
    TestQuery(
        id="mh_002",
        query="What's the connection between diet, detox and skin problems?",
        query_type=QueryType.MULTI_HOP,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Pimples, blackheads, and scars", "The dynamics of cleansing", "Eczema, atopic dermatitis"],
        expected_keywords=["diet", "detox", "skin", "cleansing", "toxins"],
        expected_answer_contains=["skin", "detox"],
    ),
    TestQuery(
        id="mh_003",
        query="How do fasting and frequency affect healing?",
        query_type=QueryType.MULTI_HOP,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Dry fasting", "How to raise our frequency", "Cleanse and raise your frequency"],
        expected_keywords=["fasting", "frequency", "healing", "cleanse"],
        expected_answer_contains=["fasting", "frequency"],
    ),
    TestQuery(
        id="mh_004",
        query="What role does the lymphatic system play in detoxification and immunity?",
        query_type=QueryType.MULTI_HOP,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Lymphatic system", "Swollen lymph nodes", "Do you have a weak immune system"],
        expected_keywords=["lymphatic", "detox", "immune", "lymph"],
        expected_answer_contains=["lymph"],
    ),
    TestQuery(
        id="mh_005",
        query="How are hormones, thyroid and energy levels connected?",
        query_type=QueryType.MULTI_HOP,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Thyroid and hormonal activity", "Energy distribution and health", "Adrenal insufficiency & thyroid problems"],
        expected_keywords=["hormones", "thyroid", "energy", "adrenal"],
        expected_answer_contains=["thyroid", "hormone"],
    ),

    # ============================================
    # AMBIGUOUS QUERIES (5 queries)
    # ============================================
    TestQuery(
        id="amb_001",
        query="What about water?",
        query_type=QueryType.AMBIGUOUS,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=[],  # Could match many topics
        expected_keywords=["water", "hydration", "plasma", "distilled"],
        expected_answer_contains=["water"],
        notes="Very vague - should still retrieve relevant water-related content",
    ),
    TestQuery(
        id="amb_002",
        query="Is it good?",
        query_type=QueryType.AMBIGUOUS,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        notes="Too vague - system should ask for clarification or indicate ambiguity",
    ),
    TestQuery(
        id="amb_003",
        query="Tell me about the protocol",
        query_type=QueryType.AMBIGUOUS,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["How strict we have to be with the SHP"],
        expected_keywords=["protocol", "SHP", "self-healing"],
        expected_answer_contains=["protocol"],
        notes="Assumes 'the protocol' refers to SHP",
    ),
    TestQuery(
        id="amb_004",
        query="What's the problem?",
        query_type=QueryType.AMBIGUOUS,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        notes="Too vague without context",
    ),
    TestQuery(
        id="amb_005",
        query="How to fix it?",
        query_type=QueryType.AMBIGUOUS,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        notes="No context for what 'it' refers to",
    ),

    # ============================================
    # DOMAIN-SPECIFIC TERMINOLOGY (5 queries)
    # ============================================
    TestQuery(
        id="dom_001",
        query="What is erythematous condition?",
        query_type=QueryType.DOMAIN_SPECIFIC,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Erythematous, skin redness"],
        expected_keywords=["erythematous", "skin", "redness", "inflammation"],
        expected_answer_contains=["erythematous", "skin"],
    ),
    TestQuery(
        id="dom_002",
        query="Explain gastroparesis",
        query_type=QueryType.DOMAIN_SPECIFIC,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Gastroparesis, slow digestion"],
        expected_keywords=["gastroparesis", "digestion", "stomach"],
        expected_answer_contains=["gastroparesis", "digestion"],
    ),
    TestQuery(
        id="dom_003",
        query="What is Stevens Johnson syndrome?",
        query_type=QueryType.DOMAIN_SPECIFIC,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Stevens Johnson syndrome"],
        expected_keywords=["Stevens Johnson", "syndrome", "skin"],
        expected_answer_contains=["Stevens Johnson"],
    ),
    TestQuery(
        id="dom_004",
        query="Tell me about hemochromatosis",
        query_type=QueryType.DOMAIN_SPECIFIC,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Hemochromatosis and anemia"],
        expected_keywords=["hemochromatosis", "iron", "blood"],
        expected_answer_contains=["hemochromatosis"],
    ),
    TestQuery(
        id="dom_005",
        query="What is xanthelasma?",
        query_type=QueryType.DOMAIN_SPECIFIC,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Xanthelasma"],
        expected_keywords=["xanthelasma", "cholesterol", "skin"],
        expected_answer_contains=["xanthelasma"],
    ),

    # ============================================
    # COMPARISON QUERIES (5 queries)
    # ============================================
    TestQuery(
        id="cmp_001",
        query="What's the difference between organic and inorganic minerals?",
        query_type=QueryType.COMPARISON,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Organic versus inorganic minerals"],
        expected_keywords=["organic", "inorganic", "minerals"],
        expected_answer_contains=["organic", "inorganic"],
    ),
    TestQuery(
        id="cmp_002",
        query="Compare fat and protein importance in diet",
        query_type=QueryType.COMPARISON,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["What is more important, fat or protein?"],
        expected_keywords=["fat", "protein", "diet"],
        expected_answer_contains=["fat", "protein"],
    ),
    TestQuery(
        id="cmp_003",
        query="Carnivore diet vs vegan diet",
        query_type=QueryType.COMPARISON,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Carnivore diet side effects explained", "If you want to be a healthy vegan, do this"],
        expected_keywords=["carnivore", "vegan", "diet"],
        expected_answer_contains=["carnivore", "vegan"],
    ),
    TestQuery(
        id="cmp_004",
        query="Big pharma vs supplement industry",
        query_type=QueryType.COMPARISON,
        difficulty=DifficultyLevel.MEDIUM,
        expected_source_titles=["Big pharma versus the supplement industry"],
        expected_keywords=["pharma", "supplement", "industry"],
        expected_answer_contains=["pharma", "supplement"],
    ),
    TestQuery(
        id="cmp_005",
        query="Hypertension vs pulmonary hypertension",
        query_type=QueryType.COMPARISON,
        difficulty=DifficultyLevel.HARD,
        expected_source_titles=["Hypertension revisited", "Pulmonary hypertension"],
        expected_keywords=["hypertension", "pulmonary", "blood pressure"],
        expected_answer_contains=["hypertension", "pulmonary"],
    ),

    # ============================================
    # NEGATIVE QUERIES - Not in knowledge base (4 queries)
    # ============================================
    TestQuery(
        id="neg_001",
        query="What is the latest iPhone model?",
        query_type=QueryType.NEGATIVE,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        should_not_find=True,
        notes="Completely unrelated to health content",
    ),
    TestQuery(
        id="neg_002",
        query="How to code in Python?",
        query_type=QueryType.NEGATIVE,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        should_not_find=True,
        notes="Programming - not in knowledge base",
    ),
    TestQuery(
        id="neg_003",
        query="What happened in World War 2?",
        query_type=QueryType.NEGATIVE,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        should_not_find=True,
        notes="History - not in knowledge base",
    ),
    TestQuery(
        id="neg_004",
        query="Recipe for chocolate cake",
        query_type=QueryType.NEGATIVE,
        difficulty=DifficultyLevel.EASY,
        expected_source_titles=[],
        expected_keywords=[],
        expected_answer_contains=[],
        should_not_find=True,
        notes="Cooking recipe - not in knowledge base",
    ),
]


def get_queries_by_type(query_type: QueryType) -> list[TestQuery]:
    """Get all test queries of a specific type."""
    return [q for q in TEST_QUERIES if q.query_type == query_type]


def get_queries_by_difficulty(difficulty: DifficultyLevel) -> list[TestQuery]:
    """Get all test queries of a specific difficulty level."""
    return [q for q in TEST_QUERIES if q.difficulty == difficulty]


def get_all_queries() -> list[TestQuery]:
    """Get all test queries."""
    return TEST_QUERIES.copy()


def get_query_by_id(query_id: str) -> Optional[TestQuery]:
    """Get a specific test query by ID."""
    for q in TEST_QUERIES:
        if q.id == query_id:
            return q
    return None
