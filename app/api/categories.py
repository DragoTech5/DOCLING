"""
Categories API Routes - Hierarchical category management with subcategories
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import repository
from app.db.vector_store import delete_collection

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    """Schema for creating a category."""
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    color: str = Field(default="#3B82F6", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = None
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    """Schema for updating a category."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = None
    parent_id: int | None = None


class CategoryMove(BaseModel):
    """Schema for moving a category to a new parent."""
    parent_id: int | None = None  # None = move to root level


class CategoryResponse(BaseModel):
    """Schema for category response."""
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


class CategoryTreeNode(CategoryResponse):
    """Schema for category tree node with children."""
    children: list["CategoryTreeNode"] = []


class MoveContentRequest(BaseModel):
    """Schema for moving content between categories."""
    content_ids: list[int] = Field(min_length=1)
    target_category_id: int | None = None


class MoveChannelRequest(BaseModel):
    """Schema for moving a channel to a category."""
    channel_id: int
    target_category_id: int | None = None


@router.get("", response_model=list[CategoryResponse])
async def list_categories():
    """List all categories in flat format, ordered by hierarchy."""
    categories = await repository.get_categories()
    return categories


@router.get("/tree")
async def get_categories_tree():
    """Get categories as a hierarchical tree structure."""
    tree = await repository.get_categories_tree()
    return tree


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: int):
    """Get a single category."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.get("/{category_id}/children", response_model=list[CategoryResponse])
async def get_subcategories(category_id: int):
    """Get direct children of a category."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    subcategories = await repository.get_subcategories(category_id)
    return subcategories


@router.get("/{category_id}/ancestors", response_model=list[CategoryResponse])
async def get_category_ancestors(category_id: int):
    """Get all ancestors of a category (breadcrumb trail)."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    ancestors = await repository.get_category_ancestors(category_id)
    return ancestors


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(data: CategoryCreate):
    """Create a new category. Max 6 levels of nesting."""
    # Check for duplicate name within same parent
    existing = await repository.get_category_by_name(data.name, data.parent_id)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Category with this name already exists at this level"
        )

    # Validate parent exists if specified
    if data.parent_id is not None:
        parent = await repository.get_category(data.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent category not found")

    try:
        category_id = await repository.create_category(
            name=data.name,
            description=data.description,
            color=data.color,
            icon=data.icon,
            parent_id=data.parent_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await repository.get_category(category_id)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: int, data: CategoryUpdate):
    """Update a category."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for duplicate name if changing (within same parent)
    target_parent = data.parent_id if data.parent_id is not None else category.get("parent_id")
    if data.name and data.name != category["name"]:
        existing = await repository.get_category_by_name(data.name, target_parent)
        if existing and existing["id"] != category_id:
            raise HTTPException(
                status_code=400,
                detail="Category with this name already exists at this level"
            )

    try:
        await repository.update_category(
            category_id,
            name=data.name,
            description=data.description,
            color=data.color,
            icon=data.icon,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await repository.get_category(category_id)


@router.put("/{category_id}/move", response_model=CategoryResponse)
async def move_category(category_id: int, data: CategoryMove):
    """Move a category to a new parent (or to root level if parent_id is null)."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Validate new parent exists if specified
    if data.parent_id is not None:
        parent = await repository.get_category(data.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Target parent category not found")

    # Check for duplicate name at target level
    existing = await repository.get_category_by_name(category["name"], data.parent_id)
    if existing and existing["id"] != category_id:
        raise HTTPException(
            status_code=400,
            detail="Category with this name already exists at target level"
        )

    try:
        await repository.update_category(
            category_id,
            parent_id=data.parent_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await repository.get_category(category_id)


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int):
    """Delete a category. Subcategories and content move to parent (grandparent)."""
    category = await repository.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Delete vector collection for this category
    delete_collection(category_id)

    # Delete category (handles moving children and content to grandparent)
    await repository.delete_category(category_id)


@router.post("/move-content", status_code=200)
async def move_content(data: MoveContentRequest):
    """Move content items to a different category."""
    # Validate target category exists if specified
    if data.target_category_id is not None:
        target = await repository.get_category(data.target_category_id)
        if not target:
            raise HTTPException(status_code=400, detail="Target category not found")

    moved_count = await repository.move_content_to_category(
        data.content_ids,
        data.target_category_id
    )
    return {"moved_count": moved_count}


@router.post("/move-channel", status_code=200)
async def move_channel(data: MoveChannelRequest):
    """Move a monitored channel to a different category."""
    # Validate target category exists if specified
    if data.target_category_id is not None:
        target = await repository.get_category(data.target_category_id)
        if not target:
            raise HTTPException(status_code=400, detail="Target category not found")

    success = await repository.move_channel_to_category(
        data.channel_id,
        data.target_category_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"success": True}
