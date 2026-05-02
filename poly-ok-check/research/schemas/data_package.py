from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class DataPackage:
    source_ts_s: float
    available_ts_s: float
    match_id: str
    map_name: str
    round_number: int
    phase: str
    scoreboard: dict
    team_states: dict
    player_states: dict
    event_slice: list[dict]
    visibility_flags: dict
    feature_version: str = "v1"

    def to_dict(self) -> dict:
        return asdict(self)

