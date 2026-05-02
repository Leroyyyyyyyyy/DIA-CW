from __future__ import annotations

import math

from research.core.feature_builder import build_features
from research.schemas.data_package import DataPackage
from research.utils.time_utils import clip_probability


WEIGHTS = {
    "intercept": 0.0,
    "score_diff": 0.30,
    "economy_diff": 0.00005,
    "alive_diff": 0.22,
    "loss_bonus_diff": -0.00002,
    "pistol_advantage": 0.35,
    "is_live_round": 0.10,
}


class BaselinePredictor:
    def predict_proba(self, data_package_or_features: DataPackage | dict[str, float]) -> float:
        if isinstance(data_package_or_features, DataPackage):
            features = build_features(data_package_or_features)
        else:
            features = data_package_or_features

        score = WEIGHTS["intercept"]
        for name, weight in WEIGHTS.items():
            if name == "intercept":
                continue
            score += weight * float(features.get(name, 0.0))
        probability = 1.0 / (1.0 + math.exp(-score))
        return clip_probability(probability)

