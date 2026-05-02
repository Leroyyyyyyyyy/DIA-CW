from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.core.data_simulator import DataSimulator, build_mock_match_channels


def test_builds_windowed_packages() -> None:
    simulator = DataSimulator(latency_offset_secs=30, window_secs=10)
    packages = simulator.build_data_packages(build_mock_match_channels(), match_id="m1")
    base_packages = [pkg for pkg in packages if pkg.source_ts_s in {10.0, 20.0, 30.0}]
    assert len(base_packages) == 3


def test_latency_offset_applied() -> None:
    simulator = DataSimulator(latency_offset_secs=30, window_secs=10)
    packages = simulator.build_data_packages(build_mock_match_channels(), match_id="m1")
    assert packages[0].available_ts_s == packages[0].source_ts_s + 30


def test_missing_optional_channel_degrades() -> None:
    channels = build_mock_match_channels()
    channels.pop("player_state")
    simulator = DataSimulator()
    packages = simulator.build_data_packages(channels, match_id="m1")
    assert packages[0].visibility_flags["player_states"] == "missing"


def test_missing_required_channel_raises() -> None:
    channels = build_mock_match_channels()
    channels.pop("event_log")
    simulator = DataSimulator()
    with pytest.raises(ValueError):
        simulator.build_data_packages(channels, match_id="m1")


def test_key_events_add_extra_packages() -> None:
    simulator = DataSimulator()
    packages = simulator.build_data_packages(build_mock_match_channels(), match_id="m1")
    event_ts = [pkg.source_ts_s for pkg in packages if pkg.source_ts_s in {18.0, 26.0}]
    assert 18.0 in event_ts
    assert 26.0 in event_ts


def test_loads_raw_csds_match_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_frames = {
        "header": pd.DataFrame([{"map_name": "nuke", "tick_rate": 1.0}]),
        "round_state": pd.DataFrame(
            [
                {"round": 1, "second": 0.0, "phase": "freezetime", "ct_score": 0, "t_score": 0},
                {"round": 2, "second": 30.0, "phase": "live", "ct_score": 1, "t_score": 0},
                {"round": 13, "second": 120.0, "phase": "freezetime", "ct_score": 6, "t_score": 7},
            ]
        ),
        "player_info": pd.DataFrame(
            [
                {"round": 1, "second": 0.0, "player_id_fixed": "a1", "team_code": "ct"},
                {"round": 1, "second": 0.0, "player_id_fixed": "a2", "team_code": "ct"},
                {"round": 1, "second": 0.0, "player_id_fixed": "b1", "team_code": "t"},
                {"round": 1, "second": 0.0, "player_id_fixed": "b2", "team_code": "t"},
                {"round": 13, "second": 120.0, "player_id_fixed": "a1", "team_code": "t"},
                {"round": 13, "second": 120.0, "player_id_fixed": "a2", "team_code": "t"},
                {"round": 13, "second": 120.0, "player_id_fixed": "b1", "team_code": "ct"},
                {"round": 13, "second": 120.0, "player_id_fixed": "b2", "team_code": "ct"},
            ]
        ),
        "player_status": pd.DataFrame(
            [
                {"round": 1, "second": 5.0, "player_id_fixed": "a1", "money": 4000, "health": 100, "armor": 50},
                {"round": 1, "second": 5.0, "player_id_fixed": "a2", "money": 3800, "health": 100, "armor": 50},
                {"round": 1, "second": 5.0, "player_id_fixed": "b1", "money": 3500, "health": 100, "armor": 0},
                {"round": 1, "second": 5.0, "player_id_fixed": "b2", "money": 3300, "health": 0, "armor": 0},
                {"round": 13, "second": 125.0, "player_id_fixed": "a1", "money": 6200, "health": 100, "armor": 100},
                {"round": 13, "second": 125.0, "player_id_fixed": "a2", "money": 6000, "health": 100, "armor": 100},
                {"round": 13, "second": 125.0, "player_id_fixed": "b1", "money": 2100, "health": 100, "armor": 0},
                {"round": 13, "second": 125.0, "player_id_fixed": "b2", "money": 1800, "health": 100, "armor": 0},
            ]
        ),
        "round_end": pd.DataFrame(
            [
                {"round": 1, "second": 28.0, "winner_team_code": "ct", "win_reason_message": "elimination"},
                {"round": 13, "second": 148.0, "winner_team_code": "t", "win_reason_message": "bomb"},
            ]
        ),
        "player_death": pd.DataFrame(
            [
                {"round": 1, "second": 12.0, "player_id_fixed": "b2", "attacker_id_fixed": "a1", "weapon_name": "ak47"},
            ]
        ),
    }
    for stem in raw_frames:
        (tmp_path / f"{stem}.parquet").touch()

    def fake_read(path: Path) -> pd.DataFrame:
        return raw_frames[path.stem].copy()

    monkeypatch.setattr(DataSimulator, "_read_tabular_frame", staticmethod(fake_read))

    simulator = DataSimulator(latency_offset_secs=30, window_secs=10)
    channels = simulator.load_match_channels(tmp_path)

    round_13 = channels["scoreboard"][channels["scoreboard"]["round_number"] == 13].iloc[0]
    assert round_13["team_a_rounds"] == 7
    assert round_13["team_b_rounds"] == 6

    team_state = channels["team_state"]
    assert team_state[team_state["team"] == "team_a"]["economy"].max() == 12_200
    assert team_state[team_state["team"] == "team_b"]["alive"].min() == 1

    event_types = set(channels["event_log"]["event_type"])
    assert "round_end" in event_types
    assert "pistol_round_end" in event_types

    packages = simulator.build_data_packages(channels, match_id="real-match-1")
    assert packages
    assert packages[-1].scoreboard["team_a_rounds"] == 7
