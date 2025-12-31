"""
Docling Processor - Document conversion with dynamic settings
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter

from app.config import config, SUPPORTED_DOCUMENT_FORMATS


@dataclass
class ProcessedDocument:
    """Result of document processing."""
    title: str
    content: str
    markdown: str
    word_count: int
    page_count: int
    metadata: dict[str, Any]


@dataclass
class ProcessingResult:
    """Result of a processing operation."""
    success: bool
    document: ProcessedDocument | None
    error: str | None


def get_docling_pipeline_options() -> dict[str, Any]:
    """Build pipeline options from current config."""
    cfg = config.docling

    options = {
        'do_ocr': cfg.ocr_enabled,
        'do_table_structure': cfg.table_structure_enabled,
    }

    # OCR settings
    if cfg.ocr_enabled:
        options['ocr_options'] = {
            'lang': cfg.ocr_lang,
        }

        if cfg.ocr_engine == 'easyocr':
            options['ocr_options']['kind'] = 'easyocr'
        elif cfg.ocr_engine == 'tesseract':
            options['ocr_options']['kind'] = 'tesseract'
        elif cfg.ocr_engine == 'tesseract_cli':
            options['ocr_options']['kind'] = 'tesseract_cli'

    # Accelerator settings
    if cfg.accelerator == 'cuda':
        options['accelerator_options'] = {'device': 'cuda'}
    elif cfg.accelerator == 'cpu':
        options['accelerator_options'] = {'device': 'cpu'}
    # auto means let docling decide

    # Image settings
    options['images_scale'] = cfg.images_scale
    options['generate_page_images'] = cfg.generate_page_images
    options['generate_picture_images'] = cfg.generate_picture_images

    return options


def is_supported_format(file_path: Path) -> bool:
    """Check if a file format is supported."""
    return file_path.suffix.lower() in SUPPORTED_DOCUMENT_FORMATS


def get_format_description(file_path: Path) -> str:
    """Get the description of a file format."""
    return SUPPORTED_DOCUMENT_FORMATS.get(file_path.suffix.lower(), "Unknown format")


async def process_document(file_path: Path | str) -> ProcessingResult:
    """
    Process a document using Docling.

    Args:
        file_path: Path to the document file

    Returns:
        ProcessingResult with the processed document or error
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    if not file_path.exists():
        return ProcessingResult(
            success=False,
            document=None,
            error=f"File not found: {file_path}"
        )

    if not is_supported_format(file_path):
        return ProcessingResult(
            success=False,
            document=None,
            error=f"Unsupported format: {file_path.suffix}"
        )

    def _process():
        try:
            # Create converter with current settings
            converter = DocumentConverter()

            # Convert document
            result = converter.convert(str(file_path))

            if result is None or result.document is None:
                return ProcessingResult(
                    success=False,
                    document=None,
                    error="Conversion returned no result"
                )

            doc = result.document

            # Export to markdown
            markdown = doc.export_to_markdown()

            # Export to dict for metadata
            doc_dict = doc.export_to_dict()

            # Extract title from filename or first heading
            title = file_path.stem
            if doc_dict.get('main-text'):
                for item in doc_dict['main-text']:
                    if item.get('type') == 'title':
                        title = item.get('text', title)
                        break

            # Count words
            word_count = len(markdown.split())

            # Page count from metadata
            page_count = len(doc_dict.get('pages', [])) or 1

            # Build metadata
            metadata = {
                'source_format': file_path.suffix.lower(),
                'source_name': file_path.name,
                'pages': page_count,
            }

            # Add any document metadata
            if 'document' in doc_dict:
                doc_meta = doc_dict['document']
                if isinstance(doc_meta, dict):
                    metadata.update({
                        k: v for k, v in doc_meta.items()
                        if isinstance(v, (str, int, float, bool))
                    })

            return ProcessingResult(
                success=True,
                document=ProcessedDocument(
                    title=title,
                    content=doc_dict.get('main-text', []),
                    markdown=markdown,
                    word_count=word_count,
                    page_count=page_count,
                    metadata=metadata,
                ),
                error=None
            )

        except Exception as e:
            return ProcessingResult(
                success=False,
                document=None,
                error=str(e)
            )

    return await asyncio.to_thread(_process)


async def process_text_file(file_path: Path | str) -> ProcessingResult:
    """
    Process a plain text file (.txt, .md).

    Args:
        file_path: Path to the text file

    Returns:
        ProcessingResult with the processed content
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    if not file_path.exists():
        return ProcessingResult(
            success=False,
            document=None,
            error=f"File not found: {file_path}"
        )

    try:
        content = file_path.read_text(encoding='utf-8')
        word_count = len(content.split())

        # For markdown files, content is already markdown
        # For text files, wrap in a code block or keep as-is
        if file_path.suffix.lower() == '.md':
            markdown = content
        else:
            markdown = content

        # Extract title from first line or filename
        title = file_path.stem
        lines = content.strip().split('\n')
        if lines:
            first_line = lines[0].strip()
            if first_line.startswith('#'):
                title = first_line.lstrip('#').strip()
            elif len(first_line) < 100:
                title = first_line

        return ProcessingResult(
            success=True,
            document=ProcessedDocument(
                title=title,
                content=content,
                markdown=markdown,
                word_count=word_count,
                page_count=1,
                metadata={
                    'source_format': file_path.suffix.lower(),
                    'source_name': file_path.name,
                },
            ),
            error=None
        )

    except Exception as e:
        return ProcessingResult(
            success=False,
            document=None,
            error=str(e)
        )


async def process_file(file_path: Path | str) -> ProcessingResult:
    """
    Process any supported file.

    Automatically chooses the appropriate processor based on file type.
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    suffix = file_path.suffix.lower()

    # Plain text files
    if suffix in ['.txt', '.md']:
        return await process_text_file(file_path)

    # All other supported formats through Docling
    if suffix in SUPPORTED_DOCUMENT_FORMATS:
        return await process_document(file_path)

    return ProcessingResult(
        success=False,
        document=None,
        error=f"Unsupported file format: {suffix}"
    )


def extract_preview(content: str, max_length: int = 500) -> str:
    """Extract a preview from content."""
    if len(content) <= max_length:
        return content

    # Try to break at a sentence
    preview = content[:max_length]
    last_period = preview.rfind('.')
    if last_period > max_length // 2:
        return preview[:last_period + 1]

    # Break at word boundary
    last_space = preview.rfind(' ')
    if last_space > 0:
        return preview[:last_space] + '...'

    return preview + '...'
