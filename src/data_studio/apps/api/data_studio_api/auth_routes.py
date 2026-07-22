from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (
    SESSION_COOKIE,
    Principal,
    authenticate_user,
    create_session_token,
    get_principal,
    hash_api_token,
    hash_password,
    issue_api_token,
    require_scope,
)
from .config import Settings, get_settings
from .database import get_db
from .errors import ConflictError, NotFoundError, StudioError
from .models import ApiToken, DatasetRepository, User
from .schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    UserLogin,
    UserRead,
    UserRegister,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
Database = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def _set_session_cookie(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user, settings),
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserRead, status_code=201)
def register(
    body: UserRegister,
    response: Response,
    db: Database,
    settings: SettingsDependency,
) -> User:
    username = body.username.strip().lower()
    email = body.email.strip().lower() if body.email else None
    is_first_user = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    user = User(
        username=username,
        display_name=body.display_name.strip() or username,
        email=email,
        password_hash=hash_password(body.password),
        is_admin=is_first_user,
    )
    db.add(user)
    try:
        db.flush()
        if is_first_user:
            db.execute(
                update(DatasetRepository)
                .where(DatasetRepository.owner_id.is_(None))
                .values(owner_id=user.id)
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That username or email is already registered.") from exc
    db.refresh(user)
    _set_session_cookie(response, user, settings)
    return user


@router.post("/login", response_model=UserRead)
def login(
    body: UserLogin,
    response: Response,
    db: Database,
    settings: SettingsDependency,
) -> User:
    user = authenticate_user(db, body.username, body.password)
    _set_session_cookie(response, user, settings)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserRead)
def me(principal: CurrentPrincipal, db: Database) -> User:
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    return user


@router.get("/tokens", response_model=list[ApiTokenRead])
def list_tokens(principal: CurrentPrincipal, db: Database) -> list[ApiToken]:
    return list(
        db.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == principal.user_id)
            .order_by(ApiToken.created_at.desc())
        ).all()
    )


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(
    body: ApiTokenCreate,
    principal: CurrentPrincipal,
    db: Database,
) -> dict[str, object]:
    if principal.credential != "session":
        raise StudioError(
            403,
            "session_required",
            "Browser session required",
            "Create personal API tokens from a signed-in browser session.",
        )
    require_scope(principal, "write")
    raw_token = issue_api_token()
    stored = ApiToken(
        user_id=principal.user_id,
        name=body.name.strip(),
        token_prefix=raw_token[:14],
        token_hash=hash_api_token(raw_token),
        scopes=body.scopes,
    )
    db.add(stored)
    db.commit()
    db.refresh(stored)
    return {
        "id": stored.id,
        "name": stored.name,
        "token_prefix": stored.token_prefix,
        "scopes": stored.scopes,
        "expires_at": stored.expires_at,
        "last_used_at": stored.last_used_at,
        "created_at": stored.created_at,
        "token": raw_token,
    }


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(token_id: str, principal: CurrentPrincipal, db: Database) -> Response:
    token = db.scalar(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == principal.user_id,
        )
    )
    if token is None:
        raise NotFoundError("API token")
    db.delete(token)
    db.commit()
    return Response(status_code=204)
