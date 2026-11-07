from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base, ExactDecimal, UTCDateTime, utcnow
from app.core.exceptions import DomainError


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(30))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    total_records: Mapped[int] = mapped_column(default=0)
    import_status: Mapped[str] = mapped_column(String(30), default="complete")
    __table_args__ = (CheckConstraint("total_records >= 0"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(200), index=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    language: Mapped[str] = mapped_column(String(2), index=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)
    audio_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    messages: Mapped[list["Message"]] = relationship(order_by="Message.message_index")
    __table_args__ = (
        UniqueConstraint("dataset_id", "conversation_id"),
        CheckConstraint("language IN ('RU', 'KZ', 'EN')"),
        CheckConstraint("channel IN ('agent chat', 'voice call')"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_index: Mapped[int] = mapped_column()
    speaker: Mapped[str] = mapped_column(String(20))
    timestamp_raw: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("conversation_id", "message_index"),
        CheckConstraint("message_index >= 0"),
        CheckConstraint("speaker IN ('client', 'operator', 'bot', 'system')"),
    )


class Checklist(Base):
    __tablename__ = "checklists"
    id: Mapped[int] = mapped_column(primary_key=True)
    seed_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("checklist_versions.id", name="fk_checklist_active_version", use_alter=True)
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    revision: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": revision}


class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"), index=True)
    version_number: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="published")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    criteria: Mapped[list["Criterion"]] = relationship(order_by="Criterion.display_order")
    __table_args__ = (
        UniqueConstraint("checklist_id", "version_number"),
        CheckConstraint("version_number > 0"),
    )


class Criterion(Base):
    __tablename__ = "criteria"
    id: Mapped[int] = mapped_column(primary_key=True)
    checklist_version_id: Mapped[int] = mapped_column(
        ForeignKey("checklist_versions.id"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(300))
    criterion_type: Mapped[str] = mapped_column(String(20))
    weight: Mapped[Decimal] = mapped_column(ExactDecimal())
    allowed_values: Mapped[list[str]] = mapped_column(JSON)
    max_score: Mapped[Decimal] = mapped_column(ExactDecimal())
    allow_na: Mapped[bool] = mapped_column(Boolean)
    na_condition: Mapped[str | None] = mapped_column(Text)
    scale_labels: Mapped[dict[str, str]] = mapped_column(JSON)
    display_order: Mapped[int] = mapped_column()
    __table_args__ = (
        UniqueConstraint("checklist_version_id", "code"),
        UniqueConstraint("checklist_version_id", "display_order"),
        CheckConstraint("criterion_type IN ('binary', 'scale', 'flag')"),
        CheckConstraint("display_order >= 0"),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    checklist_version_id: Mapped[int] = mapped_column(
        ForeignKey("checklist_versions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="completed")
    source: Mapped[str] = mapped_column(String(20))
    initial_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    final_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    initial_critical_violation: Mapped[bool] = mapped_column(Boolean)
    critical_violation: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revision: Mapped[int] = mapped_column(default=1)
    results: Mapped[list["CriterionResult"]] = relationship(order_by="CriterionResult.id")
    __mapper_args__ = {"version_id_col": revision}
    __table_args__ = (CheckConstraint("source IN ('manual', 'test', 'ai')"),)


class CriterionResult(Base):
    __tablename__ = "criterion_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey("criteria.id"), index=True)
    answer: Mapped[str] = mapped_column(String(100))
    raw_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    weighted_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    is_na: Mapped[bool] = mapped_column(Boolean)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    evidence: Mapped[list["Evidence"]] = relationship(order_by="Evidence.id")
    __table_args__ = (UniqueConstraint("evaluation_id", "criterion_id"),)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    criterion_result_id: Mapped[int] = mapped_column(ForeignKey("criterion_results.id"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), index=True)
    end_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(20))
    excerpt: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("evidence_type IN ('quote', 'range', 'absence')"),)


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    criterion_result_id: Mapped[int] = mapped_column(ForeignKey("criterion_results.id"), index=True)
    # Nullable unique key permits historical appeals but only one open appeal per result.
    pending_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("criterion_results.id"), unique=True
    )
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    decision: Mapped["AppealDecision | None"] = relationship(back_populates="appeal")
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'upheld', 'revised')"),
        CheckConstraint(
            "(status = 'pending' AND pending_result_id = criterion_result_id "
            "AND pending_result_id IS NOT NULL) OR "
            "(status != 'pending' AND pending_result_id IS NULL)"
        ),
    )


class AppealDecision(Base):
    __tablename__ = "appeal_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    appeal_id: Mapped[int] = mapped_column(ForeignKey("appeals.id"), unique=True)
    decision: Mapped[str] = mapped_column(String(20))
    original_answer: Mapped[str] = mapped_column(String(100))
    revised_answer: Mapped[str] = mapped_column(String(100))
    original_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    revised_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    original_final_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    revised_final_score: Mapped[Decimal | None] = mapped_column(ExactDecimal())
    reason: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    appeal: Mapped[Appeal] = relationship(back_populates="decision")
    __table_args__ = (CheckConstraint("decision IN ('upheld', 'revised')"),)


@event.listens_for(Session, "before_flush")
def protect_snapshots(session, flush_context, instances):
    immutable = (
        ChecklistVersion,
        Criterion,
        CriterionResult,
        Evidence,
        AppealDecision,
        Conversation,
        Message,
    )
    for obj in session.dirty:
        if isinstance(obj, immutable) and session.is_modified(obj, include_collections=False):
            raise DomainError(409, "immutable_snapshot", "Persisted snapshots cannot be edited")
        if isinstance(obj, Evaluation):
            for field in (
                "initial_score",
                "initial_critical_violation",
                "conversation_id",
                "checklist_version_id",
                "source",
            ):
                if inspect(obj).attrs[field].history.has_changes():
                    raise DomainError(
                        409, "immutable_evaluation", "Original evaluation is immutable"
                    )
    for obj in session.deleted:
        if isinstance(obj, (*immutable, Evaluation, Appeal)):
            raise DomainError(409, "immutable_history", "Historical records cannot be deleted")
