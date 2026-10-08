"""Semantic field-value fingerprints for Pydantic data, independent of computation code."""

import math
from pathlib import Path
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel

from triplum.utils.cache import content_key


def _value(value: object) -> object:
    """Encode the supported data shapes without lossy serialization or code identity."""
    if not isinstance(value, type):
        fingerprint = getattr(value, "fingerprint", None)
        if callable(fingerprint):
            return {"fingerprint": fingerprint()}
    if value is None or type(value) in (bool, int, str):
        return {type(value).__name__: value}
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("fingerprint data requires finite floats")
        return {"float": value.hex()}
    if type(value) is bytes:
        return {"bytes": value.hex()}
    if isinstance(value, UUID):
        return {"uuid": str(value)}
    if isinstance(value, Path):
        return {"path": str(value)}
    if type(value) is list or type(value) is tuple:
        return {type(value).__name__: [_value(item) for item in value]}
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise TypeError("fingerprint data requires string mapping keys")
        return {"dict": [[key, _value(item)] for key, item in sorted(value.items())]}
    raise TypeError(
        f"cannot fingerprint {type(value).__qualname__}; "
        "select supported values in fingerprint_data() or provide a nested fingerprint()"
    )


class FingerprintedModel(BaseModel):
    """A Pydantic data value with semantic field identity and ordinary serialization.

    All declared fields and allowed extras participate by default. Exclude bookkeeping
    with fingerprint_exclude, or override fingerprint_data for another projection.
    No schema, computation code, computed fields or private attributes enter identity.
    Excluded fields must not affect cached results; a hit may retain older bookkeeping.
    Nested models need fingerprint() too, or an explicit projection.
    """

    fingerprint_exclude: ClassVar[frozenset[str]] = frozenset()
    """Declared field names omitted from identity, independently of serialization."""

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        reserved = {
            "fingerprint",
            "fingerprint_data",
            "fingerprint_exclude",
        } & cls.model_fields.keys()
        if reserved:
            hint = (
                "; fingerprint_exclude must remain a ClassVar[frozenset[str]]"
                if "fingerprint_exclude" in reserved
                else ""
            )
            raise TypeError(f"reserved fingerprint fields: {', '.join(sorted(reserved))}{hint}")
        if not isinstance(cls.fingerprint_exclude, frozenset):
            raise TypeError("fingerprint_exclude must be a frozenset of declared field names")
        unknown = cls.fingerprint_exclude - cls.model_fields.keys()
        if unknown:
            raise ValueError(f"unknown fingerprint_exclude fields: {', '.join(sorted(unknown))}")

    def fingerprint_data(self) -> dict[str, object]:
        """Select actual field values plus allowed extras, minus declared exclusions.

        Serialization aliases, Field(exclude=True), and custom serializers do not change
        this projection. Declared fields and extras occupy separate namespaces so aliases
        cannot hide a field. Overrides define the complete projection, including exclusions,
        and subclasses inherit that projection: include any new semantic fields explicitly.
        Values support finite scalars, lists/tuples, string-keyed mappings, bytes, UUIDs,
        Paths (spelling only), and values with fingerprint(). Project other types explicitly.
        Mapping order is ignored; project ordered pairs if iteration order is semantic.
        """
        return {
            "fields": {
                name: getattr(self, name)
                for name in type(self).model_fields
                if name not in self.fingerprint_exclude
            },
            "extras": self.model_extra or {},
        }

    def fingerprint(self) -> str:
        """Hash the qualified model kind and selected values; recompute after mutation."""
        data = self.fingerprint_data()
        if type(data) is not dict:
            raise TypeError("fingerprint_data() must return a string-keyed dictionary")
        cls = type(self)
        return content_key(f"{cls.__module__}.{cls.__qualname__}", _value(data))
