from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import Checklist, ChecklistVersion, Criterion
from app.schemas.checklists import ChecklistCreate, CriterionConfig, VersionCreate
from app.services.common import require


class ChecklistService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, data: ChecklistCreate, seed_key: str | None = None) -> Checklist:
        checklist = Checklist(name=data.name, description=data.description, seed_key=seed_key)
        self.session.add(checklist)
        self.session.flush()
        version = self.new_version(checklist.id, data.version)
        self.activate(checklist.id, version.id)
        return checklist

    def new_version(self, checklist_id: int, data: VersionCreate) -> ChecklistVersion:
        require(self.session, Checklist, checklist_id)
        number = (
            self.session.scalar(
                select(func.max(ChecklistVersion.version_number)).where(
                    ChecklistVersion.checklist_id == checklist_id
                )
            )
            or 0
        )
        version = ChecklistVersion(checklist_id=checklist_id, version_number=number + 1)
        self.session.add(version)
        self.session.flush()
        for config in data.criteria:
            fields = config.model_dump()
            fields["allowed_values"] = [str(v) for v in config.allowed_values]
            self.session.add(Criterion(checklist_version_id=version.id, **fields))
        self.session.flush()
        return version

    def activate(self, checklist_id: int, version_id: int) -> Checklist:
        checklist = require(self.session, Checklist, checklist_id)
        version = require(self.session, ChecklistVersion, version_id)
        if version.checklist_id != checklist.id:
            raise DomainError(422, "version_mismatch", "Version belongs to another checklist")
        self.validate_weights(version)
        checklist.active_version_id = version.id
        self.session.flush()
        return checklist

    @staticmethod
    def configs(version: ChecklistVersion) -> list[CriterionConfig]:
        return [CriterionConfig.model_validate(criterion) for criterion in version.criteria]

    @staticmethod
    def validate_weights(version: ChecklistVersion):
        weight = sum((c.weight for c in version.criteria if c.criterion_type != "flag"), Decimal(0))
        if weight != 100:
            raise DomainError(422, "invalid_weights", "Scored criterion weights must sum to 100")
