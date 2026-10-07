from pathlib import Path

from pydantic import BaseModel

from triplum.cache import Cache, CachePolicy, cached, close_default_cache, default_cache
from triplum.utils.cache import content_key


class Text(BaseModel):
    text: str

    def fingerprint(self) -> str:
        return content_key("default-example-text-v1", {"text": self.text})


# Module-level bookkeeping is deliberately not part of computation identity.
CALLS: list[str] = []


@cached
def uppercase(item: Text) -> Text:
    CALLS.append(item.text)
    return Text(text=item.text.upper())


def test_bare_decorator_opens_default_lazily_and_reopens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    close_default_cache()
    CALLS.clear()
    assert not (tmp_path / "triplum").exists()
    try:
        assert uppercase(Text(text="hi")) == Text(text="HI")
        assert uppercase(Text(text="hi")) == Text(text="HI")
        assert CALLS == ["hi"]
        assert default_cache() is default_cache()
        close_default_cache()
        assert uppercase(Text(text="hi")) == Text(text="HI")
        assert CALLS == ["hi"]
    finally:
        close_default_cache()


def test_owned_decorator_infers_types_and_distinguishes_closure_config(tmp_path: Path) -> None:
    from triplum.cache import SQLiteBackend

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:

        def configured(prefix: str):
            @cache.cached
            def prepend(item: Text) -> Text:
                CALLS.append(prefix)
                return Text(text=prefix + item.text)

            return prepend

        CALLS.clear()
        first, second, equivalent = configured("a"), configured("b"), configured("a")
        assert first(Text(text="x")) == Text(text="ax")
        assert second(Text(text="x")) == Text(text="bx")
        assert equivalent(Text(text="x")) == Text(text="ax")
        assert CALLS == ["a", "b"]

        @cache.cached(policy=CachePolicy(on_full="block"))
        def lower(item: Text) -> Text:
            return Text(text=item.text.lower())

        assert lower(Text(text="HI")) == Text(text="hi")


def test_specialized_global_decorator_needs_only_overrides(tmp_path: Path) -> None:
    from triplum.cache import SQLiteBackend

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:

        @cached(cache=cache, process_id=content_key("lower-explicit-v1", {}))
        def lower(item: Text) -> Text:
            return Text(text=item.text.lower())

        assert lower(Text(text="HI")) == Text(text="hi")


def test_default_cache_constructor_uses_same_documented_location(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with Cache() as cache:

        @cache.cached
        def lower(item: Text) -> Text:
            return Text(text=item.text.lower())

        assert lower(Text(text="HI")) == Text(text="hi")
    assert (tmp_path / "triplum" / "cache.sqlite").is_file()


def test_captured_mapping_order_is_part_of_function_identity(tmp_path: Path) -> None:
    from triplum.cache import SQLiteBackend

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:

        def configured(order: dict[str, int]):
            @cache.cached
            def arrange(item: Text) -> Text:
                return Text(text="".join(order) + item.text)

            return arrange

        first = configured({"a": 1, "b": 2})
        second = configured({"b": 2, "a": 1})
        assert first(Text(text="x")) == Text(text="abx")
        assert second(Text(text="x")) == Text(text="bax")


def test_custom_builtin_subclass_needs_explicit_identity(tmp_path: Path) -> None:
    import pytest

    from triplum.cache import SQLiteBackend

    class SpecialText(str):
        pass

    with Cache(SQLiteBackend(tmp_path / "cache.sqlite")) as cache:

        def configured(prefix: str):
            @cache.cached
            def identify(item: Text) -> Text:
                return Text(text=type(prefix).__name__ + item.text)

            return identify

        assert configured("a")(Text(text="x")) == Text(text="strx")
        with pytest.raises(TypeError, match="process_id"):
            configured(SpecialText("a"))(Text(text="x"))


def test_mixin_defaults_infer_compute_output(tmp_path: Path, monkeypatch) -> None:
    from triplum.cache import CachedStep

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    close_default_cache()

    class Uppercase(CachedStep[Text, Text]):
        def fingerprint(self) -> str:
            return content_key("uppercase-default-mixin-v1", {})

        def compute(self, item: Text, /) -> Text:
            CALLS.append(item.text)
            return Text(text=item.text.upper())

    CALLS.clear()
    try:
        step = Uppercase()
        assert step(Text(text="hi")) == step(Text(text="hi")) == Text(text="HI")
        assert CALLS == ["hi"]
    finally:
        close_default_cache()


def test_editing_source_before_first_call_does_not_poison_new_implementation(
    tmp_path: Path, monkeypatch
) -> None:
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    close_default_cache()
    path = tmp_path / "live_module.py"
    source = (
        "from test_cache_defaults import Text\n"
        "from triplum.cache import cached\n"
        "@cached\n"
        "def run(item: Text) -> Text:\n"
        "    return Text(text='old')\n"
    )
    path.write_text(source)
    loader = SourceFileLoader("live_module", str(path))
    spec = spec_from_loader(loader.name, loader)
    assert spec is not None
    old = module_from_spec(spec)
    loader.exec_module(old)
    updated = source.replace("'old'", "'new value'")
    path.write_text(updated)
    try:
        assert old.run(Text(text="input")) == Text(text="old")
        new = module_from_spec(spec)
        loader.exec_module(new)
        assert new.run(Text(text="input")) == Text(text="new value")
    finally:
        close_default_cache()


def test_exit_handler_cannot_reopen_database_after_default_shutdown(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    script = tmp_path / "shutdown.py"
    script.write_text(
        "import atexit\n"
        "from pathlib import Path\n"
        "import os\n"
        "def late():\n"
        "    path = Path(os.environ['XDG_CACHE_HOME']) / 'triplum' / 'cache.sqlite'\n"
        "    path.unlink()\n"
        "    try:\n"
        "        default_cache()\n"
        "    except RuntimeError:\n"
        "        pass\n"
        "    print(path.exists())\n"
        "atexit.register(late)\n"
        "from triplum.cache import default_cache\n"
        "default_cache()\n"
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        env={**os.environ, "XDG_CACHE_HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
