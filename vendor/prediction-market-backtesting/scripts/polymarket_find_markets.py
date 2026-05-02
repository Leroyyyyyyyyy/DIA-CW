from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

if __package__ in {None, ""}:
    from _script_helpers import ensure_repo_root
else:
    from ._script_helpers import ensure_repo_root

ensure_repo_root(__file__)

from nautilus_trader.model.data import OrderBookDeltas, QuoteTick  # noqa: E402
from prediction_market_extensions.backtesting.data_sources.pmxt import (  # noqa: E402
    RunnerPolymarketPMXTDataLoader,
    configured_pmxt_data_source,
)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"
DEFAULT_PMXT_SOURCES = (
    "local:D:/Polyquant/data/pmxt_raws",
    "archive:r2v2.pmxt.dev",
    "relay:209-209-10-83.sslip.io",
)


@dataclass(frozen=True)
class PMXTCoverage:
    market_slug: str
    token_index: int
    records: int
    quotes: int
    order_book_deltas: int
    first_ts: str | None
    last_ts: str | None
    window_start: str | None = None
    window_end: str | None = None
    error: str | None = None


def _text_fields(item: dict[str, Any]) -> str:
    fields = (
        "title",
        "slug",
        "description",
        "question",
        "subtitle",
        "category",
    )
    return " ".join(str(item.get(field, "")) for field in fields).casefold()


def _matches_query(item: dict[str, Any], query: str | None) -> bool:
    if query is None:
        return True
    text = _text_fields(item)
    needle = query.strip().casefold()
    if not needle:
        return True
    if needle in text:
        return True
    terms = [term for term in needle.split() if term]
    return bool(terms) and all(term in text for term in terms)


def _coerce_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _request_json(client: httpx.Client, url: str, *, params: dict[str, Any] | None = None) -> Any:
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _search_gamma(
    client: httpx.Client,
    *,
    kind: str,
    query: str | None,
    active: bool,
    include_closed: bool,
    page_size: int,
    pages: int,
    limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    endpoint = f"{GAMMA_BASE_URL}/{kind}"
    for page in range(max(1, pages)):
        params: dict[str, Any] = {
            "limit": str(max(1, page_size)),
            "offset": str(page * max(1, page_size)),
        }
        if active:
            params["active"] = "true"
            params["closed"] = "false"
        elif not include_closed:
            params["closed"] = "false"

        items = _coerce_list(_request_json(client, endpoint, params=params))
        if not items:
            break

        for item in items:
            if _matches_query(item, query):
                matches.append(item)
                if len(matches) >= limit:
                    return matches
    return matches


def _get_event(client: httpx.Client, event_slug: str) -> dict[str, Any]:
    events = _coerce_list(
        _request_json(client, f"{GAMMA_BASE_URL}/events", params={"slug": event_slug})
    )
    if not events:
        raise RuntimeError(f"event not found: {event_slug}")
    return events[0]


def _get_market(client: httpx.Client, market_slug: str) -> dict[str, Any]:
    payload = _request_json(client, f"{GAMMA_BASE_URL}/markets/slug/{market_slug}")
    if isinstance(payload, list):
        if not payload:
            raise RuntimeError(f"market not found: {market_slug}")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected market response for {market_slug}: {type(payload).__name__}")
    return payload


def _get_clob_market(client: httpx.Client, condition_id: str) -> dict[str, Any]:
    payload = _request_json(client, f"{CLOB_BASE_URL}/markets/{condition_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"unexpected CLOB market response for {condition_id}: {type(payload).__name__}"
        )
    return payload


def _market_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": item.get("slug"),
        "question": item.get("question") or item.get("title"),
        "active": item.get("active"),
        "closed": item.get("closed"),
        "volume": item.get("volume"),
        "liquidity": item.get("liquidity"),
        "conditionId": item.get("conditionId"),
        "startDate": item.get("startDate"),
        "endDate": item.get("endDate"),
    }


def _event_summary(item: dict[str, Any]) -> dict[str, Any]:
    markets = item.get("markets")
    return {
        "slug": item.get("slug"),
        "title": item.get("title") or item.get("question"),
        "active": item.get("active"),
        "closed": item.get("closed"),
        "markets": len(markets) if isinstance(markets, list) else 0,
        "volume": item.get("volume"),
        "liquidity": item.get("liquidity"),
    }


