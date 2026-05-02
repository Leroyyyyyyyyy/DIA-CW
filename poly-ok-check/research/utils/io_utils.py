from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def read_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def ensure_sorted_by_ts(df: pd.DataFrame, ts_column: str = "ts_s") -> pd.DataFrame:
    if ts_column not in df.columns:
        raise ValueError(f"Missing required time column: {ts_column}")
    return df.sort_values(ts_column).reset_index(drop=True)

