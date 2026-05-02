# Derived from NautilusTrader prediction-market example code.
# Distributed under the GNU Lesser General Public License Version 3.0 or later.
# Modified in this repository on 2026-03-11, 2026-03-15, 2026-03-16, 2026-03-31, and 2026-04-05.
# See the repository NOTICE file for provenance and licensing scope.

"""
EMA crossover momentum on one Polymarket market using PMXT historical L2 data.
"""

# ruff: noqa: E402

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _script_helpers import ensure_repo_root
else:
    from .._script_helpers import ensure_repo_root

ensure_repo_root(__file__)

from prediction_market_extensions.backtesting._execution_config import (
    ExecutionModelConfig,
    StaticLatencyConfig,
)
from prediction_market_extensions.backtesting._experiments import (
    build_replay_experiment,
    run_experiment,
)
from prediction_market_extensions.backtesting._prediction_market_backtest import MarketReportConfig
from prediction_market_extensions.backtesting._prediction_market_runner import MarketDataConfig
from prediction_market_extensions.backtesting._replay_specs import QuoteReplay
from prediction_market_extensions.backtesting._timing_harness import timing_harness
from prediction_market_extensions.backtesting.data_sources import PMXT, Polymarket, QuoteTick

DETAIL_PLOT_PANELS = (
    "total_equity",
    "equity",
    "market_pnl",
    "periodic_pnl",
    "yes_price",
    "allocation",
    "total_drawdown",
    "drawdown",
    "total_rolling_sharpe",
    "rolling_sharpe",
    "total_cash_equity",
    "cash_equity",
    "monthly_returns",
    "total_brier_advantage",
    "brier_advantage",
)

DATA = MarketDataConfig(
    platform=Polymarket,
    data_type=QuoteTick,
    vendor=PMXT,
    sources=(
        "local:D:/Polyquant/data/pmxt_raws",
        "archive:r2v2.pmxt.dev",
        "relay:209-209-10-83.sslip.io",
    ),
)

REPLAYS_PATH = Path(__file__).with_name("replays.json")


def _load_replays(path: Path) -> tuple[QuoteReplay, ...]:
    if not path.exists():
        return (
            QuoteReplay(
                market_slug="will-ludvig-aberg-win-the-2026-masters-tournament",
                token_index=0,
                start_time="2026-04-05T05:10:00Z",
                end_time="2026-04-05T05:20:00Z",
            ),
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON list of replay windows")

    replays: list[QuoteReplay] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"{path} item {index} must be an object")
        try:
            replays.append(
                QuoteReplay(
                    market_slug=str(item["market_slug"]),
                    token_index=int(item.get("token_index", 0)),
                    start_time=str(item["start_time"]),
                    end_time=str(item["end_time"]),
                )
            )
        except KeyError as exc:
            raise ValueError(f"{path} item {index} missing required key {exc}") from exc

    if not replays:
        raise ValueError(f"{path} contains no replay windows")
    return tuple(replays)


REPLAYS = _load_replays(REPLAYS_PATH)

"""
Fallback REPLAYS when backtests/private/replays.json does not exist:

    QuoteReplay(
        market_slug="will-ludvig-aberg-win-the-2026-masters-tournament",
        token_index=0,
        start_time="2026-04-05T05:10:00Z",
        end_time="2026-04-05T05:20:00Z",
    )
"""

STRATEGY_CONFIGS = [
    {
        "strategy_path": "strategies:QuoteTickEMACrossoverStrategy",
        "config_path": "strategies:QuoteTickEMACrossoverConfig",
        "config": {
            "trade_size": Decimal(5),
            "fast_period": 8,
            "slow_period": 21,
            "entry_buffer": 0.0,
            "take_profit": 0.01,
            "stop_loss": 0.01,
        },
    }
]

REPORT = MarketReportConfig(
    count_key="quotes",
    count_label="Quotes",
    pnl_label="PnL (USDC)",
)


EXECUTION = ExecutionModelConfig(
    queue_position=True,
    latency_model=StaticLatencyConfig(
        base_latency_ms=75.0,
        insert_latency_ms=10.0,
        update_latency_ms=5.0,
        cancel_latency_ms=5.0,
    ),
)

EXPERIMENT = build_replay_experiment(
    name="weather_backtest",
    description="PMXT L2 smoke backtest following backtestreadme.md",
    data=DATA,
    replays=REPLAYS,
    strategy_configs=STRATEGY_CONFIGS,
    initial_cash=100.0,
    probability_window=16,
    min_quotes=1,
    min_price_range=0.0,
    execution=EXECUTION,
    report=REPORT,
    empty_message="No weather sims met requirements.",
    emit_html=True,
    chart_output_path="output",
    detail_plot_panels=DETAIL_PLOT_PANELS,
)


@timing_harness
def run() -> None:
    run_experiment(EXPERIMENT)


if __name__ == "__main__":
    run()
