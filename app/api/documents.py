"""
Documents API Routes - File upload and processing
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

from app.config import UPLOADS_DIR, SUPPORTED_DOCUMENT_FORMATS
from app.db import repository
from app.db.vector_store import add_documents, get_collection_name
from app.core.docling_processor import process_file, extract_preview
from app.core.embeddings import chunk_text, generate_embeddings

router = APIRouter(prefix="/api/documents", tags=["documents"])


class UploadResponse(BaseModel):
    """Response for file upload."""
    job_id: int
    filename: str
    status: str


class ContentItemResponse(BaseModel):
    """Response for content item."""
    id: int
    title: str
    source_type: str
    source_url: str | None
    source_path: str | None
    category_id: int | None
    content_preview: str | None
    word_count: int
    chunk_count: int
    created_at: str


async def process_uploaded_document(
    job_id: int,
    file_path: Path,
    category_id: int | None,
    original_filename: str,
):
    """Background task to process an uploaded document."""
    try:
        # Start job
        await repository.start_job(job_id)
        await repository.update_job(job_id, current_item=f"Processing {original_filename}")

        # Process document
        result = await process_file(file_path)

        if not result.success or not result.document:
            await repository.complete_job(job_id, error_message=result.error)
            return

        doc = result.document

        # Chunk the content
        chunks = chunk_text(doc.markdown)

        if chunks:
            # Generate embeddings
            chunk_texts = [c.text for c in chunks]
            embeddings = await generate_embeddings(chunk_texts)

            # Store in vector database
            chunk_ids = [f"doc_{job_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "job_id": job_id,
                    "chunk_index": c.index,
                    "title": doc.title,
                    "source": original_filename,
                }
                for c in chunks
            ]

            add_documents(
                documents=chunk_texts,
                metadatas=metadatas,
                ids=chunk_ids,
                category_id=category_id,
                embeddings=embeddings,
            )

        # Create content item
        await repository.create_content_item(
            title=doc.title,
            source_type="document",
            source_path=str(file_path),
            category_id=category_id,
            content_preview=extract_preview(doc.markdown),
            word_count=doc.word_count,
            chunk_count=len(chunks),
            chromadb_collection=get_collection_name(category_id),
            metadata=doc.metadata,
        )

        # Complete job
        await repository.complete_job(job_id)

    except Exception as e:
        await repository.complete_job(job_id, error_message=str(e))


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category_id: int | None = Form(default=None),
):
    """Upload a document for processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {suffix}. Supported: {', '.join(SUPPORTED_DOCUMENT_FORMATS.keys())}"
        )

    # Validate category if provided
    if category_id:
        category = await repository.get_category(category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")

    # Save uploaded file
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{suffix}"
    file_path = UPLOADS_DIR / unique_filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create job
    job_id = await repository.create_job(
        job_type="document_upload",
        source_path=str(file_path),
        category_id=category_id,
    )

    # Start background processing
    background_tasks.add_task(
        process_uploaded_document,
        job_id,
        file_path,
        category_id,
        file.filename,
    )

    return UploadResponse(
        job_id=job_id,
        filename=file.filename,
        status="processing",
    )


@router.get("", response_model=list[ContentItemResponse])
async def list_content(
    category_id: int | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List content items."""
    items = await repository.get_content_items(
        category_id=category_id,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return items


@router.get("/{item_id}", response_model=ContentItemResponse)
async def get_content(item_id: int):
    """Get a single content item."""
    item = await repository.get_content_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_content(item_id: int):
    """Delete a content item."""
    item = await repository.get_content_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    # TODO: Delete vectors from ChromaDB

    # Delete file if exists
    if item.get("source_path"):
        file_path = Path(item["source_path"])
        if file_path.exists():
            file_path.unlink()

    await repository.delete_content_item(item_id)
