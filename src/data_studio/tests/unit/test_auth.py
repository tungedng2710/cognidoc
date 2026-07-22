from pathlib import Path

from data_studio_api.auth import (
    Principal,
    authorize_repository_read,
    authorize_repository_write,
    create_session_token,
    hash_password,
    verify_password,
)
from data_studio_api.auth_routes import login, register
from data_studio_api.config import Settings
from data_studio_api.database import Base
from data_studio_api.errors import NotFoundError, StudioError
from data_studio_api.models import DatasetRepository, Visibility
from data_studio_api.schemas import UserLogin, UserRegister
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        staging_root=tmp_path / "uploads",
        auth_secret_key="test-secret-that-is-long-and-stable",
    )


def test_password_hashes_are_salted_and_verified() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "malformed")


def test_first_registration_adopts_existing_datasets_and_login_sets_cookie(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    settings = _settings(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        legacy = DatasetRepository(
            namespace="legacy",
            slug="imported",
            visibility=Visibility.private,
        )
        db.add(legacy)
        db.commit()

        register_response = Response()
        user = register(
            UserRegister(username="owner", password="secure-password"),
            register_response,
            db,
            settings,
        )
        assert user.is_admin
        db.refresh(legacy)
        assert legacy.owner_id == user.id
        assert "httponly" in register_response.headers["set-cookie"].lower()

        login_response = Response()
        logged_in = login(
            UserLogin(username="owner", password="secure-password"),
            login_response,
            db,
            settings,
        )
        assert logged_in.id == user.id
        assert create_session_token(logged_in, settings).count(".") == 1


def test_repository_access_is_public_read_and_owner_write() -> None:
    owner = Principal("owner-id", "owner", False, frozenset({"read", "write"}), "session")
    stranger = Principal("stranger-id", "stranger", False, frozenset({"read", "write"}), "session")
    public = DatasetRepository(
        owner_id=owner.user_id,
        namespace="owner",
        slug="public-data",
        visibility=Visibility.public,
    )
    private = DatasetRepository(
        owner_id=owner.user_id,
        namespace="owner",
        slug="private-data",
        visibility=Visibility.private,
    )

    authorize_repository_read(public, None)
    authorize_repository_read(private, owner)
    authorize_repository_write(private, owner)

    try:
        authorize_repository_read(private, stranger)
    except NotFoundError:
        pass
    else:
        raise AssertionError("a private dataset must be hidden from another user")

    try:
        authorize_repository_write(public, stranger)
    except StudioError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("a non-owner must not edit a public dataset")
