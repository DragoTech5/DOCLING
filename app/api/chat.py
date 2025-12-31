"""
Chat API Routes - RAG-powered conversations
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import repository
from app.services.chat_service import chat, chat_stream, chat_maglib, chat_stream_maglib

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    title: str = Field(default="New Conversation", max_length=200)
    category_ids: list[int] | None = Field(
        default=None,
        description="Category IDs to filter knowledge base. None = all categories"
    )
    use_maglib: bool = Field(
        default=False,
        description="If True, search MAG-LIB pgvector collection instead of ChromaDB"
    )


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: str | None = Field(default=None, max_length=200)
    category_ids: list[int] | None = None
    use_maglib: bool | None = Field(
        default=None,
        description="If True, search MAG-LIB pgvector collection instead of ChromaDB"
    )


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    message: str = Field(..., min_length=1, max_length=10000)
    stream: bool = Field(default=True, description="Stream the response")


class ConversationResponse(BaseModel):
    """Conversation response."""
    id: int
    title: str
    category_ids: list[int] | None
    use_maglib: bool
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    """Message response."""
    id: int
    conversation_id: int
    role: str
    content: str
    sources: list[dict] | None
    created_at: str


class ConversationWithMessagesResponse(BaseModel):
    """Conversation with messages response."""
    id: int
    title: str
    category_ids: list[int] | None
    use_maglib: bool
    created_at: str
    updated_at: str
    messages: list[MessageResponse]


class ChatResponse(BaseModel):
    """Chat response (non-streaming)."""
    content: str
    sources: list[dict]


# ============================================================================
# Conversation Routes
# ============================================================================


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """List all conversations."""
    conversations = await repository.get_conversations(limit=limit)

    result = []
    for conv in conversations:
        category_ids = None
        if conv.get("category_ids"):
            try:
                category_ids = json.loads(conv["category_ids"])
            except json.JSONDecodeError:
                pass

        result.append({
            "id": conv["id"],
            "title": conv["title"],
            "category_ids": category_ids,
            "use_maglib": bool(conv.get("use_maglib", 0)),
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
        })

    return result


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = await repository.create_conversation(
        title=request.title,
        category_ids=request.category_ids,
        use_maglib=request.use_maglib,
    )

    conversation = await repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=500, detail="Failed to create conversation")

    category_ids = None
    if conversation.get("category_ids"):
        try:
            category_ids = json.loads(conversation["category_ids"])
        except json.JSONDecodeError:
            pass

    return {
        "id": conversation["id"],
        "title": conversation["title"],
        "category_ids": category_ids,
        "use_maglib": bool(conversation.get("use_maglib", 0)),
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
    }


@router.get("/conversations/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(conversation_id: int):
    """Get a conversation with all messages."""
    conversation = await repository.get_conversation_with_messages(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    category_ids = None
    if conversation.get("category_ids"):
        try:
            category_ids = json.loads(conversation["category_ids"])
        except json.JSONDecodeError:
            pass

    # Parse sources for each message
    messages = []
    for msg in conversation.get("messages", []):
        sources = None
        if msg.get("sources"):
            try:
                sources = json.loads(msg["sources"])
            except json.JSONDecodeError:
                pass

        messages.append({
            "id": msg["id"],
            "conversation_id": msg["conversation_id"],
            "role": msg["role"],
            "content": msg["content"],
            "sources": sources,
            "created_at": msg["created_at"],
        })

    return {
        "id": conversation["id"],
        "title": conversation["title"],
        "category_ids": category_ids,
        "use_maglib": bool(conversation.get("use_maglib", 0)),
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
        "messages": messages,
    }


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: int, request: UpdateConversationRequest):
    """Update a conversation."""
    conversation = await repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await repository.update_conversation(
        conversation_id=conversation_id,
        title=request.title,
        category_ids=request.category_ids,
        use_maglib=request.use_maglib,
    )

    updated = await repository.get_conversation(conversation_id)

    category_ids = None
    if updated.get("category_ids"):
        try:
            category_ids = json.loads(updated["category_ids"])
        except json.JSONDecodeError:
            pass

    return {
        "id": updated["id"],
        "title": updated["title"],
        "category_ids": category_ids,
        "use_maglib": bool(updated.get("use_maglib", 0)),
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    """Delete a conversation."""
    deleted = await repository.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True}


# ============================================================================
# Message Routes
# ============================================================================


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: int, request: SendMessageRequest):
    """
    Send a message and get a response.

    If stream=true (default), returns a streaming response with Server-Sent Events.
    Each line is a JSON object with type: "content", "sources", "done", or "error".

    If stream=false, returns a regular JSON response.
    """
    # Verify conversation exists
    conversation = await repository.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Parse category IDs and use_maglib flag
    category_ids = None
    if conversation.get("category_ids"):
        try:
            category_ids = json.loads(conversation["category_ids"])
        except json.JSONDecodeError:
            pass

    use_maglib = bool(conversation.get("use_maglib", 0))

    if request.stream:
        # Return streaming response - use MAG-LIB or ChromaDB based on flag
        if use_maglib:
            stream_func = chat_stream_maglib(
                conversation_id=conversation_id,
                user_message=request.message,
            )
        else:
            stream_func = chat_stream(
                conversation_id=conversation_id,
                user_message=request.message,
                category_ids=category_ids,
            )
        return StreamingResponse(stream_func, media_type="text/event-stream")
    else:
        # Return regular response - use MAG-LIB or ChromaDB based on flag
        if use_maglib:
            response = await chat_maglib(
                conversation_id=conversation_id,
                user_message=request.message,
            )
        else:
            response = await chat(
                conversation_id=conversation_id,
                user_message=request.message,
                category_ids=category_ids,
            )

        return {
            "content": response.content,
            "sources": [
                {
                    "title": s.title,
                    "source_type": s.source_type,
                    "source_url": s.source_url,
                    "channel_name": s.channel_name,
                    "published_date": s.published_date,
                }
                for s in response.sources
            ],
        }
