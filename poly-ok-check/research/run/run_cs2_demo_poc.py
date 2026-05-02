from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd
from demoparser2 import DemoParser


DEFAULT_PROPS = [
    "steamid",
    "name",
    "team_name",
    "health",
    "armor_value",
    "is_alive",
    "current_equip_value",
    "CCSPlayerController.CCSPlayerController_InGameMoneyServices.m_iAccount",
    "active_weapon_name",
    "round_num",
    "game_time",
    "X",
    "Y",
    "Z",
]

EVENTS = [
    "player_death",
    "player_hurt",
    "round_start",
    "round_end",
    "bomb_planted",
    "bomb_defused",
    "bomb_exploded",
]


def main() -> None:
    args = parse_args()
    demo_path = Path(args.demo)
    if not demo_path.exists():
        raise FileNotFoundError(demo_path)

    match_id = args.match_id or demo_path.stem
    out_dir = Path(args.out_dir) / match_id
    out_dir.mkdir(parents=True, exist_ok=True)

    parser = DemoParser(str(demo_path))
    header = parser.parse_header()
    player_info = _to_pandas(parser.parse_player_info())
    events = _parse_events(parser)

    max_tick = _infer_max_tick(events)
    tickrate = _infer_tickrate(header, default=args.tickrate)
    sample_ticks = list(range(0, max_tick + 1, max(1, int(tickrate * args.snapshot_secs))))

    wanted_props = list(DEFAULT_PROPS)
    snapshots = _to_pandas(parser.parse_ticks(wanted_props, ticks=sample_ticks))

    snapshots = _normalize_snapshots(snapshots, tickrate=tickrate)
    economy = _build_economy_snapshots(snapshots)
    deaths = _normalize_event(events.get("player_death", pd.DataFrame()), tickrate=tickrate)
    rounds = _build_round_state(events, tickrate=tickrate)

    _write_json(out_dir / "header.json", header)
    player_info.to_parquet(out_dir / "player_info.parquet", index=False)
    snapshots.to_parquet(out_dir / "player_snapshot_5s.parquet", index=False)
    economy.to_parquet(out_dir / "economy_snapshot_5s.parquet", index=False)
    deaths.to_parquet(out_dir / "player_death.parquet", index=False)
    rounds.to_parquet(out_dir / "round_state.parquet", index=False)

    summary = {
        "demo": str(demo_path),
        "match_id": match_id,
        "tickrate": tickrate,
        "max_tick": max_tick,
        "snapshot_secs": args.snapshot_secs,
        "players": int(len(player_info)),
        "snapshot_rows": int(len(snapshots)),
        "economy_rows": int(len(economy)),
        "player_deaths": int(len(deaths)),
        "round_rows": int(len(rounds)),
        "available_wanted_props": wanted_props,
        "out_dir": str(out_dir),
    }
    _write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse one CS2 .dem into Polyquant PoC parquet files.")
    parser.add_argument("--demo", required=True, help="Path to a local .dem file.")
    parser.add_argument("--match-id", help="Stable output id. Defaults to demo stem.")
    parser.add_argument("--out-dir", default=r"D:\Polyquant\data\cs2_demos\parsed")
    parser.add_argument("--snapshot-secs", type=int, default=5)
    parser.add_argument("--tickrate", type=int, default=64)
    return parser.parse_args()


def _to_pandas(frame) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if isinstance(frame, pd.DataFrame):
        return frame
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    return pd.DataFrame(frame)


def _parse_events(parser: DemoParser) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for event_name in EVENTS:
        try:
            out[event_name] = _to_pandas(parser.parse_event(event_name))
        except Exception:
            out[event_name] = pd.DataFrame()
    return out


def _infer_max_tick(events: dict[str, pd.DataFrame]) -> int:
    max_tick = 0
    for frame in events.values():
        if not frame.empty and "tick" in frame.columns:
            max_tick = max(max_tick, int(pd.to_numeric(frame["tick"], errors="coerce").max()))
    if max_tick <= 0:
        raise ValueError("Could not infer max tick from demo events")
    return max_tick


def _infer_tickrate(header: dict, default: int) -> int:
    for key in ("tickrate", "tick_rate", "tickRate", "playback_ticks_per_second"):
        value = header.get(key) if isinstance(header, dict) else None
        if value:
            try:
                return int(float(value))
            except ValueError:
                pass
    return default


def _normalize_snapshots(frame: pd.DataFrame, *, tickrate: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out = out.rename(
        columns={
            "CCSPlayerController.CCSPlayerController_InGameMoneyServices.m_iAccount": "cash",
        }
    )
    if "tick" in out.columns:
        out["timestamp_s"] = pd.to_numeric(out["tick"], errors="coerce") / float(tickrate)
    if "is_alive" in out.columns:
        out["is_alive"] = out["is_alive"].map(bool)
    return out.sort_values([col for col in ("tick", "steamid") if col in out.columns]).reset_index(drop=True)


def _build_economy_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty:
        return pd.DataFrame()
    group_cols = [col for col in ("tick", "timestamp_s", "round_num", "team_name", "side") if col in snapshots.columns]
    agg: dict[str, str] = {}
    for col in ("cash", "current_equip_value"):
        if col in snapshots.columns:
            agg[col] = "sum"
    if "is_alive" in snapshots.columns:
        agg["is_alive"] = "sum"
    if not group_cols or not agg:
        return pd.DataFrame()
    out = snapshots.groupby(group_cols, dropna=False).agg(agg).reset_index()
    rename = {}
    if "cash" in out.columns:
        rename["cash"] = "team_cash"
    if "current_equip_value" in out.columns:
        rename["current_equip_value"] = "team_equip_value"
    if "is_alive" in out.columns:
        rename["is_alive"] = "alive_count"
    return out.rename(columns=rename)


def _normalize_event(frame: pd.DataFrame, *, tickrate: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "tick" in out.columns:
        out["timestamp_s"] = pd.to_numeric(out["tick"], errors="coerce") / float(tickrate)
    return out.sort_values("tick" if "tick" in out.columns else out.columns[0]).reset_index(drop=True)


def _build_round_state(events: dict[str, pd.DataFrame], *, tickrate: int) -> pd.DataFrame:
    rows: list[dict] = []
    for event_name in ("round_start", "round_end"):
        frame = _normalize_event(events.get(event_name, pd.DataFrame()), tickrate=tickrate)
        if frame.empty:
            continue
        for row in frame.to_dict(orient="records"):
            row["event_type"] = event_name
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values("tick" if "tick" in out.columns else "event_type").reset_index(drop=True)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value


if __name__ == "__main__":
    main()
