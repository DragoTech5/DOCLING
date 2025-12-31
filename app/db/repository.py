"""
Database Repository - CRUD operations for all models
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from app.db.models import (
    CategoryRecord,
    ContentItemRecord,
    JobRecord,
    MonitoredChannelRecord,
    SettingRecord,
    ConversationRecord,
    MessageRecord,
    JobStatus,
    JobType,
    SourceType,
    get_db_path,
)


# ============================================================================
# Categories Repository
# ============================================================================


MAX_CATEGORY_DEPTH = 5  # 0-indexed, so 6 levels total (0, 1, 2, 3, 4, 5)


async def get_categories() -> list[CategoryRecord]:
    """Get all categories ordered by hierarchy (depth-first, alphabetical)."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM categories ORDER BY depth, parent_id NULLS FIRST, name"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_categories_tree() -> list[dict]:
    """Get categories as a hierarchical tree structure."""
    categories = await get_categories()

    # Build a map of id -> category with children
    cat_map = {cat["id"]: {**cat, "children": []} for cat in categories}

    # Build tree
    roots = []
    for cat in categories:
        if cat["parent_id"] is None:
            roots.append(cat_map[cat["id"]])
        else:
            parent = cat_map.get(cat["parent_id"])
            if parent:
                parent["children"].append(cat_map[cat["id"]])

    return roots


async def get_category(category_id: int) -> CategoryRecord | None:
    """Get a single category by ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_category_by_name(name: str, parent_id: int | None = None) -> CategoryRecord | None:
    """Get a category by name within the same parent."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        if parent_id is None:
            cursor = await db.execute(
                "SELECT * FROM categories WHERE name = ? AND parent_id IS NULL", (name,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM categories WHERE name = ? AND parent_id = ?", (name, parent_id)
            )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_subcategories(parent_id: int) -> list[CategoryRecord]:
    """Get direct children of a category."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM categories WHERE parent_id = ? ORDER BY name",
            (parent_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_category_ancestors(category_id: int) -> list[CategoryRecord]:
    """Get all ancestors of a category (parent, grandparent, etc.)."""
    ancestors = []
    current_id = category_id

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        while current_id:
            cursor = await db.execute(
                "SELECT * FROM categories WHERE id = ?", (current_id,)
            )
            row = await cursor.fetchone()
            if not row:
                break
            cat = dict(row)
            if cat["parent_id"] is None:
                break
            # Get parent
            cursor = await db.execute(
                "SELECT * FROM categories WHERE id = ?", (cat["parent_id"],)
            )
            parent_row = await cursor.fetchone()
            if parent_row:
                ancestors.insert(0, dict(parent_row))
                current_id = dict(parent_row)["parent_id"]
            else:
                break

    return ancestors


async def create_category(
    name: str,
    description: str | None = None,
    color: str = "#3B82F6",
    icon: str | None = None,
    parent_id: int | None = None,
) -> int:
    """Create a new category. Max depth is 6 levels (0-5)."""
    depth = 0

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Calculate depth from parent
        if parent_id is not None:
            cursor = await db.execute(
                "SELECT depth FROM categories WHERE id = ?", (parent_id,)
            )
            parent_row = await cursor.fetchone()
            if parent_row:
                parent_depth = parent_row["depth"]
                depth = parent_depth + 1
                if depth > MAX_CATEGORY_DEPTH:
                    raise ValueError(f"Maximum category depth ({MAX_CATEGORY_DEPTH + 1} levels) exceeded")
            else:
                raise ValueError(f"Parent category {parent_id} not found")

        cursor = await db.execute(
            """INSERT INTO categories (name, description, color, icon, parent_id, depth)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, description, color, icon, parent_id, depth),
        )
        await db.commit()
        return cursor.lastrowid


