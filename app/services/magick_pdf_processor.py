"""
MAGICK PDFs Batch Processor

This module provides:
- Docling hybrid chunking for structure-aware PDF processing
- Metadata extraction (title, author, page count, etc.)
- Batch processing with checkpointing
- OpenAI embedding integration
- PostgreSQL + pgvector storage

This is a NEW service for the MAGICK PDFs collection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling_core.types import DoclingDocument

from app.config import config
from app.services import pgvector_service as pgvector

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ExtractedMetadata:
    """Metadata extracted from a PDF."""
    title: str
    author: str | None
    page_count: int
    file_size_bytes: int
    word_count: int
    toc: list[str] | None
    subjects: list[str] | None
    extra: dict[str, Any]


@dataclass
class ProcessedChunk:
    """A chunk extracted from a PDF."""
    content: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    chunk_type: str  # text, table, figure, heading
    token_count: int
    metadata: dict[str, Any]


@dataclass
class ProcessingProgress:
    """Progress information for batch processing."""
    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    current_file: str | None
    start_time: datetime
    errors: list[dict[str, str]]


# ============================================================================
# METADATA EXTRACTION
# ============================================================================


def extract_title_author_from_filename(filename: str) -> tuple[str, str | None]:
    """
    Extract title and author from common PDF filename patterns.

    Patterns handled:
    - "Title by Author.pdf"
    - "Author - Title.pdf"
    - "Title (Author).pdf"
    - "[Author] Title.pdf"
    - "Author, Title.pdf"

    Args:
        filename: The PDF filename (without path)

    Returns:
        Tuple of (title, author or None)
    """
    # Remove extension
    name = Path(filename).stem

    # Pattern: "Title by Author"
    match = re.match(r'^(.+?)\s+by\s+(.+)$', name, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern: "Author - Title"
    match = re.match(r'^(.+?)\s*[-–—]\s*(.+)$', name)
    if match:
        # Heuristic: if first part looks like a name (capitalized words), it's author
        first_part = match.group(1).strip()
        second_part = match.group(2).strip()
        words = first_part.split()
        if len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return second_part, first_part
        return name, None  # Can't determine reliably

    # Pattern: "Title (Author)"
    match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', name)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern: "[Author] Title"
    match = re.match(r'^\[([^\]]+)\]\s*(.+)$', name)
    if match:
        return match.group(2).strip(), match.group(1).strip()

    # Pattern with publisher info: "(Series) Author-Title-Publisher (Year)"
    match = re.match(r'^(?:\([^)]+\)\s*)?([^-]+)-(.+?)(?:-[^-]+)?(?:\s*\(\d{4}\))?$', name)
    if match:
        author_candidate = match.group(1).strip()
        title_candidate = match.group(2).strip()
        # If first part looks like author name
        words = author_candidate.split()
        if len(words) <= 5:
            return title_candidate, author_candidate

    # Clean up common artifacts
    clean_name = re.sub(r'\s*\(\d{4}\)\s*$', '', name)  # Remove year
    clean_name = re.sub(r'\s*\[OCR\]\s*$', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'\s*\(z-lib\.org\)\s*$', '', clean_name, flags=re.IGNORECASE)

    return clean_name.strip() or name, None


def extract_metadata_from_docling(
    doc: DoclingDocument,
    file_path: Path,
) -> ExtractedMetadata:
    """
    Extract metadata from a processed Docling document.

    Args:
        doc: The Docling document object
        file_path: Path to the original PDF file

    Returns:
        ExtractedMetadata object
    """
    # Get file stats
    file_stat = file_path.stat()
    file_size = file_stat.st_size

    # Export to dict for metadata
    doc_dict = doc.export_to_dict()

    # Extract title from document or filename
    title = None
    if doc_dict.get('main-text'):
        for item in doc_dict['main-text']:
            if item.get('type') == 'title':
                title = item.get('text')
                break

    # Fall back to filename extraction
    if not title:
        title, _ = extract_title_author_from_filename(file_path.name)

    # Try to get author from filename if not in document
    _, author = extract_title_author_from_filename(file_path.name)

    # Page count
    page_count = len(doc_dict.get('pages', [])) or 1

    # Word count from markdown
    markdown = doc.export_to_markdown()
    word_count = len(markdown.split())

    # Extract table of contents (headings)
    toc = []
    for item in doc_dict.get('main-text', []):
        if item.get('type') in ['section-header', 'title', 'heading']:
            heading_text = item.get('text', '').strip()
            if heading_text and len(heading_text) < 200:
                toc.append(heading_text)

    # Extra metadata from document
    extra = {}
    if 'document' in doc_dict:
        doc_meta = doc_dict['document']
        if isinstance(doc_meta, dict):
            extra.update({
                k: v for k, v in doc_meta.items()
                if isinstance(v, (str, int, float, bool))
            })

    return ExtractedMetadata(
        title=title,
        author=author,
        page_count=page_count,
        file_size_bytes=file_size,
        word_count=word_count,
        toc=toc if toc else None,
        subjects=None,  # Could be extracted from content analysis
        extra=extra,
    )


# ============================================================================
# DOCLING CHUNKING
# ============================================================================


def chunk_document(
    doc: DoclingDocument,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> list[ProcessedChunk]:
    """
    Chunk a Docling document using hybrid chunking strategy.

    Hybrid chunking respects document structure (headings, paragraphs, tables)
    while ensuring chunks don't exceed the size limit.

    Args:
        doc: The Docling document object
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        List of ProcessedChunk objects
    """
    try:
        # Use Docling's HybridChunker for structure-aware chunking
        chunker = HybridChunker(
            tokenizer="sentence",  # Use sentence tokenizer for better boundaries
            max_tokens=chunk_size // 4,  # Approximate tokens from chars
            merge_peers=True,  # Merge small adjacent chunks
        )

        chunks = list(chunker.chunk(doc))

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            # Extract chunk metadata
            page_number = None
            section_title = None
            chunk_type = "text"

            # Try to get page and section info from chunk metadata
            if hasattr(chunk, 'meta'):
                if hasattr(chunk.meta, 'page'):
                    page_number = chunk.meta.page
                if hasattr(chunk.meta, 'section'):
                    section_title = chunk.meta.section

            # Determine chunk type
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            if not chunk_text:
                continue

            if chunk_text.startswith('|') and '|' in chunk_text:
                chunk_type = "table"
            elif len(chunk_text.split('\n')) == 1 and len(chunk_text) < 100:
                chunk_type = "heading"

            # Estimate token count (rough: 4 chars per token)
            token_count = len(chunk_text) // 4

            processed_chunks.append(ProcessedChunk(
                content=chunk_text,
                chunk_index=i,
                page_number=page_number,
                section_title=section_title,
                chunk_type=chunk_type,
                token_count=token_count,
                metadata={},
            ))

        return processed_chunks

    except Exception as e:
        logger.warning(f"Hybrid chunking failed, falling back to simple chunking: {e}")
        return _simple_chunk_document(doc, chunk_size, chunk_overlap)


def _simple_chunk_document(
    doc: DoclingDocument,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ProcessedChunk]:
    """
    Simple fallback chunking by splitting markdown text.
    """
    markdown = doc.export_to_markdown()
    chunks = []

    # Split by paragraphs first
    paragraphs = markdown.split('\n\n')

    current_chunk = ""
    current_index = 0

    for para in paragraphs:
        if not para.strip():
            continue

        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(para) > chunk_size:
            if current_chunk:
                chunks.append(ProcessedChunk(
                    content=current_chunk.strip(),
                    chunk_index=current_index,
                    page_number=None,
                    section_title=None,
                    chunk_type="text",
                    token_count=len(current_chunk) // 4,
                    metadata={},
                ))
                current_index += 1

                # Keep overlap
                overlap_text = current_chunk[-chunk_overlap:] if chunk_overlap else ""
                current_chunk = overlap_text

        current_chunk += para + "\n\n"

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(ProcessedChunk(
            content=current_chunk.strip(),
            chunk_index=current_index,
            page_number=None,
            section_title=None,
            chunk_type="text",
            token_count=len(current_chunk) // 4,
            metadata={},
        ))

    return chunks


# ============================================================================
# SINGLE PDF PROCESSING
# ============================================================================


async def process_single_pdf(
    file_path: Path,
    generate_embeddings: bool = True,
) -> dict[str, Any]:
    """
    Process a single PDF file: extract, chunk, embed, and store.

    Args:
        file_path: Path to the PDF file
        generate_embeddings: Whether to generate embeddings for chunks

    Returns:
        Dict with processing results
    """
    result = {
        "file": str(file_path),
        "success": False,
        "document_id": None,
        "chunks_count": 0,
        "error": None,
    }

    try:
        # Check if already processed
        file_hash = pgvector.compute_file_hash(str(file_path))
        if await pgvector.document_exists(file_hash):
            existing = await pgvector.get_document_by_hash(file_hash)
            result["success"] = True
            result["document_id"] = str(existing.id) if existing else None
            result["skipped"] = True
            result["reason"] = "Already processed"
            logger.debug(f"Skipping already processed: {file_path.name}")
            return result

        # Process with Docling (in thread to avoid blocking)
        def _convert():
            converter = DocumentConverter()
            return converter.convert(str(file_path))

        logger.info(f"Processing: {file_path.name}")
        docling_result = await asyncio.to_thread(_convert)

        if docling_result is None or docling_result.document is None:
            result["error"] = "Docling conversion returned no result"
            return result

        doc = docling_result.document

        # Extract metadata
        metadata = extract_metadata_from_docling(doc, file_path)

        # Chunk document
        chunk_size = config.pgvector.chunk_size
        chunk_overlap = config.pgvector.chunk_overlap
        chunks = chunk_document(doc, chunk_size, chunk_overlap)

        if not chunks:
            result["error"] = "No chunks extracted from document"
            return result

        # Insert document into database
        document_id = await pgvector.insert_document(
            filename=file_path.name,
            file_hash=file_hash,
            title=metadata.title,
            author=metadata.author,
            page_count=metadata.page_count,
            file_size_bytes=metadata.file_size_bytes,
            source_path=str(file_path),
            metadata={
                "word_count": metadata.word_count,
                "toc": metadata.toc,
                "subjects": metadata.subjects,
                **metadata.extra,
            },
        )

        # Generate embeddings if requested
        embeddings = None
        if generate_embeddings:
            chunk_texts = [c.content for c in chunks]
            try:
                embeddings = await pgvector.generate_embeddings_batch(chunk_texts)
            except Exception as e:
                logger.warning(f"Embedding generation failed for {file_path.name}: {e}")
                # Continue without embeddings - can be added later

        # Prepare chunks for batch insert
        chunk_data = []
        for i, chunk in enumerate(chunks):
            chunk_dict = {
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
                "chunk_type": chunk.chunk_type,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }
            if embeddings and i < len(embeddings):
                chunk_dict["embedding"] = embeddings[i]
            chunk_data.append(chunk_dict)

        # Insert chunks
        await pgvector.insert_chunks_batch(document_id, chunk_data)

        result["success"] = True
        result["document_id"] = str(document_id)
        result["chunks_count"] = len(chunks)
        result["title"] = metadata.title
        result["author"] = metadata.author

        logger.info(f"Processed: {file_path.name} -> {len(chunks)} chunks")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to process {file_path.name}: {e}")

    return result


# ============================================================================
# BATCH PROCESSING
# ============================================================================


class BatchProcessor:
    """
    Batch processor for MAGICK PDFs collection.

    Features:
    - Checkpointing for resume capability
    - Progress tracking
    - Error handling with retry
    - Parallel processing
    """

    def __init__(
        self,
        pdf_directory: Path | str,
        checkpoint_file: Path | str | None = None,
        batch_size: int = 10,
        max_workers: int = 3,
    ):
        """
        Initialize the batch processor.

        Args:
            pdf_directory: Directory containing PDF files
            checkpoint_file: File to save/load processing checkpoint
            batch_size: Number of PDFs to process before checkpointing
            max_workers: Maximum concurrent PDF processing tasks
        """
        self.pdf_directory = Path(pdf_directory)
        self.checkpoint_file = Path(checkpoint_file) if checkpoint_file else None
        self.batch_size = batch_size
        self.max_workers = max_workers

        self.progress = ProcessingProgress(
            total_files=0,
            processed_files=0,
            skipped_files=0,
            failed_files=0,
            current_file=None,
            start_time=datetime.now(),
            errors=[],
        )

        self._processed_hashes: set[str] = set()
        self._semaphore: asyncio.Semaphore | None = None

    def _load_checkpoint(self) -> set[str]:
        """Load processed file hashes from checkpoint."""
        if self.checkpoint_file and self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file) as f:
                    data = json.load(f)
                    return set(data.get("processed_hashes", []))
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return set()

    def _save_checkpoint(self):
        """Save processed file hashes to checkpoint."""
        if self.checkpoint_file:
            try:
                with open(self.checkpoint_file, 'w') as f:
                    json.dump({
                        "processed_hashes": list(self._processed_hashes),
                        "last_updated": datetime.now().isoformat(),
                        "progress": {
                            "processed": self.progress.processed_files,
                            "skipped": self.progress.skipped_files,
                            "failed": self.progress.failed_files,
                        },
                    }, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save checkpoint: {e}")

    def get_pdf_files(self) -> list[Path]:
        """Get all PDF files in the directory."""
        pdf_files = []
        for pattern in ["*.pdf", "*.PDF"]:
            pdf_files.extend(self.pdf_directory.glob(pattern))

        # Also search subdirectories
        for pattern in ["**/*.pdf", "**/*.PDF"]:
            pdf_files.extend(self.pdf_directory.glob(pattern))

        # Deduplicate
        pdf_files = list(set(pdf_files))
        pdf_files.sort(key=lambda p: p.name.lower())

        return pdf_files

    async def _process_with_semaphore(
        self,
        file_path: Path,
        generate_embeddings: bool,
    ) -> dict[str, Any]:
        """Process a PDF with semaphore for rate limiting."""
        async with self._semaphore:
            return await process_single_pdf(file_path, generate_embeddings)

    async def process_all(
        self,
        generate_embeddings: bool = True,
        progress_callback: callable = None,
    ) -> ProcessingProgress:
        """
        Process all PDFs in the directory.

        Args:
            generate_embeddings: Whether to generate embeddings
            progress_callback: Optional callback(progress) called after each file

        Returns:
            ProcessingProgress with final statistics
        """
        # Initialize
        self._processed_hashes = self._load_checkpoint()
        self._semaphore = asyncio.Semaphore(self.max_workers)
        self.progress.start_time = datetime.now()

        # Get files
        pdf_files = self.get_pdf_files()
        self.progress.total_files = len(pdf_files)

        logger.info(f"Found {len(pdf_files)} PDF files to process")
        logger.info(f"Already processed: {len(self._processed_hashes)} files")

        # Process in batches
        batch_count = 0
        tasks = []

        for i, file_path in enumerate(pdf_files):
            self.progress.current_file = file_path.name

            # Skip if already processed
            try:
                file_hash = pgvector.compute_file_hash(str(file_path))
                if file_hash in self._processed_hashes:
                    self.progress.skipped_files += 1
                    continue
            except Exception as e:
                logger.warning(f"Cannot hash {file_path.name}: {e}")
                continue

            # Add to batch
            task = asyncio.create_task(
                self._process_with_semaphore(file_path, generate_embeddings)
            )
            tasks.append((file_path, file_hash, task))

            # Process batch when full
            if len(tasks) >= self.batch_size:
                await self._process_batch(tasks)
                tasks = []
                batch_count += 1
                self._save_checkpoint()

                if progress_callback:
                    progress_callback(self.progress)

        # Process remaining
        if tasks:
            await self._process_batch(tasks)
            self._save_checkpoint()

        self.progress.current_file = None
        logger.info(
            f"Processing complete: {self.progress.processed_files} processed, "
            f"{self.progress.skipped_files} skipped, {self.progress.failed_files} failed"
        )

        return self.progress

    async def _process_batch(self, tasks: list[tuple[Path, str, asyncio.Task]]):
        """Process a batch of PDF tasks."""
        for file_path, file_hash, task in tasks:
            try:
                result = await task

                if result.get("success"):
                    self.progress.processed_files += 1
                    self._processed_hashes.add(file_hash)
                else:
                    self.progress.failed_files += 1
                    self.progress.errors.append({
                        "file": str(file_path),
                        "error": result.get("error", "Unknown error"),
                    })

            except Exception as e:
                self.progress.failed_files += 1
                self.progress.errors.append({
                    "file": str(file_path),
                    "error": str(e),
                })
                logger.error(f"Batch processing error for {file_path.name}: {e}")


# ============================================================================
# CLI INTERFACE
# ============================================================================


async def main():
    """Command-line interface for batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Process MAGICK PDFs into vector database")
    parser.add_argument("pdf_directory", help="Directory containing PDF files")
    parser.add_argument("--checkpoint", "-c", help="Checkpoint file for resume capability")
    parser.add_argument("--batch-size", "-b", type=int, default=10, help="Batch size")
    parser.add_argument("--workers", "-w", type=int, default=3, help="Max concurrent workers")
    parser.add_argument("--no-embeddings", action="store_true", help="Skip embedding generation")
    parser.add_argument("--stats", action="store_true", help="Show database stats and exit")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.stats:
        stats = await pgvector.get_database_stats()
        print("\nDatabase Statistics:")
        print(f"  Documents: {stats['total_documents']}")
        print(f"  Chunks: {stats['total_chunks']}")
        print(f"  Embedded: {stats['embedded_chunks']} ({stats['embedding_coverage']:.1f}%)")
        print(f"  Documents size: {stats['documents_size']}")
        print(f"  Chunks size: {stats['chunks_size']}")
        return

    # Process PDFs
    processor = BatchProcessor(
        pdf_directory=args.pdf_directory,
        checkpoint_file=args.checkpoint,
        batch_size=args.batch_size,
        max_workers=args.workers,
    )

    def print_progress(progress: ProcessingProgress):
        elapsed = (datetime.now() - progress.start_time).total_seconds()
        rate = progress.processed_files / elapsed if elapsed > 0 else 0
        print(
            f"\rProgress: {progress.processed_files}/{progress.total_files} "
            f"({progress.skipped_files} skipped, {progress.failed_files} failed) "
            f"[{rate:.1f} files/sec] - {progress.current_file or 'Done'}",
            end="", flush=True
        )

    try:
        progress = await processor.process_all(
            generate_embeddings=not args.no_embeddings,
            progress_callback=print_progress,
        )
        print()  # New line after progress

        # Final stats
        stats = await pgvector.get_database_stats()
        print("\nFinal Database Statistics:")
        print(f"  Documents: {stats['total_documents']}")
        print(f"  Chunks: {stats['total_chunks']}")
        print(f"  Embedded: {stats['embedded_chunks']} ({stats['embedding_coverage']:.1f}%)")

        if progress.errors:
            print(f"\nErrors ({len(progress.errors)}):")
            for err in progress.errors[:10]:
                print(f"  - {err['file']}: {err['error']}")
            if len(progress.errors) > 10:
                print(f"  ... and {len(progress.errors) - 10} more")

    finally:
        await pgvector.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
