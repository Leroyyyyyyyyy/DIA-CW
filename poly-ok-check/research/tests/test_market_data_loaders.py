from __future__ import annotations

import json

from research.market_data import load_hub_archive_market_frames, load_ws_dump_market_frames


def test_loads_hub_archive_partial_stale_snapshot(tmp_path) -> None:
    path = tmp_path / "slices.jsonl"
    record = {
        "hub_ts": "2026-03-15T10:10:39Z",
        "markets": {
            "m1": {
                "market_id": "m1",
                "book_ticker": {
                    "bids": [{"price": 0.40, "size": 10.0}],
                    "asks": [{"price": 0.60, "size": 5.0}],
                    "best_bid": 0.40,
                    "best_ask": 0.60,
                    "midpoint": 0.50,
                    "spread": 0.20,
                },
                "quality_flags": {"stale": True, "partial": True, "source_lag_ms": 0},
            }
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    frames = load_hub_archive_market_frames([path])

    assert len(frames) == 1
    assert frames.iloc[0]["market_id"] == "m1"
    assert frames.iloc[0]["quality_stale"] is True
    assert frames.iloc[0]["quality_partial"] is True
    assert frames.iloc[0]["depth_usd"] == 7.0


def test_loads_ws_dump_levels_and_skips_non_book_rows(tmp_path) -> None:
    path = tmp_path / "orderbook.jsonl"
    rows = [
        {"type": "startup", "received_ms": 1000, "assets": ["t1"]},
        {"type": "bootstrap_error", "asset_id": "t1", "error": "bad"},
        {
            "type": "bootstrap_snapshot",
            "received_ms": 2000,
            "asset_id": "t1",
            "bids": ["0.40@10", "0.45@2"],
            "asks": ["0.70@1", "0.60@5"],
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    frames = load_ws_dump_market_frames([path])

    assert len(frames) == 1
    row = frames.iloc[0]
    assert row["token_id"] == "t1"
    assert row["best_bid"] == 0.45
    assert row["best_ask"] == 0.60
    assert row["orderbook_mid"] == 0.525
    assert row["bids"][0] == {"price": 0.45, "size": 2.0}
    assert row["asks"][0] == {"price": 0.60, "size": 5.0}
