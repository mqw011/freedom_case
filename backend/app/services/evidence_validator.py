from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import Message
from app.schemas.evaluations import EvidenceInput


class EvidenceValidator:
    """Structural/quote validation now; semantic absence validation belongs to Stage 2."""

    def __init__(self, session: Session):
        self.session = session

    def validate(self, conversation_id: int, evidence: EvidenceInput):
        messages = []
        for identifier in (evidence.message_id, evidence.end_message_id):
            if identifier is None:
                continue
            message = self.session.get(Message, identifier)
            if message is None or message.conversation_id != conversation_id:
                raise DomainError(
                    422, "invalid_evidence", "Evidence must reference this conversation"
                )
            messages.append(message)
        if len(messages) == 2 and messages[0].message_index > messages[1].message_index:
            raise DomainError(422, "invalid_evidence_range", "Evidence range is reversed")
        if evidence.excerpt is not None and evidence.excerpt not in messages[0].text:
            raise DomainError(
                422, "invalid_excerpt", "Excerpt must occur verbatim in the start message"
            )
