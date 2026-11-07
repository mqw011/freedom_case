import hashlib
import json
import logging

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DomainError
from app.models import Conversation, Dataset, Message
from app.schemas.datasets import DatasetEnvelope, DatasetRead, ImportReport

logger = logging.getLogger("cqa.import")


class DatasetImportService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def parse(self, content: bytes, *, external: bool = False) -> DatasetEnvelope:
        status = 502 if external else 422
        if len(content) > self.settings.import_max_bytes:
            raise DomainError(status, "dataset_too_large", "Dataset exceeds configured size limit")
        try:
            raw = json.loads(content)
        except (ValueError, UnicodeDecodeError) as exc:
            raise DomainError(
                502 if external else 400, "invalid_json", "Invalid dataset JSON"
            ) from exc
        if isinstance(raw, dict) and raw.get("isSuccess") is False:
            raise DomainError(
                502 if external else 422, "dataset_rejected", "Dataset reports failure"
            )
        try:
            envelope = DatasetEnvelope.model_validate(raw)
        except ValidationError as exc:
            raise DomainError(
                status, "invalid_dataset", "Dataset structure failed validation"
            ) from exc
        if not envelope.isSuccess or envelope.error:
            raise DomainError(status, "dataset_rejected", "Dataset reports an error")
        return envelope

    def fetch(self, group_id: str) -> DatasetEnvelope:
        configured_url = self.settings.dataset_api_url
        if not configured_url:
            raise DomainError(503, "dataset_not_configured", "DATASET_API_URL is not configured")
        params = None if "{group_id}" in configured_url else {"group_id": group_id}
        url = configured_url.replace("{group_id}", group_id)
        try:
            with httpx.Client(
                timeout=self.settings.dataset_api_timeout, follow_redirects=False, trust_env=False
            ) as client:
                with client.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > self.settings.import_max_bytes:
                            raise DomainError(
                                502, "dataset_too_large", "Upstream dataset is too large"
                            )
        except httpx.TimeoutException as exc:
            logger.warning("dataset_timeout")
            raise DomainError(502, "dataset_timeout", "Dataset API timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning("dataset_http_error type=%s", type(exc).__name__)
            raise DomainError(502, "dataset_http_error", "Dataset API request failed") from exc
        envelope = self.parse(bytes(content), external=True)
        if envelope.data.dataset_group_id != group_id:
            raise DomainError(502, "group_mismatch", "Dataset API returned a different group_id")
        return envelope

    def import_group(self, group_id: str) -> ImportReport:
        return self.persist(self.fetch(group_id), source="organizer_api")

    def persist(self, envelope: DatasetEnvelope, *, source: str) -> ImportReport:
        data = envelope.data
        dataset = self.session.scalar(
            select(Dataset).where(Dataset.group_id == data.dataset_group_id)
        )
        if dataset is None:
            dataset = Dataset(group_id=data.dataset_group_id, source=source)
            self.session.add(dataset)
            self.session.flush()
        inserted = skipped = 0
        existing = {
            c.conversation_id: c
            for c in self.session.scalars(
                select(Conversation).where(Conversation.dataset_id == dataset.id)
            )
        }
        for record in data.records:
            serialized = json.dumps(
                record.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
            )
            digest = hashlib.sha256(serialized.encode()).hexdigest()
            if record.conversation_id in existing:
                if existing[record.conversation_id].content_hash != digest:
                    raise DomainError(
                        409,
                        "changed_conversation",
                        "An existing conversation has different content; use a new group",
                    )
                skipped += 1
                continue
            conversation = Conversation(
                conversation_id=record.conversation_id,
                dataset_id=dataset.id,
                language=record.language,
                channel=record.channel,
                audio_url=str(record.audio_url) if record.audio_url else None,
                content_hash=digest,
            )
            self.session.add(conversation)
            self.session.flush()
            for index, message in enumerate(record.transcript):
                self.session.add(
                    Message(
                        conversation_id=conversation.id,
                        message_index=index,
                        speaker=message.speaker,
                        timestamp_raw=message.timestamp,
                        text=message.text,
                    )
                )
            inserted += 1
        self.session.flush()
        dataset.total_records = self.session.scalar(
            select(func.count(Conversation.id)).where(Conversation.dataset_id == dataset.id)
        )
        self.session.flush()
        warnings = []
        if data.total_records != len(data.records):
            warnings.append("total_records differs from actual records; actual array was imported")
        logger.info(
            "dataset_import group=%s inserted=%d skipped=%d",
            data.dataset_group_id,
            inserted,
            skipped,
        )
        return ImportReport(
            dataset=DatasetRead.model_validate(dataset),
            declared_records=data.total_records,
            received_records=len(data.records),
            inserted=inserted,
            skipped=skipped,
            warnings=warnings,
        )
