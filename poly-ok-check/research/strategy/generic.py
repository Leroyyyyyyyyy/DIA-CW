from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from research.backtest.portfolio import PortfolioState
from research.schemas.market import MarketSnapshotFrame
from research.schemas.strategy import Strategy, StrategyContext, StrategyDecision
from research.utils.time_utils import clip_probability, safe_float


VALID_TARGET_SIDES = {"YES", "NO", "FLAT"}


def load_signal_csv(path: Path | str, mode: str = "prob") -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "timestamp_s" not in frame.columns:
        raise ValueError("signal CSV missing required column: timestamp_s")
    frame = frame.copy()
    frame["timestamp_s"] = frame["timestamp_s"].astype(float)

    if mode == "prob":
        if "fair_prob" not in frame.columns:
            raise ValueError("prob signal CSV missing required column: fair_prob")
        frame["fair_prob"] = frame["fair_prob"].map(lambda value: clip_probability(safe_float(value, default=0.5)))
    elif mode == "target":
        missing = sorted({"target_side", "target_notional_usd"} - set(frame.columns))
        if missing:
            raise ValueError(f"target signal CSV missing required columns: {missing}")
        frame["target_side"] = frame["target_side"].astype(str).str.upper()
        bad_sides = sorted(set(frame["target_side"]) - VALID_TARGET_SIDES)
        if bad_sides:
            raise ValueError(f"target_side must be one of {sorted(VALID_TARGET_SIDES)}, got: {bad_sides}")
        frame["target_notional_usd"] = frame["target_notional_usd"].astype(float)
    else:
        raise ValueError("mode must be prob or target")

    if "reason" not in frame.columns:
        frame["reason"] = ""
    return frame.sort_values("timestamp_s").reset_index(drop=True)


class ProbabilityCsvStrategy:
    def __init__(
        self,
        path: Path | str,
        entry_threshold: float = 0.03,
        exit_threshold: float = 0.0,
        position_size: float = 100.0,
        fee_bps: float = 100.0,
    ):
        self.signals = load_signal_csv(path, mode="prob")
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.position_size = position_size
        self.fee_bps = fee_bps

    def on_snapshot(
        self,
        snapshot: MarketSnapshotFrame,
        portfolio: PortfolioState,
        context: StrategyContext,
    ) -> list[StrategyDecision]:
        signal = _latest_signal(self.signals, snapshot.timestamp_s)
        if signal is None:
            return []
        fair_prob = float(signal["fair_prob"])
        market_prob = snapshot.orderbook_mid if snapshot.orderbook_mid > 0.0 else _midpoint(snapshot)
        spread_penalty = max(snapshot.best_ask - snapshot.best_bid, 0.0) / 2.0
        fee_penalty = max(self.fee_bps, 0.0) / 10_000.0
        yes_edge = fair_prob - market_prob - spread_penalty - fee_penalty
        no_edge = market_prob - fair_prob - spread_penalty - fee_penalty
        active = portfolio.active_position()
        reason = str(signal.get("reason") or "")

        if active is not None:
            if active.side == "YES" and yes_edge <= self.exit_threshold:
                return [StrategyDecision("FLAT", 0.0, reason or "prob_exit_yes", {"fair_prob": fair_prob, "edge_net": yes_edge})]
            if active.side == "NO" and no_edge <= self.exit_threshold:
                return [StrategyDecision("FLAT", 0.0, reason or "prob_exit_no", {"fair_prob": fair_prob, "edge_net": no_edge})]
            return []

        if yes_edge > self.entry_threshold:
            return [StrategyDecision("YES", self.position_size, reason or "prob_enter_yes", {"fair_prob": fair_prob, "edge_net": yes_edge})]
        if no_edge > self.entry_threshold:
            return [StrategyDecision("NO", self.position_size, reason or "prob_enter_no", {"fair_prob": fair_prob, "edge_net": no_edge})]
        return []


class TargetCsvStrategy:
    def __init__(self, path: Path | str):
        self.signals = load_signal_csv(path, mode="target")

    def on_snapshot(
        self,
        snapshot: MarketSnapshotFrame,
        portfolio: PortfolioState,
        context: StrategyContext,
    ) -> list[StrategyDecision]:
        signal = _latest_signal(self.signals, snapshot.timestamp_s)
        if signal is None:
            return []
        return [
            StrategyDecision(
                target_side=str(signal["target_side"]).upper(),
                target_notional_usd=float(signal["target_notional_usd"]),
                reason=str(signal.get("reason") or "target_signal"),
            )
        ]


def load_strategy_from_path(strategy_path: Path | str, strategy_class: str) -> Strategy:
    path = Path(strategy_path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load strategy module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, strategy_class, None)
    if cls is None:
        raise ValueError(f"Strategy class not found: {strategy_class}")
    strategy = cls()
    if not hasattr(strategy, "on_snapshot"):
        raise ValueError(f"{strategy_class} must define on_snapshot(snapshot, portfolio, context)")
    return strategy


def _latest_signal(signals: pd.DataFrame, timestamp_s: float) -> pd.Series | None:
    eligible = signals[signals["timestamp_s"] <= timestamp_s]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


def _midpoint(snapshot: MarketSnapshotFrame) -> float:
    if snapshot.best_bid > 0.0 and snapshot.best_ask > 0.0:
        return (snapshot.best_bid + snapshot.best_ask) / 2.0
    return 0.5
