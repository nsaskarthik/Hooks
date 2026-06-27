"""Tests for the scalable multi-channel notifier."""

import json

from hooks_v2.shared import notify as notify_mod


def test_log_channel_writes_record(config, monkeypatch):
    monkeypatch.delenv("NOTIFY_CHANNELS", raising=False)
    config.notify_channels = ["log"]
    res = notify_mod.notify("hello", level="info", event="X", config=config)
    assert res == {"log": "ok"}
    rec = json.loads((config.log_dir / "notify.log.jsonl").read_text().splitlines()[-1])
    assert rec["message"] == "hello" and rec["category"] == "notification"


def test_env_overrides_channels_and_flags_unknown(config, monkeypatch):
    monkeypatch.setenv("NOTIFY_CHANNELS", "log,bogus")
    res = notify_mod.notify("hi", config=config)
    assert res["log"] == "ok" and res["bogus"] == "unknown-channel"


def test_one_bad_channel_does_not_break_others(config, monkeypatch):
    monkeypatch.setenv("NOTIFY_CHANNELS", "boom,log")

    def boom(*args, **kwargs):
        raise RuntimeError("nope")

    monkeypatch.setitem(notify_mod._CHANNELS, "boom", boom)
    res = notify_mod.notify("hi", config=config)
    assert res["boom"].startswith("error:") and res["log"] == "ok"


def test_webhook_noop_without_url(config, monkeypatch):
    monkeypatch.setenv("NOTIFY_CHANNELS", "webhook")
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    assert notify_mod.notify("hi", config=config) == {"webhook": "ok"}  # no URL -> silent no-op
