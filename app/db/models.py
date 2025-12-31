"""
SQLite Database Models for Docling Knowledge Hub
"""

from __future__ import annotations

import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import TypedDict, Literal

from app.config import config


# Type definitions for database records
class CategoryRecord(TypedDict):
    id: int
    name: str
    description: str | None
    color: str
    icon: str | None
    parent_id: int | None
    depth: int
    item_count: int
    created_at: str
    updated_at: str


class MonitoredChannelRecord(TypedDict):
    id: int
    channel_id: str
    channel_name: str
    channel_url: str
    category_id: int | None
    last_checked_at: str | None
    last_video_id: str | None
    video_count: int
    is_active: bool
    check_interval_hours: int
    created_at: str
    updated_at: str


class JobRecord(TypedDict):
    id: int
    job_type: str
    status: str
    source_url: str | None
    source_path: str | None
    category_id: int | None
    progress: int
    total_items: int
    current_item: str | None
    error_message: str | None
    priority: int  # Higher = more priority (0-100)
    started_at: str | None
    completed_at: str | None
    created_at: str


class ContentItemRecord(TypedDict):
    id: int
    title: str
    source_type: str
    source_url: str | None
    source_path: str | None
    category_id: int | None
    content_preview: str | None
    word_count: int
    chunk_count: int
    chromadb_collection: str | None
    metadata: str | None
    created_at: str
    updated_at: str


class SettingRecord(TypedDict):
    id: int
    key: str
    value: str
    category: str
    updated_at: str


class ConversationRecord(TypedDict):
    id: int
    title: str
    category_ids: str | None  # JSON array of category IDs, null = all categories
    use_maglib: bool  # If True, search MAG-LIB pgvector instead of ChromaDB
    created_at: str
    updated_at: str


class MessageRecord(TypedDict):
    id: int
    conversation_id: int
    role: str  # 'user' or 'assistant'
    content: str
    sources: str | None  # JSON array of source citations
    created_at: str


# Telegram Mini App models
class TelegramUserRecord(TypedDict):
    id: int
    telegram_id: int  # Telegram user ID
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    is_premium: bool
    tier: str  # 'free', 'starter', 'pro', 'business', 'enterprise'
    queries_used: int
    queries_remaining: int
    subscription_ends_at: str | None
    created_at: str
    updated_at: str


class SubscriptionRecord(TypedDict):
    id: int
    telegram_user_id: int
    tier: str
    status: str  # 'active', 'cancelled', 'expired'
    started_at: str
    ends_at: str
    telegram_payment_charge_id: str | None
    created_at: str


class PaymentHistoryRecord(TypedDict):
    id: int
    telegram_user_id: int
    payment_type: str  # 'subscription', 'token_bundle'
    amount_stars: int
    tier: str | None  # For subscriptions
    bundle_id: str | None  # For token bundles
    tokens_added: int | None
    telegram_payment_charge_id: str
    provider_payment_charge_id: str | None
    status: str  # 'completed', 'refunded'
    created_at: str


class TgConversationRecord(TypedDict):
    id: int
    telegram_user_id: int
    title: str
    pdf_ids: str | None  # JSON array of PDF/category IDs
    created_at: str
    updated_at: str


class TgMessageRecord(TypedDict):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: str | None
    created_at: str


class SavedConversationRecord(TypedDict):
    id: int
    telegram_user_id: int
    conversation_id: int
    title: str
    share_token: str | None
    is_public: int
    created_at: str
    updated_at: str


class SavedConversationDocumentRecord(TypedDict):
    id: int
    saved_conversation_id: int
    document_id: str
    added_at: str


# Analytics models (for tracking user events and metrics)
class AnalyticsEventRecord(TypedDict):
    id: int
    event_type: str
    telegram_user_id: int
    telegram_id: int
    user_tier: str
    metadata: str | None  # JSON blob
    session_id: str | None
    created_at: str


