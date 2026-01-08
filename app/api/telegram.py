"""
Telegram Mini App API Routes

Handles:
- Bot webhook (commands, payments)
- Mini App authentication
- Chat conversations
- Subscription management
- PDF listing
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import secrets
from datetime import datetime, timedelta
from typing import Annotated, Optional

import httpx
import psycopg2
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.db import telegram_repository as tg_repo
from app.db.models import TIER_LIMITS
from app.middleware.telegram_auth import (
    TelegramUser,
    get_current_telegram_user,
    get_optional_telegram_user,
    require_telegram_tier,
    require_query_credits,
)
from app.services.chat_service import chat, telegram_chat_stream, telegram_chat_stream_maglib, telegram_chat_stream_bibliothek
from app.services.analytics_service import analytics_service
from app.db.analytics_repository import analytics_repo

# MAG-LIB category ID (uses pgvector instead of ChromaDB)
MAGLIB_CATEGORY_ID = 20
from app.db import repository  # For getting PDFs/categories

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


# ============================================================================
# Configuration
# ============================================================================

def get_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


BOT_API = "https://api.telegram.org/bot"


# Token bundle definitions
TOKEN_BUNDLES = {
    "bundle_small": {"name": "50 Queries", "tokens": 50, "price": 25},
    "bundle_medium": {"name": "150 Queries", "tokens": 150, "price": 60},
    "bundle_large": {"name": "500 Queries", "tokens": 500, "price": 175},
}


# ============================================================================
# Request/Response Models
# ============================================================================


class AuthResponse(BaseModel):
    """Authentication response with user profile (camelCase for frontend)."""
    telegramId: int
    firstName: str
    username: Optional[str]
    tier: str
    queriesUsed: int
    queriesRemaining: int
    dailyQueryLimit: Optional[int] = None  # null = unlimited
    downloadsUsed: int = 0
    downloadsRemaining: int = 1
    downloadQuotaResets: Optional[str] = None
    dailyDownloadLimit: Optional[int] = 1  # null = unlimited
    subscriptionEndsAt: Optional[str]
    createdAt: str


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pdf_ids: list[str] = Field(default_factory=list, description="PDF/category IDs to chat with (format: 'maglib:123' or 'bibliothek:456')")


class SendMessageRequest(BaseModel):
    """Request to send a chat message."""
    conversationId: Optional[str] = None  # String from frontend, converted to int
    message: str = Field(..., min_length=1, max_length=10000)
    pdfIds: Optional[list[str]] = None  # String IDs from frontend (None = not provided, [] = archive chat)
    collection: str = Field(default="maglib", pattern="^(maglib|bibliothek|all)$")  # Which collection to search


class SubscribeRequest(BaseModel):
    """Request to create subscription invoice."""
    tier: str = Field(..., pattern="^(starter|pro|unlimited|business|enterprise|scholar|researcher)$")


class PurchaseTokensRequest(BaseModel):
    """Request to purchase token bundle."""
    bundle_id: str


class ShareConversationRequest(BaseModel):
    """Request to share an unsaved conversation directly."""
    conversation_id: str
    title: str


class PDFResponse(BaseModel):
    """PDF/category available for selection."""
    id: str  # String ID for frontend compatibility
    title: str
    description: Optional[str]
    category: str
    pageCount: int  # Renamed from item_count for frontend
    createdAt: str  # Added for frontend compatibility


class MessageResponse(BaseModel):
    """Message response."""
    id: str  # String for frontend
    role: str
    content: str
    sources: Optional[list[dict]] = None
    timestamp: str


class ConversationResponse(BaseModel):
    """Conversation response - matches frontend Conversation type."""
    id: str  # String for frontend
    title: str
    pdfIds: list[str]  # camelCase, string IDs for frontend
    messages: list[MessageResponse] = []  # Include messages (empty for new)
    createdAt: str  # camelCase for frontend
    updatedAt: str  # camelCase for frontend


class ConversationWithMessagesResponse(BaseModel):
    """Conversation with messages - same as ConversationResponse."""
    id: str
    title: str
    pdfIds: list[str]
    messages: list[MessageResponse]
    createdAt: str
    updatedAt: str


class SaveConversationRequest(BaseModel):
    """Request to save a conversation."""
    conversationId: str
    title: str
    selectedDocIds: list[str] = Field(default_factory=list)


class SavedConversationResponse(BaseModel):
    """Saved conversation response."""
    id: str
    title: str
    createdAt: str
    messageCount: int = 0
    docCount: int = 0


class SavedConversationDetailResponse(BaseModel):
    """Detailed saved conversation response with messages and documents."""
    id: str
    title: str
    messages: list[MessageResponse]
    documents: list[dict] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class ShareConversationResponse(BaseModel):
    """Response when sharing a conversation."""
    shareToken: str
    shareUrl: str


# ============================================================================
# Authentication Endpoints
# ============================================================================


@router.post("/auth", response_model=AuthResponse)
async def authenticate(user: TelegramUser = Depends(get_current_telegram_user)):
    """
    Authenticate Telegram user and return profile.

    The initData is validated via the X-Telegram-Init-Data header.
    Creates user if not exists, updates profile if exists.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    # Track analytics (non-blocking)
    # Check if this is a new user signup or returning user login
    created_at = user.db_record.get("created_at")
    updated_at = user.db_record.get("updated_at")
    is_new_user = created_at == updated_at if created_at and updated_at else False

    if is_new_user:
        await analytics_service.track_user_signup(user.db_record)
    else:
        await analytics_service.track_user_login(user.db_record)

    return {
        "telegramId": user.db_record["telegram_id"],
        "firstName": user.db_record["first_name"],
        "username": user.db_record.get("username"),
        "tier": user.db_record["tier"],
        "queriesUsed": user.db_record["queries_used"],
        "queriesRemaining": user.db_record["queries_remaining"],
        "subscriptionEndsAt": user.db_record.get("subscription_ends_at"),
        "createdAt": user.db_record["created_at"],
    }


@router.get("/profile", response_model=AuthResponse)
async def get_profile(user: TelegramUser = Depends(get_current_telegram_user)):
    """Get current user profile with query and download quotas."""
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    tier = user.db_record["tier"]
    tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    # Get query limit for tier
    daily_query_limit = tier_limits.get("daily_queries")  # None = unlimited

    # Get download quota remaining and tier limit
    downloads_remaining = await tg_repo.get_download_quota_remaining(user.id)
    daily_download_limit = tier_limits.get("daily_downloads", 1)

    # For unlimited tiers, return None for limits and a high number for remaining
    if daily_download_limit is None:
        downloads_remaining_display = 999999  # High number for unlimited
        daily_download_limit_display = None
    else:
        downloads_remaining_display = max(0, downloads_remaining)  # 0 minimum for exhausted quota
        daily_download_limit_display = daily_download_limit

    return {
        "telegramId": user.db_record["telegram_id"],
        "firstName": user.db_record["first_name"],
        "username": user.db_record.get("username"),
        "tier": tier,
        "queriesUsed": user.db_record["queries_used"],
        "queriesRemaining": user.db_record["queries_remaining"],
        "dailyQueryLimit": daily_query_limit,
        "downloadsUsed": user.db_record.get("downloads_used", 0),
        "downloadsRemaining": downloads_remaining_display,
        "downloadQuotaResets": user.db_record.get("download_quota_resets_at"),
        "dailyDownloadLimit": daily_download_limit_display,
        "subscriptionEndsAt": user.db_record.get("subscription_ends_at"),
        "createdAt": user.db_record["created_at"],
    }


# ============================================================================
# PDF/Category Endpoints
# ============================================================================


@router.get("/pdfs", response_model=list[PDFResponse])
async def list_pdfs(user: TelegramUser = Depends(get_current_telegram_user)):
    """
    List available PDFs/categories for selection.

    Returns categories from the knowledge base that can be selected for chat.
    """
    categories = await repository.get_categories()

    return [
        {
            "id": str(cat["id"]),  # Convert to string for frontend
            "title": cat["name"],
            "description": cat.get("description"),
            "category": cat["name"],
            "pageCount": cat.get("item_count", 0),  # Renamed for frontend
            "createdAt": datetime.now().isoformat(),  # Placeholder timestamp
        }
        for cat in categories
        if cat.get("item_count", 0) > 0  # Only show categories with content
    ]


# ============================================================================
# Document Archive Endpoints (Knowledge Archive TWA)
# ============================================================================


