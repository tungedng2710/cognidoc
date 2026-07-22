from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .auth import Principal, Role, authorize, get_principal
from .config import Settings, get_settings
from .database import get_db
from .domain.paths import normalize_repository_path
from .errors import NotFoundError
from .models import DatasetConfig, DatasetRevision, DatasetSplit, ProcessingJob
from .schemas import (
    ConfigRead,
    DatasetCreate,
    DatasetList,
    DatasetPatch,
    DatasetRead,
    JobRead,
    RevisionRead,
    RevisionSummary,
    UploadComplete,
    UploadCreate,
    UploadFilesResult,
    UploadRead,
    ViewerResponse,
)
from .service import (
    DatasetService,
    apply_viewer_filter,
    get_repository,
    repository_payload,
    resolve_revision,
)
from .storage import ObjectStorage

router = APIRouter(prefix="/api/v1")

Database = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def service(request: Request, db: Database, settings: SettingsDependency) -> DatasetService:
    storage: ObjectStorage = request.app.state.storage
    return DatasetService(db, storage, settings)


Service = Annotated[DatasetService, Depends(service)]


@router.get("/datasets", response_model=DatasetList)
def list_datasets(db: Database, datasets: Service, principal: CurrentPrincipal) -> dict[str, Any]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    return {"items": [repository_payload(db, item) for item in datasets.list_repositories()]}


@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(
    body: DatasetCreate, db: Database, datasets: Service, principal: CurrentPrincipal
) -> dict[str, Any]:
    authorize(principal, Role.contributor, Role.admin)
    return repository_payload(db, datasets.create_repository(body))


@router.get("/datasets/{namespace}/{dataset}", response_model=DatasetRead)
def read_dataset(
    namespace: str, dataset: str, db: Database, principal: CurrentPrincipal
) -> dict[str, Any]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    return repository_payload(db, get_repository(db, namespace, dataset))


