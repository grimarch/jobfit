"""Role registry — maps slug → Role definition."""

from jobfit.roles._base import Role
from jobfit.roles.devops import ROLE as _DEVOPS

ROLES: dict[str, Role] = {
    "devops": _DEVOPS,
}

DEFAULT_ROLE = "devops"

__all__ = ["Role", "ROLES", "DEFAULT_ROLE"]
