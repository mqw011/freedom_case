from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from app.api.dependencies import DB, Config, Limit, Offset
from app.core.exceptions import DomainError
from app.models import Dataset
from app.schemas.common import Page
from app.schemas.datasets import DatasetRead, ImportReport, ImportRequest
from app.services.common import page, require
from app.services.dataset_import import DatasetImportService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post("/import", response_model=ImportReport, status_code=201)
def import_dataset(data: ImportRequest, db: DB, config: Config):
    return DatasetImportService(db, config).import_group(data.group_id)


@router.post("/import-json", response_model=ImportReport, status_code=201)
def import_json(db: DB, config: Config, file: Annotated[UploadFile, File()]):
    content = file.file.read(config.import_max_bytes + 1)
    if len(content) > config.import_max_bytes:
        raise DomainError(422, "dataset_too_large", "Dataset file exceeds configured size limit")
    service = DatasetImportService(db, config)
    return service.persist(service.parse(content), source="json_file")


@router.get("", response_model=Page[DatasetRead])
def datasets(db: DB, offset: Offset = 0, limit: Limit = 50):
    return page(db, select(Dataset).order_by(Dataset.id), offset, limit)


@router.get("/{dataset_id}", response_model=DatasetRead)
def dataset(dataset_id: int, db: DB):
    return require(db, Dataset, dataset_id)
