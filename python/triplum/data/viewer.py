"""The query context every store read takes: who is asking, and as of when."""

from __future__ import annotations

from dataclasses import dataclass, field

from triplum.data.schema import now_us


@dataclass(frozen=True)
class Viewer:
    """principals: identities the caller holds. as_of_valid: world time. as_of_recorded:
    transaction time. permission_revision: the ACL snapshot the query was authorised against
    (None = current)."""

    principals: frozenset[str]
    as_of_valid: int = field(default_factory=now_us)
    as_of_recorded: int | None = None
    permission_revision: int | None = None

    def __post_init__(self) -> None:
        ps = frozenset(self.principals) if not isinstance(self.principals, frozenset) else self.principals
        if not ps:
            raise ValueError("Viewer needs at least one principal")
        object.__setattr__(self, "principals", ps)
        if self.as_of_recorded is None:
            object.__setattr__(self, "as_of_recorded", self.as_of_valid)

    @classmethod
    def of(cls, *principals: str, **kw) -> Viewer:
        return cls(principals=frozenset(principals), **kw)

    def sorted_principals(self) -> list[str]:
        return sorted(self.principals)
