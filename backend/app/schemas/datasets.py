import re
from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, StrictBool, model_validator

from app.schemas.common import GroupId, NonEmpty, Schema

Language = Literal["RU", "KZ", "EN"]
Channel = Literal["agent chat", "voice call"]
Speaker = Literal["client", "operator", "bot", "system"]


class TranscriptMessage(Schema):
    timestamp: str = Field(min_length=1, max_length=100)
    speaker: Speaker
    text: str = Field(min_length=1, max_length=100000)


class DatasetRecord(Schema):
    conversation_id: NonEmpty = Field(max_length=200)
    channel: Channel
    language: Language
    transcript: list[TranscriptMessage] = Field(min_length=1, max_length=100000)
    audio_url: HttpUrl | None = None

    @model_validator(mode="after")
    def timestamps(self):
        for message in self.transcript:
            if self.channel == "agent chat":
                if not re.fullmatch(r"\d{2,}:[0-5]\d", message.timestamp):
                    raise ValueError("Chat timestamps must use MM:SS")
            else:
                if "T" not in message.timestamp:
                    raise ValueError("Call timestamps must use ISO 8601 with timezone")
                try:
                    parsed = datetime.fromisoformat(message.timestamp)
                except ValueError as exc:
                    raise ValueError("Invalid call timestamp") from exc
                if parsed.tzinfo is None:
                    raise ValueError("Call timestamps require a timezone")
        if self.channel == "agent chat" and self.audio_url is not None:
            raise ValueError("Chat audio_url must be null")
        return self


class DatasetPayload(Schema):
    dataset_group_id: GroupId
    total_records: int = Field(ge=0, strict=True)
    records: list[DatasetRecord] = Field(max_length=100000)

    @model_validator(mode="after")
    def unique_records(self):
        ids = [record.conversation_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate conversation_id in dataset payload")
        return self


class DatasetEnvelope(Schema):
    error: str
    isSuccess: StrictBool
    data: DatasetPayload


class ImportRequest(Schema):
    group_id: GroupId


class DatasetRead(Schema):
    id: int
    group_id: str
    source: str
    imported_at: datetime
    total_records: int
    import_status: str


class ImportReport(Schema):
    dataset: DatasetRead
    declared_records: int
    received_records: int
    inserted: int
    skipped: int
    warnings: list[str]


class ConversationRead(Schema):
    id: int
    conversation_id: str
    dataset_id: int
    language: Language
    channel: Channel
    audio_url: str | None
    created_at: datetime


class MessageRead(Schema):
    id: int
    conversation_id: int
    message_index: int
    speaker: Speaker
    timestamp_raw: str
    text: str


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]
