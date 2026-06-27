"""Tests for the Pre/Post TDD state handshake."""

from hooks_v2.context_manager.context import ContextStore, make_key


def test_make_key_prefers_tool_use_id():
    assert make_key("s1", "abc", {"prompt": "x"}) == "tuid_abc"


def test_make_key_falls_back_to_hash_and_is_stable():
    k1 = make_key("s1", None, {"prompt": "x"})
    k2 = make_key("s1", None, {"prompt": "x"})
    k3 = make_key("s1", None, {"prompt": "y"})
    assert k1 == k2 and k1 != k3 and k1.startswith("hash_")


def test_store_roundtrip(tmp_path):
    store = ContextStore(tmp_path / "state")
    store.save("tuid_1", {"tests": [{"name": "t1"}], "cycle": 0})
    loaded = store.load("tuid_1")
    assert loaded["cycle"] == 0 and loaded["tests"][0]["name"] == "t1"
    store.clear("tuid_1")
    assert store.load("tuid_1") is None


def test_load_missing_returns_none(tmp_path):
    assert ContextStore(tmp_path / "state").load("nope") is None
