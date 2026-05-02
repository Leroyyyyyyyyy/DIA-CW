from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.schemas.execution import BacktestResult


def write_backtest_report(
    result: BacktestResult,
    market_df: pd.DataFrame,
    config: dict,
    out_dir: Path | str,
) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    run_id = config.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "summary.json", result.summary)
    _write_json(run_dir / "quality.json", {"source_quality": result.summary.get("source_quality", {})})
    _write_json(run_dir / "config.json", config)
    result.timeline.to_csv(run_dir / "timeline.csv", index=False)
    result.orders.to_csv(run_dir / "orders.csv", index=False)
    result.fills.to_csv(run_dir / "fills.csv", index=False)
    result.trades.to_csv(run_dir / "trades.csv", index=False)
    market_df.to_csv(run_dir / "market_frames.csv", index=False)
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
