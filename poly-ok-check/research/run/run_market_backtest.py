from __future__ import annotations

import argparse
from pathlib import Path

from research.backtest.execution import ExecutionSimulator, LatencyModel
from research.backtest.generic_env import GenericMarketBacktestEnv
from research.backtest.report import write_backtest_report
from research.polymarket_history import (
    download_price_history,
    load_cached_price_history,
    price_history_to_market_frames,
    write_market_frames_cache,
)
from research.schemas.risk_context import RiskContext
from research.strategy.generic import ProbabilityCsvStrategy, TargetCsvStrategy, load_strategy_from_path


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    price_path = download_price_history(
        token_id=args.token_id,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
        fidelity_minutes=args.fidelity_minutes,
        data_dir=data_dir,
        refresh=args.refresh,
    )
    price_df = load_cached_price_history(price_path)
    price_df = price_df[(price_df["timestamp_s"] >= args.start_ts) & (price_df["timestamp_s"] <= args.end_ts)].reset_index(drop=True)
    if price_df.empty:
        raise ValueError("No price-history rows remain after applying start-ts/end-ts filter")
    market_df = price_history_to_market_frames(
        price_df,
        token_id=args.token_id,
        market_id=args.market_id,
        synthetic_spread_bps=args.synthetic_spread_bps,
        synthetic_depth_usd=args.synthetic_depth_usd,
    )
    market_cache_path = write_market_frames_cache(
        market_df,
        token_id=args.token_id,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
        fidelity_minutes=args.fidelity_minutes,
        data_dir=data_dir,
    )

    strategy = build_strategy(args)
    risk = RiskContext(
        equity=args.initial_cash,
        cash=args.initial_cash,
        current_position_side=None,
        current_position_size=0.0,
        drawdown=0.0,
        event_tier="generic",
        allow_new_entry=True,
        reduce_only=False,
    )
    env = GenericMarketBacktestEnv(
        execution_simulator=ExecutionSimulator(fee_bps=args.fee_bps, stale_threshold_ms=args.stale_threshold_ms),
        latency_model=LatencyModel(
            base_latency_ms=args.base_latency_ms,
            jitter_ms=args.jitter_ms,
            seed=args.latency_seed,
        ),
    )
    config = vars(args).copy()
    config["price_history_path"] = str(price_path)
    config["market_cache_path"] = str(market_cache_path)
    result = env.run(market_df=market_df, strategy=strategy, risk_context=risk, outcome=args.outcome, run_config=config)
    run_dir = write_backtest_report(result, market_df=market_df, config=config, out_dir=out_dir)

    print(f"run_dir={run_dir}")
    print(f"summary={result.summary}")


def build_strategy(args):
    if args.strategy_path and args.strategy_class:
        return load_strategy_from_path(args.strategy_path, args.strategy_class)
    if not args.signals:
        raise ValueError("Either --signals or --strategy-path/--strategy-class is required")
    if args.signal_mode == "prob":
        return ProbabilityCsvStrategy(
            args.signals,
            entry_threshold=args.entry_threshold,
            exit_threshold=args.exit_threshold,
            position_size=args.position_size,
            fee_bps=args.fee_bps,
        )
    if args.signal_mode == "target":
        return TargetCsvStrategy(args.signals)
    raise ValueError("--signal-mode must be prob or target")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a generic single-token Polymarket backtest.")
    parser.add_argument("--token-id", required=True)
    parser.add_argument("--market-id")
    parser.add_argument("--start-ts", type=int, required=True)
    parser.add_argument("--end-ts", type=int, required=True)
    parser.add_argument("--strategy-path")
    parser.add_argument("--strategy-class")
    parser.add_argument("--signals")
    parser.add_argument("--signal-mode", choices=["prob", "target"], default="prob")
    parser.add_argument("--outcome", type=float, choices=[0.0, 1.0])
    parser.add_argument("--data-dir", default="research/data/polymarket")
    parser.add_argument("--out-dir", default="research/runs")
    parser.add_argument("--fidelity-minutes", type=int, default=1)
    parser.add_argument("--synthetic-spread-bps", type=float, default=200.0)
    parser.add_argument("--synthetic-depth-usd", type=float, default=1000.0)
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--position-size", type=float, default=100.0)
    parser.add_argument("--fee-bps", type=float, default=100.0)
    parser.add_argument("--entry-threshold", type=float, default=0.03)
    parser.add_argument("--exit-threshold", type=float, default=0.0)
    parser.add_argument("--base-latency-ms", type=float, default=500.0)
    parser.add_argument("--jitter-ms", type=float, default=100.0)
    parser.add_argument("--latency-seed", type=int, default=42)
    parser.add_argument("--stale-threshold-ms", type=float, default=15_000.0)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
