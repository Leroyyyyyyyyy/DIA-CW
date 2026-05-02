from __future__ import annotations

import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import requests

# ============================================================
# User-editable config
# ============================================================
OUTPUT_DIR = "./polymarket_outputs"
TOP_N = 200
MAX_WORKERS = 12
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.06  # gentle throttle

# Leaderboard periods supported by the official API: DAY / WEEK / MONTH / ALL
# We analyze WEEK and MONTH and use rolling windows below for trade/activity fetches.
ANALYSIS_WINDOWS = {
    "WEEK": 7,
    "MONTH": 30,
}

# Strategy heuristics (tune these if needed)
MAKER_REBATE_WEIGHT = 2.2
TWO_SIDED_MARKET_WEIGHT = 1.8
SMALL_TRADE_WEIGHT = 0.8
MANY_MARKETS_WEIGHT = 0.8
PAIR_OUTCOME_WEIGHT = 1.8
NEG_RISK_WEIGHT = 1.5
CONVERSION_WEIGHT = 2.2
SPLIT_MERGE_WEIGHT = 1.2
SHORT_HOLD_WEIGHT = 1.4
ONE_SIDED_WEIGHT = 1.6
CONCENTRATION_WEIGHT = 1.2
BOT_ACTIVITY_WEIGHT = 1.3

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

USER_AGENT = (
    "Mozilla/5.0 (compatible; PolymarketTop200Analyzer/1.0; +https://docs.polymarket.com)"
)


# ============================================================
# HTTP helpers
# ============================================================
class PolyClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 4,
        acceptable_404: bool = False,
    ) -> Any:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
                if acceptable_404 and resp.status_code == 404:
                    return None
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt, 8)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                return resp.json()
            except Exception as exc:
                last_err = exc
                wait = min(2 ** attempt, 8)
                time.sleep(wait)
        if last_err is not None:
            raise last_err
        raise RuntimeError(f"Unknown error calling {url}")


# ============================================================
# Time helpers
# ============================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())


def safe_dt_from_ts(ts: Any) -> Optional[datetime]:
    try:
        if ts is None or (isinstance(ts, float) and math.isnan(ts)):
            return None
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


# ============================================================
# Core fetchers
# ============================================================
def fetch_leaderboard(client: PolyClient, time_period: str, top_n: int = 200) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while len(rows) < top_n:
        limit = min(50, top_n - len(rows))
        data = client.get_json(
            f"{DATA_API}/v1/leaderboard",
            params={
                "category": "OVERALL",
                "timePeriod": time_period,
                "orderBy": "PNL",
                "limit": limit,
                "offset": offset,
            },
        )
        if not data:
            break
        rows.extend(data)
        offset += limit
        if len(data) < limit:
            break
    df = pd.DataFrame(rows)
    if not df.empty:
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
        df["vol"] = pd.to_numeric(df.get("vol"), errors="coerce")
        df["pnl"] = pd.to_numeric(df.get("pnl"), errors="coerce")
        df["period"] = time_period
    return df


def fetch_user_activity(
    client: PolyClient,
    user: str,
    start_ts: int,
    end_ts: int,
    limit_per_page: int = 500,
    max_pages: int = 50,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        data = client.get_json(
            f"{DATA_API}/activity",
            params={
                "user": user,
                "start": start_ts,
                "end": end_ts,
                "limit": limit_per_page,
                "offset": offset,
                "sortBy": "TIMESTAMP",
                "sortDirection": "DESC",
            },
        )
        if not data:
            break
        rows.extend(data)
        if len(data) < limit_per_page:
            break
        offset += limit_per_page
    df = pd.DataFrame(rows)
    if not df.empty:
        numeric_cols = ["timestamp", "size", "usdcSize", "price", "outcomeIndex"]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True, errors="coerce")
        df["user"] = user
    return df