async def update_category(
    category_id: int,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
    parent_id: int | None = ...,  # Use ... as sentinel for "not provided"
) -> bool:
    """Update a category. Use parent_id=None to move to root level."""
    updates = []
    values = []

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if color is not None:
            updates.append("color = ?")
            values.append(color)
        if icon is not None:
            updates.append("icon = ?")
            values.append(icon)

        # Handle parent change (moving category)
        if parent_id is not ...:
            # Prevent circular reference
            if parent_id == category_id:
                raise ValueError("Category cannot be its own parent")

            # Check if new parent is a descendant (would create cycle)
            if parent_id is not None:
                descendants = await _get_all_descendant_ids(db, category_id)
                if parent_id in descendants:
                    raise ValueError("Cannot move category under its own descendant")

                # Calculate new depth
                cursor = await db.execute(
                    "SELECT depth FROM categories WHERE id = ?", (parent_id,)
                )
                parent_row = await cursor.fetchone()
                if not parent_row:
                    raise ValueError(f"Parent category {parent_id} not found")
                new_depth = parent_row["depth"] + 1
            else:
                new_depth = 0

            # Check depth limit for this category and all descendants
            cursor = await db.execute(
                "SELECT depth FROM categories WHERE id = ?", (category_id,)
            )
            current_row = await cursor.fetchone()
            if current_row:
                current_depth = current_row["depth"]
                depth_change = new_depth - current_depth

                # Check max depth for all descendants
                cursor = await db.execute(
                    "SELECT MAX(depth) FROM categories WHERE id IN (SELECT id FROM categories WHERE parent_id = ?)",
                    (category_id,)
                )
                max_desc_depth_row = await cursor.fetchone()
                max_descendant_depth = max_desc_depth_row[0] if max_desc_depth_row and max_desc_depth_row[0] else current_depth

                if max_descendant_depth + depth_change > MAX_CATEGORY_DEPTH:
                    raise ValueError(f"Moving would exceed maximum depth ({MAX_CATEGORY_DEPTH + 1} levels)")

            updates.append("parent_id = ?")
            values.append(parent_id)
            updates.append("depth = ?")
            values.append(new_depth)

        if not updates:
            return False

        values.append(category_id)
        query = f"UPDATE categories SET {', '.join(updates)} WHERE id = ?"

        cursor = await db.execute(query, values)
        await db.commit()

        # Update depths of all descendants if parent changed
        if parent_id is not ... and cursor.rowcount > 0:
            await _update_descendant_depths(db, category_id)
            await db.commit()

        return cursor.rowcount > 0


async def _get_all_descendant_ids(db: aiosqlite.Connection, category_id: int) -> set[int]:
    """Get all descendant IDs of a category (children, grandchildren, etc.)."""
    descendants = set()
    to_check = [category_id]

    while to_check:
        current_id = to_check.pop()
        cursor = await db.execute(
            "SELECT id FROM categories WHERE parent_id = ?", (current_id,)
        )
        rows = await cursor.fetchall()
        for row in rows:
            child_id = row[0]
            if child_id not in descendants:
                descendants.add(child_id)
                to_check.append(child_id)

    return descendants