class AnalyticsSessionRecord(TypedDict):
    id: int
    session_id: str
    telegram_user_id: int
    page_views: int
    events_count: int
    started_at: str
    ended_at: str | None


class AnalyticsQueryMetadataRecord(TypedDict):
    id: int
    event_id: int
    conversation_id: int | None
    query_text: str
    query_length: int
    collection: str
    selected_doc_count: int
    response_time_ms: int | None
    source_count: int | None
    has_sources: bool
    created_at: str


class AnalyticsConversionFunnelRecord(TypedDict):
    id: int
    telegram_user_id: int
    reached_signup: bool
    reached_first_query: bool
    reached_purchase: bool
    signup_at: str | None
    first_query_at: str | None
    purchase_at: str | None
    queries_before_upgrade: int
    created_at: str
    updated_at: str


# Subscription tier constants
SubscriptionTier = Literal["free", "starter", "pro", "business", "enterprise"]

# Tier limits configuration - Knowledge Archive TWA
# Note: Using daily_queries instead of monthly_queries for the new system
TIER_LIMITS = {
    "free": {
        "max_pdfs": 1,                    # Document selections (MVP v1 not implemented)
        "daily_queries": 3,               # MVP v1: 3 questions per day
        "monthly_queries": 3,             # Legacy: same as daily for backwards compat
        "max_saved_conversations": 0,     # MVP v1: cannot save conversations
        "history_days": 30,
        "price_stars": 0,
        "price_usd": 0,
        "payment_method": None,
    },
    "starter": {
        "max_pdfs": None,                 # MVP v1: doc selection not implemented
        "daily_queries": 25,              # MVP v1: 25 questions per day
        "monthly_queries": 25,            # Legacy
        "max_saved_conversations": None,  # MVP v1: unlimited saves
        "history_days": 90,
        "price_stars": 680,               # ~$14.99 USD (approx)
        "price_usd": 1499,                # In cents
        "payment_method": "telegram_stars",
    },
    "pro": {
        "max_pdfs": None,                 # MVP v1: doc selection not implemented
        "daily_queries": 100,             # MVP v1: 100 questions per day
        "monthly_queries": 100,           # Legacy
        "max_saved_conversations": None,  # MVP v1: unlimited saves
        "history_days": 365,
        "price_stars": 1360,              # ~$29.99 USD (approx)
        "price_usd": 2999,                # In cents
        "payment_method": "telegram_stars",
    },
    "unlimited": {
        "max_pdfs": None,                 # Unlimited
        "daily_queries": None,            # Unlimited
        "monthly_queries": None,          # Legacy
        "max_saved_conversations": None,  # Unlimited saved conversations/chats
        "history_days": None,
        "price_stars": 5777,              # ~$99.99 USD (approx)
        "price_usd": 9999,                # In cents
        "payment_method": "telegram_stars",
    },
    "enterprise": {
        "max_pdfs": None,                 # Unlimited
        "daily_queries": None,            # Unlimited
        "monthly_queries": None,          # Legacy
        "max_saved_conversations": None,  # Unlimited
        "history_days": None,
        "price_stars": None,              # Admin only - no payment
        "price_usd": None,                # Admin only - no payment
        "payment_method": None,           # Admin/whitelisted users only
    },
    # Legacy tiers for backwards compatibility
    "scholar": {
        "max_pdfs": None,
        "daily_queries": 20,
        "monthly_queries": 20,
        "max_saved_conversations": None,
        "history_days": 90,
        "price_stars": 915,
        "price_usd": 1999,
        "payment_method": "telegram_stars",
    },
    "researcher": {
        "max_pdfs": None,
        "daily_queries": 100,
        "monthly_queries": 100,
        "max_saved_conversations": None,
        "history_days": 365,
        "price_stars": 2298,
        "price_usd": 4999,
        "payment_method": "telegram_stars",
    },
    "business": {
        "max_pdfs": None,
        "daily_queries": None,
        "monthly_queries": None,
        "max_saved_conversations": None,
        "history_days": None,
        "price_stars": 5777,
        "price_usd": 9999,
        "payment_method": "telegram_stars",
    },
    "enterprise": {
        "max_pdfs": None,
        "daily_queries": None,
        "monthly_queries": None,
        "max_saved_conversations": None,
        "history_days": None,
        "price_stars": 5777,
        "price_usd": 9999,
        "payment_method": "telegram_stars",
    },
}