def fetch_user_trades(
    client: PolyClient,
    user: str,
    limit_per_page: int = 1000,
    max_pages: int = 30,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        data = client.get_json(
            f"{DATA_API}/trades",
            params={
                "user": user,
                "takerOnly": "false",
                "limit": limit_per_page,
                "offset": offset,
            },
        )
        if not data:
            break
        rows.extend(data)
        if len(data) < limit_per_page:
            break
        offset += limit_per_page
    df = pd.DataFrame(rows)
    if not df.empty:
        numeric_cols = ["timestamp", "size", "price", "outcomeIndex"]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True, errors="coerce")
        df["user"] = user
    return df


def fetch_markets_by_condition_ids(client: PolyClient, condition_ids: Sequence[str]) -> pd.DataFrame:
    ids = [x for x in dict.fromkeys(condition_ids) if isinstance(x, str) and x.strip()]
    if not ids:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    chunk_size = 50
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        data = client.get_json(
            f"{GAMMA_API}/markets",
            params={
                "condition_ids": chunk,
                "limit": len(chunk),
                "closed": "true",
            },
        )
        if data:
            rows.extend(data)
    df = pd.DataFrame(rows)
    if not df.empty:
        keep_cols = [
            "id",
            "conditionId",
            "question",
            "slug",
            "category",
            "endDate",
            "clobTokenIds",
            "negRisk",
            "volume",
            "volume1wk",
            "volume1mo",
            "liquidity",
            "acceptingOrders",
            "active",
            "closed",
        ]
        keep_cols = [c for c in keep_cols if c in df.columns]
        df = df[keep_cols].copy()
        if "conditionId" in df.columns:
            df = df.drop_duplicates(subset=["conditionId"])
    return df


def fetch_current_positions(client: PolyClient, user: str, limit_per_page: int = 500) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        data = client.get_json(
            f"{DATA_API}/positions",
            params={
                "user": user,
                "limit": limit_per_page,
                "offset": offset,
                "sortBy": "TOKENS",
                "sortDirection": "DESC",
                "sizeThreshold": 0,
            },
        )
        if not data:
            break
        rows.extend(data)
        if len(data) < limit_per_page:
            break
        offset += limit_per_page
    df = pd.DataFrame(rows)
    if not df.empty:
        num_cols = [
            "size",
            "avgPrice",
            "initialValue",
            "currentValue",
            "cashPnl",
            "percentPnl",
            "totalBought",
            "realizedPnl",
            "percentRealizedPnl",
            "curPrice",
        ]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["user"] = user
    return df


# ============================================================
# Feature engineering
# ============================================================
def normalize_market_key(df: pd.DataFrame) -> pd.Series:
    if "conditionId" in df.columns:
        cond = df["conditionId"].fillna("")
    else:
        cond = pd.Series([""] * len(df), index=df.index)
    if "slug" in df.columns:
        slug = df["slug"].fillna("")
    else:
        slug = pd.Series([""] * len(df), index=df.index)
    if "title" in df.columns:
        title = df["title"].fillna("")
    else:
        title = pd.Series([""] * len(df), index=df.index)
    return cond.where(cond != "", slug.where(slug != "", title))


