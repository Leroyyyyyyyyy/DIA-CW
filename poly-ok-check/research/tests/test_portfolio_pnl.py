from __future__ import annotations

import pandas as pd

from research.backtest.outcomes import OutcomeStore
from research.backtest.portfolio import PortfolioState
from research.schemas.execution import Fill


def test_portfolio_tracks_buy_sell_pnl_and_fees() -> None:
    portfolio = PortfolioState(equity=1000.0, cash=1000.0)
    portfolio.apply_fill(
        Fill("o1", 1.0, "m1", "t1", "YES", "BUY", qty=10.0, avg_price=0.50, notional_usd=5.0, fee_usd=0.05, slippage_usd=0.10)
    )
    portfolio.apply_fill(
        Fill("o2", 2.0, "m1", "t1", "YES", "SELL", qty=4.0, avg_price=0.70, notional_usd=2.8, fee_usd=0.028, slippage_usd=0.05)
    )

    position = portfolio.get_position("m1", "t1", "YES")
    assert position is not None
    assert position.qty == 6.0
    assert round(portfolio.realized_pnl, 6) == 0.772
    assert round(portfolio.fees_paid, 6) == 0.078
    assert round(portfolio.slippage_paid, 6) == 0.15


def test_portfolio_marks_open_position_to_conservative_exit_price() -> None:
    portfolio = PortfolioState(equity=1000.0, cash=1000.0)
    portfolio.apply_fill(
        Fill("o1", 1.0, "m1", "t1", "YES", "BUY", qty=10.0, avg_price=0.50, notional_usd=5.0, fee_usd=0.0, slippage_usd=0.0)
    )
    market_df = pd.DataFrame([{"timestamp_s": 2.0, "market_id": "m1", "token_id": "t1", "best_bid": 0.60, "best_ask": 0.70}])

    portfolio.mark_to_market(market_df, as_of_ts_s=2.0)

    assert portfolio.unrealized_pnl == 1.0
    assert portfolio.equity == 1001.0


def test_portfolio_settles_open_position_from_outcome_store() -> None:
    portfolio = PortfolioState(equity=1000.0, cash=1000.0)
    portfolio.apply_fill(
        Fill("o1", 1.0, "m1", "t1", "YES", "BUY", qty=10.0, avg_price=0.50, notional_usd=5.0, fee_usd=0.0, slippage_usd=0.0)
    )

    portfolio.settle(OutcomeStore({"t1": 1.0}), ts_s=99.0)

    assert portfolio.positions == {}
    assert portfolio.cash == 1005.0
    assert portfolio.equity == 1005.0
    assert portfolio.realized_pnl == 5.0