# Job status constants
JobStatus = Literal["pending", "running", "completed", "failed", "cancelled", "paused"]

# Job type constants
JobType = Literal[
    "document_upload",
    "youtube_video",
    "youtube_channel",
    "youtube_channel_check",
    "website_scrape",
]

# Source type constants
SourceType = Literal[
    "document",
    "youtube_video",
    "youtube_transcript",
    "website",
    "audio_transcript",
]


# Database schema
SCHEMA = """
-- Categories for organizing content (hierarchical with max 6 levels)
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT NOT NULL DEFAULT '#3B82F6',
    icon TEXT,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    item_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, parent_id)
);

-- Monitored YouTube channels
CREATE TABLE IF NOT EXISTS monitored_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT NOT NULL,
    channel_url TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    last_checked_at TEXT,
    last_video_id TEXT,
    video_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    check_interval_hours INTEGER DEFAULT 48,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Processing jobs queue
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source_url TEXT,
    source_path TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    progress INTEGER DEFAULT 0,
    total_items INTEGER DEFAULT 1,
    current_item TEXT,
    error_message TEXT,
    priority INTEGER DEFAULT 50,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ingested content items
CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    source_path TEXT,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    content_preview TEXT,
    word_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    chromadb_collection TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Application settings (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Chat conversations
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    category_ids TEXT,  -- JSON array of category IDs, NULL = all categories
    use_maglib INTEGER DEFAULT 0,  -- If 1, search MAG-LIB pgvector instead of ChromaDB
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Chat messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sources TEXT,  -- JSON array of source citations
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
CREATE INDEX IF NOT EXISTS idx_content_category ON content_items(category_id);
CREATE INDEX IF NOT EXISTS idx_content_source_type ON content_items(source_type);
CREATE INDEX IF NOT EXISTS idx_channels_active ON monitored_channels(is_active);
CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_categories_depth ON categories(depth);

-- Triggers to auto-update timestamps
CREATE TRIGGER IF NOT EXISTS update_categories_timestamp
    AFTER UPDATE ON categories
    BEGIN
        UPDATE categories SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_channels_timestamp
    AFTER UPDATE ON monitored_channels
    BEGIN
        UPDATE monitored_channels SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_content_timestamp
    AFTER UPDATE ON content_items
    BEGIN
        UPDATE content_items SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_settings_timestamp
    AFTER UPDATE ON settings
    BEGIN
        UPDATE settings SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_conversations_timestamp
    AFTER UPDATE ON conversations
    BEGIN
        UPDATE conversations SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_conversation_on_message
    AFTER INSERT ON messages
    BEGIN
        UPDATE conversations SET updated_at = datetime('now') WHERE id = NEW.conversation_id;
    END;

-- ============================================================================
-- Telegram Mini App Tables
-- ============================================================================

-- Telegram users (linked to Telegram account)
CREATE TABLE IF NOT EXISTS telegram_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    username TEXT,
    language_code TEXT,
    is_premium INTEGER DEFAULT 0,
    tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'starter', 'scholar', 'pro', 'researcher', 'business', 'enterprise')),
    queries_used INTEGER DEFAULT 0,
    queries_remaining INTEGER DEFAULT 20,
    subscription_ends_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Subscription history
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('starter', 'scholar', 'pro', 'researcher', 'business', 'enterprise')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'expired')),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ends_at TEXT NOT NULL,
    telegram_payment_charge_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Payment history (subscriptions and token bundles)
CREATE TABLE IF NOT EXISTS payment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    payment_type TEXT NOT NULL CHECK (payment_type IN ('subscription', 'token_bundle')),
    amount_stars INTEGER NOT NULL,
    tier TEXT,
    bundle_id TEXT,
    tokens_added INTEGER,
    telegram_payment_charge_id TEXT NOT NULL,
    provider_payment_charge_id TEXT,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'refunded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Telegram conversations (separate from main conversations)
CREATE TABLE IF NOT EXISTS tg_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Chat',
    pdf_ids TEXT,  -- JSON array of PDF/category IDs
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Telegram messages
CREATE TABLE IF NOT EXISTS tg_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES tg_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sources TEXT,  -- JSON array of source citations
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Saved conversations (user-saved chats with history)
CREATE TABLE IF NOT EXISTS saved_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES tg_conversations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,  -- User-provided name like "Magick Research"
    share_token TEXT UNIQUE,  -- UUID for public sharing
    is_public INTEGER DEFAULT 0,  -- 0=private, 1=shared
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Documents selected for a saved conversation
CREATE TABLE IF NOT EXISTS saved_conversation_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_conversation_id INTEGER NOT NULL REFERENCES saved_conversations(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,  -- Format: "maglib:123" or "bibliothek:456"
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for Telegram tables
CREATE INDEX IF NOT EXISTS idx_telegram_users_telegram_id ON telegram_users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_payment_history_user ON payment_history(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_tg_conversations_user ON tg_conversations(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_tg_conversations_updated ON tg_conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tg_messages_conversation ON tg_messages(conversation_id);

-- Indexes for saved conversations
CREATE INDEX IF NOT EXISTS idx_saved_conversations_user ON saved_conversations(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_saved_conversations_share_token ON saved_conversations(share_token);
CREATE INDEX IF NOT EXISTS idx_saved_conversations_created ON saved_conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_saved_conversation_documents ON saved_conversation_documents(saved_conversation_id);

-- Triggers for Telegram tables
CREATE TRIGGER IF NOT EXISTS update_telegram_users_timestamp
    AFTER UPDATE ON telegram_users
    BEGIN
        UPDATE telegram_users SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_tg_conversations_timestamp
    AFTER UPDATE ON tg_conversations
    BEGIN
        UPDATE tg_conversations SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS update_tg_conversation_on_message
    AFTER INSERT ON tg_messages
    BEGIN
        UPDATE tg_conversations SET updated_at = datetime('now') WHERE id = NEW.conversation_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_saved_conversations_timestamp
    AFTER UPDATE ON saved_conversations
    BEGIN
        UPDATE saved_conversations SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

-- ============================================================================
-- Analytics Tables (for tracking user events and metrics)
-- ============================================================================

-- Core event tracking with denormalized user data for fast queries
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'user_signup', 'user_login', 'document_browse', 'chat_query',
        'conversation_saved', 'subscription_purchase', 'payment_failed'
    )),
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    telegram_id INTEGER NOT NULL,
    user_tier TEXT NOT NULL,
    metadata TEXT,  -- JSON blob: {"collection": "maglib", "query_length": 42}
    session_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- User session tracking
CREATE TABLE IF NOT EXISTS analytics_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
    page_views INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);

-- Detailed query metrics (response time, tokens, sources)
CREATE TABLE IF NOT EXISTS analytics_query_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES analytics_events(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES tg_conversations(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    query_length INTEGER NOT NULL,
    collection TEXT NOT NULL,
    selected_doc_count INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    source_count INTEGER,
    has_sources INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-user conversion funnel tracking
CREATE TABLE IF NOT EXISTS analytics_conversion_funnel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE REFERENCES telegram_users(id) ON DELETE CASCADE,
    reached_signup INTEGER DEFAULT 0,
    reached_first_query INTEGER DEFAULT 0,
    reached_purchase INTEGER DEFAULT 0,
    signup_at TEXT,
    first_query_at TEXT,
    purchase_at TEXT,
    queries_before_upgrade INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for analytics tables
CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_user ON analytics_events(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_created ON analytics_events(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type_created ON analytics_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_sessions_user ON analytics_sessions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_query_metadata_event ON analytics_query_metadata(event_id);
CREATE INDEX IF NOT EXISTS idx_analytics_query_metadata_conversation ON analytics_query_metadata(conversation_id);
CREATE INDEX IF NOT EXISTS idx_analytics_funnel_user ON analytics_conversion_funnel(telegram_user_id);

-- Trigger for conversion funnel timestamp update
CREATE TRIGGER IF NOT EXISTS update_analytics_funnel_timestamp
    AFTER UPDATE ON analytics_conversion_funnel
    BEGIN
        UPDATE analytics_conversion_funnel SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

-- ============================================================================
-- Dodo Payments Integration (for credit card payments)
-- ============================================================================

-- Dodo payment transactions tracking
CREATE TABLE IF NOT EXISTS dodo_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,

    -- Dodo transaction identifiers
    checkout_session_id TEXT UNIQUE,  -- From checkout session creation
    payment_id TEXT UNIQUE,           -- From completed payment (payment.completed webhook)

    -- Payment details
    tier TEXT NOT NULL,               -- scholar/researcher/unlimited
    amount_usd INTEGER NOT NULL,      -- Amount in cents (1500, 3900, 9900)
    currency TEXT DEFAULT 'USD',

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    payment_method TEXT,              -- card_visa, card_mastercard, etc.

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,                -- When payment.completed webhook received
    expires_at TEXT,                  -- Checkout session expiry (24h or 15min)

    -- Metadata
    customer_email TEXT,
    customer_id TEXT,                 -- Dodo customer ID
    error_code TEXT,                  -- If status = failed
    error_message TEXT,
    webhook_event_id TEXT,            -- For deduplication

    FOREIGN KEY (telegram_user_id) REFERENCES telegram_users(id) ON DELETE CASCADE
);

-- Indexes for dodo_payments table
CREATE INDEX IF NOT EXISTS idx_dodo_payments_user ON dodo_payments(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_dodo_payments_session ON dodo_payments(checkout_session_id);
CREATE INDEX IF NOT EXISTS idx_dodo_payments_status ON dodo_payments(status);
CREATE INDEX IF NOT EXISTS idx_dodo_payments_created ON dodo_payments(created_at);

-- Trigger for dodo_payments timestamp update
CREATE TRIGGER IF NOT EXISTS update_dodo_payments_timestamp
    AFTER UPDATE ON dodo_payments
    BEGIN
        UPDATE dodo_payments SET created_at = created_at WHERE id = NEW.id;
    END;
"""

