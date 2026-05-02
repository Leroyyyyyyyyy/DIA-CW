from __future__ import annotations

import math

from research.utils.time_utils import clip_probability, safe_float


class ProbabilityCalibrator:
    def __init__(self, method: str = "identity"):
        supported = {"identity", "platt_like"}
        if method not in supported:
            raise ValueError(f"Unsupported calibration method: {method}")
        self.method = method

    def transform(self, p: float) -> float:
        value = clip_probability(safe_float(p, default=0.5))
        if self.method == "identity":
            return value
        centered = (value - 0.5) * 4.0
        calibrated = 1.0 / (1.0 + math.exp(-centered))
        return clip_probability(calibrated)

