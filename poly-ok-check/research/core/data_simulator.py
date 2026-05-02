from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from research.schemas.data_package import DataPackage
from research.utils.io_utils import ensure_sorted_by_ts, read_jsonl


REQUIRED_CHANNELS = {"scoreboard", "team_state", "event_log"}
OPTIONAL_CHANNELS = {"player_state", "utility_detail", "equipment_detail"}
KEY_EVENT_TYPES = {"round_end", "economy_reset", "timeout_start", "pistol_round_end"}
CHANNEL_BASENAMES = {name: name for name in REQUIRED_CHANNELS | OPTIONAL_CHANNELS}
SUPPORTED_TABULAR_EXTENSIONS = (".jsonl", ".parquet")
RAW_CSDS_REQUIRED = {"header", "round_state", "player_status", "player_info", "round_end"}
RAW_CSDS_OPTIONAL = {"player_death"}
SIDE_CODE_ALIASES = {
    "ct": "ct",
    "counterterrorist": "ct",
    "counter-terrorist": "ct",
    "counter_terrorist": "ct",
    "3": "ct",
    "t": "t",
    "terrorist": "t",
    "2": "t",
}
INITIAL_TEAM_LABEL_BY_SIDE = {"ct": "team_a", "t": "team_b"}


@dataclass(slots=True)
class ChannelValidationResult:
    degradation_flags: dict[str, str]


