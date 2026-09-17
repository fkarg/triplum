"""The query context every store read takes: who is asking, and as of when."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from triplum.data.schema import now_us


@dataclass(frozen=True, init=False)
class Viewer:
    """principals: identities the caller holds. as_of_valid: world time. as_of_recorded:
    transaction time. permission_revision: the ACL snapshot the query was authorised against
    (None = current)."""

    principals: frozenset[str]
    as_of_valid: int
    as_of_recorded: int
    permission_revision: int | None

    def __init__(
        self,
        principals: Iterable[str],
        as_of_valid: int | None = None,
        as_of_recorded: int | None = None,
        permission_revision: int | None = None,
    ) -> None:
        ps = frozenset(principals)
        if not ps:
            raise ValueError("Viewer needs at least one principal")
        valid = now_us() if as_of_valid is None else as_of_valid
        object.__setattr__(self, "principals", ps)
        object.__setattr__(self, "as_of_valid", valid)
        object.__setattr__(
            self, "as_of_recorded", valid if as_of_recorded is None else as_of_recorded
        )
        object.__setattr__(self, "permission_revision", permission_revision)

    @classmethod
    def of(
        cls,
        *principals: str,
        as_of_valid: int | None = None,
        as_of_recorded: int | None = None,
        permission_revision: int | None = None,
    ) -> Viewer:
        return cls(principals, as_of_valid, as_of_recorded, permission_revision)

    def sorted_principals(self) -> list[str]:
        return sorted(self.principals)
