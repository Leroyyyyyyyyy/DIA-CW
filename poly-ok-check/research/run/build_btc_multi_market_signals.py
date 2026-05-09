from __future__ import annotations

import argparse
import csv
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from research.schemas.domain_report import parse_json_cell


def build_btc_multi_market_signal_rows(
    source_signals_csv: Path | str,
    decision_times: Iterable[str],
    horizon_minutes: int = 5,
    source_market_id: str | None = None,
) -> list[dict[str, Any]]:
    times = list(decision_times)
    source_row = _load_source_btc_row(source_signals_csv, source_market_id=source_market_id)
    source_metadata = parse_json_cell(source_row.get("metadata"), default={})
    source_time_window = source_metadata.get("time_window") or {}
    source_as_of = str(source_time_window.get("as_of") or source_row.get("generated_at") or "")
    source_market = str(source_metadata.get("market_id") or source_row.get("market_id") or "btc_5m_up_down")

    rows: list[dict[str, Any]] = []
    for index, raw_time in enumerate(times, start=1):
        as_of = _parse_datetime(raw_time)
        end_at = as_of + timedelta(minutes=horizon_minutes)
        market_id = f"btc_5m_up_down_{_compact_timestamp(as_of)}"
        row = dict(source_row)
        metadata = deepcopy(source_metadata)
        metadata["market_id"] = market_id
        metadata["time_window"] = {"as_of": _iso_z(as_of), "start": "", "end": ""}
        metadata["market_window"] = {
            "as_of": _iso_z(as_of),
            "end_at": _iso_z(end_at),
            "horizon_minutes": horizon_minutes,
        }
        metadata["source_signal_market_id"] = source_market
        metadata["source_signal_as_of"] = source_as_of
        metadata["source_signal_generated_at"] = str(source_row.get("generated_at") or "")
        metadata["rolling_window_index"] = index
        metadata["rolling_window_count"] = len(times)

        row["generated_at"] = _iso_z(as_of)
        row["domain"] = "btc"
        row["action"] = "AUTO"
        row["metadata"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        row["top_evidence"] = _json_cell(row.get("top_evidence"), default=[])
        row["outcome_scores"] = _json_cell(row.get("outcome_scores"), default={})
        rows.append(row)
    return rows


def write_btc_multi_market_signals(rows: list[dict[str, Any]], out_path: Path | str) -> Path:
    if not rows:
        raise ValueError("No BTC multi-market signal rows were generated")
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def default_decision_times(start: str, count: int, step_minutes: int) -> list[str]:
    start_dt = _parse_datetime(start)
    return [_iso_z(start_dt + timedelta(minutes=step_minutes * index)) for index in range(count)]


def _load_source_btc_row(path: Path | str, source_market_id: str | None) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if str(row.get("domain") or "").strip().lower() != "btc":
            continue
        metadata = parse_json_cell(row.get("metadata"), default={})
        market_id = str(metadata.get("market_id") or row.get("market_id") or "")
        if source_market_id and market_id != source_market_id:
            continue
        return row
    raise ValueError(f"No BTC source signal row found in {path}")


def _json_cell(value: Any, default: Any) -> str:
    parsed = parse_json_cell(value, default=default)
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def _parse_datetime(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("decision time is empty")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _compact_timestamp(value: datetime) -> str:
    return re.sub(r"[-:]", "", _iso_z(value).replace(".000000", "")).replace("+0000", "").replace("Z", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build rolling BTC 5-minute multi-market signal snapshots.")
    parser.add_argument("--source", default="research/data/external/dia_btc/signals.csv")
    parser.add_argument("--out", default="research/data/external/dia_btc/signals_multi_market.csv")
    parser.add_argument("--start", default="2026-05-06T18:25:00Z")
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--step-minutes", type=int, default=5)
    parser.add_argument("--horizon-minutes", type=int, default=5)
    parser.add_argument("--decision-time", action="append", default=[])
    parser.add_argument("--source-market-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    decision_times = args.decision_time or default_decision_times(args.start, args.count, args.step_minutes)
    rows = build_btc_multi_market_signal_rows(
        args.source,
        decision_times=decision_times,
        horizon_minutes=args.horizon_minutes,
        source_market_id=args.source_market_id,
    )
    path = write_btc_multi_market_signals(rows, args.out)
    print(f"wrote_btc_multi_market_signals={path}")
    print(f"rows={len(rows)}")
    print(f"first_market_id={json.loads(rows[0]['metadata'])['market_id']}")
    print(f"last_market_id={json.loads(rows[-1]['metadata'])['market_id']}")


if __name__ == "__main__":
    main()