# Default categories
DEFAULT_CATEGORIES = [
    ("General", "Uncategorized content", "#6B7280", "folder"),
    ("Documentation", "Technical documentation and guides", "#3B82F6", "book-open"),
    ("Research", "Research papers and articles", "#8B5CF6", "flask"),
    ("Tutorials", "Educational and tutorial content", "#10B981", "graduation-cap"),
    ("News", "News and updates", "#F59E0B", "newspaper"),
]


async def migrate_categories_hierarchy(db: aiosqlite.Connection) -> None:
    """Migrate categories table to support hierarchy (parent_id, depth)."""
    # Check if parent_id column exists
    cursor = await db.execute("PRAGMA table_info(categories)")
    columns = [row[1] for row in await cursor.fetchall()]

    if "parent_id" not in columns:
        print("Migrating categories table to support hierarchy...")
        # Add parent_id and depth columns
        await db.execute("ALTER TABLE categories ADD COLUMN parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
        await db.execute("ALTER TABLE categories ADD COLUMN depth INTEGER NOT NULL DEFAULT 0")
        await db.commit()

        # Create indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_categories_depth ON categories(depth)")
        await db.commit()

        # Drop the old unique constraint and create new one
        # Note: SQLite doesn't support DROP CONSTRAINT, so we need to recreate the table
        # For now, we'll just proceed - duplicate names at same level will be caught by the app
        print("Categories hierarchy migration complete.")


async def migrate_jobs_priority(db: aiosqlite.Connection) -> None:
    """Migrate jobs table to add priority column."""
    cursor = await db.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in await cursor.fetchall()]

    if "priority" not in columns:
        print("Migrating jobs table to add priority column...")
        await db.execute("ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 50")
        await db.commit()
        await db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC)")
        await db.commit()
        print("Jobs priority migration complete.")


