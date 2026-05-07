from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from research.schemas.domain_report import parse_json_cell


OUTCOME_FIELDS = [
    "market_id",
    "as_of",
    "end_at",
    "start_price",
    "end_price",
    "yes_outcome",
    "winning_side",
    "source",
    "source_symbol",
    "rule",
    "fetched_at",
]


def build_btc_outcome_rows(
    signals_csv: Path | str,
    fetcher: Callable[[datetime, datetime], dict[str, Any]] | None = None,
    horizon_minutes: int = 5,
) -> list[dict[str, Any]]:
    fetch_price_window = fetcher or fetch_btc_price_window
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    with Path(signals_csv).open("r", encoding="utf-8", newline="") as handle:
        for signal in csv.DictReader(handle):
            metadata = parse_json_cell(signal.get("metadata"), default={})
            market_id = str(metadata.get("market_id") or "btc_5m_up_down")
            as_of = _parse_datetime(
                (metadata.get("time_window") or {}).get("as_of") or signal.get("generated_at") or ""
            )
            end_at = as_of + timedelta(minutes=horizon_minutes)
            key = (market_id, as_of.isoformat())
            if key in seen:
                continue
            seen.add(key)

            prices = fetch_price_window(as_of, end_at)
            start_price = float(prices["start_price"])
            end_price = float(prices["end_price"])
            yes_outcome = 1.0 if end_price > start_price else 0.0
            rows.append(
                {
                    "market_id": market_id,
                    "as_of": _iso_z(as_of),
                    "end_at": _iso_z(end_at),
                    "start_price": f"{start_price:.8f}",
                    "end_price": f"{end_price:.8f}",
                    "yes_outcome": f"{yes_outcome:.1f}",
                    "winning_side": "YES" if yes_outcome >= 0.5 else "NO",
                    "source": str(prices["source"]),
                    "source_symbol": str(prices["source_symbol"]),
                    "rule": "YES=end_price>start_price over 5m; otherwise NO",
                    "fetched_at": _iso_z(datetime.now(timezone.utc)),
                }
            )
    return rows


def write_btc_outcome_csv(rows: list[dict[str, Any]], out_path: Path | str) -> Path:
    if not rows:
        raise ValueError("No BTC outcome rows were generated")
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTCOME_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def fetch_btc_price_window(as_of: datetime, end_at: datetime) -> dict[str, Any]:
    errors: list[str] = []
    for fetcher in (_fetch_binance_window, _fetch_coinbase_window):
        try:
            return fetcher(as_of, end_at)
        except Exception as exc:  # noqa: BLE001 - report both public data-source failures.
            errors.append(f"{fetcher.__name__}: {exc}")
    raise RuntimeError("Unable to fetch BTC 5m outcome from public price APIs: " + " | ".join(errors))


def _fetch_binance_window(as_of: datetime, end_at: datetime) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "startTime": int(_floor_minute(as_of).timestamp() * 1000),
            "endTime": int(_ceil_minute(end_at).timestamp() * 1000),
            "limit": 10,
        }
    )
    payload = _get_json(f"https://api.binance.com/api/v3/klines?{params}")
    if not isinstance(payload, list) or not payload:
        raise ValueError("empty Binance kline response")
    return {
        "start_price": float(payload[0][1]),
        "end_price": float(payload[-1][4]),
        "source": "binance",
        "source_symbol": "BTCUSDT",
    }


def _fetch_coinbase_window(as_of: datetime, end_at: datetime) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "granularity": 60,
            "start": _iso_z(_floor_minute(as_of)),
            "end": _iso_z(_ceil_minute(end_at)),
        }
    )
    payload = _get_json(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?{params}")
    if not isinstance(payload, list) or not payload:
        raise ValueError("empty Coinbase candle response")
    candles = sorted(payload, key=lambda row: row[0])
    return {
        "start_price": float(candles[0][3]),
        "end_price": float(candles[-1][4]),
        "source": "coinbase",
        "source_symbol": "BTC-USD",
    }


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "polyquant-cw-evaluation/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_datetime(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("BTC signal is missing as_of/generated_at timestamp")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _floor_minute(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _ceil_minute(value: datetime) -> datetime:
    floored = _floor_minute(value)
    if math.isclose(value.astimezone(timezone.utc).timestamp(), floored.timestamp()):
        return floored
    return floored + timedelta(minutes=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch BTC 5-minute up/down outcomes for cw_final evaluation.")
    parser.add_argument("--signals-csv", default="research/data/external/dia_btc/signals.csv")
    parser.add_argument("--out", default="research/data/external/outcomes/btc_5m_outcome.csv")
    parser.add_argument("--horizon-minutes", type=int, default=5)
    args = parser.parse_args()

    rows = build_btc_outcome_rows(args.signals_csv, horizon_minutes=args.horizon_minutes)
    path = write_btc_outcome_csv(rows, args.out)
    print(f"wrote_btc_outcomes={path}")
    for row in rows:
        print(
            " ".join(
                [
                    f"market_id={row['market_id']}",
                    f"as_of={row['as_of']}",
                    f"end_at={row['end_at']}",
                    f"start_price={row['start_price']}",
                    f"end_price={row['end_price']}",
                    f"winning_side={row['winning_side']}",
                    f"source={row['source']}",
                ]
            )
        )


if __name__ == "__main__":
    main()
