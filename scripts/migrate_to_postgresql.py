#!/usr/bin/env python3
"""
Migration script: SQLite knowledge_hub.db → PostgreSQL docling_metadata

This script:
1. Creates all required PostgreSQL tables
2. Migrates data from SQLite to PostgreSQL
3. Preserves all relationships and constraints
4. Validates data integrity
"""

import asyncio
import asyncpg
import sqlite3
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from sshtunnel import SSHTunnelForwarder

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
SQLITE_PATH = PROJECT_ROOT / "data" / "knowledge_hub.db"

# PostgreSQL connection details (NAS)
PG_HOST = "192.168.1.117"
PG_PORT = 5432
PG_USER = "docling"
PG_PASSWORD = "docling_secure_pwd_2024"
PG_DATABASE = "docling_metadata"

# SSH tunnel details
SSH_HOST = "192.168.1.117"
SSH_PORT = 22
SSH_USER = "kanat"
SSH_PASSWORD = "Drakuul55+"


async def create_postgresql_schema(pool):
    """Create all PostgreSQL tables"""
    print("Creating PostgreSQL schema...")

    # Enable uuid-ossp extension
    await pool.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

    sql_commands = [
        # Categories table
        """
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            color TEXT NOT NULL DEFAULT '#3B82F6',
            icon TEXT,
            item_count INTEGER DEFAULT 0,
            parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            depth INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Monitored channels
        """
        CREATE TABLE IF NOT EXISTS monitored_channels (
            id SERIAL PRIMARY KEY,
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL,
            channel_url TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            last_checked_at TIMESTAMP,
            last_video_id TEXT,
            video_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            check_interval_hours INTEGER DEFAULT 48,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Jobs
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            source_url TEXT,
            source_path TEXT,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            progress INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 1,
            current_item TEXT,
            error_message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            priority INTEGER DEFAULT 50,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Content items
        """
        CREATE TABLE IF NOT EXISTS content_items (
            id SERIAL PRIMARY KEY,
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
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Settings
        """
        CREATE TABLE IF NOT EXISTS settings (
            id SERIAL PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Telegram users
        """
        CREATE TABLE IF NOT EXISTS telegram_users (
            id SERIAL PRIMARY KEY,
            telegram_id INTEGER NOT NULL UNIQUE,
            first_name TEXT NOT NULL,
            last_name TEXT,
            username TEXT,
            language_code TEXT,
            is_premium INTEGER DEFAULT 0,
            tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'starter', 'pro', 'business', 'enterprise')),
            queries_used INTEGER DEFAULT 0,
            queries_remaining INTEGER DEFAULT 20,
            subscription_ends_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Subscriptions
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            tier TEXT NOT NULL CHECK (tier IN ('starter', 'pro', 'business', 'enterprise')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'expired')),
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMP NOT NULL,
            telegram_payment_charge_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Payment history
        """
        CREATE TABLE IF NOT EXISTS payment_history (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            payment_type TEXT NOT NULL CHECK (payment_type IN ('subscription', 'token_bundle')),
            amount_stars INTEGER NOT NULL,
            tier TEXT,
            bundle_id TEXT,
            tokens_added INTEGER,
            telegram_payment_charge_id TEXT NOT NULL,
            provider_payment_charge_id TEXT,
            status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed', 'refunded')),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Telegram conversations
        """
        CREATE TABLE IF NOT EXISTS tg_conversations (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT 'New Chat',
            pdf_ids TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Telegram messages
        """
        CREATE TABLE IF NOT EXISTS tg_messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES tg_conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            sources TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Saved conversations
        """
        CREATE TABLE IF NOT EXISTS saved_conversations (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES tg_conversations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            share_token TEXT UNIQUE,
            is_public INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Saved conversation documents
        """
        CREATE TABLE IF NOT EXISTS saved_conversation_documents (
            id SERIAL PRIMARY KEY,
            saved_conversation_id INTEGER NOT NULL REFERENCES saved_conversations(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL,
            added_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Analytics events
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
            id SERIAL PRIMARY KEY,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'user_signup', 'user_login', 'document_browse', 'chat_query',
                'conversation_saved', 'subscription_purchase', 'payment_failed'
            )),
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            telegram_id INTEGER NOT NULL,
            user_tier TEXT NOT NULL,
            metadata TEXT,
            session_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Analytics sessions
        """
        CREATE TABLE IF NOT EXISTS analytics_sessions (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL UNIQUE,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            page_views INTEGER DEFAULT 0,
            events_count INTEGER DEFAULT 0,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMP
        );
        """,

        # Analytics query metadata
        """
        CREATE TABLE IF NOT EXISTS analytics_query_metadata (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES analytics_events(id) ON DELETE CASCADE,
            conversation_id INTEGER REFERENCES tg_conversations(id) ON DELETE SET NULL,
            query_text TEXT NOT NULL,
            query_length INTEGER NOT NULL,
            collection TEXT NOT NULL,
            selected_doc_count INTEGER DEFAULT 0,
            response_time_ms INTEGER,
            source_count INTEGER,
            has_sources INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Analytics conversion funnel
        """
        CREATE TABLE IF NOT EXISTS analytics_conversion_funnel (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL UNIQUE REFERENCES telegram_users(id) ON DELETE CASCADE,
            reached_signup INTEGER DEFAULT 0,
            reached_first_query INTEGER DEFAULT 0,
            reached_purchase INTEGER DEFAULT 0,
            signup_at TIMESTAMP,
            first_query_at TIMESTAMP,
            purchase_at TIMESTAMP,
            queries_before_upgrade INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """,

        # Dodo payments
        """
        CREATE TABLE IF NOT EXISTS dodo_payments (
            id SERIAL PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
            checkout_session_id TEXT UNIQUE,
            payment_id TEXT UNIQUE,
            tier TEXT NOT NULL,
            amount_usd INTEGER NOT NULL,
            currency TEXT DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
            payment_method TEXT,
            customer_email TEXT,
            customer_id TEXT,
            error_code TEXT,
            error_message TEXT,
            webhook_event_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            expires_at TIMESTAMP
        );
        """,
    ]

    for sql in sql_commands:
        try:
            await pool.execute(sql)
            print(f"  ✓ Created table")
        except asyncpg.DuplicateTableError:
            print(f"  • Table already exists")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            raise

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);",
        "CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);",
        "CREATE INDEX IF NOT EXISTS idx_content_category ON content_items(category_id);",
        "CREATE INDEX IF NOT EXISTS idx_content_source_type ON content_items(source_type);",
        "CREATE INDEX IF NOT EXISTS idx_channels_active ON monitored_channels(is_active);",
        "CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category);",
        "CREATE INDEX IF NOT EXISTS idx_telegram_users_telegram_id ON telegram_users(telegram_id);",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);",
        "CREATE INDEX IF NOT EXISTS idx_payment_history_user ON payment_history(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_tg_conversations_user ON tg_conversations(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_tg_conversations_updated ON tg_conversations(updated_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_tg_messages_conversation ON tg_messages(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_saved_conversations_user ON saved_conversations(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_saved_conversations_share_token ON saved_conversations(share_token);",
        "CREATE INDEX IF NOT EXISTS idx_saved_conversations_created ON saved_conversations(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);",
        "CREATE INDEX IF NOT EXISTS idx_analytics_events_user ON analytics_events(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_analytics_events_created ON analytics_events(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_analytics_sessions_user ON analytics_sessions(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_analytics_query_metadata_event ON analytics_query_metadata(event_id);",
        "CREATE INDEX IF NOT EXISTS idx_dodo_payments_user ON dodo_payments(telegram_user_id);",
        "CREATE INDEX IF NOT EXISTS idx_dodo_payments_session ON dodo_payments(checkout_session_id);",
        "CREATE INDEX IF NOT EXISTS idx_dodo_payments_status ON dodo_payments(status);",
    ]

    for idx_sql in indexes:
        try:
            await pool.execute(idx_sql)
        except:
            pass  # Index may already exist

    print("✓ PostgreSQL schema created")


def convert_sqlite_timestamp(dt_str):
    """Convert SQLite datetime string to Python datetime"""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None


async def migrate_data(pool):
    """Migrate all data from SQLite to PostgreSQL"""
    print("\nMigrating data from SQLite to PostgreSQL...")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    try:
        # Tables to migrate in order (respecting foreign keys)
        tables_order = [
            'categories',
            'monitored_channels',
            'jobs',
            'content_items',
            'settings',
            'telegram_users',
            'subscriptions',
            'payment_history',
            'tg_conversations',
            'tg_messages',
            'saved_conversations',
            'saved_conversation_documents',
            'analytics_events',
            'analytics_sessions',
            'analytics_query_metadata',
            'analytics_conversion_funnel',
            'dodo_payments',
        ]

        for table in tables_order:
            print(f"\n  Migrating '{table}'...")
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"    Found {count} records")

            if count == 0:
                print(f"    ✓ Empty table")
                continue

            # Get all data from SQLite
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            column_names = [description[0] for description in cursor.description]

            if not rows:
                continue

            # Insert into PostgreSQL
            inserted = 0
            failed = 0

            for row in rows:
                try:
                    values = []
                    for i, col in enumerate(column_names):
                        val = row[i]
                        # Convert SQLite types to PostgreSQL
                        if val is None:
                            values.append(None)
                        elif isinstance(val, str) and col.endswith('_at') or col.endswith('At'):
                            # Convert timestamp strings
                            converted = convert_sqlite_timestamp(val)
                            values.append(converted)
                        else:
                            values.append(val)

                    # Build INSERT statement
                    placeholders = ', '.join([f'${i+1}' for i in range(len(values))])
                    insert_sql = f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({placeholders})"

                    await pool.execute(insert_sql, *values)
                    inserted += 1

                except Exception as e:
                    failed += 1
                    print(f"    ✗ Failed to insert row: {e}")

            print(f"    ✓ Inserted {inserted} records" + (f" ({failed} failed)" if failed > 0 else ""))

        print("\n✓ Data migration completed")

    finally:
        sqlite_conn.close()


async def verify_migration(pool):
    """Verify that all data was migrated correctly"""
    print("\nVerifying migration...")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    cursor = sqlite_conn.cursor()

    tables = [
        'categories', 'monitored_channels', 'jobs', 'content_items', 'settings',
        'telegram_users', 'subscriptions', 'payment_history',
        'tg_conversations', 'tg_messages', 'saved_conversations',
        'saved_conversation_documents', 'analytics_events', 'analytics_sessions',
        'analytics_query_metadata', 'analytics_conversion_funnel', 'dodo_payments'
    ]

    all_match = True
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = cursor.fetchone()[0]

        pg_count = await pool.fetchval(f"SELECT COUNT(*) FROM {table}")

        match = "✓" if sqlite_count == pg_count else "✗"
        print(f"  {match} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")

        if sqlite_count != pg_count:
            all_match = False

    sqlite_conn.close()

    if all_match:
        print("\n✓ All data verified successfully!")
    else:
        print("\n✗ Some data mismatches detected")
        return False

    return True


async def main():
    """Main migration function"""
    print("=" * 60)
    print("SQLite → PostgreSQL Migration")
    print("=" * 60)
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {PG_HOST}:{PG_PORT}/{PG_DATABASE} (via SSH tunnel)")
    print("=" * 60)

    # Create SSH tunnel
    print("\nSetting up SSH tunnel...")
    tunnel = None
    try:
        tunnel = SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=("127.0.0.1", PG_PORT)
        )
        tunnel.start()
        print(f"✓ SSH tunnel established")
        print(f"  Local bind: {tunnel.local_bind_host}:{tunnel.local_bind_port}")
    except Exception as e:
        print(f"✗ Failed to create SSH tunnel: {e}")
        sys.exit(1)

    # Connect to PostgreSQL via tunnel
    print("\nConnecting to PostgreSQL...")
    try:
        pool = await asyncpg.create_pool(
            host=tunnel.local_bind_host,
            port=tunnel.local_bind_port,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE,
            min_size=1,
            max_size=10,
            timeout=30
        )
        print("✓ Connected to PostgreSQL via SSH tunnel")
    except Exception as e:
        print(f"✗ Failed to connect to PostgreSQL: {e}")
        tunnel.stop()
        sys.exit(1)

    try:
        # Create schema
        await create_postgresql_schema(pool)

        # Migrate data
        await migrate_data(pool)

        # Verify
        success = await verify_migration(pool)

        if success:
            print("\n" + "=" * 60)
            print("✓ Migration completed successfully!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Update app/config.py to enable PostgreSQL metadata")
            print("2. Update app/services/pgvector_service.py for metadata pool")
            print("3. Test the app with new PostgreSQL backend")
            print("4. Commit changes: git commit -m 'feat: Migrate metadata to PostgreSQL'")
            print("5. Redeploy to Railway")
        else:
            print("\n✗ Migration verification failed")
            sys.exit(1)
    finally:
        await pool.close()
        if tunnel:
            tunnel.stop()
            print("\n✓ SSH tunnel closed")


if __name__ == "__main__":
    asyncio.run(main())
