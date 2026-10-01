"""Production entrypoint configuration tests."""

from __future__ import annotations

import runpy


def test_start_trusts_platform_proxy_headers(monkeypatch):
    """Railway TLS termination must not produce HTTP redirect locations."""
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setenv("PORT", "8765")
    monkeypatch.setattr("uvicorn.run", fake_run)

    runpy.run_module("start", run_name="__main__")

    assert captured["args"] == ("server:app",)
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["port"] == 8765
    assert kwargs["proxy_headers"] is True
    assert kwargs["forwarded_allow_ips"] == "*"
