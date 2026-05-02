from __future__ import annotations

from research.schemas.data_package import DataPackage
from research.utils.time_utils import safe_float


PISTOL_EVENT_TYPES = {"pistol_round_end"}


def build_features(data_package: DataPackage) -> dict[str, float]:
    scoreboard = data_package.scoreboard
    team_a = data_package.team_states.get("team_a", {})
    team_b = data_package.team_states.get("team_b", {})

    pistol_advantage = 0.0
    for event in data_package.event_slice:
        if event.get("event_type") in PISTOL_EVENT_TYPES and event.get("team") == "team_a":
            pistol_advantage = 1.0
            break
        if event.get("event_type") in PISTOL_EVENT_TYPES and event.get("team") == "team_b":
            pistol_advantage = -1.0
            break

    return {
        "score_diff": safe_float(scoreboard.get("team_a_rounds")) - safe_float(scoreboard.get("team_b_rounds")),
        "economy_diff": safe_float(team_a.get("economy")) - safe_float(team_b.get("economy")),
        "alive_diff": safe_float(team_a.get("alive")) - safe_float(team_b.get("alive")),
        "loss_bonus_diff": safe_float(team_a.get("loss_bonus")) - safe_float(team_b.get("loss_bonus")),
        "pistol_advantage": pistol_advantage,
        "is_live_round": 1.0 if data_package.phase not in {"freeze_time", "timeout"} else 0.0,
    }

