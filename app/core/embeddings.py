"""
Embeddings - Text chunking and embedding generation
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from sentence_transformers import SentenceTransformer

from app.config import config


# Global model instance
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or create the embedding model."""
    global _embedding_model

    if _embedding_model is None:
        device = config.embedding.device
        if device == "auto":
            device = None  # Let sentence-transformers decide

        _embedding_model = SentenceTransformer(
            config.embedding.model_name,
            device=device,
        )

    return _embedding_model


@dataclass
class TextChunk:
    """A chunk of text with metadata."""
    text: str
    index: int
    start_char: int
    end_char: int
    metadata: dict[str, Any]


def chunk_text_fixed(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    min_chunk_size: int = 100,
) -> list[TextChunk]:
    """
    Split text into fixed-size chunks with overlap.

    Args:
        text: Text to chunk
        chunk_size: Target size of each chunk in characters
        chunk_overlap: Overlap between consecutive chunks
        min_chunk_size: Minimum chunk size to keep

    Returns:
        List of TextChunk objects
    """
    if not text or len(text) < min_chunk_size:
        if text.strip():
            return [TextChunk(
                text=text.strip(),
                index=0,
                start_char=0,
                end_char=len(text),
                metadata={},
            )]
        return []

    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size

        # If we're past the end, just take the rest
        if end >= len(text):
            chunk_text = text[start:].strip()
            if len(chunk_text) >= min_chunk_size:
                chunks.append(TextChunk(
                    text=chunk_text,
                    index=index,
                    start_char=start,
                    end_char=len(text),
                    metadata={},
                ))
            break

        # Try to break at a sentence boundary
        chunk_text = text[start:end]
        last_period = chunk_text.rfind('. ')
        if last_period > chunk_size // 2:
            end = start + last_period + 1
        else:
            # Try to break at a newline
            last_newline = chunk_text.rfind('\n')
            if last_newline > chunk_size // 2:
                end = start + last_newline
            else:
                # Try to break at a space
                last_space = chunk_text.rfind(' ')
                if last_space > chunk_size // 2:
                    end = start + last_space

        chunk_text = text[start:end].strip()
        if len(chunk_text) >= min_chunk_size:
            chunks.append(TextChunk(
                text=chunk_text,
                index=index,
                start_char=start,
                end_char=end,
                metadata={},
            ))
            index += 1

        # Move start position with overlap
        start = end - chunk_overlap
        if start <= chunks[-1].start_char if chunks else 0:
            start = end

    return chunks


def chunk_text_paragraph(
    text: str,
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
) -> list[TextChunk]:
    """
    Split text into chunks based on paragraphs.

    Args:
        text: Text to chunk
        max_chunk_size: Maximum size of each chunk
        min_chunk_size: Minimum chunk size to keep

    Returns:
        List of TextChunk objects
    """
    # Split on double newlines (paragraphs)
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks = []
    current_chunk = ""
    current_start = 0
    char_pos = 0
    index = 0

    for para in paragraphs:
        if not para:
            continue

        para_len = len(para)

        # If adding this paragraph exceeds max size, save current chunk
        if current_chunk and len(current_chunk) + para_len + 2 > max_chunk_size:
            if len(current_chunk) >= min_chunk_size:
                chunks.append(TextChunk(
                    text=current_chunk,
                    index=index,
                    start_char=current_start,
                    end_char=char_pos,
                    metadata={},
                ))
                index += 1
            current_chunk = ""
            current_start = char_pos

        # Add paragraph to current chunk
        if current_chunk:
            current_chunk += "\n\n" + para
        else:
            current_chunk = para
            current_start = char_pos

        char_pos += para_len + 2  # Account for paragraph separator

    # Add remaining chunk
    if current_chunk and len(current_chunk) >= min_chunk_size:
        chunks.append(TextChunk(
            text=current_chunk,
            index=index,
            start_char=current_start,
            end_char=len(text),
            metadata={},
        ))

    return chunks


def chunk_text_semantic(
    text: str,
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
) -> list[TextChunk]:
    """
    Split text into semantically coherent chunks.

    Uses paragraph-based chunking with heading awareness.
    """
    # Split on headings and paragraphs
    # Headings are lines starting with # or all caps lines
    heading_pattern = r'(?:^#{1,6}\s.+$|^[A-Z][A-Z\s]+$)'

    lines = text.split('\n')
    sections = []
    current_section = ""

    for line in lines:
        # Check if this is a heading
        if re.match(heading_pattern, line.strip(), re.MULTILINE):
            if current_section.strip():
                sections.append(current_section.strip())
            current_section = line + "\n"
        else:
            current_section += line + "\n"

    if current_section.strip():
        sections.append(current_section.strip())

    # Now chunk each section
    chunks = []
    char_pos = 0
    index = 0

    for section in sections:
        section_chunks = chunk_text_paragraph(
            section,
            max_chunk_size=max_chunk_size,
            min_chunk_size=min_chunk_size,
        )

        for chunk in section_chunks:
            chunk.index = index
            chunk.start_char = char_pos + chunk.start_char
            chunk.end_char = char_pos + chunk.end_char
            chunks.append(chunk)
            index += 1

        char_pos += len(section) + 2

    return chunks


def chunk_text(
    text: str,
    strategy: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    min_chunk_size: int | None = None,
) -> list[TextChunk]:
    """
    Split text into chunks using the configured strategy.

    Args:
        text: Text to chunk
        strategy: Chunking strategy (fixed, paragraph, semantic)
        chunk_size: Override chunk size
        chunk_overlap: Override chunk overlap
        min_chunk_size: Override minimum chunk size

    Returns:
        List of TextChunk objects
    """
    cfg = config.chunking

    strategy = strategy or cfg.strategy
    chunk_size = chunk_size or cfg.chunk_size
    chunk_overlap = chunk_overlap or cfg.chunk_overlap
    min_chunk_size = min_chunk_size or cfg.min_chunk_size

    if strategy == "fixed":
        return chunk_text_fixed(text, chunk_size, chunk_overlap, min_chunk_size)
    elif strategy == "paragraph":
        return chunk_text_paragraph(text, chunk_size, min_chunk_size)
    elif strategy == "semantic":
        return chunk_text_semantic(text, chunk_size, min_chunk_size)
    else:
        # Default to paragraph
        return chunk_text_paragraph(text, chunk_size, min_chunk_size)


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: List of texts to embed

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    def _embed():
        model = get_embedding_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    return await asyncio.to_thread(_embed)


async def generate_embedding(text: str) -> list[float]:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed

    Returns:
        Embedding vector
    """
    embeddings = await generate_embeddings([text])
    return embeddings[0] if embeddings else []


def get_embedding_dimension() -> int:
    """Get the dimension of embeddings from the current model."""
    model = get_embedding_model()
    return model.get_sentence_embedding_dimension()
