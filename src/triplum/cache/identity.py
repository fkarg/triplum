"""Default function identities share the loaded-definition computation engine."""

from types import FunctionType

from triplum.utils.fingerprint import definition_hash


def function_fingerprint(compute: object) -> str:
    """Hash loaded code, defaults, captures and statically resolvable application helpers.

    Freeze on first use. Keep definitions and captured/global settings fixed afterwards.
    External libraries and hidden resource state remain outside automatic discovery.
    """
    if not isinstance(compute, FunctionType):
        raise TypeError("automatic identity requires a Python function; supply process_id")
    try:
        return definition_hash(compute)
    except TypeError as error:
        raise TypeError(f"{error}; supply fingerprintable settings or process_id") from error