@router.patch("/datasets/{namespace}/{dataset}", response_model=DatasetRead)
def patch_dataset(
    namespace: str,
    dataset: str,
    body: DatasetPatch,
    db: Database,
    datasets: Service,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    authorize(principal, Role.admin)
    repository = datasets.patch_repository(namespace, dataset, body)
    return repository_payload(db, repository)


@router.post("/datasets/{namespace}/{dataset}/uploads", response_model=UploadRead, status_code=201)
def create_upload(
    namespace: str,
    dataset: str,
    body: UploadCreate,
    datasets: Service,
    principal: CurrentPrincipal,
) -> UploadRead:
    authorize(principal, Role.contributor, Role.admin)
    return UploadRead.model_validate(
        datasets.create_upload(namespace, dataset, body.commit_message)
    )


@router.post("/uploads/{upload_id}/files", response_model=UploadFilesResult)
async def upload_files(
    upload_id: str,
    datasets: Service,
    principal: CurrentPrincipal,
    files: Annotated[list[UploadFile], File(description="Repository files")],
    paths: Annotated[list[str], Form(description="POSIX path corresponding to each file")],
) -> UploadFilesResult:
    authorize(principal, Role.contributor, Role.admin)
    accepted = await datasets.add_files(upload_id, files, paths)
    upload = datasets.get_upload(upload_id)
    return UploadFilesResult(
        upload_id=upload.id, accepted_paths=accepted, bytes_received=upload.bytes_received
    )


@router.post("/uploads/{upload_id}/complete", response_model=RevisionRead)
def complete_upload(
    upload_id: str,
    body: UploadComplete,
    datasets: Service,
    principal: CurrentPrincipal,
) -> RevisionRead:
    authorize(principal, Role.contributor, Role.admin)
    return RevisionRead.model_validate(
        datasets.complete_upload(upload_id, body.expected_file_count)
    )


@router.get("/uploads/{upload_id}", response_model=UploadRead)
def read_upload(upload_id: str, datasets: Service, principal: CurrentPrincipal) -> UploadRead:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    return UploadRead.model_validate(datasets.get_upload(upload_id))


@router.get("/datasets/{namespace}/{dataset}/revisions", response_model=list[RevisionSummary])
def list_revisions(
    namespace: str, dataset: str, db: Database, principal: CurrentPrincipal
) -> list[DatasetRevision]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    repository = get_repository(db, namespace, dataset)
    return list(
        db.scalars(
            select(DatasetRevision)
            .where(DatasetRevision.repository_id == repository.id)
            .order_by(DatasetRevision.created_at.desc(), DatasetRevision.id.desc())
        ).all()
    )


@router.get("/datasets/{namespace}/{dataset}/revisions/{revision}", response_model=RevisionRead)
def read_revision(
    namespace: str, dataset: str, revision: str, db: Database, principal: CurrentPrincipal
) -> DatasetRevision:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    repository = get_repository(db, namespace, dataset)
    return resolve_revision(db, repository, revision)


@router.get("/datasets/{namespace}/{dataset}/tree/{revision}", response_model=list[dict[str, Any]])
def read_tree(
    namespace: str, dataset: str, revision: str, db: Database, principal: CurrentPrincipal
) -> list[dict[str, Any]]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    resolved = resolve_revision(db, get_repository(db, namespace, dataset), revision)
    return [
        {
            "path": file.path,
            "size_bytes": file.size_bytes,
            "sha256": file.sha256,
            "media_type": file.media_type,
            "is_previewable": file.is_previewable,
        }
        for file in sorted(resolved.files, key=lambda item: item.path)
    ]


@router.get("/datasets/{namespace}/{dataset}/blob/{revision}/{path:path}")
def download_blob(
    namespace: str,
    dataset: str,
    revision: str,
    path: str,
    request: Request,
    db: Database,
    principal: CurrentPrincipal,
    inline: bool = False,
) -> StreamingResponse:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    normalized = normalize_repository_path(path)
    resolved = resolve_revision(db, get_repository(db, namespace, dataset), revision)
    repository_file = next((file for file in resolved.files if file.path == normalized), None)
    if repository_file is None:
        raise NotFoundError(f"File {normalized}")
    storage: ObjectStorage = request.app.state.storage
    return StreamingResponse(
        storage.iter_object(repository_file.storage_object_key),
        media_type=repository_file.media_type,
        headers={
            "Content-Disposition": (
                f"{'inline' if inline else 'attachment'}; "
                f'filename="{normalized.rsplit("/", 1)[-1]}"'
            )
        },
    )


@router.get("/datasets/{namespace}/{dataset}/configs", response_model=list[ConfigRead])
def list_configs(
    namespace: str,
    dataset: str,
    db: Database,
    principal: CurrentPrincipal,
    revision: str = "main",
) -> list[DatasetConfig]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    resolved = resolve_revision(db, get_repository(db, namespace, dataset), revision)
    return resolved.configs


def _resolve_split(
    db: Session,
    namespace: str,
    dataset: str,
    revision: str,
    config_name: str,
    split_name: str,
) -> tuple[DatasetRevision, DatasetSplit]:
    repository = get_repository(db, namespace, dataset)
    resolved = resolve_revision(db, repository, revision)
    statement = (
        select(DatasetSplit)
        .join(DatasetConfig)
        .where(
            DatasetConfig.revision_id == resolved.id,
            DatasetConfig.name == config_name,
            DatasetSplit.name == split_name,
        )
        .options(selectinload(DatasetSplit.config))
    )
    split = db.scalar(statement)
    if split is None:
        raise NotFoundError(f"Config/split {config_name}/{split_name}")
    return resolved, split


@router.get(
    "/datasets/{namespace}/{dataset}/viewer/{config_name}/{split_name}",
    response_model=ViewerResponse,
)
def viewer(
    namespace: str,
    dataset: str,
    config_name: str,
    split_name: str,
    db: Database,
    principal: CurrentPrincipal,
    revision: str = "main",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    columns: str | None = None,
    filter_: Annotated[str | None, Query(alias="filter")] = None,
) -> ViewerResponse:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    resolved, split = _resolve_split(db, namespace, dataset, revision, config_name, split_name)
    filtered = apply_viewer_filter(split.preview_json, filter_)
    selected = [column for column in columns.split(",") if column] if columns else None
    rows = filtered[offset : offset + limit]
    if selected is not None:
        rows = [{key: row.get(key) for key in selected if key in row} for row in rows]
    return ViewerResponse(
        repository=f"{namespace}/{dataset}",
        revision=resolved.revision_id,
        config=config_name,
        split=split_name,
        offset=offset,
        limit=limit,
        total_rows=split.num_rows,
        rows=rows,
        schema_=split.schema_json,
        capabilities={
            "projection": True,
            "filter": True,
            "global_sort": False,
            "text_search": False,
            "preview_is_bounded": True,
        },
    )


@router.get("/datasets/{namespace}/{dataset}/statistics/{config_name}/{split_name}")
def statistics(
    namespace: str,
    dataset: str,
    config_name: str,
    split_name: str,
    db: Database,
    principal: CurrentPrincipal,
    revision: str = "main",
) -> dict[str, Any]:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    resolved, split = _resolve_split(db, namespace, dataset, revision, config_name, split_name)
    return {
        "repository": f"{namespace}/{dataset}",
        "revision": resolved.revision_id,
        "config": config_name,
        "split": split_name,
        **split.statistics_json,
    }


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job_id: str, db: Database, principal: CurrentPrincipal) -> ProcessingJob:
    authorize(principal, Role.reader, Role.contributor, Role.admin)
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id}")
    return job
