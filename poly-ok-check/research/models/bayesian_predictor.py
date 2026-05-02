from __future__ import annotations

from research.models.baseline_predictor import BaselinePredictor
from research.schemas.data_package import DataPackage


class BayesianPredictor:
    """V1 wrapper that preserves the future Bayesian interface without market labels."""

    def __init__(self, base_predictor: BaselinePredictor | None = None):
        self.base_predictor = base_predictor or BaselinePredictor()
        self.fit_history: list[tuple[dict, int]] = []
        self.online_updates: list[tuple[dict, int | None]] = []

    def fit(self, feature_rows: list[dict], labels: list[int]) -> None:
        for features, label in zip(feature_rows, labels, strict=False):
            self.fit_history.append((features, int(label)))

    def predict_proba(self, data_package_or_features: DataPackage | dict[str, float]) -> float:
        return self.base_predictor.predict_proba(data_package_or_features)

    def update_online(self, features: dict, outcome: int | None = None) -> None:
        self.online_updates.append((features, outcome))