async def migrate_conversations_use_maglib(db: aiosqlite.Connection) -> None:
    """Migrate conversations table to add use_maglib column for MAG-LIB pgvector search."""
    cursor = await db.execute("PRAGMA table_info(conversations)")
    columns = [row[1] for row in await cursor.fetchall()]

    if "use_maglib" not in columns:
        print("Migrating conversations table to add use_maglib column...")
        await db.execute("ALTER TABLE conversations ADD COLUMN use_maglib INTEGER DEFAULT 0")
        await db.commit()
        print("Conversations use_maglib migration complete.")


async def migrate_saved_conversations(db: aiosqlite.Connection) -> None:
    """Create saved_conversations and saved_conversation_documents tables if they don't exist."""
    # Check if saved_conversations table exists
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='saved_conversations'"
    )
    if await cursor.fetchone():
        # Table already exists, no migration needed
        return

    print("Creating saved_conversations and saved_conversation_documents tables...")

    # Create saved_conversations table
    await db.execute("""
        CREATE TABLE IF NOT EXISTS saved_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES tg_conversations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            share_token TEXT UNIQUE,
            is_public INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Create saved_conversation_documents table
    await db.execute("""
        CREATE TABLE IF NOT EXISTS saved_conversation_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_conversation_id INTEGER NOT NULL REFERENCES saved_conversations(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Create indexes
    await db.execute("CREATE INDEX IF NOT EXISTS idx_saved_conversations_user ON saved_conversations(telegram_user_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_saved_conversations_share_token ON saved_conversations(share_token)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_saved_conversations_created ON saved_conversations(created_at DESC)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_saved_conversation_documents ON saved_conversation_documents(saved_conversation_id)")

    # Create trigger for timestamp auto-update
    await db.execute("""
        CREATE TRIGGER IF NOT EXISTS update_saved_conversations_timestamp
            AFTER UPDATE ON saved_conversations
            BEGIN
                UPDATE saved_conversations SET updated_at = datetime('now') WHERE id = NEW.id;
            END
    """)

    await db.commit()
    print("Saved conversations migration complete.")


async def init_database() -> None:
    """Initialize the SQLite database with schema and default data."""
    db_path = config.database.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        # Run migrations FIRST for existing databases (before schema which has new indexes)
        await migrate_categories_hierarchy(db)
        await migrate_jobs_priority(db)
        await migrate_conversations_use_maglib(db)
        await migrate_saved_conversations(db)

        # Now execute the full schema (CREATE IF NOT EXISTS is safe)
        await db.executescript(SCHEMA)
        await db.commit()

        # Insert default categories if none exist
        cursor = await db.execute("SELECT COUNT(*) FROM categories")
        count = (await cursor.fetchone())[0]

        if count == 0:
            await db.executemany(
                "INSERT INTO categories (name, description, color, icon, depth) VALUES (?, ?, ?, ?, 0)",
                DEFAULT_CATEGORIES,
            )
            await db.commit()


def get_db_path() -> Path:
    """Get the database file path."""
    return config.database.sqlite_path