def market_summary_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    tmp = trades.copy()
    tmp["market_key"] = normalize_market_key(tmp)
    tmp["notional"] = tmp["price"].fillna(0) * tmp["size"].fillna(0)

    out = []
    for (user, market_key), g in tmp.groupby(["user", "market_key"], dropna=False):
        buy_cnt = int((g["side"] == "BUY").sum()) if "side" in g.columns else 0
        sell_cnt = int((g["side"] == "SELL").sum()) if "side" in g.columns else 0
        outcomes = sorted(x for x in g.get("outcome", pd.Series(dtype=object)).dropna().astype(str).unique())
        min_dt = g["datetime"].min() if "datetime" in g.columns else pd.NaT
        max_dt = g["datetime"].max() if "datetime" in g.columns else pd.NaT
        span_hours = None
        if pd.notna(min_dt) and pd.notna(max_dt):
            span_hours = (max_dt - min_dt).total_seconds() / 3600.0
        out.append(
            {
                "user": user,
                "market_key": market_key,
                "conditionId": g["conditionId"].dropna().iloc[0] if "conditionId" in g.columns and g["conditionId"].notna().any() else None,
                "title": g["title"].dropna().iloc[0] if "title" in g.columns and g["title"].notna().any() else None,
                "slug": g["slug"].dropna().iloc[0] if "slug" in g.columns and g["slug"].notna().any() else None,
                "eventSlug": g["eventSlug"].dropna().iloc[0] if "eventSlug" in g.columns and g["eventSlug"].notna().any() else None,
                "trade_count": len(g),
                "buy_count": buy_cnt,
                "sell_count": sell_cnt,
                "two_sided_market": int(buy_cnt > 0 and sell_cnt > 0),
                "distinct_outcomes": len(outcomes),
                "outcomes_traded": " | ".join(outcomes),
                "volume_tokens": g["size"].fillna(0).sum(),
                "volume_notional": g["notional"].fillna(0).sum(),
                "avg_price": g["price"].fillna(0).mean(),
                "median_trade_tokens": g["size"].fillna(0).median(),
                "first_trade_dt": min_dt,
                "last_trade_dt": max_dt,
                "trade_span_hours": span_hours,
            }
        )
    return pd.DataFrame(out)


def enrich_with_market_meta(df: pd.DataFrame, market_meta: pd.DataFrame) -> pd.DataFrame:
    if df.empty or market_meta.empty or "conditionId" not in df.columns or "conditionId" not in market_meta.columns:
        return df
    mm = market_meta.rename(
        columns={
            "question": "meta_question",
            "slug": "meta_slug",
            "category": "meta_category",
            "negRisk": "meta_negRisk",
            "volume": "meta_volume",
            "liquidity": "meta_liquidity",
        }
    )
    keep = [c for c in [
        "conditionId",
        "meta_question",
        "meta_slug",
        "meta_category",
        "meta_negRisk",
        "meta_volume",
        "meta_liquidity",
    ] if c in mm.columns]
    return df.merge(mm[keep], on="conditionId", how="left")


def compute_trade_time_features(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["user", "median_gap_minutes", "p95_gap_minutes", "night_hour_share_utc"])
    out = []
    for user, g in trades.sort_values(["user", "datetime"]).groupby("user"):
        gaps = g["datetime"].diff().dropna().dt.total_seconds() / 60.0
        median_gap = float(gaps.median()) if not gaps.empty else None
        p95_gap = float(gaps.quantile(0.95)) if not gaps.empty else None
        hour = g["datetime"].dt.hour
        night_share = float(hour.isin([0, 1, 2, 3, 4, 5]).mean()) if not hour.empty else None
        out.append(
            {
                "user": user,
                "median_gap_minutes": median_gap,
                "p95_gap_minutes": p95_gap,
                "night_hour_share_utc": night_share,
            }
        )
    return pd.DataFrame(out)


def summarize_activity(activity: pd.DataFrame) -> pd.DataFrame:
    if activity.empty:
        return pd.DataFrame(
            columns=[
                "user",
                "activity_count",
                "trade_activity_count",
                "split_count",
                "merge_count",
                "redeem_count",
                "conversion_count",
                "maker_rebate_count",
                "activity_notional",
            ]
        )
    out = []
    for user, g in activity.groupby("user"):
        type_counts = Counter(g["type"].dropna().astype(str)) if "type" in g.columns else Counter()
        out.append(
            {
                "user": user,
                "activity_count": len(g),
                "trade_activity_count": type_counts.get("TRADE", 0),
                "split_count": type_counts.get("SPLIT", 0),
                "merge_count": type_counts.get("MERGE", 0),
                "redeem_count": type_counts.get("REDEEM", 0),
                "conversion_count": type_counts.get("CONVERSION", 0),
                "maker_rebate_count": type_counts.get("MAKER_REBATE", 0),
                "activity_notional": pd.to_numeric(g.get("usdcSize"), errors="coerce").fillna(0).sum(),
            }
        )
    return pd.DataFrame(out)


