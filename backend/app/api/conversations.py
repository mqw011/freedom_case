from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import DB, Limit, Offset
from app.models import Conversation, Evaluation
from app.schemas.common import Page
from app.schemas.datasets import (
    Channel,
    ConversationDetail,
    ConversationRead,
    Language,
    MessageRead,
)
from app.schemas.evaluations import EvaluationRead
from app.services.common import page, require

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=Page[ConversationRead])
def conversations(
    db: DB,
    offset: Offset = 0,
    limit: Limit = 50,
    search: Annotated[str | None, Query(max_length=200)] = None,
    language: Language | None = None,
    channel: Channel | None = None,
    dataset_id: Annotated[int | None, Query(gt=0)] = None,
):
    statement = select(Conversation)
    if search:
        statement = statement.where(Conversation.conversation_id.contains(search, autoescape=True))
    if language:
        statement = statement.where(Conversation.language == language)
    if channel:
        statement = statement.where(Conversation.channel == channel)
    if dataset_id:
        statement = statement.where(Conversation.dataset_id == dataset_id)
    return page(db, statement.order_by(Conversation.id), offset, limit)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def conversation(conversation_id: int, db: DB):
    return require(db, Conversation, conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
def messages(conversation_id: int, db: DB):
    return require(db, Conversation, conversation_id).messages


@router.get("/{conversation_id}/evaluations", response_model=Page[EvaluationRead])
def evaluations(conversation_id: int, db: DB, offset: Offset = 0, limit: Limit = 50):
    require(db, Conversation, conversation_id)
    return page(
        db,
        select(Evaluation)
        .where(Evaluation.conversation_id == conversation_id)
        .order_by(Evaluation.id),
        offset,
        limit,
    )