class DataSimulator:
    def __init__(self, latency_offset_secs: int = 30, window_secs: int = 10):
        self.latency_offset_secs = latency_offset_secs
        self.window_secs = window_secs
        self.last_degradation_flags: dict[str, str] = {}

    def load_match_channels(self, match_dir: Path) -> dict[str, pd.DataFrame]:
        match_dir = Path(match_dir)
        standard_channels = self._load_standard_channels(match_dir)
        if standard_channels:
            return standard_channels
        if self._has_raw_csds_files(match_dir):
            return self._load_raw_csds_channels(match_dir)
        expected = sorted(CHANNEL_BASENAMES) + sorted(RAW_CSDS_REQUIRED)
        raise ValueError(f"No supported match channels found in {match_dir}. Expected one of: {expected}")

    def _load_standard_channels(self, match_dir: Path) -> dict[str, pd.DataFrame]:
        channels: dict[str, pd.DataFrame] = {}
        for channel_name in CHANNEL_BASENAMES:
            path = self._find_channel_file(match_dir, channel_name)
            if path is None:
                continue
            frame = self._read_tabular_frame(path)
            if "ts_s" not in frame.columns:
                raise ValueError(f"{channel_name} missing required column ts_s")
            channels[channel_name] = ensure_sorted_by_ts(frame)
        return channels

    def _has_raw_csds_files(self, match_dir: Path) -> bool:
        return all(self._find_channel_file(match_dir, channel_name) is not None for channel_name in RAW_CSDS_REQUIRED)

    def _load_raw_csds_channels(self, match_dir: Path) -> dict[str, pd.DataFrame]:
        raw = {
            channel_name: self._read_tabular_frame(self._require_channel_file(match_dir, channel_name))
            for channel_name in RAW_CSDS_REQUIRED | RAW_CSDS_OPTIONAL
            if self._find_channel_file(match_dir, channel_name) is not None
        }
        adapter = _CsdsAdapter(raw)
        return adapter.to_standard_channels()

    def validate_channels(self, channels: dict[str, pd.DataFrame]) -> dict[str, str]:
        missing_required = sorted(REQUIRED_CHANNELS - set(channels))
        if missing_required:
            raise ValueError(f"Missing required channels: {missing_required}")

        degradation_flags: dict[str, str] = {}
        for channel_name in sorted(OPTIONAL_CHANNELS):
            if channel_name not in channels:
                degradation_flags[channel_name] = "missing"
        self.last_degradation_flags = degradation_flags
        return degradation_flags

    def build_data_packages(self, channels: dict[str, pd.DataFrame], match_id: str) -> list[DataPackage]:
        degradation = self.validate_channels(channels)
        scoreboard_df = channels["scoreboard"]
        team_df = channels["team_state"]
        event_df = channels["event_log"]
        player_df = channels.get("player_state", pd.DataFrame(columns=["ts_s", "player_id", "team"]))

        max_ts = max(
            float(scoreboard_df["ts_s"].max()),
            float(team_df["ts_s"].max()),
            float(event_df["ts_s"].max()),
        )
        window_edges = list(range(0, int(max_ts // self.window_secs) * self.window_secs + self.window_secs, self.window_secs))
        packages: list[DataPackage] = []

        for start_ts in window_edges:
            end_ts = start_ts + self.window_secs
            packages.append(
                self._build_package(
                    source_ts_s=float(end_ts),
                    scoreboard_df=scoreboard_df,
                    team_df=team_df,
                    event_df=event_df[(event_df["ts_s"] >= start_ts) & (event_df["ts_s"] < end_ts)],
                    player_df=player_df[player_df["ts_s"] < end_ts],
                    degradation=degradation,
                    match_id=match_id,
                )
            )

        for _, event_row in event_df[event_df["event_type"].isin(KEY_EVENT_TYPES)].iterrows():
            event_ts = float(event_row["ts_s"])
            packages.append(
                self._build_package(
                    source_ts_s=event_ts,
                    scoreboard_df=scoreboard_df,
                    team_df=team_df,
                    event_df=event_df[event_df["ts_s"] == event_ts],
                    player_df=player_df[player_df["ts_s"] <= event_ts],
                    degradation=degradation,
                    match_id=match_id,
                )
            )

        packages.sort(key=lambda item: (item.source_ts_s, item.available_ts_s, item.round_number))
        return packages

    def _build_package(
        self,
        source_ts_s: float,
        scoreboard_df: pd.DataFrame,
        team_df: pd.DataFrame,
        event_df: pd.DataFrame,
        player_df: pd.DataFrame,
        degradation: dict[str, str],
        match_id: str,
    ) -> DataPackage:
        scoreboard_row = self._latest_row_before(scoreboard_df, source_ts_s)
        if scoreboard_row is None:
            raise ValueError("No scoreboard state available at source_ts_s")

        team_slice = team_df[team_df["ts_s"] <= source_ts_s]
        latest_team_rows = team_slice.sort_values("ts_s").groupby("team", as_index=False).tail(1)
        team_states = {
            row["team"]: {
                "economy": float(row["economy"]),
                "loss_bonus": float(row["loss_bonus"]),
                "alive": int(row["alive"]),
            }
            for _, row in latest_team_rows.iterrows()
        }

        players = {}
        if not player_df.empty:
            latest_player_rows = player_df.sort_values("ts_s").groupby("player_id", as_index=False).tail(1)
            for _, row in latest_player_rows.iterrows():
                players[str(row["player_id"])] = {
                    "team": row["team"],
                    "hp": float(row.get("hp", 100.0)),
                    "armor": float(row.get("armor", 0.0)),
                }

        visibility_flags = {
            "team_states": "ok",
            "player_states": "ok" if players else "missing",
            "utility_detail": degradation.get("utility_detail", "ok"),
            "equipment_detail": degradation.get("equipment_detail", "ok"),
            "economy_estimated": False,
        }

        return DataPackage(
            source_ts_s=source_ts_s,
            available_ts_s=source_ts_s + self.latency_offset_secs,
            match_id=match_id,
            map_name=str(scoreboard_row["map_name"]),
            round_number=int(scoreboard_row["round_number"]),
            phase=str(scoreboard_row["phase"]),
            scoreboard={
                "team_a_rounds": int(scoreboard_row["team_a_rounds"]),
                "team_b_rounds": int(scoreboard_row["team_b_rounds"]),
            },
            team_states=team_states,
            player_states=players,
            event_slice=event_df.to_dict(orient="records"),
            visibility_flags=visibility_flags,
            feature_version="v1",
        )

    @staticmethod
    def _latest_row_before(df: pd.DataFrame, ts_s: float):
        eligible = df[df["ts_s"] <= ts_s]
        if eligible.empty:
            return None
        return eligible.sort_values("ts_s").iloc[-1]

    @staticmethod
    def _find_channel_file(match_dir: Path, channel_name: str) -> Path | None:
        for extension in SUPPORTED_TABULAR_EXTENSIONS:
            candidate = match_dir / f"{channel_name}{extension}"
            if candidate.exists():
                return candidate
        return None

    def _require_channel_file(self, match_dir: Path, channel_name: str) -> Path:
        path = self._find_channel_file(match_dir, channel_name)
        if path is None:
            raise ValueError(f"Missing required raw CSDS file: {channel_name}")
        return path

    @staticmethod
    def _read_tabular_frame(path: Path) -> pd.DataFrame:
        if path.suffix == ".jsonl":
            return read_jsonl(path)
        if path.suffix == ".parquet":
            try:
                return pd.read_parquet(path)
            except ImportError as exc:
                raise ImportError("Parquet support requires 'pyarrow' or 'fastparquet' to be installed.") from exc
        raise ValueError(f"Unsupported tabular file extension for {path}")


class _CsdsAdapter:
    def __init__(self, raw_channels: dict[str, pd.DataFrame]):
        self.raw_channels = raw_channels
        self.header = raw_channels["header"].copy()
        self.round_state = self._ensure_time_columns(raw_channels["round_state"].copy())
        self.player_status = self._ensure_time_columns(raw_channels["player_status"].copy())
        self.player_info = self._ensure_time_columns(raw_channels["player_info"].copy())
        self.round_end = self._ensure_time_columns(raw_channels["round_end"].copy())
        player_death = raw_channels.get("player_death")
        self.player_death = self._ensure_time_columns(player_death.copy()) if player_death is not None else pd.DataFrame()
        self.map_name = str(self.header.iloc[0].get("map_name", "unknown"))
        self.player_key_col = self._detect_player_key_column(self.player_info, self.player_status, self.player_death)
        self.initial_rosters = self._build_initial_rosters()
        self.round_side_mapping = self._build_round_side_mapping()

    def to_standard_channels(self) -> dict[str, pd.DataFrame]:
        return {
            "scoreboard": self._build_scoreboard_channel(),
            "team_state": self._build_team_state_channel(),
            "event_log": self._build_event_log_channel(),
            "player_state": self._build_player_state_channel(),
        }

    def _build_scoreboard_channel(self) -> pd.DataFrame:
        rows: list[dict] = []
        for _, row in self.round_state.iterrows():
            round_number = int(row["round"])
            side_map = self.round_side_mapping.get(round_number, self.round_side_mapping.get(self._earliest_round(), {}))
            team_a_side = side_map.get("team_a", "ct")
            rows.append(
                {
                    "ts_s": float(row["ts_s"]),
                    "map_name": self.map_name,
                    "round_number": round_number,
                    "phase": self._normalize_phase(row.get("phase")),
                    "team_a_rounds": self._score_for_side(row, team_a_side),
                    "team_b_rounds": self._score_for_side(row, "t" if team_a_side == "ct" else "ct"),
                }
            )
        return ensure_sorted_by_ts(pd.DataFrame(rows))

    def _build_team_state_channel(self) -> pd.DataFrame:
        status = self.player_status.copy()
        status["team"] = status.apply(lambda row: self._stable_team_from_row(row), axis=1)
        status = status[status["team"].isin({"team_a", "team_b"})].copy()
        health = status["health"] if "health" in status.columns else pd.Series(0, index=status.index)
        status["alive"] = (health.fillna(0) > 0).astype(int)
        grouped = (
            status.groupby(["ts_s", "team"], as_index=False)
            .agg(
                economy=("money", "sum"),
                loss_bonus=("money", lambda _: 0.0),
                alive=("alive", "sum"),
            )
            .sort_values("ts_s")
        )
        return ensure_sorted_by_ts(grouped)

    def _build_player_state_channel(self) -> pd.DataFrame:
        status = self.player_status.copy()
        status["team"] = status.apply(lambda row: self._stable_team_from_row(row), axis=1)
        status = status[status["team"].isin({"team_a", "team_b"})].copy()
        player_id_series = status[self.player_key_col] if self.player_key_col in status.columns else status["player_id"]
        health = status["health"] if "health" in status.columns else pd.Series(100.0, index=status.index)
        armor = status["armor"] if "armor" in status.columns else pd.Series(0.0, index=status.index)
        player_state = pd.DataFrame(
            {
                "ts_s": status["ts_s"],
                "player_id": player_id_series.astype(str),
                "team": status["team"],
                "hp": health.fillna(100.0),
                "armor": armor.fillna(0.0),
            }
        )
        return ensure_sorted_by_ts(player_state)

    def _build_event_log_channel(self) -> pd.DataFrame:
        rows: list[dict] = []
        if not self.player_death.empty:
            for _, row in self.player_death.iterrows():
                rows.append(
                    {
                        "ts_s": float(row["ts_s"]),
                        "event_type": "player_death",
                        "team": self._stable_team_from_row(row),
                        "payload": {
                            "victim": str(row.get(self.player_key_col, row.get("player_id", ""))),
                            "attacker": str(row.get("attacker_id_fixed", row.get("attacker_id", ""))),
                            "weapon": row.get("weapon_name"),
                        },
                    }
                )

        for _, row in self.round_end.iterrows():
            stable_winner = self._stable_team_from_winner_code(row.get("winner_team_code"), int(row["round"]))
            base_event = {
                "ts_s": float(row["ts_s"]),
                "event_type": "round_end",
                "team": stable_winner,
                "payload": {
                    "winner": stable_winner,
                    "win_reason": row.get("win_reason_message"),
                },
            }
            rows.append(base_event)
            if self._is_pistol_round(int(row["round"])):
                rows.append(
                    {
                        "ts_s": float(row["ts_s"]),
                        "event_type": "pistol_round_end",
                        "team": stable_winner,
                        "payload": {"winner": stable_winner},
                    }
                )

        if "event_type" in self.round_state.columns:
            timeout_mask = self.round_state["event_type"].astype(str).str.contains("timeout", case=False, na=False)
            timeout_rows = self.round_state[timeout_mask]
        else:
            timeout_rows = self.round_state.iloc[0:0]
        for _, row in timeout_rows.iterrows():
            rows.append(
                {
                    "ts_s": float(row["ts_s"]),
                    "event_type": "timeout_start",
                    "team": None,
                    "payload": {"phase": self._normalize_phase(row.get("phase"))},
                }
            )

        event_log = pd.DataFrame(rows or [{"ts_s": 0.0, "event_type": "round_end", "team": None, "payload": {}}])
        return ensure_sorted_by_ts(event_log)

    def _build_initial_rosters(self) -> dict[str, set[str]]:
        initial_round = self._earliest_round()
        initial_info = self.player_info[self.player_info["round"] == initial_round].copy()
        initial_info["side_code"] = initial_info["team_code"].map(_normalize_side_code)
        rosters: dict[str, set[str]] = {"team_a": set(), "team_b": set()}
        for side_code, team_label in INITIAL_TEAM_LABEL_BY_SIDE.items():
            team_rows = initial_info[initial_info["side_code"] == side_code]
            rosters[team_label] = set(team_rows[self.player_key_col].astype(str))
        if not rosters["team_a"] or not rosters["team_b"]:
            raise ValueError("Could not infer stable CSDS rosters from player_info")
        return rosters

    def _build_round_side_mapping(self) -> dict[int, dict[str, str]]:
        mapping: dict[int, dict[str, str]] = {}
        for round_number, frame in self.player_info.groupby("round"):
            mapping[int(round_number)] = {
                "team_a": self._majority_side_code(frame, "team_a"),
                "team_b": self._majority_side_code(frame, "team_b"),
            }
        if not mapping:
            raise ValueError("Could not infer round-side mapping from player_info")
        return mapping

    def _majority_side_code(self, frame: pd.DataFrame, team_label: str) -> str:
        rows = frame[frame[self.player_key_col].astype(str).isin(self.initial_rosters[team_label])].copy()
        if rows.empty:
            return "ct" if team_label == "team_a" else "t"
        counts = rows["team_code"].map(_normalize_side_code).dropna().value_counts()
        if counts.empty:
            return "ct" if team_label == "team_a" else "t"
        return str(counts.index[0])

    def _stable_team_from_row(self, row: pd.Series) -> str | None:
        player_key = str(row.get(self.player_key_col, row.get("player_id", "")))
        if player_key in self.initial_rosters["team_a"]:
            return "team_a"
        if player_key in self.initial_rosters["team_b"]:
            return "team_b"
        return None

    def _stable_team_from_winner_code(self, winner_code: object, round_number: int) -> str | None:
        winner_side = _normalize_side_code(winner_code)
        if winner_side is None:
            return None
        side_map = self.round_side_mapping.get(round_number, {})
        for team_label, side_code in side_map.items():
            if side_code == winner_side:
                return team_label
        return None

    def _score_for_side(self, row: pd.Series, side_code: str) -> int:
        if side_code == "ct":
            return int(row.get("ct_score", row.get("ct_score_raw", 0)))
        return int(row.get("t_score", row.get("t_score_raw", 0)))

    def _earliest_round(self) -> int:
        return int(self.player_info["round"].min())

    def _ensure_time_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        if "ts_s" in frame.columns:
            return ensure_sorted_by_ts(frame)
        if "second" in frame.columns:
            frame["ts_s"] = frame["second"].astype(float)
            return ensure_sorted_by_ts(frame)
        tick_rate = float(self.header.iloc[0].get("tick_rate", 64.0))
        if "tick" in frame.columns:
            frame["ts_s"] = frame["tick"].astype(float) / tick_rate
            return ensure_sorted_by_ts(frame)
        raise ValueError("CSDS frame is missing second/tick time columns")

    @staticmethod
    def _detect_player_key_column(*frames: pd.DataFrame) -> str:
        for column in ("player_id_fixed", "player_id"):
            if any(column in frame.columns for frame in frames if not frame.empty):
                return column
        raise ValueError("Could not find a stable player identifier in CSDS frames")

    @staticmethod
    def _normalize_phase(value: object) -> str:
        phase = str(value or "").strip().lower()
        if phase in {"freeze", "freezetime", "freeze_time"}:
            return "freeze_time"
        if "timeout" in phase:
            return "timeout"
        if phase in {"live", "playing"}:
            return "live"
        return phase or "unknown"

    @staticmethod
    def _is_pistol_round(round_number: int) -> bool:
        return round_number in {1, 13}


def _normalize_side_code(value: object) -> str | None:
    if value is None:
        return None
    return SIDE_CODE_ALIASES.get(str(value).strip().lower())


def build_mock_match_channels() -> dict[str, pd.DataFrame]:
    scoreboard = pd.DataFrame(
        [
            {"ts_s": 0.0, "map_name": "nuke", "round_number": 1, "phase": "freeze_time", "team_a_rounds": 0, "team_b_rounds": 0},
            {"ts_s": 10.0, "map_name": "nuke", "round_number": 1, "phase": "live", "team_a_rounds": 0, "team_b_rounds": 0},
            {"ts_s": 20.0, "map_name": "nuke", "round_number": 2, "phase": "freeze_time", "team_a_rounds": 1, "team_b_rounds": 0},
            {"ts_s": 30.0, "map_name": "nuke", "round_number": 2, "phase": "live", "team_a_rounds": 1, "team_b_rounds": 0},
        ]
    )
    team_state = pd.DataFrame(
        [
            {"ts_s": 0.0, "team": "team_a", "economy": 4000, "loss_bonus": 1400, "alive": 5},
            {"ts_s": 0.0, "team": "team_b", "economy": 4000, "loss_bonus": 1400, "alive": 5},
            {"ts_s": 12.0, "team": "team_a", "economy": 7000, "loss_bonus": 1400, "alive": 4},
            {"ts_s": 12.0, "team": "team_b", "economy": 2200, "loss_bonus": 1900, "alive": 2},
            {"ts_s": 24.0, "team": "team_a", "economy": 9000, "loss_bonus": 1400, "alive": 5},
            {"ts_s": 24.0, "team": "team_b", "economy": 1800, "loss_bonus": 2400, "alive": 5},
        ]
    )
    event_log = pd.DataFrame(
        [
            {"ts_s": 8.0, "event_type": "player_death", "team": "team_b", "payload": {"victim": "b1"}},
            {"ts_s": 18.0, "event_type": "pistol_round_end", "team": "team_a", "payload": {"winner": "team_a"}},
            {"ts_s": 18.0, "event_type": "round_end", "team": "team_a", "payload": {"winner": "team_a"}},
            {"ts_s": 26.0, "event_type": "economy_reset", "team": "team_b", "payload": {"team": "team_b"}},
        ]
    )
    player_state = pd.DataFrame(
        [
            {"ts_s": 5.0, "player_id": "a1", "team": "team_a", "hp": 100, "armor": 100},
            {"ts_s": 5.0, "player_id": "b1", "team": "team_b", "hp": 100, "armor": 50},
            {"ts_s": 15.0, "player_id": "a1", "team": "team_a", "hp": 82, "armor": 80},
        ]
    )
    return {
        "scoreboard": ensure_sorted_by_ts(scoreboard),
        "team_state": ensure_sorted_by_ts(team_state),
        "event_log": ensure_sorted_by_ts(event_log),
        "player_state": ensure_sorted_by_ts(player_state),
    }