def summarize_positions(positions: pd.DataFrame) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(
            columns=[
                "user",
                "current_positions_count",
                "current_position_value",
                "current_cash_pnl",
                "current_realized_pnl",
                "current_neg_risk_positions",
                "current_mergeable_positions",
                "current_redeemable_positions",
            ]
        )
    out = []
    for user, g in positions.groupby("user"):
        out.append(
            {
                "user": user,
                "current_positions_count": len(g),
                "current_position_value": pd.to_numeric(g.get("currentValue"), errors="coerce").fillna(0).sum(),
                "current_cash_pnl": pd.to_numeric(g.get("cashPnl"), errors="coerce").fillna(0).sum(),
                "current_realized_pnl": pd.to_numeric(g.get("realizedPnl"), errors="coerce").fillna(0).sum(),
                "current_neg_risk_positions": int(pd.Series(g.get("negativeRisk", pd.Series(dtype=bool))).fillna(False).sum()),
                "current_mergeable_positions": int(pd.Series(g.get("mergeable", pd.Series(dtype=bool))).fillna(False).sum()),
                "current_redeemable_positions": int(pd.Series(g.get("redeemable", pd.Series(dtype=bool))).fillna(False).sum()),
            }
        )
    return pd.DataFrame(out)


def infer_strategy_scores(user_row: pd.Series) -> Dict[str, float]:
    maker_rebate = float(user_row.get("maker_rebate_count", 0) or 0)
    two_sided_ratio = float(user_row.get("two_sided_market_ratio", 0) or 0)
    small_trade_ratio = float(user_row.get("small_trade_ratio", 0) or 0)
    market_diversity = float(user_row.get("unique_markets", 0) or 0)
    paired_ratio = float(user_row.get("paired_outcome_market_ratio", 0) or 0)
    neg_risk_ratio = float(user_row.get("neg_risk_market_ratio", 0) or 0)
    conversion_count = float(user_row.get("conversion_count", 0) or 0)
    split_merge_count = float(user_row.get("split_count", 0) or 0) + float(user_row.get("merge_count", 0) or 0)
    short_hold_ratio = float(user_row.get("fast_roundtrip_market_ratio", 0) or 0)
    one_sided_ratio = float(user_row.get("one_sided_side_ratio", 0) or 0)
    concentration = float(user_row.get("top1_market_volume_share", 0) or 0)
    trade_count = float(user_row.get("trade_count", 0) or 0)
    median_gap = user_row.get("median_gap_minutes", None)
    median_gap = float(median_gap) if median_gap is not None and not pd.isna(median_gap) else None

    many_markets_term = min(market_diversity / 20.0, 1.5)
    maker_term = min(maker_rebate / 5.0, 2.0)
    conversion_term = min(conversion_count / 3.0, 2.0)
    split_merge_term = min(split_merge_count / 6.0, 2.0)
    bot_term = 0.0
    if trade_count >= 50:
        bot_term += 0.5
    if median_gap is not None and median_gap <= 20:
        bot_term += 0.8

    market_maker_score = (
        MAKER_REBATE_WEIGHT * maker_term
        + TWO_SIDED_MARKET_WEIGHT * two_sided_ratio
        + SMALL_TRADE_WEIGHT * small_trade_ratio
        + MANY_MARKETS_WEIGHT * many_markets_term
    )

    arb_like_score = (
        PAIR_OUTCOME_WEIGHT * paired_ratio
        + NEG_RISK_WEIGHT * neg_risk_ratio
        + CONVERSION_WEIGHT * conversion_term
        + SPLIT_MERGE_WEIGHT * split_merge_term
        + 0.8 * two_sided_ratio
    )

    directional_score = (
        ONE_SIDED_WEIGHT * one_sided_ratio
        + CONCENTRATION_WEIGHT * concentration
        + 0.9 * max(0.0, 1.0 - two_sided_ratio)
        + 0.6 * max(0.0, 1.0 - many_markets_term / 1.5)
    )

    scalper_score = (
        SHORT_HOLD_WEIGHT * short_hold_ratio
        + 1.0 * two_sided_ratio
        + 0.6 * small_trade_ratio
        + 0.4 * many_markets_term
    )

    systematic_bot_score = (
        BOT_ACTIVITY_WEIGHT * bot_term
        + 0.7 * many_markets_term
        + 0.7 * small_trade_ratio
        + 0.7 * two_sided_ratio
        + 0.7 * maker_term
    )

    return {
        "score_market_maker": round(market_maker_score, 4),
        "score_arb_like": round(arb_like_score, 4),
        "score_directional": round(directional_score, 4),
        "score_scalper": round(scalper_score, 4),
        "score_systematic_bot": round(systematic_bot_score, 4),
    }


