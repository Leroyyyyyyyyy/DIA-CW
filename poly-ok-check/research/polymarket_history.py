from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from research.market_data import normalize_market_frames
from research.utils.time_utils import clip_probability, safe_float


CLOB_PRICE_HISTORY_URL = "https://clob.polymarket.com/prices-history"


def fetch_price_history(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
    timeout_secs: float = 30.0,
) -> dict:
    params = {
        "market": str(token_id),
        "startTs": int(start_ts),
        "endTs": int(end_ts),
        "fidelity": int(fidelity_minutes),
    }
    url = f"{CLOB_PRICE_HISTORY_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "polyquant-research/0.1",
        },
    )
    with urlopen(request, timeout=timeout_secs) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    if "history" not in data:
        raise ValueError("price-history response missing history field")
    if not data["history"]:
        raise ValueError("price-history response contains empty history")
    return data


def download_price_history(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
    data_dir: Path | str,
    refresh: bool = False,
) -> Path:
    data_dir = Path(data_dir)
    path = _price_history_path(data_dir, token_id, start_ts, end_ts, fidelity_minutes)
    if path.exists() and not refresh:
        _append_manifest(
            data_dir,
            token_id,
            start_ts,
            end_ts,
            fidelity_minutes,
            row_count=_history_count(path),
            local_path=path,
            status="cache_hit",
            error="",
        )
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = fetch_price_history(token_id, start_ts, end_ts, fidelity_minutes)
        path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        _append_manifest(
            data_dir,
            token_id,
            start_ts,
            end_ts,
            fidelity_minutes,
            row_count=len(data.get("history") or []),
            local_path=path,
            status="ok",
            error="",
        )
        return path
    except Exception as exc:
        _append_manifest(
            data_dir,
            token_id,
            start_ts,
            end_ts,
            fidelity_minutes,
            row_count=0,
            local_path=path,
            status="error",
            error=str(exc),
        )
        raise


def load_cached_price_history(path: Path | str) -> pd.DataFrame:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    history = data.get("history")
    if not history:
        raise ValueError(f"price-history file has no history rows: {path}")
    rows = []
    for item in history:
        rows.append(
            {
                "timestamp_s": safe_float(item.get("t"), default=float("nan")),
                "price": clip_probability(safe_float(item.get("p"), default=0.5)),
            }
        )
    frame = pd.DataFrame(rows)
    return frame[pd.notna(frame["timestamp_s"])].sort_values("timestamp_s").reset_index(drop=True)


def price_history_to_market_frames(
    price_df: pd.DataFrame,
    token_id: str,
    market_id: str | None = None,
    synthetic_spread_bps: float = 200.0,
    synthetic_depth_usd: float = 1000.0,
) -> pd.DataFrame:
    if price_df.empty:
        raise ValueError("price_df is empty")
    rows: list[dict] = []
    for _, row in price_df.iterrows():
        midpoint = clip_probability(safe_float(row.get("price"), default=0.5))
        spread = midpoint * max(synthetic_spread_bps, 0.0) / 10_000.0
        best_bid = max(midpoint - spread / 2.0, 0.0)
        best_ask = min(midpoint + spread / 2.0, 1.0)
        bid_size = synthetic_depth_usd / best_bid if best_bid > 0.0 else 0.0
        ask_size = synthetic_depth_usd / best_ask if best_ask > 0.0 else 0.0
        rows.append(
            {
                "timestamp_s": float(row["timestamp_s"]),
                "market_id": market_id or token_id,
                "token_id": token_id,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "orderbook_mid": midpoint,
                "spread": best_ask - best_bid,
                "depth_usd": synthetic_depth_usd * 2.0,
                "bids": [{"price": best_bid, "size": bid_size}] if bid_size > 0.0 else [],
                "asks": [{"price": best_ask, "size": ask_size}] if ask_size > 0.0 else [],
                "source": "clob_price_history",
                "quality_stale": False,
                "quality_partial": True,
                "metadata": {"synthetic": True, "synthetic_spread_bps": synthetic_spread_bps},
            }
        )
    return normalize_market_frames(pd.DataFrame(rows))


def write_market_frames_cache(
    market_df: pd.DataFrame,
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
    data_dir: Path | str,
) -> Path:
    data_dir = Path(data_dir)
    base = data_dir / "market_frames" / str(token_id)
    base.mkdir(parents=True, exist_ok=True)
    parquet_path = base / f"{int(start_ts)}_{int(end_ts)}_f{int(fidelity_minutes)}.parquet"
    try:
        market_df.to_parquet(parquet_path, index=False)
        return parquet_path
    except Exception:
        csv_path = parquet_path.with_suffix(".csv")
        market_df.to_csv(csv_path, index=False)
        return csv_path


def _price_history_path(data_dir: Path, token_id: str, start_ts: int, end_ts: int, fidelity_minutes: int) -> Path:
    return data_dir / "price_history" / str(token_id) / f"{int(start_ts)}_{int(end_ts)}_f{int(fidelity_minutes)}.json"


def _append_manifest(
    data_dir: Path,
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity_minutes: int,
    row_count: int,
    local_path: Path,
    status: str,
    error: str,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "token_id": str(token_id),
        "start_ts": int(start_ts),
        "end_ts": int(end_ts),
        "fidelity": int(fidelity_minutes),
        "source": CLOB_PRICE_HISTORY_URL,
        "row_count": int(row_count),
        "local_path": str(local_path),
        "status": status,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
    manifest = data_dir / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _history_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return len(data.get("history") or [])
    except Exception:
        return 0
