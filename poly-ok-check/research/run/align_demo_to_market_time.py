from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PARQUET_FILES = [
    "player_snapshot_5s.parquet",
    "economy_snapshot_5s.parquet",
    "player_death.parquet",
    "round_state.parquet",
]


def main() -> None:
    args = parse_args()
    parsed_dir = Path(args.parsed_dir)
    if not parsed_dir.exists():
        raise FileNotFoundError(parsed_dir)

    anchor_utc = _parse_utc(args.anchor_utc)
    anchor_tick = int(args.anchor_tick) if args.anchor_tick is not None else _infer_anchor_tick(parsed_dir)
    tickrate = int(args.tickrate) if args.tickrate is not None else _infer_tickrate(parsed_dir)
    market_slug = args.market_slug or ""
    token_index = int(args.token_index)

    out_dir = Path(args.out_dir) if args.out_dir else parsed_dir / "market_aligned"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "parsed_dir": str(parsed_dir),
        "out_dir": str(out_dir),
        "market_slug": market_slug,
        "token_index": token_index,
        "anchor_utc": anchor_utc.isoformat().replace("+00:00", "Z"),
        "anchor_tick": anchor_tick,
        "tickrate": tickrate,
        "files": {},
    }

    for name in PARQUET_FILES:
        src = parsed_dir / name
        if not src.exists():
            continue
        frame = pd.read_parquet(src)
        if "tick" not in frame.columns:
            continue
        aligned = frame.copy()
        aligned["utc_ts"] = pd.to_datetime(
            [
                anchor_utc.timestamp() + ((float(tick) - float(anchor_tick)) / float(tickrate))
                for tick in aligned["tick"]
            ],
            unit="s",
            utc=True,
        )
        if market_slug:
            aligned["market_slug"] = market_slug
            aligned["token_index"] = token_index
        dst = out_dir / name
        aligned.to_parquet(dst, index=False)
        summary["files"][name] = {
            "rows": int(len(aligned)),
            "first_utc": _format_ts(aligned["utc_ts"].min()) if not aligned.empty else None,
            "last_utc": _format_ts(aligned["utc_ts"].max()) if not aligned.empty else None,
            "path": str(dst),
        }

    (out_dir / "alignment_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align parsed CS2 demo parquet files to Polymarket UTC time using a market-side "
            "anchor timestamp. Does not use GRID."
        )
    )
    parser.add_argument("--parsed-dir", required=True, help="Directory produced by run_cs2_demo_poc.py.")
    parser.add_argument(
        "--anchor-utc",
        required=True,
        help="UTC timestamp for anchor tick, e.g. official round 1 start from Polymarket/market research.",
    )
    parser.add_argument(
        "--anchor-tick",
        type=int,
        help="Demo tick corresponding to --anchor-utc. Defaults to first real round_start tick > 1.",
    )
    parser.add_argument("--tickrate", type=int, help="Defaults to summary.json tickrate or 64.")
    parser.add_argument("--market-slug", default="", help="Optional Polymarket market_slug to stamp outputs.")
    parser.add_argument("--token-index", type=int, default=0)
    parser.add_argument("--out-dir", help="Defaults to <parsed-dir>/market_aligned.")
    return parser.parse_args()


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _infer_anchor_tick(parsed_dir: Path) -> int:
    round_path = parsed_dir / "round_state.parquet"
    if not round_path.exists():
        raise FileNotFoundError(f"Missing {round_path}; pass --anchor-tick explicitly.")
    frame = pd.read_parquet(round_path)
    candidates = frame[
        (frame.get("event_type") == "round_start")
        & (pd.to_numeric(frame.get("round"), errors="coerce") == 1)
        & (pd.to_numeric(frame.get("tick"), errors="coerce") > 1)
    ]
    if candidates.empty:
        raise ValueError("Could not infer anchor tick; pass --anchor-tick explicitly.")
    return int(candidates.sort_values("tick").iloc[0]["tick"])


def _infer_tickrate(parsed_dir: Path) -> int:
    summary_path = parsed_dir / "summary.json"
    if not summary_path.exists():
        return 64
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return int(payload.get("tickrate") or 64)


def _format_ts(value: pd.Timestamp) -> str:
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