def label_from_scores(score_dict: Dict[str, float]) -> str:
    label_map = {
        "score_market_maker": "market_maker_like",
        "score_arb_like": "arb_or_conversion_like",
        "score_directional": "directional_like",
        "score_scalper": "short_term_scalper_like",
        "score_systematic_bot": "systematic_bot_like",
    }
    best_key = max(score_dict, key=score_dict.get)
    return label_map[best_key]


# ============================================================
# Period analysis
# ============================================================
@dataclass
class PeriodArtifacts:
    leaderboard: pd.DataFrame
    trades: pd.DataFrame
    activity: pd.DataFrame
    positions: pd.DataFrame
    trader_summary: pd.DataFrame
    trader_market_summary: pd.DataFrame
    strategy_market_summary: pd.DataFrame
    market_meta: pd.DataFrame


def analyze_period(client: PolyClient, period: str, days: int, output_dir: str) -> PeriodArtifacts:
    lb = fetch_leaderboard(client, period, TOP_N)
    if lb.empty:
        raise RuntimeError(f"No leaderboard data returned for {period}")

    users = lb["proxyWallet"].dropna().astype(str).tolist()
    end_dt = now_utc()
    start_dt = end_dt - timedelta(days=days)
    start_ts = to_unix_seconds(start_dt)
    end_ts = to_unix_seconds(end_dt)

    trades_chunks: List[pd.DataFrame] = []
    activity_chunks: List[pd.DataFrame] = []
    position_chunks: List[pd.DataFrame] = []

    def worker(user: str) -> Tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        tr = fetch_user_trades(client, user)
        if not tr.empty:
            tr = tr[(tr["timestamp"] >= start_ts) & (tr["timestamp"] <= end_ts)].copy()
        act = fetch_user_activity(client, user, start_ts, end_ts)
        pos = fetch_current_positions(client, user)
        return user, tr, act, pos

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(worker, user): user for user in users}
        for fut in as_completed(futs):
            user = futs[fut]
            try:
                _, tr, act, pos = fut.result()
                if not tr.empty:
                    trades_chunks.append(tr)
                if not act.empty:
                    activity_chunks.append(act)
                if not pos.empty:
                    position_chunks.append(pos)
            except Exception as exc:
                print(f"[WARN] failed user {user}: {exc}")

    trades = pd.concat(trades_chunks, ignore_index=True) if trades_chunks else pd.DataFrame()
    activity = pd.concat(activity_chunks, ignore_index=True) if activity_chunks else pd.DataFrame()
    positions = pd.concat(position_chunks, ignore_index=True) if position_chunks else pd.DataFrame()

    condition_ids = []
    if not trades.empty and "conditionId" in trades.columns:
        condition_ids.extend(trades["conditionId"].dropna().astype(str).tolist())
    if not activity.empty and "conditionId" in activity.columns:
        condition_ids.extend(activity["conditionId"].dropna().astype(str).tolist())
    if not positions.empty and "conditionId" in positions.columns:
        condition_ids.extend(positions["conditionId"].dropna().astype(str).tolist())
    market_meta = fetch_markets_by_condition_ids(client, condition_ids)

    trader_market_summary = market_summary_from_trades(trades)
    trader_market_summary = enrich_with_market_meta(trader_market_summary, market_meta)

    activity_summary = summarize_activity(activity)
    position_summary = summarize_positions(positions)
    time_summary = compute_trade_time_features(trades)

    if trades.empty:
        trade_summary = pd.DataFrame(columns=["user"])
    else:
        tmp = trades.copy()
        tmp["notional"] = tmp["price"].fillna(0) * tmp["size"].fillna(0)
        tmp["market_key"] = normalize_market_key(tmp)

        market_meta_small = market_meta[[c for c in ["conditionId", "negRisk"] if c in market_meta.columns]].copy() if not market_meta.empty else pd.DataFrame()
        if not market_meta_small.empty:
            market_meta_small = market_meta_small.rename(columns={"negRisk": "market_negRisk"})
            tmp = tmp.merge(market_meta_small, on="conditionId", how="left")
        else:
            tmp["market_negRisk"] = None

        out = []
        for user, g in tmp.groupby("user"):
            sides = g["side"].dropna().astype(str) if "side" in g.columns else pd.Series(dtype=str)
            buy_count = int((sides == "BUY").sum())
            sell_count = int((sides == "SELL").sum())
            trade_count = len(g)
            unique_markets = g["market_key"].nunique(dropna=True)
            unique_conditions = g["conditionId"].nunique(dropna=True) if "conditionId" in g.columns else None
            median_trade_tokens = float(g["size"].fillna(0).median()) if "size" in g.columns else None
            median_trade_notional = float(g["notional"].fillna(0).median()) if "notional" in g.columns else None
            volume_tokens = float(g["size"].fillna(0).sum()) if "size" in g.columns else None
            volume_notional = float(g["notional"].fillna(0).sum()) if "notional" in g.columns else None

            side_ratio = max(buy_count, sell_count) / trade_count if trade_count else 0
            top1_share = 0.0
            if trade_count:
                vol_by_market = g.groupby("market_key")["notional"].sum().sort_values(ascending=False)
                total_vol = vol_by_market.sum()
                top1_share = float(vol_by_market.iloc[0] / total_vol) if total_vol > 0 and len(vol_by_market) > 0 else 0.0

            small_trade_ratio = 0.0
            if median_trade_notional is not None and trade_count > 0:
                threshold = max(median_trade_notional, 1.0)
                small_trade_ratio = float((g["notional"].fillna(0) <= threshold).mean())

            per_market = []
            for market_key, mg in g.groupby("market_key"):
                outcomes = set(mg.get("outcome", pd.Series(dtype=object)).dropna().astype(str))
                buy_n = int((mg["side"] == "BUY").sum()) if "side" in mg.columns else 0
                sell_n = int((mg["side"] == "SELL").sum()) if "side" in mg.columns else 0
                span_hours = None
                if "datetime" in mg.columns and mg["datetime"].notna().any():
                    span_hours = (mg["datetime"].max() - mg["datetime"].min()).total_seconds() / 3600.0
                per_market.append(
                    {
                        "market_key": market_key,
                        "paired_outcome": int(len(outcomes) >= 2),
                        "two_sided": int(buy_n > 0 and sell_n > 0),
                        "fast_roundtrip": int((buy_n > 0 and sell_n > 0) and (span_hours is not None and span_hours <= 24)),
                        "neg_risk": bool(pd.Series(mg.get("market_negRisk", pd.Series(dtype=bool))).fillna(False).any()),
                    }
                )
            pm = pd.DataFrame(per_market)
            out.append(
                {
                    "user": user,
                    "trade_count": trade_count,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "one_sided_side_ratio": side_ratio,
                    "unique_markets": unique_markets,
                    "unique_conditions": unique_conditions,
                    "median_trade_tokens": median_trade_tokens,
                    "median_trade_notional": median_trade_notional,
                    "volume_tokens": volume_tokens,
                    "volume_notional": volume_notional,
                    "top1_market_volume_share": top1_share,
                    "small_trade_ratio": small_trade_ratio,
                    "paired_outcome_market_ratio": float(pm["paired_outcome"].mean()) if not pm.empty else 0.0,
                    "two_sided_market_ratio": float(pm["two_sided"].mean()) if not pm.empty else 0.0,
                    "fast_roundtrip_market_ratio": float(pm["fast_roundtrip"].mean()) if not pm.empty else 0.0,
                    "neg_risk_market_ratio": float(pm["neg_risk"].mean()) if not pm.empty else 0.0,
                }
            )
        trade_summary = pd.DataFrame(out)

    trader_summary = lb.merge(trade_summary, left_on="proxyWallet", right_on="user", how="left")
    trader_summary = trader_summary.merge(activity_summary, left_on="proxyWallet", right_on="user", how="left", suffixes=("", "_activity"))
    trader_summary = trader_summary.merge(position_summary, left_on="proxyWallet", right_on="user", how="left", suffixes=("", "_positions"))
    trader_summary = trader_summary.merge(time_summary, left_on="proxyWallet", right_on="user", how="left", suffixes=("", "_time"))

    # clean duplicated helper columns
    duplicate_user_cols = [c for c in trader_summary.columns if c.startswith("user_")]
    if duplicate_user_cols:
        trader_summary = trader_summary.drop(columns=duplicate_user_cols)

    score_records = []
    for _, row in trader_summary.iterrows():
        scores = infer_strategy_scores(row)
        scores["primary_style"] = label_from_scores(scores)
        score_records.append(scores)
    score_df = pd.DataFrame(score_records)
    trader_summary = pd.concat([trader_summary.reset_index(drop=True), score_df], axis=1)

    def likely_bot_flag(r: pd.Series) -> int:
        return int((r.get("score_systematic_bot", 0) or 0) >= 1.8 or (r.get("score_market_maker", 0) or 0) >= 2.2)

    trader_summary["likely_systematic_bot"] = trader_summary.apply(likely_bot_flag, axis=1)
    trader_summary["analysis_window_days"] = days
    trader_summary["analysis_start_utc"] = start_dt.isoformat()
    trader_summary["analysis_end_utc"] = end_dt.isoformat()

    # Attach primary style to per-market rows for downstream aggregation.
    if not trader_market_summary.empty:
        trader_market_summary = trader_market_summary.merge(
            trader_summary[["proxyWallet", "primary_style", "likely_systematic_bot"]],
            left_on="user",
            right_on="proxyWallet",
            how="left",
        )
        trader_market_summary = trader_market_summary.drop(columns=["proxyWallet"], errors="ignore")

    strategy_market_summary = pd.DataFrame()
    if not trader_market_summary.empty:
        tmp = trader_market_summary.copy()
        group_cols = ["primary_style", "title", "slug", "conditionId"]
        tmp["title"] = tmp["title"].fillna(tmp.get("meta_question", pd.Series(dtype=object)))
        strategy_market_summary = (
            tmp.groupby(group_cols, dropna=False)
            .agg(
                traders=("user", "nunique"),
                total_trade_count=("trade_count", "sum"),
                total_notional=("volume_notional", "sum"),
                total_tokens=("volume_tokens", "sum"),
                avg_market_span_hours=("trade_span_hours", "mean"),
                two_sided_trader_count=("two_sided_market", "sum"),
                bot_flag_count=("likely_systematic_bot", "sum"),
            )
            .reset_index()
            .sort_values(["primary_style", "total_notional", "traders"], ascending=[True, False, False])
        )

    # Save outputs
    os.makedirs(output_dir, exist_ok=True)
    prefix = period.lower()
    lb.to_csv(os.path.join(output_dir, f"leaderboard_{prefix}_top{TOP_N}.csv"), index=False)
    trades.to_csv(os.path.join(output_dir, f"raw_trades_{prefix}.csv"), index=False)
    activity.to_csv(os.path.join(output_dir, f"raw_activity_{prefix}.csv"), index=False)
    positions.to_csv(os.path.join(output_dir, f"raw_positions_{prefix}.csv"), index=False)
    market_meta.to_csv(os.path.join(output_dir, f"market_meta_{prefix}.csv"), index=False)
    trader_summary.to_csv(os.path.join(output_dir, f"trader_summary_{prefix}.csv"), index=False)
    trader_market_summary.to_csv(os.path.join(output_dir, f"trader_market_summary_{prefix}.csv"), index=False)
    strategy_market_summary.to_csv(os.path.join(output_dir, f"strategy_market_summary_{prefix}.csv"), index=False)

    snapshot = {
        "period": period,
        "analysis_window_days": days,
        "leaderboard_rows": int(len(lb)),
        "trade_rows": int(len(trades)),
        "activity_rows": int(len(activity)),
        "position_rows": int(len(positions)),
        "likely_systematic_bot_count": int(trader_summary["likely_systematic_bot"].fillna(0).sum()) if not trader_summary.empty else 0,
        "primary_style_counts": trader_summary["primary_style"].value_counts(dropna=False).to_dict() if "primary_style" in trader_summary.columns else {},
        "top_10_markets_by_notional": (
            strategy_market_summary.sort_values("total_notional", ascending=False)
            .head(10)[[c for c in ["primary_style", "title", "slug", "traders", "total_notional"] if c in strategy_market_summary.columns]]
            .to_dict(orient="records")
            if not strategy_market_summary.empty
            else []
        ),
    }
    with open(os.path.join(output_dir, f"summary_{prefix}.json"), "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return PeriodArtifacts(
        leaderboard=lb,
        trades=trades,
        activity=activity,
        positions=positions,
        trader_summary=trader_summary,
        trader_market_summary=trader_market_summary,
        strategy_market_summary=strategy_market_summary,
        market_meta=market_meta,
    )


