"""
Websites API Routes - Web scraping
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.db import repository
from app.db.vector_store import add_documents, get_collection_name
from app.core.web_scraper import scrape_url, crawl_website
from app.core.embeddings import chunk_text, generate_embeddings
from app.core.docling_processor import extract_preview

router = APIRouter(prefix="/api/websites", tags=["websites"])


class ScrapeRequest(BaseModel):
    """Request to scrape a website."""
    url: str = Field(description="URL to scrape")
    category_id: int | None = None
    crawl: bool = Field(default=False, description="Crawl multiple pages")
    max_pages: int = Field(default=10, ge=1, le=100, description="Max pages to crawl")


class JobResponse(BaseModel):
    """Response with job information."""
    job_id: int
    status: str


async def process_website_scrape(
    job_id: int,
    url: str,
    category_id: int | None,
    crawl: bool,
    max_pages: int,
):
    """Background task to scrape a website."""
    try:
        await repository.start_job(job_id)
        await repository.update_job(job_id, current_item=url)

        if crawl:
            results = await crawl_website(url, max_pages)
            pages = [r.page for r in results if r.success and r.page]
        else:
            result = await scrape_url(url)
            if not result.success or not result.page:
                await repository.complete_job(job_id, error_message=result.error or "Scrape failed")
                return
            pages = [result.page]

        if not pages:
            await repository.complete_job(job_id, error_message="No content scraped")
            return

        await repository.update_job(job_id, total_items=len(pages))

        for i, page in enumerate(pages):
            await repository.update_job(
                job_id,
                progress=i,
                current_item=page.title or page.url,
            )

            # Chunk the content
            chunks = chunk_text(page.text)

            if chunks:
                # Generate embeddings
                chunk_texts = [c.text for c in chunks]
                embeddings = await generate_embeddings(chunk_texts)

                # Store in vector database
                chunk_ids = [f"web_{job_id}_{i}_chunk_{j}" for j in range(len(chunks))]
                metadatas = [
                    {
                        "job_id": job_id,
                        "url": page.url,
                        "chunk_index": c.index,
                        "title": page.title,
                        "source_type": "website",
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
                title=page.title or page.url,
                source_type="website",
                source_url=page.url,
                category_id=category_id,
                content_preview=extract_preview(page.text),
                word_count=page.word_count,
                chunk_count=len(chunks),
                chromadb_collection=get_collection_name(category_id),
                metadata=page.metadata,
            )

        await repository.update_job(job_id, progress=len(pages))
        await repository.complete_job(job_id)

    except Exception as e:
        await repository.complete_job(job_id, error_message=str(e))


@router.post("/scrape", response_model=JobResponse)
async def scrape_website(
    data: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """Scrape a website."""
    # Validate category
    if data.category_id:
        category = await repository.get_category(data.category_id)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")

    # Create job
    job_id = await repository.create_job(
        job_type="website_scrape",
        source_url=data.url,
        category_id=data.category_id,
        total_items=data.max_pages if data.crawl else 1,
    )

    # Start background processing
    background_tasks.add_task(
        process_website_scrape,
        job_id,
        data.url,
        data.category_id,
        data.crawl,
        data.max_pages,
    )

    return JobResponse(job_id=job_id, status="processing")
