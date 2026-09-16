from triplum.cache import Cache, canonical_json, content_key


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_content_key_changes_with_kind_and_payload():
    k1 = content_key("llm", {"m": "x"})
    k2 = content_key("embed", {"m": "x"})
    k3 = content_key("llm", {"m": "y"})
    assert len(k1) == 64 and k1 != k2 and k1 != k3


def test_cache_roundtrip_and_miss(tmp_path):
    c = Cache(tmp_path)
    key = content_key("llm", {"q": 1})
    assert c.get(key) is None
    c.put(key, b"hello")
    assert c.get(key) == b"hello"
    assert (tmp_path / key[:2] / key).exists()


def test_cache_json_helpers(tmp_path):
    c = Cache(tmp_path)
    key = content_key("x", {})
    assert c.get_json(key) is None
    c.put_json(key, {"a": 1})
    assert c.get_json(key) == {"a": 1}
