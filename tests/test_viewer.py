import pytest
from triplum.data.schema import TS_MAX
from triplum.data.viewer import Viewer


def test_defaults_are_now_and_public():
    v = Viewer(principals=frozenset({"public"}))
    assert v.principals == frozenset({"public"})
    assert v.as_of_valid <= TS_MAX and v.as_of_valid > 0
    assert v.as_of_recorded == v.as_of_valid
    assert v.permission_revision is None


def test_principals_are_normalised_to_frozenset():
    v = Viewer(principals=["b", "a", "a"])
    assert v.principals == frozenset({"a", "b"})


def test_viewer_is_hashable_and_stable():
    a = Viewer(principals={"x"}, as_of_valid=10, as_of_recorded=10)
    b = Viewer(principals={"x"}, as_of_valid=10, as_of_recorded=10)
    assert hash(a) == hash(b) and a == b


def test_empty_principals_rejected():
    with pytest.raises(ValueError):
        Viewer(principals=[])
