from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from edison_core.api.dependencies import get_conversation_store
from edison_core.schemas import (
    ConversationCreate,
    ConversationRecord,
    ConversationWithMessages,
    MessageCreate,
    MessageRecord,
)
from edison_core.services.conversation_store import ConversationNotFoundError, ConversationStore


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRecord, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    store: ConversationStore = Depends(get_conversation_store),
) -> ConversationRecord:
    return store.create_conversation(payload)


@router.get("", response_model=list[ConversationRecord])
def list_conversations(
    store: ConversationStore = Depends(get_conversation_store),
) -> list[ConversationRecord]:
    return store.list_conversations()


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
def get_conversation(
    conversation_id: str,
    store: ConversationStore = Depends(get_conversation_store),
) -> ConversationWithMessages:
    try:
        return store.get_conversation(conversation_id)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRecord,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    conversation_id: str,
    payload: MessageCreate,
    store: ConversationStore = Depends(get_conversation_store),
) -> MessageRecord:
    try:
        return store.add_message(conversation_id, payload)
    except ConversationNotFoundError as error:
        raise HTTPException(status_code=404, detail="Conversation not found") from error