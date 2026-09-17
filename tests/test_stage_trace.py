"""Discovery records the code a stage actually ran, including dynamically dispatched methods,
generator bodies consumed later, and code entered inside a nested recording."""

from triplum.stage import trace


class Base:
    def target(self):
        return 1


class Derived(Base):
    def target(self):
        return 2


def helper():
    return 3


def dispatch(obj):
    return obj.target()


def produce():
    yield helper()
    yield helper()


def names(rec: trace.Recording) -> set[str]:
    return {c.co_qualname for c in rec.codes}


def test_records_the_dispatched_method_not_the_static_one():
    with trace.Recording() as rec:
        dispatch(Derived())
    assert {"dispatch", "Derived.target"} <= names(rec)
    assert "Base.target" not in names(rec)


def test_generator_bodies_run_on_pull_not_on_call():
    with trace.Recording() as rec:
        gen = produce()
    assert "helper" not in names(rec)
    with trace.Recording() as rec:
        list(gen)
    assert {"produce", "helper"} <= names(rec)


def test_a_recording_held_open_across_pulls_sees_everything():
    rec = trace.Recording().start()
    gen = produce()
    next(gen)
    next(gen)
    rec.stop()
    assert {"produce", "helper"} <= names(rec)


def test_nested_recordings_both_see_the_inner_entry():
    with trace.Recording() as outer:
        helper()
        with trace.Recording() as inner:
            helper()
            dispatch(Base())
    assert {"helper", "dispatch", "Base.target"} <= names(inner)
    assert names(inner) <= names(outer)


def test_a_function_seen_by_an_earlier_recording_is_reported_again():
    with trace.Recording() as first:
        helper()
    with trace.Recording() as second:
        helper()
    assert "helper" in names(first) and "helper" in names(second)