def _tokens_from_market(client: httpx.Client, market: dict[str, Any]) -> list[dict[str, Any]]:
    condition_id = market.get("conditionId")
    if not condition_id:
        return []
    clob = _get_clob_market(client, str(condition_id))
    tokens = clob.get("tokens")
    if not isinstance(tokens, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        normalized.append(
            {
                "token_index": index,
                "outcome": token.get("outcome"),
                "token_id": token.get("token_id"),
                "price": token.get("price"),
            }
        )
    return normalized


def _record_ts(record: object) -> int | None:
    value = getattr(record, "ts_event", None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_ns(value: int | None) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(value, unit="ns", tz="UTC").isoformat()


def _utc_timestamp(value: object, *, label: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise SystemExit(f"{label} must be a valid timestamp: {value}") from exc
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _iter_scan_windows(
    *,
    scan_start: object,
    scan_end: object,
    step_hours: float,
    window_minutes: float,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = _utc_timestamp(scan_start, label="--scan-start")
    end = _utc_timestamp(scan_end, label="--scan-end")
    if start >= end:
        raise SystemExit("--scan-start must be earlier than --scan-end")
    if step_hours <= 0:
        raise SystemExit("--scan-step-hours must be greater than 0")
    if window_minutes <= 0:
        raise SystemExit("--window-minutes must be greater than 0")

    step = pd.Timedelta(hours=float(step_hours))
    width = pd.Timedelta(minutes=float(window_minutes))
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = start
    while cursor < end:
        window_end = cursor + width
        if window_end <= end:
            windows.append((cursor, window_end))
        cursor += step
    return windows


def _market_timestamp(market: dict[str, Any], *keys: str) -> pd.Timestamp | None:
    for key in keys:
        value = market.get(key)
        if value in {None, ""}:
            continue
        try:
            ts = pd.Timestamp(value)
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("UTC")
    return None


def _resolve_scan_range_for_market(
    market: dict[str, Any],
    *,
    scan_start: str | None,
    scan_end: str | None,
    lookback_days: float,
    delay_hours: float,
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    if scan_start is not None or scan_end is not None:
        if scan_start is None or scan_end is None:
            raise SystemExit("--scan-start and --scan-end must be provided together")
        return (
            _utc_timestamp(scan_start, label="--scan-start"),
            _utc_timestamp(scan_end, label="--scan-end"),
            "explicit",
        )

    if lookback_days <= 0:
        raise SystemExit("--scan-lookback-days must be greater than 0")
    if delay_hours < 0:
        raise SystemExit("--scan-delay-hours must be greater than or equal to 0")

    now = pd.Timestamp.now(tz="UTC")
    market_start = _market_timestamp(market, "startDate", "startDateIso", "createdAt")
    market_end = _market_timestamp(market, "endDate", "endDateIso")
    closed = bool(market.get("closed"))

    if closed and market_end is not None:
        end = market_end
        reason = "closed market endDate"
    else:
        end = now - pd.Timedelta(hours=float(delay_hours))
        reason = f"now minus {delay_hours:g}h delay"
        if market_end is not None:
            capped_end = min(end, market_end)
            if capped_end != end:
                reason = "market endDate"
            end = capped_end

    start = end - pd.Timedelta(days=float(lookback_days))
    if market_start is not None and start < market_start:
        start = market_start

    if start >= end:
        slug = market.get("slug") or "<unknown>"
        raise SystemExit(
            f"auto scan range for {slug} is empty "
            f"({start.isoformat()} -> {end.isoformat()}); provide --scan-start/--scan-end"
        )

    return start, end, f"auto ({reason}, lookback {lookback_days:g}d)"


def _coverage_from_records(
    *,
    market_slug: str,
    token_index: int,
    records: Sequence[object],
    window_start: pd.Timestamp | None = None,
    window_end: pd.Timestamp | None = None,
) -> PMXTCoverage:
    timestamps = [_record_ts(record) for record in records]
    timestamps = [ts for ts in timestamps if ts is not None]
    return PMXTCoverage(
        market_slug=market_slug,
        token_index=token_index,
        records=len(records),
        quotes=sum(isinstance(record, QuoteTick) for record in records),
        order_book_deltas=sum(isinstance(record, OrderBookDeltas) for record in records),
        first_ts=_format_ns(min(timestamps) if timestamps else None),
        last_ts=_format_ns(max(timestamps) if timestamps else None),
        window_start=window_start.isoformat() if window_start is not None else None,
        window_end=window_end.isoformat() if window_end is not None else None,
    )


async def _check_pmxt_one(
    market_slug: str,
    *,
    token_index: int,
    start_time: str,
    end_time: str,
    sources: Sequence[str],
) -> PMXTCoverage:
    try:
        with configured_pmxt_data_source(sources=sources):
            loader = await RunnerPolymarketPMXTDataLoader.from_market_slug(
                market_slug,
                token_index=token_index,
            )
            records = tuple(
                loader.load_order_book_and_quotes(
                    pd.Timestamp(start_time),
                    pd.Timestamp(end_time),
                )
            )
    except Exception as exc:
        return PMXTCoverage(
            market_slug=market_slug,
            token_index=token_index,
            records=0,
            quotes=0,
            order_book_deltas=0,
            first_ts=None,
            last_ts=None,
            window_start=pd.Timestamp(start_time).isoformat(),
            window_end=pd.Timestamp(end_time).isoformat(),
            error=f"{type(exc).__name__}: {exc}",
        )

    return _coverage_from_records(
        market_slug=market_slug,
        token_index=token_index,
        records=records,
        window_start=pd.Timestamp(start_time),
        window_end=pd.Timestamp(end_time),
    )


async def _check_pmxt_many(
    market_slugs: Sequence[str],
    *,
    token_index: int,
    start_time: str,
    end_time: str,
    sources: Sequence[str],
) -> list[PMXTCoverage]:
    results: list[PMXTCoverage] = []
    for market_slug in market_slugs:
        print(f"Checking PMXT {market_slug} token_index={token_index}...", flush=True)
        results.append(
            await _check_pmxt_one(
                market_slug,
                token_index=token_index,
                start_time=start_time,
                end_time=end_time,
                sources=sources,
            )
        )
    return results


async def _scan_pmxt_one(
    market_slug: str,
    *,
    token_index: int,
    windows: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
    sources: Sequence[str],
    only_hits: bool,
) -> list[PMXTCoverage]:
    results: list[PMXTCoverage] = []
    try:
        with configured_pmxt_data_source(sources=sources):
            loader = await RunnerPolymarketPMXTDataLoader.from_market_slug(
                market_slug,
                token_index=token_index,
            )
            for window_start, window_end in windows:
                print(
                    "Scanning PMXT "
                    f"{market_slug} token_index={token_index} "
                    f"{window_start.isoformat()} -> {window_end.isoformat()}...",
                    flush=True,
                )
                try:
                    records = tuple(loader.load_order_book_and_quotes(window_start, window_end))
                    coverage = _coverage_from_records(
                        market_slug=market_slug,
                        token_index=token_index,
                        records=records,
                        window_start=window_start,
                        window_end=window_end,
                    )
                except Exception as exc:
                    coverage = PMXTCoverage(
                        market_slug=market_slug,
                        token_index=token_index,
                        records=0,
                        quotes=0,
                        order_book_deltas=0,
                        first_ts=None,
                        last_ts=None,
                        window_start=window_start.isoformat(),
                        window_end=window_end.isoformat(),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                if not only_hits or coverage.quotes > 0:
                    results.append(coverage)
    except Exception as exc:
        for window_start, window_end in windows:
            coverage = PMXTCoverage(
                market_slug=market_slug,
                token_index=token_index,
                records=0,
                quotes=0,
                order_book_deltas=0,
                first_ts=None,
                last_ts=None,
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                error=f"{type(exc).__name__}: {exc}",
            )
            if not only_hits:
                results.append(coverage)
    return results


async def _scan_pmxt_many(
    market_slugs: Sequence[str],
    *,
    token_index: int,
    scan_start: str,
    scan_end: str,
    scan_step_hours: float,
    window_minutes: float,
    max_windows: int | None,
    sources: Sequence[str],
    only_hits: bool,
) -> list[PMXTCoverage]:
    windows = _iter_scan_windows(
        scan_start=scan_start,
        scan_end=scan_end,
        step_hours=scan_step_hours,
        window_minutes=window_minutes,
    )
    if max_windows is not None:
        windows = windows[: max(0, max_windows)]
    if not windows:
        raise SystemExit("PMXT scan produced no candidate windows")

    results: list[PMXTCoverage] = []
    for market_slug in market_slugs:
        results.extend(
            await _scan_pmxt_one(
                market_slug,
                token_index=token_index,
                windows=windows,
                sources=sources,
                only_hits=only_hits,
            )
        )
    return results


async def _scan_pmxt_markets(
    markets: Sequence[dict[str, Any]],
    *,
    token_index: int,
    scan_start: str | None,
    scan_end: str | None,
    scan_lookback_days: float,
    scan_delay_hours: float,
    scan_step_hours: float,
    window_minutes: float,
    max_windows: int | None,
    sources: Sequence[str],
    only_hits: bool,
) -> list[PMXTCoverage]:
    results: list[PMXTCoverage] = []
    for market in markets:
        market_slug = market.get("slug")
        if not market_slug:
            continue
        resolved_start, resolved_end, reason = _resolve_scan_range_for_market(
            market,
            scan_start=scan_start,
            scan_end=scan_end,
            lookback_days=scan_lookback_days,
            delay_hours=scan_delay_hours,
        )
        windows = _iter_scan_windows(
            scan_start=resolved_start,
            scan_end=resolved_end,
            step_hours=scan_step_hours,
            window_minutes=window_minutes,
        )
        if max_windows is not None:
            windows = windows[: max(0, max_windows)]
        if not windows:
            raise SystemExit(f"PMXT scan produced no candidate windows for {market_slug}")
        print(
            f"PMXT scan range for {market_slug}: "
            f"{resolved_start.isoformat()} -> {resolved_end.isoformat()} "
            f"[{reason}], windows={len(windows)}",
            flush=True,
        )
        results.extend(
            await _scan_pmxt_one(
                str(market_slug),
                token_index=token_index,
                windows=windows,
                sources=sources,
                only_hits=only_hits,
            )
        )
    return results


def _short(value: object, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "~"


def _print_events(events: Sequence[dict[str, Any]]) -> None:
    print(f"{'event_slug':56} {'markets':>7} title")
    print("-" * 90)
    for event in events:
        summary = _event_summary(event)
        print(
            f"{_short(summary['slug'], 56):56} "
            f"{str(summary['markets']):>7} "
            f"{_short(summary['title'], 80)}"
        )


def _print_markets(markets: Sequence[dict[str, Any]]) -> None:
    print(f"{'market_slug':64} {'active':>6} {'closed':>6} {'volume':>12} question")
    print("-" * 120)
    for market in markets:
        summary = _market_summary(market)
        print(
            f"{_short(summary['slug'], 64):64} "
            f"{str(summary['active']):>6} "
            f"{str(summary['closed']):>6} "
            f"{_short(summary['volume'], 12):>12} "
            f"{_short(summary['question'], 80)}"
        )


def _print_market_detail(market: dict[str, Any], tokens: Sequence[dict[str, Any]]) -> None:
    summary = _market_summary(market)
    print("MARKET")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    if tokens:
        print()
        print(f"{'token_index':>11} {'outcome':12} {'price':>10} token_id")
        print("-" * 100)
        for token in tokens:
            print(
                f"{str(token.get('token_index')):>11} "
                f"{_short(token.get('outcome'), 12):12} "
                f"{_short(token.get('price'), 10):>10} "
                f"{token.get('token_id')}"
            )


def _print_pmxt(results: Sequence[PMXTCoverage]) -> None:
    print()
    has_windows = any(result.window_start or result.window_end for result in results)
    if has_windows:
        print(
            f"{'market_slug':48} {'token':>5} {'window_start':27} "
            f"{'window_end':27} {'records':>8} {'quotes':>8} status"
        )
        print("-" * 140)
    else:
        print(
            f"{'market_slug':64} {'token':>5} {'records':>8} "
            f"{'quotes':>8} {'deltas':>8} status"
        )
        print("-" * 120)
    for result in results:
        status = result.error or (
            f"{result.first_ts or '-'} -> {result.last_ts or '-'}"
            if result.records
            else "no PMXT records returned"
        )
        if has_windows:
            print(
                f"{_short(result.market_slug, 48):48} "
                f"{result.token_index:>5} "
                f"{_short(result.window_start, 27):27} "
                f"{_short(result.window_end, 27):27} "
                f"{result.records:>8} "
                f"{result.quotes:>8} "
                f"{_short(status, 60)}"
            )
        else:
            print(
                f"{_short(result.market_slug, 64):64} "
                f"{result.token_index:>5} "
                f"{result.records:>8} "
                f"{result.quotes:>8} "
                f"{result.order_book_deltas:>8} "
                f"{_short(status, 80)}"
            )


def _json_default(value: object) -> object:
    if isinstance(value, PMXTCoverage):
        return value.__dict__
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _iso_z(value: str | None) -> str | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    text = ts.tz_convert("UTC").isoformat()
    return text.replace("+00:00", "Z")


def _replay_entries(results: Sequence[PMXTCoverage]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for result in results:
        if result.error or result.quotes <= 0 or not result.window_start or not result.window_end:
            continue
        start_time = _iso_z(result.window_start)
        end_time = _iso_z(result.window_end)
        if start_time is None or end_time is None:
            continue
        key = (result.market_slug, result.token_index, start_time, end_time)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "market_slug": result.market_slug,
                "token_index": result.token_index,
                "start_time": start_time,
                "end_time": end_time,
                "quotes": result.quotes,
                "records": result.records,
                "order_book_deltas": result.order_book_deltas,
            }
        )
    return entries


def _write_replays(path: Path, results: Sequence[PMXTCoverage]) -> list[dict[str, Any]]:
    entries = _replay_entries(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} replay window(s) to {path}")
    if not entries:
        print("No replay windows had quotes > 0; the written file is an empty list.")
    return entries


def _require_pmxt_window(args: argparse.Namespace) -> None:
    if args.write_replays and not (args.check_pmxt or args.scan_pmxt):
        raise SystemExit("--write-replays requires --check-pmxt or --scan-pmxt")
    if args.check_pmxt and (not args.start_time or not args.end_time):
        raise SystemExit("--check-pmxt requires --start-time and --end-time")
    if args.scan_pmxt:
        if not args.market and not args.event:
            raise SystemExit("--scan-pmxt requires --market or --event")
        if args.scan_start is None and args.start_time is not None:
            args.scan_start = args.start_time
        if args.scan_end is None and args.end_time is not None:
            args.scan_end = args.end_time
        if (args.scan_start is None) != (args.scan_end is None):
            raise SystemExit(
                "--scan-start and --scan-end must be provided together; "
                "omit both to auto-select a scan range"
            )


def _market_slugs(markets: Iterable[dict[str, Any]]) -> list[str]:
    return [str(market["slug"]) for market in markets if market.get("slug")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find Polymarket events/markets, inspect CLOB tokens, and optionally "
            "check PMXT L2 coverage for a UTC time window."
        )
    )
    parser.add_argument("--query", help="Keyword or phrase to search client-side.")
    parser.add_argument("--kind", choices=("events", "markets"), default="events")
    parser.add_argument("--event", help="Expand one Gamma event slug into market slugs.")
    parser.add_argument("--market", help="Inspect one market slug.")
    parser.add_argument("--active", action="store_true", help="Only request active/open items.")
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Do not add closed=false when searching.",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--tokens", action="store_true", help="Show CLOB Yes/No tokens.")
    parser.add_argument("--check-pmxt", action="store_true")
    parser.add_argument("--start-time", help="UTC ISO start time for --check-pmxt.")
    parser.add_argument("--end-time", help="UTC ISO end time for --check-pmxt.")
    parser.add_argument(
        "--scan-pmxt",
        action="store_true",
        help=(
            "Scan repeated PMXT windows. If --scan-start/--scan-end are omitted, "
            "a range is inferred from market dates."
        ),
    )
    parser.add_argument("--scan-start", help="Optional UTC ISO scan range start.")
    parser.add_argument("--scan-end", help="Optional UTC ISO scan range end.")
    parser.add_argument(
        "--scan-lookback-days",
        type=float,
        default=7.0,
        help="Auto scan lookback window in days. Default: 7.",
    )
    parser.add_argument(
        "--scan-delay-hours",
        type=float,
        default=3.0,
        help="For open markets, end auto scan at now minus this delay. Default: 3.",
    )
    parser.add_argument(
        "--scan-step-hours",
        type=float,
        default=6.0,
        help="Hours between candidate PMXT windows. Default: 6.",
    )
    parser.add_argument(
        "--window-minutes",
        type=float,
        default=10.0,
        help="Minutes per candidate PMXT window. Default: 10.",
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        default=28,
        help="Cap on candidate windows per market. Default: 28.",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="For --scan-pmxt, print empty windows too. By default only hits are shown.",
    )
    parser.add_argument(
        "--write-replays",
        type=Path,
        help=(
            "Write PMXT windows with quotes > 0 to a replay JSON file, e.g. "
            "backtests/private/replays.json."
        ),
    )
    parser.add_argument("--token-index", type=int, default=0)
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help=(
            "PMXT source in local:/ archive:/ relay: form. May be repeated. "
            "Defaults to local D:/Polyquant/data/pmxt_raws, r2v2 archive, then relay."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()
    _require_pmxt_window(args)

    output: dict[str, Any] = {}
    replay_candidates: list[PMXTCoverage] = []
    sources = tuple(args.sources or DEFAULT_PMXT_SOURCES)

    with httpx.Client(timeout=20) as client:
        if args.market:
            market = _get_market(client, args.market)
            tokens = (
                _tokens_from_market(client, market)
                if (args.tokens or args.check_pmxt or args.scan_pmxt)
                else []
            )
            output["market"] = _market_summary(market)
            output["tokens"] = tokens
            if not args.json:
                _print_market_detail(market, tokens)

            if args.check_pmxt:
                pmxt = asyncio.run(
                    _check_pmxt_many(
                        [str(market["slug"])],
                        token_index=args.token_index,
                        start_time=args.start_time,
                        end_time=args.end_time,
                        sources=sources,
                    )
                )
                output["pmxt"] = pmxt
                replay_candidates.extend(pmxt)
                if not args.json:
                    _print_pmxt(pmxt)

            if args.scan_pmxt:
                scan = asyncio.run(
                    _scan_pmxt_markets(
                        [market],
                        token_index=args.token_index,
                        scan_start=args.scan_start,
                        scan_end=args.scan_end,
                        scan_lookback_days=args.scan_lookback_days,
                        scan_delay_hours=args.scan_delay_hours,
                        scan_step_hours=args.scan_step_hours,
                        window_minutes=args.window_minutes,
                        max_windows=args.max_windows,
                        sources=sources,
                        only_hits=not args.scan_all,
                    )
                )
                output["pmxt_scan"] = scan
                replay_candidates.extend(scan)
                if not args.json:
                    _print_pmxt(scan)

        elif args.event:
            event = _get_event(client, args.event)
            markets = [m for m in event.get("markets") or [] if isinstance(m, dict)]
            output["event"] = _event_summary(event)
            output["markets"] = [_market_summary(market) for market in markets]
            if not args.json:
                print(f"EVENT: {event.get('slug')} | {event.get('title')}")
                _print_markets(markets)

            if args.tokens:
                token_map = {
                    str(market.get("slug")): _tokens_from_market(client, market)
                    for market in markets
                    if market.get("slug")
                }
                output["tokens"] = token_map

            if args.check_pmxt:
                pmxt = asyncio.run(
                    _check_pmxt_many(
                        _market_slugs(markets),
                        token_index=args.token_index,
                        start_time=args.start_time,
                        end_time=args.end_time,
                        sources=sources,
                    )
                )
                output["pmxt"] = pmxt
                replay_candidates.extend(pmxt)
                if not args.json:
                    _print_pmxt(pmxt)

            if args.scan_pmxt:
                scan = asyncio.run(
                    _scan_pmxt_markets(
                        markets,
                        token_index=args.token_index,
                        scan_start=args.scan_start,
                        scan_end=args.scan_end,
                        scan_lookback_days=args.scan_lookback_days,
                        scan_delay_hours=args.scan_delay_hours,
                        scan_step_hours=args.scan_step_hours,
                        window_minutes=args.window_minutes,
                        max_windows=args.max_windows,
                        sources=sources,
                        only_hits=not args.scan_all,
                    )
                )
                output["pmxt_scan"] = scan
                replay_candidates.extend(scan)
                if not args.json:
                    _print_pmxt(scan)

        else:
            items = _search_gamma(
                client,
                kind=args.kind,
                query=args.query,
                active=args.active,
                include_closed=args.include_closed,
                page_size=args.page_size,
                pages=args.pages,
                limit=max(1, args.limit),
            )
            output[args.kind] = [
                _event_summary(item) if args.kind == "events" else _market_summary(item)
                for item in items
            ]
            if not args.json:
                if args.kind == "events":
                    _print_events(items)
                else:
                    _print_markets(items)

    if args.write_replays:
        output["written_replays"] = _write_replays(args.write_replays, replay_candidates)

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