async def _update_descendant_depths(db: aiosqlite.Connection, category_id: int) -> None:
    """Recursively update depths of all descendants after a parent move."""
    cursor = await db.execute(
        "SELECT id, depth FROM categories WHERE id = ?", (category_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return

    parent_depth = row[1]

    # Get direct children and update their depths
    cursor = await db.execute(
        "SELECT id FROM categories WHERE parent_id = ?", (category_id,)
    )
    children = await cursor.fetchall()

    for child in children:
        child_id = child[0]
        new_depth = parent_depth + 1
        await db.execute(
            "UPDATE categories SET depth = ? WHERE id = ?",
            (new_depth, child_id)
        )
        # Recursively update grandchildren
        await _update_descendant_depths(db, child_id)


async def update_category_item_count(category_id: int, delta: int = 1) -> None:
    """Update the item count for a category."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE categories SET item_count = item_count + ? WHERE id = ?",
            (delta, category_id),
        )
        await db.commit()


async def delete_category(category_id: int) -> bool:
    """Delete a category, moving subcategories and content to parent (grandparent)."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get the category to delete
        cursor = await db.execute(
            "SELECT parent_id, depth FROM categories WHERE id = ?", (category_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False

        grandparent_id = row["parent_id"]  # May be None (root level)

        # Calculate new depth for children
        new_child_depth = row["depth"]  # Children take the deleted category's depth

        # Move all direct subcategories to the grandparent
        await db.execute(
            "UPDATE categories SET parent_id = ?, depth = ? WHERE parent_id = ?",
            (grandparent_id, new_child_depth, category_id)
        )

        # Update depths of descendants recursively
        cursor = await db.execute(
            "SELECT id FROM categories WHERE parent_id = ?", (grandparent_id if grandparent_id else -1,)
        )
        # Actually we need to update all former children
        cursor = await db.execute(
            "SELECT id FROM categories WHERE parent_id IS ? AND depth = ?",
            (grandparent_id, new_child_depth)
        )
        former_children = await cursor.fetchall()
        for child in former_children:
            await _update_descendant_depths(db, child[0])

        # Move content items to grandparent (or set to NULL if no grandparent)
        await db.execute(
            "UPDATE content_items SET category_id = ? WHERE category_id = ?",
            (grandparent_id, category_id)
        )

        # Move monitored channels to grandparent
        await db.execute(
            "UPDATE monitored_channels SET category_id = ? WHERE category_id = ?",
            (grandparent_id, category_id)
        )

        # Update grandparent's item count if it exists
        if grandparent_id:
            cursor = await db.execute(
                "SELECT item_count FROM categories WHERE id = ?", (category_id,)
            )
            deleted_count_row = await cursor.fetchone()
            if deleted_count_row and deleted_count_row[0]:
                await db.execute(
                    "UPDATE categories SET item_count = item_count + ? WHERE id = ?",
                    (deleted_count_row[0], grandparent_id)
                )

        # Delete the category
        cursor = await db.execute(
            "DELETE FROM categories WHERE id = ?", (category_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def move_content_to_category(
    content_ids: list[int],
    target_category_id: int | None
) -> int:
    """Move content items to a different category. Returns count of items moved."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get current categories for updating counts
        placeholders = ",".join(["?"] * len(content_ids))
        cursor = await db.execute(
            f"SELECT DISTINCT category_id FROM content_items WHERE id IN ({placeholders})",
            content_ids
        )
        old_categories = [row[0] for row in await cursor.fetchall() if row[0]]

        # Move the items
        cursor = await db.execute(
            f"UPDATE content_items SET category_id = ? WHERE id IN ({placeholders})",
            [target_category_id] + content_ids
        )
        moved_count = cursor.rowcount

        # Update item counts
        for old_cat_id in old_categories:
            if old_cat_id != target_category_id:
                # Count how many items were in this category
                cursor = await db.execute(
                    f"SELECT COUNT(*) FROM content_items WHERE category_id = ? AND id IN ({placeholders})",
                    [old_cat_id] + content_ids
                )
                # Decrement old category (items already moved, so count from original selection)
                await db.execute(
                    "UPDATE categories SET item_count = item_count - ? WHERE id = ?",
                    (moved_count, old_cat_id)
                )

        if target_category_id:
            await db.execute(
                "UPDATE categories SET item_count = item_count + ? WHERE id = ?",
                (moved_count, target_category_id)
            )

        await db.commit()
        return moved_count


async def move_channel_to_category(
    channel_id: int,
    target_category_id: int | None
) -> bool:
    """Move a monitored channel to a different category."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "UPDATE monitored_channels SET category_id = ? WHERE id = ?",
            (target_category_id, channel_id)
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Monitored Channels Repository
# ============================================================================


async def get_monitored_channels(active_only: bool = False) -> list[MonitoredChannelRecord]:
    """Get all monitored channels."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM monitored_channels"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY channel_name"

        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_monitored_channel(channel_id: int) -> MonitoredChannelRecord | None:
    """Get a monitored channel by ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM monitored_channels WHERE id = ?", (channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_channel_by_youtube_id(youtube_channel_id: str) -> MonitoredChannelRecord | None:
    """Get a channel by YouTube channel ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM monitored_channels WHERE channel_id = ?",
            (youtube_channel_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_monitored_channel(
    channel_id: str,
    channel_name: str,
    channel_url: str,
    category_id: int | None = None,
    check_interval_hours: int = 48,
) -> int:
    """Create a new monitored channel."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO monitored_channels
               (channel_id, channel_name, channel_url, category_id, check_interval_hours)
               VALUES (?, ?, ?, ?, ?)""",
            (channel_id, channel_name, channel_url, category_id, check_interval_hours),
        )
        await db.commit()
        return cursor.lastrowid


async def update_monitored_channel(
    channel_id: int,
    last_checked_at: str | None = None,
    last_video_id: str | None = None,
    video_count: int | None = None,
    is_active: bool | None = None,
    category_id: int | None = None,
) -> bool:
    """Update a monitored channel."""
    updates = []
    values = []

    if last_checked_at is not None:
        updates.append("last_checked_at = ?")
        values.append(last_checked_at)
    if last_video_id is not None:
        updates.append("last_video_id = ?")
        values.append(last_video_id)
    if video_count is not None:
        updates.append("video_count = ?")
        values.append(video_count)
    if is_active is not None:
        updates.append("is_active = ?")
        values.append(1 if is_active else 0)
    if category_id is not None:
        updates.append("category_id = ?")
        values.append(category_id)

    if not updates:
        return False

    values.append(channel_id)
    query = f"UPDATE monitored_channels SET {', '.join(updates)} WHERE id = ?"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, values)
        await db.commit()
        return cursor.rowcount > 0


async def delete_monitored_channel(channel_id: int) -> bool:
    """Delete a monitored channel."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM monitored_channels WHERE id = ?", (channel_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Jobs Repository
# ============================================================================


async def get_jobs(
    status: JobStatus | None = None,
    job_type: JobType | None = None,
    limit: int = 50,
) -> list[JobRecord]:
    """Get jobs with optional filters."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM jobs WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if job_type:
            query += " AND job_type = ?"
            params.append(job_type)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_job(job_id: int) -> JobRecord | None:
    """Get a job by ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_active_job_by_url(source_url: str) -> dict | None:
    """
    Check if there's an active job (pending/running/paused) for the given URL.

    Used for deduplication - prevents creating duplicate jobs for the same URL.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM jobs
               WHERE source_url = ? AND status IN ('pending', 'running', 'paused')
               ORDER BY created_at DESC
               LIMIT 1""",
            (source_url,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_content_by_url(source_url: str) -> dict | None:
    """
    Check if content has already been processed for the given URL.

    Used for deduplication - prevents reprocessing already completed content.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM content_items
               WHERE source_url = ?
               LIMIT 1""",
            (source_url,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_job(
    job_type: JobType,
    source_url: str | None = None,
    source_path: str | None = None,
    category_id: int | None = None,
    total_items: int = 1,
    priority: int = 50,
) -> int:
    """Create a new job."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO jobs (job_type, source_url, source_path, category_id, total_items, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_type, source_url, source_path, category_id, total_items, priority),
        )
        await db.commit()
        return cursor.lastrowid


async def update_job(
    job_id: int,
    status: JobStatus | None = None,
    progress: int | None = None,
    total_items: int | None = None,
    current_item: str | None = None,
    error_message: str | None = None,
    priority: int | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> bool:
    """Update a job."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if progress is not None:
        updates.append("progress = ?")
        values.append(progress)
    if total_items is not None:
        updates.append("total_items = ?")
        values.append(total_items)
    if current_item is not None:
        updates.append("current_item = ?")
        values.append(current_item)
    if error_message is not None:
        updates.append("error_message = ?")
        values.append(error_message)
    if priority is not None:
        updates.append("priority = ?")
        values.append(priority)
    if started_at is not None:
        updates.append("started_at = ?")
        values.append(started_at)
    if completed_at is not None:
        updates.append("completed_at = ?")
        values.append(completed_at)

    if not updates:
        return False

    values.append(job_id)
    query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, values)
        await db.commit()
        return cursor.rowcount > 0


async def start_job(job_id: int) -> bool:
    """Mark a job as started."""
    return await update_job(
        job_id,
        status="running",
        started_at=datetime.now().isoformat(),
    )


async def complete_job(job_id: int, error_message: str | None = None) -> bool:
    """Mark a job as completed or failed."""
    status = "failed" if error_message else "completed"
    return await update_job(
        job_id,
        status=status,
        error_message=error_message,
        completed_at=datetime.now().isoformat(),
    )


async def get_pending_jobs() -> list[JobRecord]:
    """
    Get jobs that need processing.

    Returns jobs with status 'pending' (new jobs) or 'running' (interrupted jobs).
    Ordered by priority (highest first), then created_at (oldest first).
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM jobs
               WHERE status IN ('pending', 'running')
               ORDER BY priority DESC, created_at ASC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def pause_job(job_id: int) -> bool:
    """
    Pause a running or pending job.

    The job's progress is preserved so it can resume where it left off.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """UPDATE jobs SET status = 'paused'
               WHERE id = ? AND status IN ('pending', 'running')""",
            (job_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def resume_job(job_id: int) -> bool:
    """
    Resume a paused job.

    Sets the job back to 'pending' so the worker will pick it up.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """UPDATE jobs SET status = 'pending'
               WHERE id = ? AND status = 'paused'""",
            (job_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_higher_priority_pending_job(current_priority: int) -> dict | None:
    """
    Check if there's a pending job with higher priority than the current one.

    Used for priority preemption - allows higher priority jobs to interrupt
    lower priority jobs that are currently running.

    Args:
        current_priority: Priority of the currently running job

    Returns:
        The highest priority pending job if one exists with higher priority,
        None otherwise.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM jobs
               WHERE status = 'pending' AND priority > ?
               ORDER BY priority DESC
               LIMIT 1""",
            (current_priority,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_worker_paused() -> bool:
    """Check if the worker is globally paused."""
    paused = await get_setting("worker_paused")
    return paused == "true"


async def set_worker_paused(paused: bool) -> None:
    """Set the global worker pause state."""
    await set_setting("worker_paused", "true" if paused else "false", category="worker")


async def claim_job(job_id: int, worker_id: str | None = None) -> bool:
    """
    Atomically claim a job for processing.

    Sets status to 'running' and records start time.
    Returns True if job was successfully claimed.
    """
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        # Only claim if job is pending or running (for resume)
        cursor = await db.execute(
            """UPDATE jobs
               SET status = 'running',
                   started_at = COALESCE(started_at, ?)
               WHERE id = ?
               AND status IN ('pending', 'running')""",
            (datetime.now().isoformat(), job_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Content Items Repository
# ============================================================================


async def get_content_items(
    category_id: int | None = None,
    source_type: SourceType | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ContentItemRecord]:
    """Get content items with optional filters."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM content_items WHERE 1=1"
        params = []

        if category_id is not None:
            query += " AND category_id = ?"
            params.append(category_id)
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_content_item(item_id: int) -> ContentItemRecord | None:
    """Get a content item by ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM content_items WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_content_by_source_path(source_path: str) -> ContentItemRecord | None:
    """Check if content has already been imported from this source path."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM content_items WHERE source_path = ? LIMIT 1",
            (source_path,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_content_item(
    title: str,
    source_type: SourceType,
    source_url: str | None = None,
    source_path: str | None = None,
    category_id: int | None = None,
    content_preview: str | None = None,
    word_count: int = 0,
    chunk_count: int = 0,
    chromadb_collection: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Create a new content item."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO content_items
               (title, source_type, source_url, source_path, category_id,
                content_preview, word_count, chunk_count, chromadb_collection, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                source_type,
                source_url,
                source_path,
                category_id,
                content_preview,
                word_count,
                chunk_count,
                chromadb_collection,
                json.dumps(metadata) if metadata else None,
            ),
        )
        await db.commit()

        # Update category item count
        if category_id:
            await update_category_item_count(category_id, 1)

        return cursor.lastrowid


async def video_exists(video_id: str, source_type: str = "youtube_transcript") -> bool:
    """Check if a video has already been transcribed.

    Checks both by video_id in metadata AND by source_url for robustness.
    This handles cases where metadata might be NULL due to earlier bugs.

    Args:
        video_id: The video ID to check
        source_type: "youtube_transcript" or "rumble_transcript"

    Returns:
        True if the video has already been transcribed
    """
    # Build the expected video URL based on source type
    if source_type == "rumble_transcript":
        # Rumble URL format: https://rumble.com/v{id}
        vid = video_id if video_id.startswith('v') else f"v{video_id}"
        video_url = f"https://rumble.com/{vid}"
    else:
        # YouTube URL format: https://www.youtube.com/watch?v={id}
        video_url = f"https://www.youtube.com/watch?v={video_id}"

    async with aiosqlite.connect(get_db_path()) as db:
        cursor = await db.execute(
            """SELECT 1 FROM content_items
               WHERE source_type = ?
               AND (json_extract(metadata, '$.video_id') = ? OR source_url = ?)
               LIMIT 1""",
            (source_type, video_id, video_url),
        )
        row = await cursor.fetchone()
        return row is not None


async def delete_content_item(item_id: int) -> bool:
    """Delete a content item."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        # Get category_id before deletion
        cursor = await db.execute(
            "SELECT category_id FROM content_items WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return False

        category_id = row["category_id"]

        cursor = await db.execute(
            "DELETE FROM content_items WHERE id = ?", (item_id,)
        )
        await db.commit()

        # Update category item count
        if category_id:
            await update_category_item_count(category_id, -1)

        return cursor.rowcount > 0


# ============================================================================
# Settings Repository
# ============================================================================


async def get_settings(category: str | None = None) -> list[SettingRecord]:
    """Get all settings, optionally filtered by category."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        if category:
            cursor = await db.execute(
                "SELECT * FROM settings WHERE category = ? ORDER BY key",
                (category,),
            )
        else:
            cursor = await db.execute("SELECT * FROM settings ORDER BY category, key")

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_setting(key: str) -> str | None:
    """Get a single setting value."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None


async def set_setting(key: str, value: str, category: str = "general") -> None:
    """Set a setting value (upsert)."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO settings (key, value, category)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, category = ?""",
            (key, value, category, value, category),
        )
        await db.commit()


async def delete_setting(key: str) -> bool:
    """Delete a setting."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Conversations Repository
# ============================================================================


async def get_conversations(limit: int = 50) -> list[ConversationRecord]:
    """Get all conversations ordered by most recent."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_conversation(conversation_id: int) -> ConversationRecord | None:
    """Get a single conversation by ID."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_conversation(
    title: str = "New Conversation",
    category_ids: list[int] | None = None,
    use_maglib: bool = False,
) -> int:
    """Create a new conversation."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO conversations (title, category_ids, use_maglib)
               VALUES (?, ?, ?)""",
            (title, json.dumps(category_ids) if category_ids else None, 1 if use_maglib else 0),
        )
        await db.commit()
        return cursor.lastrowid


async def update_conversation(
    conversation_id: int,
    title: str | None = None,
    category_ids: list[int] | None = None,
    use_maglib: bool | None = None,
) -> bool:
    """Update a conversation."""
    updates = []
    values = []

    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if category_ids is not None:
        updates.append("category_ids = ?")
        values.append(json.dumps(category_ids) if category_ids else None)
    if use_maglib is not None:
        updates.append("use_maglib = ?")
        values.append(1 if use_maglib else 0)

    if not updates:
        return False

    values.append(conversation_id)
    query = f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?"

    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, values)
        await db.commit()
        return cursor.rowcount > 0


async def delete_conversation(conversation_id: int) -> bool:
    """Delete a conversation and all its messages."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# ============================================================================
# Messages Repository
# ============================================================================


async def get_messages(
    conversation_id: int,
    limit: int = 100,
) -> list[MessageRecord]:
    """Get all messages for a conversation."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC LIMIT ?""",
            (conversation_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def create_message(
    conversation_id: int,
    role: str,
    content: str,
    sources: list[dict] | None = None,
) -> int:
    """Create a new message."""
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO messages (conversation_id, role, content, sources)
               VALUES (?, ?, ?, ?)""",
            (
                conversation_id,
                role,
                content,
                json.dumps(sources) if sources else None,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_conversation_with_messages(
    conversation_id: int,
) -> dict | None:
    """Get a conversation with all its messages."""
    conversation = await get_conversation(conversation_id)
    if not conversation:
        return None

    messages = await get_messages(conversation_id)

    return {
        **conversation,
        "messages": messages,
    }
