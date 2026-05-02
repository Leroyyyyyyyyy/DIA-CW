from __future__ import annotations

import math


PROB_EPSILON = 1e-6


def seconds_to_millis(seconds: float) -> float:
    return float(seconds) * 1000.0


def millis_to_seconds(milliseconds: float) -> float:
    return float(milliseconds) / 1000.0


def clip_probability(value: float, epsilon: float = PROB_EPSILON) -> float:
    if math.isnan(value) or math.isinf(value):
        value = 0.5
    return min(max(float(value), epsilon), 1.0 - epsilon)


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number