class DocumentResponse(BaseModel):
    """Document from pgvector database."""
    id: str
    title: str
    author: Optional[str]
    filename: str
    page_count: int
    chunk_count: int
    cover_url: Optional[str]  # Primary cover URL
    cover_urls: list[str] = []  # Fallback URLs to try
    collection: str  # 'maglib' or 'bibliothek'
    # Extraction metadata (optional)
    extraction_confidence: Optional[float] = None
    extraction_method: Optional[str] = None
    original_title: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Paginated document list response."""
    documents: list[DocumentResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


def _generate_cover_url(title: str, filename: str, collection_name: str) -> str:
    """Generate cover URL based on document title and collection.

    Cover naming conventions:
    - Most: {title}.jpg
    - Some: {title}.pdf_thumb.jpg
    - With underscores: {title_with_underscores}.pdf_thumb.jpg
    """
    import re
    from urllib.parse import quote

    # Use title for cover name, fallback to filename
    base_name = title or filename
    if base_name.lower().endswith('.pdf'):
        base_name = base_name[:-4]

    # Normalize: collapse multiple spaces to single space
    base_name = re.sub(r'\s+', ' ', base_name).strip()

    # Map collection to cover path
    cover_path = "maglib" if collection_name == "maglib" else "bibliothek"

    # Try .jpg extension (most common)
    cover_filename = f"{base_name}.jpg"

    # URL encode the filename (handles spaces and special chars)
    return f"/covers/{cover_path}/{quote(cover_filename)}"


def _generate_cover_urls(title: str, filename: str, collection_name: str) -> list[str]:
    """Generate multiple cover URL variants to try.

    Returns a list of URLs to try in order:
    1. {title}.jpg (spaces)
    2. {title}.pdf_thumb.jpg (spaces)
    3. {title_underscored}.pdf_thumb.jpg (underscores)
    """
    import re
    from urllib.parse import quote

    base_name = title or filename
    if base_name.lower().endswith('.pdf'):
        base_name = base_name[:-4]

    # Normalize: collapse multiple spaces to single space
    base_name = re.sub(r'\s+', ' ', base_name).strip()

    # Map collection to cover path
    cover_path = "maglib" if collection_name == "maglib" else "bibliothek"

    urls = []

    # Variant 1: title.jpg (with spaces)
    urls.append(f"/covers/{cover_path}/{quote(f'{base_name}.jpg')}")

    # Variant 2: title.pdf_thumb.jpg (with spaces)
    urls.append(f"/covers/{cover_path}/{quote(f'{base_name}.pdf_thumb.jpg')}")

    # Variant 3: title_underscored.pdf_thumb.jpg
    underscored = base_name.replace(' ', '_')
    urls.append(f"/covers/{cover_path}/{quote(f'{underscored}.pdf_thumb.jpg')}")

    return urls


async def _get_documents_from_db(
    db_config: dict,
    collection_name: str,
    page: int,
    per_page: int,
    search: Optional[str] = None,
    starts_with: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Fetch documents from a pgvector database.

    Handles both databases with and without extraction metadata columns.

    Args:
        starts_with: Optional single letter (A-Z) to filter documents by starting letter
    """
    import asyncpg

    try:
        conn = await asyncpg.connect(
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )

        try:
            # Build query - try with extraction columns first, fallback if they don't exist
            offset = (page - 1) * per_page
            has_extraction_cols = True

            # Normalize starts_with parameter (single letter, case-insensitive)
            letter_filter = None
            if starts_with:
                letter_filter = starts_with.upper()[:1] if starts_with else None

            # Try query with extraction columns first, fallback if they don't exist
            if search:
                # Search by title or author
                search_pattern = f"%{search}%"

                if letter_filter:
                    # With both search and letter filter
                    where_clause = "WHERE (d.title ILIKE $1 OR d.filename ILIKE $1) AND UPPER(SUBSTRING(d.title, 1, 1)) = $2"
                    count_sql = f"""
                        SELECT COUNT(*) FROM documents d
                        {where_clause}
                    """
                    docs_sql_full = f"""
                        SELECT d.id, d.filename, d.title, d.page_count,
                               d.extraction_confidence, d.extraction_method, d.original_title
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $3 OFFSET $4
                    """
                    docs_sql_simple = f"""
                        SELECT d.id, d.filename, d.title, d.page_count
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $3 OFFSET $4
                    """
                    total = await conn.fetchval(count_sql, search_pattern, letter_filter)
                else:
                    # Search only, no letter filter
                    where_clause = "WHERE (d.title ILIKE $1 OR d.filename ILIKE $1)"
                    count_sql = f"""
                        SELECT COUNT(*) FROM documents d
                        {where_clause}
                    """
                    docs_sql_full = f"""
                        SELECT d.id, d.filename, d.title, d.page_count,
                               d.extraction_confidence, d.extraction_method, d.original_title
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $2 OFFSET $3
                    """
                    docs_sql_simple = f"""
                        SELECT d.id, d.filename, d.title, d.page_count
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $2 OFFSET $3
                    """
                    total = await conn.fetchval(count_sql, search_pattern)

                try:
                    if letter_filter:
                        rows = await conn.fetch(docs_sql_full, search_pattern, letter_filter, per_page, offset)
                    else:
                        rows = await conn.fetch(docs_sql_full, search_pattern, per_page, offset)
                except Exception as col_error:
                    # If extraction columns don't exist, use simple query
                    if "column" in str(col_error).lower() or "extraction" in str(col_error).lower():
                        has_extraction_cols = False
                        if letter_filter:
                            rows = await conn.fetch(docs_sql_simple, search_pattern, letter_filter, per_page, offset)
                        else:
                            rows = await conn.fetch(docs_sql_simple, search_pattern, per_page, offset)
                    else:
                        raise
            else:
                # No search, just paginate (but may have letter filter)
                if letter_filter:
                    where_clause = "WHERE UPPER(SUBSTRING(d.title, 1, 1)) = $1"
                    # For letter filter: $1=letter, $2=per_page, $3=offset
                    count_sql = f"SELECT COUNT(*) FROM documents d {where_clause}"
                    docs_sql_full = f"""
                        SELECT d.id, d.filename, d.title, d.page_count,
                               d.extraction_confidence, d.extraction_method, d.original_title
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $2 OFFSET $3
                    """
                    docs_sql_simple = f"""
                        SELECT d.id, d.filename, d.title, d.page_count
                        FROM documents d
                        {where_clause}
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $2 OFFSET $3
                    """
                    total = await conn.fetchval(count_sql, letter_filter)
                else:
                    where_clause = ""
                    count_sql = "SELECT COUNT(*) FROM documents d"
                    docs_sql_full = f"""
                        SELECT d.id, d.filename, d.title, d.page_count,
                               d.extraction_confidence, d.extraction_method, d.original_title
                        FROM documents d
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $1 OFFSET $2
                    """
                    docs_sql_simple = f"""
                        SELECT d.id, d.filename, d.title, d.page_count
                        FROM documents d
                        ORDER BY CASE
                            WHEN d.title ~ '^[A-Za-z]' THEN 0
                            ELSE 1
                        END, d.title ASC
                        LIMIT $1 OFFSET $2
                    """
                    total = await conn.fetchval(count_sql)

                try:
                    if letter_filter:
                        rows = await conn.fetch(docs_sql_full, letter_filter, per_page, offset)
                    else:
                        rows = await conn.fetch(docs_sql_full, per_page, offset)
                except Exception as col_error:
                    # If extraction columns don't exist, use simple query
                    if "column" in str(col_error).lower() or "extraction" in str(col_error).lower():
                        has_extraction_cols = False
                        if letter_filter:
                            rows = await conn.fetch(docs_sql_simple, letter_filter, per_page, offset)
                        else:
                            rows = await conn.fetch(docs_sql_simple, per_page, offset)
                    else:
                        raise

            documents = []
            for row in rows:
                cover_urls = _generate_cover_urls(row["title"], row["filename"], collection_name)
                documents.append({
                    "id": f"{collection_name}:{row['id']}",
                    "title": row["title"] or row["filename"],
                    "author": None,  # TODO: Add author field to documents table
                    "filename": row["filename"],
                    "page_count": row["page_count"] or 0,
                    "chunk_count": 0,  # Not fetched in list view for performance
                    "cover_url": cover_urls[0] if cover_urls else None,
                    "collection": collection_name,
                    # Extraction metadata (if available)
                    "extraction_confidence": row.get("extraction_confidence") if has_extraction_cols else None,
                    "extraction_method": row.get("extraction_method") if has_extraction_cols else None,
                    "original_title": row.get("original_title") if has_extraction_cols else None,
                })

            return documents, total

        finally:
            await conn.close()

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching documents from {collection_name}: {e}")
        return [], 0


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=500)] = 20,
    collection: Annotated[str, Query()] = "all",
    search: Optional[str] = None,
    starts_with: Optional[str] = None,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    List documents from the Knowledge Archive (MAG-LIB + BIBLIOTHEK).

    Supports pagination, collection filtering, search, and alphabetical filtering.

    Query Parameters:
        starts_with: Single letter (A-Z) to filter documents by starting letter
    """
    # Database configurations
    maglib_config = {
        "host": os.getenv("PGVECTOR_HOST", "localhost"),
        "port": int(os.getenv("PGVECTOR_PORT", "5432")),
        "database": os.getenv("PGVECTOR_DATABASE", "magick_knowledge"),
        "user": os.getenv("PGVECTOR_USER", "docling"),
        "password": os.getenv("PGVECTOR_PASSWORD", "docling_secure_pwd_2024"),
    }

    bibliothek_config = {
        "host": os.getenv("BIBLIOTHEK_HOST", "localhost"),
        "port": int(os.getenv("BIBLIOTHEK_PORT", "5432")),  # Same PostgreSQL instance as MAG-LIB
        "database": os.getenv("BIBLIOTHEK_DATABASE", "bibliothek_knowledge"),
        "user": os.getenv("BIBLIOTHEK_USER", "docling"),  # docling user has access to both databases
        "password": os.getenv("BIBLIOTHEK_PASSWORD", "docling_secure_pwd_2024"),
    }

    all_documents = []
    total_count = 0

    # For "all" collection, we need to handle pagination differently:
    # - Fetch all documents from both DBs (up to a reasonable limit)
    # - Combine, sort, then paginate
    # For single collection, use DB-level pagination directly

    if collection == "all":
        # For combined view, fetch larger batches without DB-level pagination
        # to allow proper cross-database sorting and pagination
        fetch_limit = per_page * 2  # Fetch enough to cover the page from both DBs

        if collection in ("all", "maglib"):
            docs, count = await _get_documents_from_db(
                maglib_config, "maglib", 1, fetch_limit * page, search, starts_with
            )
            all_documents.extend(docs)
            total_count += count

        if collection in ("all", "bibliothek"):
            docs, count = await _get_documents_from_db(
                bibliothek_config, "bibliothek", 1, fetch_limit * page, search, starts_with
            )
            all_documents.extend(docs)
            total_count += count

        # Sort combined results by title
        all_documents.sort(key=lambda d: d["title"].lower())

        # Apply pagination to combined results
        start = (page - 1) * per_page
        all_documents = all_documents[start:start + per_page]
    else:
        # Single collection - use DB-level pagination directly
        if collection == "maglib":
            docs, count = await _get_documents_from_db(
                maglib_config, "maglib", page, per_page, search, starts_with
            )
            all_documents.extend(docs)
            total_count = count
        elif collection == "bibliothek":
            docs, count = await _get_documents_from_db(
                bibliothek_config, "bibliothek", page, per_page, search, starts_with
            )
            all_documents.extend(docs)
            total_count = count

    # Track document browse event (non-blocking)
    await analytics_service.track_document_browse(
        telegram_user=user.db_record,
        collection=collection,
        page=page,
        result_count=len(all_documents),
    )

    return DocumentListResponse(
        documents=all_documents,
        total=total_count,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total_count,
    )


# ============================================================================
# PDF Download Endpoint
# ============================================================================

@router.get("/download/{document_id}")
async def download_pdf(
    document_id: str,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Download a PDF document with quota enforcement.

    Returns the PDF file with appropriate headers for browser download.
    Enforces daily download limits per subscription tier.
    """
    import time

    start_time = time.time()

    if not user.db_record:
        raise HTTPException(status_code=401, detail="Authentication required")

    telegram_id = user.id
    user_tier = user.db_record.get("tier", "free")

    # Determine collection from document_id prefix FIRST (needed for error logging)
    if document_id.startswith("maglib:"):
        collection = "maglib"
        doc_id = document_id.replace("maglib:", "")
        db_config = {
            "host": os.getenv("PGVECTOR_HOST", "localhost"),
            "port": int(os.getenv("PGVECTOR_PORT", "5432")),
            "database": os.getenv("PGVECTOR_DATABASE", "magick_knowledge"),
            "user": os.getenv("PGVECTOR_USER", "docling"),
            "password": os.getenv("PGVECTOR_PASSWORD", "docling_secure_pwd_2024"),
        }
    elif document_id.startswith("bibliothek:"):
        collection = "bibliothek"
        doc_id = document_id.replace("bibliothek:", "")
        db_config = {
            "host": os.getenv("BIBLIOTHEK_HOST", "localhost"),
            "port": int(os.getenv("BIBLIOTHEK_PORT", "5433")),
            "database": os.getenv("BIBLIOTHEK_DATABASE", "bibliothek_knowledge"),
            "user": os.getenv("BIBLIOTHEK_USER", "docling"),
            "password": os.getenv("BIBLIOTHEK_PASSWORD", "docling_secure_pwd_2024"),
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    # Check download quota (after we know the collection for proper error logging)
    remaining = await tg_repo.get_download_quota_remaining(telegram_id)
    if remaining == -2:
        # Log failed download - user not found
        await tg_repo.log_pdf_download(
            telegram_id=telegram_id,
            document_id=document_id,
            document_title="Unknown",
            collection=collection,
            user_tier=user_tier,
            response_time_ms=int((time.time() - start_time) * 1000),
            success=False,
            error_type="user_not_found"
        )
        raise HTTPException(status_code=401, detail="User not found")
    if remaining == 0:
        # User has exhausted their daily download quota
        logger.info(f"[Download] Quota exhausted for user {telegram_id}, tier: {user_tier}, collection: {collection}")
        # Skip logging the failed download - return error directly
        # Return detailed error with tier info for frontend to display appropriately
        error_detail = {
            "code": "download_quota_exhausted",
            "tier": user_tier,
            "message": f"You've exhausted your daily download limit on the {user_tier.capitalize()} plan"
        }
        raise HTTPException(
            status_code=429,
            detail=json.dumps(error_detail)
        )

    # Query pgvector to get document filename and title
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, title FROM documents WHERE id = %s LIMIT 1",
            (doc_id,)
        )
        doc_row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not doc_row:
            # Log failed download - document not found
            await tg_repo.log_pdf_download(
                telegram_id=telegram_id,
                document_id=document_id,
                document_title="Unknown",
                collection=collection,
                user_tier=user_tier,
                response_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_type="document_not_found"
            )
            raise HTTPException(status_code=404, detail="Document not found")

        filename, document_title = doc_row
    except HTTPException:
        raise  # Re-raise HTTP exceptions (already logged)
    except Exception as e:
        logger.error(f"Database error querying document: {e}")
        # Log failed download - database error
        await tg_repo.log_pdf_download(
            telegram_id=telegram_id,
            document_id=document_id,
            document_title="Unknown",
            collection=collection,
            user_tier=user_tier,
            response_time_ms=int((time.time() - start_time) * 1000),
            success=False,
            error_type="database_error"
        )
        raise HTTPException(status_code=500, detail="Database error")

    # Check if file exists
    pdf_path = pathlib.Path("/mnt/smb_terra/ALL-PDFs") / filename
    if not pdf_path.exists():
        # Log failed download - file not found
        await tg_repo.log_pdf_download(
            telegram_id=telegram_id,
            document_id=document_id,
            document_title=document_title or filename,
            collection=collection,
            user_tier=user_tier,
            response_time_ms=int((time.time() - start_time) * 1000),
            success=False,
            error_type="file_not_found"
        )
        raise HTTPException(status_code=404, detail="PDF file not found on server")

    # Get file size in MB
    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)

    # Deduct download credit
    if not await tg_repo.deduct_download_credit(telegram_id):
        raise HTTPException(status_code=429, detail="Download quota exhausted")

    # Log download for analytics
    await tg_repo.log_pdf_download(
        telegram_id=telegram_id,
        document_id=document_id,
        document_title=document_title or filename,
        collection=collection,
        file_size_mb=file_size_mb,
        user_tier=user_tier,
        response_time_ms=int((time.time() - start_time) * 1000),
        success=True,
        error_type=None
    )

    # Stream the file
    # Sanitize filename for headers (remove quotes and special chars)
    safe_filename = (document_title or "document").replace('"', '').replace("'", '')

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{safe_filename}.pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}.pdf"',
        }
    )


