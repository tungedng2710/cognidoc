from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import RevisionStatus, UploadStatus, Visibility

ApiTokenScope = Literal["read", "write"]


def default_api_token_scopes() -> list[ApiTokenScope]:
    return ["read", "write"]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    instance: str


class DatasetCreate(BaseModel):
    namespace: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,95}$")
    visibility: Visibility = Visibility.private
    description: str = Field(default="", max_length=2_000)


class DatasetPatch(BaseModel):
    visibility: Visibility | None = None
    description: str | None = Field(default=None, max_length=2_000)


class FileRead(OrmModel):
    path: str
    size_bytes: int
    sha256: str
    media_type: str
    is_previewable: bool


class FilePage(BaseModel):
    items: list[FileRead]
    total: int
    offset: int
    limit: int


class SplitRead(OrmModel):
    name: str
    data_files: list[str]
    num_rows: int | None
    num_bytes: int
    schema_: list[dict[str, Any]] = Field(
        validation_alias="schema_json", serialization_alias="schema"
    )


class ConfigRead(OrmModel):
    name: str
    builder_name: str
    builder_parameters: dict[str, Any]
    splits: list[SplitRead] = []


class RevisionSummary(OrmModel):
    revision_id: str
    branch: str
    commit_message: str
    status: RevisionStatus
    manifest_sha256: str
    error_code: str | None
    error_message: str | None
    created_at: datetime


class RevisionRead(RevisionSummary):
    card_markdown: str
    card_html: str
    card_metadata: dict[str, Any]
    files: list[FileRead] = []
    configs: list[ConfigRead] = []


class DatasetRead(OrmModel):
    id: str
    namespace: str
    slug: str
    visibility: Visibility
    description: str
    default_branch: str
    created_at: datetime
    updated_at: datetime
    owner: str | None = None
    can_edit: bool = False
    latest_revision: RevisionSummary | None = None


class UserRegister(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    display_name: str = Field(default="", max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def plausible_email(cls, email: str | None) -> str | None:
        if email is None:
            return None
        normalized = email.strip().lower()
        if normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        return normalized


class UserLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserRead(OrmModel):
    id: str
    username: str
    display_name: str
    email: str | None
    is_admin: bool
    created_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[ApiTokenScope] = Field(default_factory=default_api_token_scopes)

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, scopes: list[ApiTokenScope]) -> list[ApiTokenScope]:
        unique = list(dict.fromkeys(scopes))
        if not unique:
            raise ValueError("at least one scope is required")
        return unique


class ApiTokenRead(OrmModel):
    id: str
    name: str
    token_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class ApiTokenCreated(ApiTokenRead):
    token: str


class DatasetList(BaseModel):
    items: list[DatasetRead]


class UploadCreate(BaseModel):
    commit_message: str = Field(default="Upload dataset", min_length=1, max_length=500)


class UploadRead(OrmModel):
    id: str
    repository_id: str
    status: UploadStatus
    commit_message: str
    bytes_received: int
    file_count: int
    revision_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class UploadFilesResult(BaseModel):
    upload_id: str
    accepted_paths: list[str]
    bytes_received: int


class UploadComplete(BaseModel):
    expected_file_count: int | None = Field(default=None, ge=1)


class ViewerResponse(BaseModel):
    repository: str
    revision: str
    config: str
    split: str
    offset: int
    limit: int
    total_rows: int | None
    available_rows: int
    rows: list[dict[str, Any]]
    schema_: list[dict[str, Any]] = Field(alias="schema", serialization_alias="schema")
    capabilities: dict[str, bool]

    model_config = ConfigDict(populate_by_name=True)


class ViewerFilter(BaseModel):
    column: str
    op: Literal["eq", "ne", "contains", "gt", "gte", "lt", "lte"]
    value: str | int | float | bool | None


class JobRead(OrmModel):
    id: str
    repository_id: str
    revision_id: str | None
    job_type: str
    status: str
    progress: float
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PathList(BaseModel):
    paths: list[str]

    @field_validator("paths")
    @classmethod
    def no_duplicates(cls, paths: list[str]) -> list[str]:
        if len(paths) != len(set(paths)):
            raise ValueError("paths must be unique")
        return paths
