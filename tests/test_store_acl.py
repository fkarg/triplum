"""Coverage for the surviving principal and ACL identity helpers."""

from triplum.store.sqlite.acl import acl_hash, acl_tokens, principal_token


def test_acl_helpers():
    assert principal_token("alice@example.org") == principal_token("alice@example.org")
    assert principal_token("a") != principal_token("b")
    assert acl_hash({"b", "a"}) == acl_hash(["a", "b"]) and len(acl_hash({"a"})) == 16


def test_acl_hash_encoding_is_unambiguous():
    assert acl_hash(["a\x00b", "c"]) != acl_hash(["a", "b\x00c"])


def test_acl_tokens_are_sorted_deduplicated_and_empty_safe():
    assert acl_tokens(["bob", "alice", "bob"]) == (
        f"{principal_token('alice')} {principal_token('bob')}"
    )
    assert acl_tokens([]) == ""