# ============================================================================
# Conversation Endpoints
# ============================================================================


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """List user's conversations."""
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    conversations = await tg_repo.get_tg_conversations(
        telegram_user_id=user.db_record["id"],
        limit=limit,
    )

    result = []
    for conv in conversations:
        pdf_ids = []
        if conv.get("pdf_ids"):
            try:
                pdf_ids = json.loads(conv["pdf_ids"])
            except json.JSONDecodeError:
                pass

        result.append({
            "id": str(conv["id"]),
            "title": conv["title"],
            "pdfIds": [str(pid) for pid in pdf_ids],
            "messages": [],  # Empty for list view
            "createdAt": conv["created_at"],
            "updatedAt": conv["updated_at"],
        })

    return result


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """Create a new conversation."""
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    # Validate PDF selection against tier limits
    tier = user.db_record["tier"]
    tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_pdfs = tier_limits.get("max_pdfs")

    if max_pdfs is not None and len(request.pdf_ids) > max_pdfs:
        raise HTTPException(
            status_code=403,
            detail=f"Your {tier} plan allows selecting up to {max_pdfs} PDFs. Upgrade for more."
        )

    # Create conversation
    conversation_id = await tg_repo.create_tg_conversation(
        telegram_user_id=user.db_record["id"],
        title="New Chat",
        pdf_ids=request.pdf_ids,
    )

    conversation = await tg_repo.get_tg_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    pdf_ids = []
    if conversation.get("pdf_ids"):
        try:
            pdf_ids = json.loads(conversation["pdf_ids"])
        except json.JSONDecodeError:
            pass

    return {
        "id": str(conversation["id"]),
        "title": conversation["title"],
        "pdfIds": [str(pid) for pid in pdf_ids],
        "messages": [],  # Empty for new conversation
        "createdAt": conversation["created_at"],
        "updatedAt": conversation["updated_at"],
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: int,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """Get conversation with messages."""
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    conversation = await tg_repo.get_tg_conversation_with_messages(
        conversation_id=conversation_id,
        telegram_user_id=user.db_record["id"],
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    pdf_ids = []
    if conversation.get("pdf_ids"):
        try:
            pdf_ids = json.loads(conversation["pdf_ids"])
        except json.JSONDecodeError:
            pass

    messages = []
    for msg in conversation.get("messages", []):
        sources = None
        if msg.get("sources"):
            try:
                sources = json.loads(msg["sources"])
            except json.JSONDecodeError:
                pass

        messages.append({
            "id": str(msg["id"]),
            "role": msg["role"],
            "content": msg["content"],
            "sources": sources,
            "timestamp": msg["created_at"],
        })

    return {
        "id": str(conversation["id"]),
        "title": conversation["title"],
        "pdfIds": [str(pid) for pid in pdf_ids],
        "messages": messages,
        "createdAt": conversation["created_at"],
        "updatedAt": conversation["updated_at"],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """Delete a conversation."""
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    deleted = await tg_repo.delete_tg_conversation(
        conversation_id=conversation_id,
        telegram_user_id=user.db_record["id"],
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True}


# ============================================================================
# Chat Endpoints
# ============================================================================


@router.post("/chat")
async def send_chat_message(
    request: SendMessageRequest,
    user: TelegramUser = Depends(require_query_credits()),
):
    """
    Send a chat message (non-streaming).

    Requires available query credits.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    # Get or create conversation
    # Convert string IDs to integers for database operations
    conversation_id = int(request.conversationId) if request.conversationId else None
    pdf_ids_int = []
    if request.pdfIds:
        for pid in request.pdfIds:
            if ':' in pid:
                collection, doc_id = pid.split(':', 1)
                pdf_ids_int.append(int(doc_id))
            else:
                pdf_ids_int.append(int(pid))

    if not conversation_id:
        # Create new conversation
        conversation_id = await tg_repo.create_tg_conversation(
            telegram_user_id=user.db_record["id"],
            pdf_ids=pdf_ids_int,
        )

    # Deduct query credit
    success = await tg_repo.deduct_query_credit(user.id)
    if not success and user.db_record["tier"] != "enterprise":
        raise HTTPException(status_code=402, detail="No query credits remaining")

    # Fetch conversation history from tg_messages table (CRITICAL for conversation memory)
    messages = await tg_repo.get_tg_messages(conversation_id)
    conversation_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
    ]

    # Store user message
    await tg_repo.create_tg_message(conversation_id, "user", request.message)

    # Call Telegram-specific chat function (default to MAG-LIB)
    # Note: telegram_chat_stream_maglib is an async generator, don't await it
    response = telegram_chat_stream_maglib(
        conversation_id=conversation_id,
        user_message=request.message,
        conversation_history=conversation_history,
        document_ids=pdf_ids_int if pdf_ids_int else None,
    )

    # Collect full response and sources
    full_content = ""
    sources_data = []
    async for chunk in response:
        try:
            data = json.loads(chunk.strip())
            if data.get("type") == "content":
                full_content += data.get("data", "")
            elif data.get("type") == "sources":
                sources_data = data.get("data", [])
        except json.JSONDecodeError:
            pass

    # Store assistant message in Telegram conversation
    await tg_repo.create_tg_message(conversation_id, "assistant", full_content, sources_data)

    # Generate title from first message
    await tg_repo.update_tg_conversation(
        conversation_id,
        title=request.message[:50] + ("..." if len(request.message) > 50 else ""),
    )

    return {
        "conversation_id": conversation_id,
        "message": {
            "id": f"msg-{conversation_id}",
            "role": "assistant",
            "content": full_content,
            "sources": sources_data,
            "timestamp": datetime.now().isoformat(),
        }
    }


@router.post("/chat/stream")
async def stream_chat_message(
    request: SendMessageRequest,
    user: TelegramUser = Depends(require_query_credits()),
):
    """
    Send a chat message with streaming response.

    Returns Server-Sent Events with type: "chunk", "sources", "error".
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    # Get or create conversation
    # Convert string IDs to integers for database operations
    # pdfIds can be "maglib:123" or "bibliothek:456" format - extract numeric part
    conversation_id = int(request.conversationId) if request.conversationId else None
    pdf_ids_int = []
    pdf_collections = {}  # Map ID to collection for later use
    if request.pdfIds:
        for pid in request.pdfIds:
            if ':' in pid:
                collection, doc_id = pid.split(':', 1)
                pdf_ids_int.append(int(doc_id))
                pdf_collections[int(doc_id)] = collection
            else:
                pdf_ids_int.append(int(pid))
                pdf_collections[int(pid)] = 'maglib'  # Default to maglib

    logger.info(f"[STREAM] Initial pdf_ids_int from request: {pdf_ids_int}")

    if not conversation_id:
        conversation_id = await tg_repo.create_tg_conversation(
            telegram_user_id=user.db_record["id"],
            pdf_ids=pdf_ids_int,
        )
        logger.info(f"[STREAM] Created new conversation {conversation_id} with pdf_ids: {pdf_ids_int}")
    elif request.pdfIds is None:
        # CRITICAL FIX: For follow-up messages where pdfIds not provided, load conversation's stored pdf_ids
        # This preserves document filtering (e.g., single-book chat) across the conversation
        # pdfIds=None means "not provided in request" vs pdfIds=[] which means "archive chat"
        logger.info(f"[ENDPOINT] pdfIds not provided for follow-up message, loading from conversation {conversation_id}")
        conversation_record = await tg_repo.get_tg_conversation(conversation_id)
        if conversation_record and conversation_record.get("pdf_ids"):
            try:
                pdf_ids_int = json.loads(conversation_record["pdf_ids"])
                # Rebuild pdf_collections - for stored IDs we default to maglib
                # The merged stream logic will handle cross-collection queries
                for doc_id in pdf_ids_int:
                    pdf_collections[doc_id] = 'maglib'
                logger.info(f"[ENDPOINT] Loaded conversation pdf_ids from storage: {pdf_ids_int}")
            except json.JSONDecodeError:
                logger.warning(f"[ENDPOINT] Failed to parse stored pdf_ids for conversation {conversation_id}")

    # Deduct query credit
    success = await tg_repo.deduct_query_credit(user.id)
    if not success and user.db_record["tier"] != "enterprise":
        raise HTTPException(status_code=402, detail="No query credits remaining")

    # Fetch conversation history from tg_messages table
    messages = await tg_repo.get_tg_messages(conversation_id)
    conversation_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
    ]

    # Store user message
    await tg_repo.create_tg_message(conversation_id, "user", request.message)

    # Track chat query event (fire-and-forget)
    import time
    start_time = time.time()
    event_id = await analytics_service.track_chat_query(
        telegram_user=user.db_record,
        conversation_id=conversation_id,
        query_text=request.message,
        collection=request.collection,
        selected_doc_ids=pdf_ids_int,
        session_id=None,
    )

    # Update title if this is the first message
    if not messages:
        await tg_repo.update_tg_conversation(
            conversation_id,
            title=request.message[:50] + ("..." if len(request.message) > 50 else ""),
        )

    # Route to appropriate collection based on request
    # - maglib: 534k chunks from 6,377 MAGICK PDFs
    # - bibliothek: 1.8M chunks from 2,701 BIBLIOTHEK PDFs
    logger.info(f"Telegram chat: collection={request.collection}, pdf_ids={pdf_ids_int}")

    async def generate():
        full_content = ""
        sources_data = []

        # CRITICAL: Send conversation_id as first event so frontend can track the conversation
        # This enables conversation memory by allowing frontend to update temporary IDs
        logger.info(f"[ENDPOINT] Starting stream generation for conversation_id={conversation_id}")
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversationId': str(conversation_id)})}\n\n"

        # Check if we have mixed collections
        has_maglib = any(coll == 'maglib' for coll in pdf_collections.values()) if pdf_collections else False
        has_bibliothek = any(coll == 'bibliothek' for coll in pdf_collections.values()) if pdf_collections else False
        has_mixed = has_maglib and has_bibliothek

        logger.info(f"[ENDPOINT] Collection routing: has_maglib={has_maglib}, has_bibliothek={has_bibliothek}, has_mixed={has_mixed}")

        # Route to appropriate collection's search function
        if has_mixed:
            logger.info(f"[ENDPOINT] Mixed collections detected - will search both databases")
            # For mixed collections, we need to search both and merge results
            # For now, we'll create separate search streams and merge them
            maglib_ids = [doc_id for doc_id, coll in pdf_collections.items() if coll == 'maglib'] if pdf_collections else None
            bibliothek_ids = [doc_id for doc_id, coll in pdf_collections.items() if coll == 'bibliothek'] if pdf_collections else None

            logger.info(f"[ENDPOINT] maglib_ids={maglib_ids}, bibliothek_ids={bibliothek_ids}")

            # Create a merged stream that queries both collections
            async def merged_stream():
                # We'll collect results from both and yield merged sources
                maglib_stream = telegram_chat_stream_maglib(
                    conversation_id=conversation_id,
                    user_message=request.message,
                    conversation_history=conversation_history,
                    document_ids=maglib_ids,
                )

                bibliothek_stream = telegram_chat_stream_bibliothek(
                    conversation_id=conversation_id,
                    user_message=request.message,
                    conversation_history=conversation_history,
                    document_ids=bibliothek_ids,
                )

                collected_sources = []
                content_chunks = []
                maglib_sources_found = False
                bibliothek_sources_found = False
                maglib_source_count = 0  # Track MAG-LIB source count for citation offset

                # Yield from maglib first
                async for chunk in maglib_stream:
                    try:
                        data = json.loads(chunk.strip())
                        if data.get("type") == "sources":
                            collected_sources.extend(data.get("data", []))
                            maglib_source_count = len(data.get("data", []))  # Store count for offset
                            maglib_sources_found = True
                            # CRITICAL FIX: Don't yield sources here - collect and merge first
                        elif data.get("type") in ["content", "done", "error", "conversation_id"]:
                            yield chunk
                        if data.get("type") == "content":
                            content_chunks.append(data.get("data", ""))
                    except json.JSONDecodeError:
                        yield chunk

                # Yield from bibliothek second, with citation renumbering
                async for chunk in bibliothek_stream:
                    try:
                        data = json.loads(chunk.strip())
                        if data.get("type") == "sources":
                            # Merge sources and deduplicate, noting original indices
                            for src in data.get("data", []):
                                if src not in collected_sources:
                                    collected_sources.append(src)
                            bibliothek_sources_found = True
                            # CRITICAL FIX: Don't yield sources here - collect and merge first
                        elif data.get("type") in ["content", "done", "error"]:
                            # Skip conversation_id from second stream
                            if data.get("type") != "conversation_id":
                                # CITATION RENUMBERING FIX: Adjust citations in BIBLIOTHEK content
                                # If MAG-LIB had sources, renumber BIBLIOTHEK citations [1][2] -> [offset+1][offset+2]
                                if data.get("type") == "content" and maglib_source_count > 0:
                                    content = data.get("data", "")
                                    # Renumber citations: [1] -> [offset+1], [2] -> [offset+2], etc.
                                    import re
                                    def renumber_citation(match):
                                        citation_num = int(match.group(1))
                                        new_num = citation_num + maglib_source_count
                                        return f"[{new_num}]"

                                    renumbered_content = re.sub(r'\[(\d+)\]', renumber_citation, content)
                                    data["data"] = renumbered_content
                                    logger.debug(f"[MERGED_STREAM] Renumbered BIBLIOTHEK citations: offset={maglib_source_count}")

                                yield json.dumps(data) + "\n"
                        if data.get("type") == "content":
                            content_chunks.append(data.get("data", ""))
                    except json.JSONDecodeError:
                        yield chunk

                # CRITICAL FIX: Always yield merged sources (even if empty) to ensure frontend gets sources event
                logger.info(f"[MERGED_STREAM] Yielding merged sources: {len(collected_sources)} unique documents from both streams")
                logger.info(f"[MERGED_STREAM] MAG-LIB sources: {maglib_source_count}, Total sources: {len(collected_sources)}")
                for i, src in enumerate(collected_sources, 1):
                    logger.info(f"[MERGED_STREAM]   [{i}] {src.get('title', 'Unknown')} (doc_id: {src.get('document_id')})")
                # Yield in plain JSON format (not SSE) so endpoint can parse and re-format it
                yield json.dumps({"type": "sources", "data": collected_sources}) + "\n"

            stream_func = merged_stream()
        elif request.collection == "bibliothek":
            logger.info(f"[ENDPOINT] Routing to telegram_chat_stream_bibliothek with document_ids={pdf_ids_int if pdf_ids_int else None}")
            stream_func = telegram_chat_stream_bibliothek(
                conversation_id=conversation_id,
                user_message=request.message,
                conversation_history=conversation_history,
                document_ids=pdf_ids_int if pdf_ids_int else None,
            )
        else:
            # Default to MAG-LIB (maglib or all)
            logger.info(f"[ENDPOINT] Routing to telegram_chat_stream_maglib with document_ids={pdf_ids_int if pdf_ids_int else None}")
            stream_func = telegram_chat_stream_maglib(
                conversation_id=conversation_id,
                user_message=request.message,
                conversation_history=conversation_history,
                document_ids=pdf_ids_int if pdf_ids_int else None,
            )

        logger.info(f"[ENDPOINT] Starting to iterate over stream_func")
        chunk_count = 0
        sources_data = []  # Initialize sources_data before loop to avoid NameError
        async for chunk in stream_func:
            chunk_count += 1
            logger.debug(f"[ENDPOINT] Received chunk #{chunk_count}: {chunk[:100]}")  # Log first 100 chars
            # Parse the JSON line from telegram_chat_stream
            try:
                data = json.loads(chunk.strip())
                logger.debug(f"[ENDPOINT] Parsed chunk type: {data.get('type')}")
                if data.get("type") == "content":
                    full_content += data.get("data", "")
                    yield f"data: {json.dumps({'type': 'chunk', 'content': data.get('data', '')})}\n\n"
                elif data.get("type") == "sources":
                    sources_data = data.get("data", [])
                    logger.info(f"[ENDPOINT] Captured sources event with {len(sources_data)} sources")
                    for i, src in enumerate(sources_data, 1):
                        logger.info(f"[ENDPOINT]   [{i}] {src.get('title', 'Unknown')}")
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"
                elif data.get("type") == "done":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                elif data.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': data.get('data', 'Unknown error')})}\n\n"
            except json.JSONDecodeError as e:
                logger.warning(f"[ENDPOINT] Failed to parse chunk #{chunk_count}: {e}. Raw: {chunk[:200]}")
                pass

        logger.info(f"[ENDPOINT] Stream iteration complete. Received {chunk_count} chunks total. full_content length={len(full_content)}, sources_count={len(sources_data)}")

        # Store assistant message
        await tg_repo.create_tg_message(conversation_id, "assistant", full_content, sources_data)

        # Track query metrics (after response is complete)
        response_time_ms = int((time.time() - start_time) * 1000)
        source_count = len(sources_data) if sources_data else 0
        await analytics_service.update_query_metrics(
            event_id=event_id,
            response_time_ms=response_time_ms,
            chunk_count=len(full_content.split()),  # Approximate chunk count from word count
            source_count=source_count,
        )

        # Update conversion funnel - mark first query
        from datetime import datetime
        await analytics_repo.update_funnel_first_query(user.db_record["id"], datetime.now().isoformat())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


# ============================================================================
# Saved Conversations Endpoints
# ============================================================================


@router.post("/saved-conversations", response_model=SavedConversationResponse)
async def save_conversation(
    request: SaveConversationRequest,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Save current conversation with selected documents.

    Available for all users including free tier.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    # Check tier limits
    tier = user.db_record["tier"]
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS.get("free", {}))
    max_saved = tier_config.get("max_saved_conversations", 0)

    # None or negative means unlimited, 0 means not allowed
    # For free tier, we still allow 1 saved conversation for sharing purposes
    if max_saved == 0:
        max_saved = 1  # Allow free tier 1 saved conversation for sharing

    # Check quota (skip if unlimited, i.e., None or negative)
    if max_saved is not None and max_saved > 0:
        count = await tg_repo.count_saved_conversations(user.db_record["id"])
        if count >= max_saved:
            raise HTTPException(
                status_code=429,
                detail=f"You can save {max_saved} conversations. Delete one to save another."
            )

    # Convert string IDs to integers for documents
    doc_ids = []
    if request.selectedDocIds:
        for doc_id in request.selectedDocIds:
            if ':' in doc_id:
                # Format: "maglib:123" or "bibliothek:456"
                collection, doc_num = doc_id.split(':', 1)
                doc_ids.append(doc_num)
            else:
                doc_ids.append(doc_id)

    # Save conversation
    saved_conv = await tg_repo.save_conversation(
        telegram_user_id=user.db_record["id"],
        conversation_id=int(request.conversationId),
        title=request.title,
        selected_doc_ids=doc_ids,
    )

    # Track saved conversation event (non-blocking)
    await analytics_service.track_conversation_saved(
        telegram_user=user.db_record,
        conversation_id=int(request.conversationId),
        doc_count=len(doc_ids),
    )

    return {
        "id": str(saved_conv["id"]),
        "title": saved_conv["title"],
        "createdAt": saved_conv["created_at"],
        "messageCount": 0,  # Will be populated by frontend if needed
        "docCount": len(doc_ids),
    }


@router.get("/saved-conversations", response_model=list[SavedConversationResponse])
async def list_saved_conversations(
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    List user's saved conversations.

    Returns basic info (title, created date, message count, doc count).
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    conversations = await tg_repo.get_saved_conversations(user.db_record["id"])

    return [
        {
            "id": str(conv["id"]),
            "title": conv["title"],
            "createdAt": conv["created_at"],
            "messageCount": conv.get("message_count", 0),
            "docCount": conv.get("doc_count", 0),
        }
        for conv in conversations
    ]


@router.get("/saved-conversations/{saved_conversation_id}", response_model=SavedConversationDetailResponse)
async def get_saved_conversation(
    saved_conversation_id: str,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Load full saved conversation with all messages and documents.

    User must own the conversation.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    conv = await tg_repo.get_saved_conversation(
        saved_conversation_id=int(saved_conversation_id),
        telegram_user_id=user.db_record["id"],
    )

    if not conv:
        raise HTTPException(status_code=404, detail="Saved conversation not found")

    # Format messages
    messages = [
        {
            "id": f"msg-{msg['id']}",
            "role": msg["role"],
            "content": msg["content"],
            "sources": msg.get("sources") or [],
            "timestamp": msg["created_at"],
        }
        for msg in conv.get("messages", [])
    ]

    # Format documents (just IDs for now)
    documents = [
        {"id": doc["document_id"]}
        for doc in conv.get("documents", [])
    ]

    return {
        "id": str(conv["id"]),
        "title": conv["title"],
        "messages": messages,
        "documents": documents,
        "createdAt": conv["created_at"],
        "updatedAt": conv["updated_at"],
    }


@router.delete("/saved-conversations/{saved_conversation_id}")
async def delete_saved_conversation(
    saved_conversation_id: str,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Delete saved conversation.

    User must own the conversation.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    success = await tg_repo.delete_saved_conversation(
        saved_conversation_id=int(saved_conversation_id),
        telegram_user_id=user.db_record["id"],
    )

    if not success:
        raise HTTPException(status_code=404, detail="Saved conversation not found")

    return {"success": True}


@router.post("/share-conversation", response_model=ShareConversationResponse)
async def share_unsaved_conversation(
    request: ShareConversationRequest,
    http_request: Request,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Share an UNSAVED conversation directly - NO NEED TO SAVE FIRST.

    Automatically saves the conversation in the background (without counting quota)
    and generates a public share token and URL.
    User sees instant share URL without any save dialog or quota penalty.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    try:
        # Automatically save the conversation in the background
        # This is SILENT - no quota penalty, no dialog shown to user
        saved_conv = await tg_repo.save_conversation(
            telegram_user_id=user.db_record["id"],
            conversation_id=int(request.conversation_id) if request.conversation_id.isdigit() else request.conversation_id,
            title=request.title,
            selected_doc_ids=[],  # Share without specific doc selection
        )

        saved_conv_id = int(saved_conv["id"])

        # Now enable sharing on this auto-saved conversation
        share_token = await tg_repo.enable_conversation_sharing(
            saved_conversation_id=saved_conv_id,
            telegram_user_id=user.db_record["id"],
        )

        if not share_token:
            raise HTTPException(status_code=500, detail="Failed to generate share token")

    except Exception as e:
        # If auto-save fails, still generate a token (graceful degradation)
        print(f"Warning: Auto-save failed ({e}), generating token anyway")
        import uuid
        share_token = str(uuid.uuid4())

    # Log the share action for analytics
    try:
        await analytics_service.track_conversation_shared(
            telegram_user=user.db_record,
            conversation_id=request.conversation_id,
            is_saved=True,
        )
    except Exception as log_err:
        print(f"Analytics error (non-blocking): {log_err}")

    # Get public TWA URL from environment, fallback to current request base URL
    # Construct from request if not explicitly configured (works on localhost, Railway, etc.)
    if twa_public_url := os.getenv("TWA_PUBLIC_URL"):
        share_url = f"{twa_public_url}/share/{share_token}"
    else:
        # Use current request's base URL (scheme + host)
        base_url = f"{http_request.url.scheme}://{http_request.url.netloc}"
        share_url = f"{base_url}/twa/share/{share_token}"

    return {
        "shareToken": share_token,
        "shareUrl": share_url,
    }


@router.post("/saved-conversations/{saved_conversation_id}/share", response_model=ShareConversationResponse)
async def share_conversation(
    saved_conversation_id: str,
    http_request: Request,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Enable public sharing for a saved conversation.

    Returns share token and public URL.
    User must own the conversation.
    """
    if not user.db_record:
        raise HTTPException(status_code=500, detail="Database error")

    share_token = await tg_repo.enable_conversation_sharing(
        saved_conversation_id=int(saved_conversation_id),
        telegram_user_id=user.db_record["id"],
    )

    if not share_token:
        raise HTTPException(status_code=404, detail="Saved conversation not found")

    # Get public TWA URL from environment, fallback to current request base URL
    # Construct from request if not explicitly configured (works on localhost, Railway, etc.)
    if twa_public_url := os.getenv("TWA_PUBLIC_URL"):
        share_url = f"{twa_public_url}/share/{share_token}"
    else:
        # Use current request's base URL (scheme + host)
        base_url = f"{http_request.url.scheme}://{http_request.url.netloc}"
        share_url = f"{base_url}/twa/share/{share_token}"

    return {
        "shareToken": share_token,
        "shareUrl": share_url,
    }


@router.get("/share/{share_token}", response_model=SavedConversationDetailResponse)
async def view_shared_conversation(
    share_token: str,
    user: TelegramUser = Depends(get_optional_telegram_user),
):
    """
    View shared conversation (public endpoint, no authentication required).

    Works for both:
    - Saved conversations (marked as public)
    - Unsaved conversations (with share token)
    """
    # Get shared conversation by share token
    conv = await tg_repo.get_saved_conversation_by_share_token(share_token)

    if not conv:
        raise HTTPException(status_code=404, detail="Shared conversation not found or expired")

    # Format messages
    messages = [
        {
            "id": f"msg-{msg['id']}",
            "role": msg["role"],
            "content": msg["content"],
            "sources": msg.get("sources") or [],
            "timestamp": msg["created_at"],
        }
        for msg in conv.get("messages", [])
    ]

    # Format documents
    documents = [
        {"id": doc["document_id"]}
        for doc in conv.get("documents", [])
    ]

    return {
        "id": str(conv["id"]),
        "title": conv["title"],
        "messages": messages,
        "documents": documents,
        "createdAt": conv["created_at"],
        "updatedAt": conv["updated_at"],
    }


# ============================================================================
# Subscription Endpoints
# ============================================================================


@router.post("/subscribe")
async def create_subscription_invoice(
    request: SubscribeRequest,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Create a subscription invoice for Telegram Stars payment.

    Returns invoice URL to open with Telegram.WebApp.openInvoice().
    """
    tier_limits = TIER_LIMITS.get(request.tier)
    if not tier_limits:
        raise HTTPException(status_code=400, detail="Invalid tier")

    price_stars = tier_limits["price_stars"]
    if price_stars == 0:
        raise HTTPException(status_code=400, detail="Free tier doesn't require payment")

    # Create invoice link via Bot API
    bot_token = get_bot_token()
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot not configured")

    payload = {
        "title": f"{request.tier.capitalize()} Subscription",
        "description": f"Monthly {request.tier} plan with {tier_limits['monthly_queries'] or 'unlimited'} queries",
        "payload": json.dumps({
            "type": "subscription",
            "tier": request.tier,
            "user_id": user.id,
        }),
        "currency": "XTR",  # Telegram Stars
        "prices": [{"label": f"{request.tier.capitalize()} Plan", "amount": price_stars}],
        "subscription_period": 2592000,  # 30 days in seconds
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BOT_API}{bot_token}/createInvoiceLink",
            json=payload,
        )

    result = response.json()
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=f"Failed to create invoice: {result}")

    return {"invoiceUrl": result["result"]}


@router.post("/purchase-tokens")
async def purchase_token_bundle(
    request: PurchaseTokensRequest,
    user: TelegramUser = Depends(get_current_telegram_user),
):
    """
    Create invoice for token bundle purchase.

    Returns invoice URL for one-time Stars payment.
    """
    bundle = TOKEN_BUNDLES.get(request.bundle_id)
    if not bundle:
        raise HTTPException(status_code=400, detail="Invalid bundle ID")

    bot_token = get_bot_token()
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot not configured")

    payload = {
        "title": bundle["name"],
        "description": f"One-time purchase of {bundle['tokens']} query tokens",
        "payload": json.dumps({
            "type": "token_bundle",
            "bundle_id": request.bundle_id,
            "tokens": bundle["tokens"],
            "user_id": user.id,
        }),
        "currency": "XTR",
        "prices": [{"label": bundle["name"], "amount": bundle["price"]}],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BOT_API}{bot_token}/createInvoiceLink",
            json=payload,
        )

    result = response.json()
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=f"Failed to create invoice: {result}")

    return {"invoiceUrl": result["result"]}


# ============================================================================
# Webhook Endpoint (for Bot updates)
# ============================================================================


@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handle Telegram Bot webhook updates.

    Processes:
    - pre_checkout_query (MUST respond within 10 seconds!)
    - successful_payment
    - message commands (/start, /help, /subscribe, /balance)
    """
    bot_token = get_bot_token()
    if not bot_token:
        return JSONResponse({"ok": True})

    try:
        update = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    # Handle pre_checkout_query (critical: must respond fast!)
    if "pre_checkout_query" in update:
        query = update["pre_checkout_query"]
        query_id = query["id"]

        # Always approve (validation happens later)
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(
                f"{BOT_API}{bot_token}/answerPreCheckoutQuery",
                json={"pre_checkout_query_id": query_id, "ok": True},
            )

        return JSONResponse({"ok": True})

    # Handle successful_payment
    if "message" in update and "successful_payment" in update["message"]:
        message = update["message"]
        payment = message["successful_payment"]
        user_data = message.get("from", {})

        telegram_id = user_data.get("id")
        if telegram_id:
            await handle_successful_payment(telegram_id, payment)

        return JSONResponse({"ok": True})

    # Handle message commands
    if "message" in update:
        message = update["message"]
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        user_data = message.get("from", {})
        telegram_id = user_data.get("id")

        # ===== AFFILIATE SYSTEM HANDLERS =====

        # Handle forwarded message (for channel verification)
        if "forward_from_chat" in message:
            forward_info = message["forward_from_chat"]

            # Only accept channels
            if forward_info.get("type") != "channel":
                await send_bot_message(bot_token, chat_id,
                    "❌ Please forward a message from a CHANNEL, not a group."
                )
                return JSONResponse({"ok": True})

            # Check if user already has pending/approved affiliate channel
            existing = await tg_repo.get_affiliate_channel_by_user(telegram_id)
            if existing:
                await send_bot_message(bot_token, chat_id,
                    f"You already have a registered channel: {existing['channel_title']}"
                )
                return JSONResponse({"ok": True})

            # Extract channel info
            channel_id = forward_info["id"]
            channel_title = forward_info["title"]
            channel_username = forward_info.get("username")

            # Create affiliate channel record
            try:
                affiliate_id = await tg_repo.create_affiliate_channel_from_forward(
                    telegram_user_id=telegram_id,
                    channel_id=channel_id,
                    channel_username=channel_username,
                    channel_title=channel_title,
                )

                await send_bot_message(bot_token, chat_id,
                    f"✅ Channel detected: {channel_title}\n\n"
                    f"Now please reply with your channel info in this format:\n\n"
                    f"Subscribers: [number]\n"
                    f"Last post: [YYYY-MM-DD]\n\n"
                    f"Example:\n"
                    f"Subscribers: 1500\n"
                    f"Last post: 2026-01-01"
                )
            except Exception as e:
                logger.error(f"Failed to create affiliate channel: {e}")
                await send_bot_message(bot_token, chat_id,
                    "❌ Error registering channel. Please try again."
                )
            return JSONResponse({"ok": True})

        # Handle subscriber info submission
        if "Subscribers:" in text and "Last post:" in text:
            affiliate = await tg_repo.get_affiliate_channel_by_user(telegram_id)
            if not affiliate or affiliate["status"] not in ["pending_info", "pending_review"]:
                await send_bot_message(bot_token, chat_id,
                    "Please forward a channel message first."
                )
                return JSONResponse({"ok": True})

            # Parse subscriber info
            sub_match = re.search(r'Subscribers:\s*(\d+)', text)
            date_match = re.search(r'Last post:\s*(\d{4}-\d{2}-\d{2})', text)

            if not (sub_match and date_match):
                await send_bot_message(bot_token, chat_id,
                    "❌ Invalid format. Please use:\nSubscribers: [number]\nLast post: YYYY-MM-DD"
                )
                return JSONResponse({"ok": True})

            subscriber_count = int(sub_match.group(1))
            last_post_date = date_match.group(1)

            # Validate minimum 500 subscribers
            if subscriber_count < 500:
                await send_bot_message(bot_token, chat_id,
                    f"❌ Sorry, you need at least 500 subscribers. You have {subscriber_count:,}."
                )
                return JSONResponse({"ok": True})

            # Update affiliate channel
            try:
                await tg_repo.update_affiliate_channel_info(
                    affiliate_channel_id=affiliate["id"],
                    subscriber_count=subscriber_count,
                    last_post_date=last_post_date,
                )

                await send_bot_message(bot_token, chat_id,
                    "✅ Application submitted!\n\n"
                    f"Channel: {affiliate['channel_title']}\n"
                    f"Subscribers: {subscriber_count:,}\n"
                    f"Last post: {last_post_date}\n\n"
                    "An admin will review within 24-48 hours."
                )

                # Notify admin
                admin_id = os.getenv("ADMIN_TELEGRAM_ID")
                if admin_id:
                    await send_bot_message(bot_token, int(admin_id),
                        f"🆕 New affiliate application\n\n"
                        f"Channel: {affiliate['channel_title']}\n"
                        f"Subscribers: {subscriber_count:,}\n"
                        f"Username: @{affiliate['channel_username']}\n"
                        f"Last post: {last_post_date}\n\n"
                        f"Review: /approve_affiliate {affiliate['id']}"
                    )
            except Exception as e:
                logger.error(f"Failed to update affiliate info: {e}")
                await send_bot_message(bot_token, chat_id,
                    "❌ Error processing application. Please try again."
                )
            return JSONResponse({"ok": True})

        # Handle /start aff_TOKEN (affiliate invite)
        if text.startswith("/start aff_"):
            invite_token = text.replace("/start aff_", "").strip()

            try:
                # Validate invite token
                invite = await tg_repo.get_affiliate_invite(invite_token)
                if not invite:
                    await send_bot_message(bot_token, chat_id,
                        "❌ Invalid or expired invite link."
                    )
                    return JSONResponse({"ok": True})

                # Mark invite as used
                await tg_repo.mark_invite_used(invite_token, telegram_id)

                await send_bot_message(bot_token, chat_id,
                    "🎯 Welcome to the Affiliate Program!\n\n"
                    "To verify your channel ownership:\n"
                    "1. Forward ANY message from your channel to me\n"
                    "2. I'll extract your channel info\n"
                    "3. Provide subscriber count and last post date\n"
                    "4. Admin will review within 24-48h\n\n"
                    "Ready? Forward a message from your channel now 👇"
                )
            except Exception as e:
                logger.error(f"Failed to process affiliate invite: {e}")
                await send_bot_message(bot_token, chat_id,
                    "❌ Error processing invite. Please try again."
                )
            return JSONResponse({"ok": True})

        # Handle /start ref_CODE (referral signup)
        if text.startswith("/start ref_"):
            referral_code = text.replace("/start ref_", "").strip()

            try:
                # Find affiliate and create referral
                affiliate = await tg_repo.get_affiliate_channel_by_referral_code(referral_code)

                if affiliate and affiliate["status"] == "approved":
                    # Check if user already referred
                    existing = await tg_repo.get_referral_by_user(telegram_id)
                    if not existing:
                        # Create referral record
                        await tg_repo.create_referral(
                            affiliate_channel_id=affiliate["id"],
                            referred_user_id=telegram_id,
                            referral_code=referral_code,
                        )
            except Exception as e:
                logger.error(f"Failed to process referral: {e}")
            # Continue with normal welcome flow
            return JSONResponse({"ok": True})

        # ===== END AFFILIATE HANDLERS =====

        if text.startswith("/start"):
            await send_bot_message(bot_token, chat_id,
                "Welcome to PDF Chat AI! \n\n"
                "Tap the button below to open the Mini App and start chatting with PDFs.\n\n"
                "Commands:\n"
                "/subscribe - View subscription plans\n"
                "/balance - Check your credits\n"
                "/help - Get help"
            )
        elif text.startswith("/subscribe"):
            await send_bot_message(bot_token, chat_id,
                "Choose your plan:\n\n"
                "Free - 20 queries/month, 1 PDF\n"
                "Starter (50 Stars) - 100 queries/month, 3 PDFs\n"
                "Pro (150 Stars) - 500 queries/month, 6 PDFs\n"
                "Business (300 Stars) - 2000 queries/month, 9 PDFs\n"
                "Enterprise (500 Stars) - Unlimited\n\n"
                "Open the Mini App to subscribe!"
            )
        elif text.startswith("/balance"):
            telegram_id = user_data.get("id")
            if telegram_id:
                db_user = await tg_repo.get_telegram_user(telegram_id)
                if db_user:
                    tier = db_user["tier"]
                    remaining = db_user["queries_remaining"]
                    tier_info = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
                    total = tier_info.get("monthly_queries")

                    msg = f"Plan: {tier.capitalize()}\n"
                    if total:
                        msg += f"Queries: {remaining}/{total} remaining"
                    else:
                        msg += "Queries: Unlimited"

                    await send_bot_message(bot_token, chat_id, msg)
        elif text.startswith("/help"):
            await send_bot_message(bot_token, chat_id,
                "PDF Chat AI Help\n\n"
                "This bot lets you chat with PDF documents using AI.\n\n"
                "1. Open the Mini App from the menu button\n"
                "2. Select PDFs to chat with\n"
                "3. Ask questions about the documents\n\n"
                "For billing issues, use /paysupport"
            )
        elif text.startswith("/paysupport"):
            await send_bot_message(bot_token, chat_id,
                "Payment Support\n\n"
                "For refunds or payment issues, please contact support.\n"
                "Include your Telegram username and transaction details."
            )

    return JSONResponse({"ok": True})


async def send_bot_message(bot_token: str, chat_id: int, text: str):
    """Send a message via Bot API."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{BOT_API}{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def handle_successful_payment(telegram_id: int, payment: dict):
    """Process successful payment."""
    try:
        payload = json.loads(payment.get("invoice_payload", "{}"))
        payment_type = payload.get("type")
        charge_id = payment.get("telegram_payment_charge_id", "")
        amount = payment.get("total_amount", 0)

        # Get or create user
        db_user = await tg_repo.get_telegram_user(telegram_id)
        if not db_user:
            return

        user_id = db_user["id"]

        if payment_type == "subscription":
            tier = payload.get("tier", "starter")

            # Update user tier
            ends_at = (datetime.now() + timedelta(days=30)).isoformat()
            await tg_repo.update_telegram_user_tier(telegram_id, tier, ends_at)

            # Create subscription record
            await tg_repo.create_subscription(user_id, tier, charge_id)

            # Create payment record
            payment_record = await tg_repo.create_payment_record(
                telegram_user_id=user_id,
                payment_type="subscription",
                amount_stars=amount,
                telegram_payment_charge_id=charge_id,
                tier=tier,
            )

            # ===== AFFILIATE COMMISSION TRACKING =====
            try:
                referral = await tg_repo.get_referral_by_user(telegram_id)
                if referral:
                    # Calculate 20% commission
                    commission_stars = int(amount * 0.20)

                    # Get the payment record ID (get_payment_record_id method or fallback)
                    # Since we don't have direct access to payment_record ID, fetch it
                    payment_records = await tg_repo.get_payment_history(user_id, limit=1)
                    if payment_records:
                        payment_id = payment_records[0]["id"]

                        # Create commission record
                        await tg_repo.create_commission(
                            affiliate_channel_id=referral["affiliate_channel_id"],
                            referral_id=referral["id"],
                            payment_id=payment_id,
                            tier=tier,
                            sale_amount_stars=amount,
                            commission_amount_stars=commission_stars,
                        )

                        # Add to affiliate's pending balance
                        await tg_repo.add_to_affiliate_balance(
                            affiliate_channel_id=referral["affiliate_channel_id"],
                            amount_stars=commission_stars,
                        )

                        # Mark referral as converted (first purchase)
                        if not referral["has_converted"]:
                            await tg_repo.mark_referral_converted(referral["id"])

                        logger.info(f"Commission created: {commission_stars} stars for affiliate {referral['affiliate_channel_id']}")
            except Exception as e:
                logger.error(f"Failed to track affiliate commission: {e}")
            # ===== END AFFILIATE COMMISSION TRACKING =====

            # Track subscription purchase (non-blocking)
            await analytics_service.track_subscription_purchase(
                telegram_user=db_user,
                tier=tier,
                amount_stars=amount,
                session_id=None,
            )

        elif payment_type == "token_bundle":
            tokens = payload.get("tokens", 0)
            bundle_id = payload.get("bundle_id", "")

            # Add tokens to user
            await tg_repo.add_query_credits(telegram_id, tokens)

            # Create payment record
            await tg_repo.create_payment_record(
                telegram_user_id=user_id,
                payment_type="token_bundle",
                amount_stars=amount,
                telegram_payment_charge_id=charge_id,
                bundle_id=bundle_id,
                tokens_added=tokens,
            )

    except Exception as e:
        print(f"Payment processing error: {e}")


# ============================================================================
# AFFILIATE ENDPOINTS FOR USERS
# ============================================================================


@router.get("/affiliate/status")
async def get_affiliate_status(
    user: Annotated[TelegramUser, Depends(get_current_telegram_user)] = None,
):
    """
    Check if current user is an approved affiliate.
    Returns: is_affiliate flag, status, and referral_code if applicable.
    """
    try:
        affiliate = await tg_repo.get_affiliate_channel_by_user(user.telegram_id)

        if not affiliate:
            return {
                "is_affiliate": False,
                "status": None,
                "referral_code": None,
            }

        return {
            "is_affiliate": True,
            "status": affiliate["status"],
            "referral_code": affiliate.get("referral_code") if affiliate["status"] == "approved" else None,
            "channel_title": affiliate["channel_title"],
        }
    except Exception as e:
        logger.error(f"Error getting affiliate status: {e}")
        return {
            "is_affiliate": False,
            "error": str(e),
        }


@router.get("/affiliate/dashboard")
async def get_affiliate_dashboard(
    user: Annotated[TelegramUser, Depends(get_current_telegram_user)] = None,
):
    """
    Get affiliate dashboard data (stats, earnings, payout info).
    Only available to approved affiliates.
    """
    try:
        affiliate = await tg_repo.get_affiliate_channel_by_user(user.telegram_id)

        if not affiliate or affiliate["status"] != "approved":
            raise HTTPException(
                status_code=403,
                detail="User is not an approved affiliate",
            )

        # Get dashboard data
        data = await tg_repo.get_affiliate_dashboard_data(affiliate["id"])

        # Construct referral link
        referral_url = f"https://t.me/AkashaAIHub_bot?start=ref_{affiliate['referral_code']}"

        return {
            "overview": {
                "totalReferrals": data["total_referrals"],
                "totalConversions": data["total_conversions"],
                "conversionRate": data["conversion_rate"],
                "totalEarnings": data["total_earnings_stars"],
                "pendingBalance": data["pending_balance_stars"],
            },
            "referralLink": referral_url,
            "nextPayout": {
                "estimatedDate": "1st of next month",
                "estimatedAmount": data["pending_balance_stars"],
                "minThreshold": 2000,
            },
            "channelInfo": {
                "title": data["channel_title"],
                "referralCode": data["referral_code"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting affiliate dashboard: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving dashboard: {str(e)}",
        )
