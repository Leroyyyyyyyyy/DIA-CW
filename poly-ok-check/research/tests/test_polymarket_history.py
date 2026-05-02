from __future__ import annotations

import json

import pandas as pd
import pytest

from research.polymarket_history import (
    download_price_history,
    load_cached_price_history,
    price_history_to_market_frames,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_download_price_history_saves_json_and_manifest(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return FakeResponse({"history": [{"t": 10, "p": 0.42}]})

    monkeypatch.setattr("research.polymarket_history.urlopen", fake_urlopen)

    path = download_price_history("t1", 1, 20, 1, tmp_path)

    assert path.exists()
    assert calls
    assert json.loads(path.read_text(encoding="utf-8"))["history"][0]["p"] == 0.42
    manifest = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
    assert '"status": "ok"' in manifest
    assert '"row_count": 1' in manifest


def test_download_price_history_uses_cache_without_network(tmp_path, monkeypatch) -> None:
    path = tmp_path / "price_history" / "t1" / "1_20_f1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"history": [{"t": 10, "p": 0.42}]}), encoding="utf-8")

    def fake_urlopen(url, timeout):
        raise AssertionError("network should not be called")

    monkeypatch.setattr("research.polymarket_history.urlopen", fake_urlopen)

    cached = download_price_history("t1", 1, 20, 1, tmp_path, refresh=False)

    assert cached == path
    assert '"status": "cache_hit"' in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")


def test_download_price_history_records_error(tmp_path, monkeypatch) -> None:
    def fake_urlopen(url, timeout):
        return FakeResponse({"history": []})

    monkeypatch.setattr("research.polymarket_history.urlopen", fake_urlopen)

    with pytest.raises(ValueError):
        download_price_history("t1", 1, 20, 1, tmp_path, refresh=True)

    manifest = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8")
    assert '"status": "error"' in manifest
    assert "empty history" in manifest


def test_price_history_to_market_frames_builds_synthetic_book() -> None:
    price_df = pd.DataFrame([{"timestamp_s": 10.0, "price": 0.50}])

    frames = price_history_to_market_frames(price_df, "t1", synthetic_spread_bps=200, synthetic_depth_usd=1000)

    row = frames.iloc[0]
    assert row["best_bid"] == 0.495
    assert row["best_ask"] == 0.505
    assert row["source"] == "clob_price_history"
    assert row["quality_partial"] is True
    assert row["depth_usd"] == 2000.0


def test_load_cached_price_history_normalizes_rows(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"history": [{"t": 10, "p": "0.42"}]}), encoding="utf-8")

    frame = load_cached_price_history(path)

    assert list(frame.columns) == ["timestamp_s", "price"]
    assert frame.iloc[0]["price"] == 0.42


def test_price_history_range_filter_used_by_runner_style_flow(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps({"history": [{"t": 10, "p": 0.42}, {"t": 999, "p": 0.99}]}),
        encoding="utf-8",
    )

    frame = load_cached_price_history(path)
    frame = frame[(frame["timestamp_s"] >= 1) & (frame["timestamp_s"] <= 20)].reset_index(drop=True)

    assert len(frame) == 1
    assert frame.iloc[0]["timestamp_s"] == 10
