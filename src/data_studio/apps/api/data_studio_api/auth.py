from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Header

from .errors import StudioError


class Role(StrEnum):
    reader = "reader"
    contributor = "contributor"
    admin = "admin"


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role


def get_principal(
    role: Annotated[Role, Header(alias="X-Data-Studio-Role")] = Role.admin,
    subject: Annotated[str, Header(alias="X-Data-Studio-Subject")] = "local-development-user",
) -> Principal:
    """Development auth boundary, replaceable with OIDC or hashed API tokens.

    The default admin identity is intentionally limited to development deployments. A
    production proxy should always set both headers after authenticating the caller.
    """

    return Principal(subject=subject, role=role)


def authorize(principal: Principal, *allowed: Role) -> None:
    if principal.role not in allowed:
        raise StudioError(
            403,
            "forbidden",
            "Access denied",
            f"The {principal.role.value} role cannot perform this operation.",
        )