# ============================================================
# Main
# ============================================================
def build_readme(output_dir: str) -> None:
    text = """# Polymarket Top200 Weekly / Monthly Analyzer

This script fetches the official Polymarket leaderboard, then analyzes the top 200 traders for WEEK and MONTH.

## What it downloads
- `leaderboard_week_top200.csv` / `leaderboard_month_top200.csv`
- `raw_trades_*.csv`
- `raw_activity_*.csv`
- `raw_positions_*.csv`
- `market_meta_*.csv`
- `trader_summary_*.csv`
- `trader_market_summary_*.csv`
- `strategy_market_summary_*.csv`
- `summary_*.json`

## Heuristic labels
These are inference labels, not ground truth:
- `market_maker_like`
- `arb_or_conversion_like`
- `directional_like`
- `short_term_scalper_like`
- `systematic_bot_like`

## How to run
```bash
pip install pandas requests
python polymarket_top200_analysis.py
```

## Notes
- Leaderboard ranking itself is pulled directly from the official leaderboard API.
- Trade/activity analysis uses rolling windows: 7 days for WEEK and 30 days for MONTH by default.
- Public APIs do **not** expose every private order/cancel event for other users, so this script infers style from executed trades, onchain/public activity, market metadata, and current positions.
"""
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = PolyClient()

    all_period_summaries: List[pd.DataFrame] = []
    for period, days in ANALYSIS_WINDOWS.items():
        print(f"[INFO] analyzing {period} (rolling {days}d) ...")
        artifacts = analyze_period(client, period, days, OUTPUT_DIR)
        mini = artifacts.trader_summary.copy()
        mini["period"] = period
        all_period_summaries.append(mini)

    merged = pd.concat(all_period_summaries, ignore_index=True) if all_period_summaries else pd.DataFrame()
    if not merged.empty:
        merged.to_csv(os.path.join(OUTPUT_DIR, "trader_summary_all_periods.csv"), index=False)

        # Same wallet across WEEK / MONTH for comparison.
        compare_cols = [
            "proxyWallet",
            "userName",
            "period",
            "rank",
            "pnl",
            "vol",
            "trade_count",
            "volume_notional",
            "maker_rebate_count",
            "primary_style",
            "likely_systematic_bot",
            "score_market_maker",
            "score_arb_like",
            "score_directional",
            "score_scalper",
            "score_systematic_bot",
        ]
        compare_cols = [c for c in compare_cols if c in merged.columns]
        merged[compare_cols].to_csv(os.path.join(OUTPUT_DIR, "trader_period_compare.csv"), index=False)

    build_readme(OUTPUT_DIR)
    print(f"[DONE] outputs saved to: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
