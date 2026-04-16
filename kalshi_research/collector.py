from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .models import ForecastHistoryPoint, NormalizedSnapshot, SocialTradeRecord, WatchlistMarket
from .snapshot_store import (
    append_forecast_history_points,
    append_snapshots,
    append_social_trade_records,
    ensure_storage_layout,
    load_watchlist,
)


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
PUBLIC_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
PUBLIC_EVENT_API_BASE = "https://api.elections.kalshi.com/v1"


@dataclass
class ResolvedWatchMarket:
    watchlist_label: str
    category: str
    title: str
    market_url: str
    market_id: str
    market_ticker: str
    event_ticker: str
    series_ticker: str
    selection_mode: str
    family_code: Optional[str]
    notes: str = ""


@dataclass
class CollectionResult:
    collected_count: int
    resolved_count: int
    forecast_point_count: int
    social_trade_count: int
    failures: list[str]
    rate_limited: bool = False


class KalshiCollector:
    def __init__(self, dataset_root: Path, watchlist_path: Path, timeout_seconds: int = 20) -> None:
        self.dataset_root = dataset_root
        self.watchlist_path = watchlist_path
        self.timeout_seconds = timeout_seconds
        self.paths = ensure_storage_layout(dataset_root)
        self.logs_dir = dataset_root / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.forecast_lookback_days = 30

    def collect_once(self) -> CollectionResult:
        watchlist = [market for market in load_watchlist(self.watchlist_path) if market.active]
        resolved_markets: list[ResolvedWatchMarket] = []
        failures: list[str] = []
        rate_limited = False
        snapshots: list[NormalizedSnapshot] = []
        forecast_points: list[ForecastHistoryPoint] = []
        social_trades: list[SocialTradeRecord] = []

        for market in watchlist:
            try:
                resolved_batch, snapshot_batch = self.resolve_market(market)
                resolved_markets.extend(resolved_batch)
                snapshots.extend(snapshot_batch)
                for resolved in resolved_batch:
                    try:
                        social_batch = self.fetch_social_trades(resolved)
                        social_trades.extend(social_batch)
                        enriched_market_id = self._market_id_from_social_trades(social_batch, resolved.market_ticker)
                        if enriched_market_id:
                            resolved.market_id = enriched_market_id
                    except Exception as exc:
                        failures.append(f"social:{resolved.watchlist_label}:{exc}")
                        self._log_event("social_error", resolved.watchlist_label, {"error": str(exc)})
                    try:
                        forecast_points.extend(self.fetch_forecast_history(resolved))
                    except Exception as exc:
                        failures.append(f"forecast:{resolved.watchlist_label}:{exc}")
                        self._log_event("forecast_error", resolved.watchlist_label, {"error": str(exc)})
            except Exception as exc:
                failures.append(f"resolve:{market.label}:{exc}")
                self._log_event("resolve_error", market.label, {"error": str(exc)})

        for failure in failures:
            if "HTTP 429" in failure:
                rate_limited = True

        if snapshots:
            append_snapshots(self.dataset_root, snapshots)
        if forecast_points:
            append_forecast_history_points(self.dataset_root, forecast_points)
        if social_trades:
            append_social_trade_records(self.dataset_root, social_trades)

        return CollectionResult(
            collected_count=len(snapshots),
            resolved_count=len(resolved_markets),
            forecast_point_count=len(forecast_points),
            social_trade_count=len(social_trades),
            failures=failures,
            rate_limited=rate_limited,
        )

    def run_loop(self, interval_seconds: int, max_cycles: Optional[int] = None) -> None:
        cycles = 0
        while True:
            cycles += 1
            result = self.collect_once()
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"resolved={result.resolved_count} collected={result.collected_count} "
                f"forecast_points={result.forecast_point_count} social_trades={result.social_trade_count} "
                f"failures={len(result.failures)} rate_limited={result.rate_limited}"
            )
            for failure in result.failures[:10]:
                print(f"  - {failure}")
            if max_cycles is not None and cycles >= max_cycles:
                break
            sleep_seconds = interval_seconds * (2 if result.rate_limited else 1)
            time.sleep(sleep_seconds)

    def resolve_market(self, market: WatchlistMarket) -> tuple[list[ResolvedWatchMarket], list[NormalizedSnapshot]]:
        if market.selection_mode not in {"fixed", "family"}:
            raise ValueError(f"Unsupported selection mode: {market.selection_mode}")

        try:
            api_markets = self.fetch_markets_v2(market)
            selected = self.select_markets(api_markets, market)
            snapshots = [self.snapshot_from_market_v2(item, market) for item in selected]
            resolved = [
                ResolvedWatchMarket(
                    watchlist_label=market.label,
                    category=market.category,
                    title=item.get("title") or market.title,
                    market_url=market.market_url,
                    market_id=item.get("id") or item.get("ticker"),
                    market_ticker=item["ticker"],
                    event_ticker=item.get("event_ticker") or self.derive_event_ticker(market),
                    series_ticker=item.get("series_ticker") or self.derive_series_ticker(market),
                    selection_mode=market.selection_mode,
                    family_code=market.family_code,
                    notes=market.notes,
                )
                for item in selected
            ]
            if selected:
                self._write_raw_json(
                    f"{market.label}-markets",
                    {"markets": selected},
                    snapshots[0].timestamp,
                )
            return resolved, snapshots
        except HTTPError as exc:
            self._log_event("fetch_http_error", market.label, {"code": exc.code, "url": market.market_url})
            if exc.code != 429:
                raise
            return self.resolve_market_from_bootstrap_fallback(market, exc)
        except URLError as exc:
            self._log_event("fetch_url_error", market.label, {"error": str(exc.reason), "url": market.market_url})
            return self.resolve_market_from_bootstrap_fallback(market, exc)

    def resolve_market_from_bootstrap_fallback(
        self,
        market: WatchlistMarket,
        original_error: Exception,
    ) -> tuple[list[ResolvedWatchMarket], list[NormalizedSnapshot]]:
        try:
            html = self.fetch_text(market.market_url)
            bootstrap = self.extract_bootstrap_market_data(html)
            snapshots = self.snapshots_from_bootstrap_market_data(market, bootstrap)
            resolved = [
                ResolvedWatchMarket(
                    watchlist_label=market.label,
                    category=market.category,
                    title=snapshot.title,
                    market_url=market.market_url,
                    market_id=snapshot.market_id,
                    market_ticker=entry["ticker_name"],
                    event_ticker=entry["event_ticker"],
                    series_ticker=entry["series_ticker"],
                    selection_mode=market.selection_mode,
                    family_code=market.family_code,
                    notes=market.notes,
                )
                for snapshot, entry in snapshots
            ]
            output_snapshots = [snapshot for snapshot, _entry in snapshots]
            if output_snapshots:
                self._write_raw_html(output_snapshots[0].market_id, html, output_snapshots[0].timestamp)
            return resolved, output_snapshots
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} after API fallback from {type(original_error).__name__}") from exc
        except Exception as exc:
            raise RuntimeError(f"{type(original_error).__name__}; bootstrap fallback failed: {exc}") from exc

    def fetch_markets_v2(self, market: WatchlistMarket) -> list[dict[str, Any]]:
        if market.selection_mode == "fixed":
            direct_market = self.fetch_market_v2(self.derive_event_ticker(market))
            if direct_market is not None:
                return [direct_market]

        base_params: dict[str, Any] = {
            "status": "open",
            "limit": max(5, market.max_active_contracts * 5),
        }
        query_params: list[dict[str, Any]] = []
        if market.selection_mode == "family":
            query_params.append({**base_params, "series_ticker": self.derive_series_ticker(market)})
        else:
            event_ticker = self.derive_event_ticker(market)
            series_ticker = self.derive_series_ticker(market)
            query_params.append({**base_params, "event_ticker": event_ticker})
            if series_ticker and series_ticker != event_ticker:
                query_params.append({**base_params, "series_ticker": series_ticker})

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for params in query_params:
            payload = self.fetch_json(f"{PUBLIC_API_BASE}/markets", params=params)
            for item in payload.get("markets", []):
                key = str(item.get("ticker") or item.get("id") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    def fetch_market_v2(self, market_ticker: str) -> Optional[dict[str, Any]]:
        try:
            payload = self.fetch_json(f"{PUBLIC_API_BASE}/markets/{market_ticker}")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        market = payload.get("market")
        if isinstance(market, dict):
            return market
        if isinstance(payload, dict) and payload.get("ticker"):
            return payload
        return None

    def select_markets(self, markets: list[dict[str, Any]], watchlist: WatchlistMarket) -> list[dict[str, Any]]:
        if watchlist.selection_mode == "fixed":
            exact_matches = self._match_fixed_markets(markets, watchlist)
            if exact_matches:
                markets = exact_matches

        filtered = []
        for market in markets:
            status = str(market.get("status", "")).lower()
            if status and status not in {"open", "active", "initialized"}:
                continue
            close_ts = self._extract_close_ts(market)
            if close_ts is not None:
                hours_to_close = max(0.0, (close_ts - time.time()) / 3600.0)
                if watchlist.resolution_hours_min is not None and hours_to_close < watchlist.resolution_hours_min:
                    continue
                if watchlist.resolution_hours_max is not None and hours_to_close > watchlist.resolution_hours_max:
                    continue
            filtered.append(market)
        filtered.sort(
            key=lambda item: (
                -float(item.get("volume", item.get("volume_fp", 0.0)) or 0.0),
                -float(item.get("open_interest", item.get("open_interest_fp", 0.0)) or 0.0),
            )
        )
        return filtered[: watchlist.max_active_contracts]

    def snapshot_from_market_v2(self, market: dict[str, Any], watchlist: WatchlistMarket) -> NormalizedSnapshot:
        timestamp = datetime.now(timezone.utc).astimezone()
        yes_bid = self._coerce_price(
            market.get("yes_bid_dollars", market.get("yes_bid", market.get("yes_price")))
        )
        yes_ask = self._coerce_price(
            market.get("yes_ask_dollars", market.get("yes_ask"))
        )
        last_price = self._coerce_price(
            market.get("last_price_dollars", market.get("last_price"))
        )
        if yes_bid is None and last_price is not None:
            yes_bid = last_price
        if yes_ask is None and last_price is not None:
            yes_ask = last_price
        if yes_bid is None or yes_ask is None:
            yes_bid, yes_ask = self.fetch_orderbook_top(market["ticker"])
        inferred_no_bid, inferred_no_ask = self._infer_no_quotes(yes_bid, yes_ask)
        return NormalizedSnapshot(
            timestamp=timestamp,
            platform="kalshi",
            market_id=str(market.get("id", market["ticker"])),
            title=str(market.get("title") or watchlist.title),
            category=watchlist.category,
            yes_bid=round(yes_bid, 4),
            yes_ask=round(yes_ask, 4),
            no_bid=round(inferred_no_bid, 4),
            no_ask=round(inferred_no_ask, 4),
            last_price=round(last_price, 4) if last_price is not None else None,
            volume=float(market.get("volume_fp", market.get("volume", 0.0)) or 0.0),
            open_interest=float(market.get("open_interest_fp", market.get("open_interest", 0.0)) or 0.0),
            seconds_to_resolution=self._seconds_to_resolution(
                str(market.get("close_time") or market.get("close_date") or ""),
                timestamp,
            ),
            status=str(market.get("status", "open")).lower(),
        )

    def fetch_orderbook_top(self, market_ticker: str) -> tuple[float, float]:
        payload = self.fetch_json(f"{PUBLIC_API_BASE}/markets/{market_ticker}/orderbook")
        orderbook = payload.get("orderbook", {})
        yes_levels = orderbook.get("yes", [])
        no_levels = orderbook.get("no", [])
        yes_bid = self._orderbook_best_bid(yes_levels)
        no_bid = self._orderbook_best_bid(no_levels)
        if yes_bid is None and no_bid is None:
            raise ValueError(f"Orderbook missing yes/no bids for {market_ticker}")
        yes_bid = yes_bid if yes_bid is not None else max(0.0, 1.0 - no_bid)
        no_bid = no_bid if no_bid is not None else max(0.0, 1.0 - yes_bid)
        yes_ask = min(1.0, max(yes_bid, 1.0 - no_bid))
        return yes_bid, yes_ask

    def fetch_forecast_history(self, market: ResolvedWatchMarket) -> list[ForecastHistoryPoint]:
        if not self._is_uuid_like(market.market_id):
            resolved_market_id = self.resolve_market_uuid_from_bootstrap(market)
            if resolved_market_id:
                market.market_id = resolved_market_id
        if not self._is_uuid_like(market.market_id):
            raise ValueError(f"Missing UUID market id for forecast history: {market.market_ticker}")

        period_seconds = 60 * 60
        end_ts = int(time.time())
        end_ts -= end_ts % period_seconds
        start_ts = end_ts - (self.forecast_lookback_days * 24 * period_seconds)
        payload = self.fetch_json(
            f"{PUBLIC_EVENT_API_BASE}/series/{market.series_ticker}/markets/{market.market_id}/forecast_history",
            params={
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 60,
            },
        )
        items = payload.get("forecast_history", [])
        if items:
            self._write_raw_json(f"{market.market_ticker}-forecast-history", payload, datetime.now(timezone.utc).astimezone())
        points: list[ForecastHistoryPoint] = []
        for item in items:
            end_period_ts = item.get("end_period_ts")
            if end_period_ts is None:
                continue
            forecast = item.get("numerical_forecast")
            if forecast is None:
                continue
            points.append(
                ForecastHistoryPoint(
                    series_ticker=market.series_ticker,
                    event_ticker=str(item.get("event_ticker") or market.event_ticker),
                    market_ticker=str(item.get("market_ticker") or market.market_ticker),
                    market_id=market.market_id,
                    end_time=datetime.fromtimestamp(int(end_period_ts), tz=timezone.utc).astimezone(),
                    period_interval=int(item.get("period_interval", 60) or 60),
                    numerical_forecast=float(forecast),
                    raw_numerical_forecast=float(item["raw_numerical_forecast"]) if item.get("raw_numerical_forecast") is not None else None,
                    formatted_forecast=item.get("formatted_forecast"),
                )
            )
        return points

    def fetch_social_trades(self, market: ResolvedWatchMarket) -> list[SocialTradeRecord]:
        payload = self.fetch_json(
            f"{PUBLIC_EVENT_API_BASE}/social/trades",
            params={"series_ticker": market.series_ticker},
        )
        raw_trades = payload.get("trades", payload.get("social_trades", payload.get("data", [])))
        if raw_trades:
            self._write_raw_json(f"{market.series_ticker}-social-trades", payload, datetime.now(timezone.utc).astimezone())
        market_candidates = {market.market_ticker.upper(), market.event_ticker.upper()}
        records: list[SocialTradeRecord] = []
        for item in raw_trades:
            item_market_ticker = str(
                item.get("market_ticker")
                or item.get("ticker")
                or item.get("event_ticker")
                or market.market_ticker
            )
            if item_market_ticker.upper() not in market_candidates and market.selection_mode == "fixed":
                continue
            trade_time = self._parse_trade_time(item)
            if trade_time is None:
                continue
            trade_id = str(
                item.get("trade_id")
                or item.get("id")
                or item.get("created_at")
                or item.get("timestamp")
                or f"{item_market_ticker}-{trade_time.isoformat()}"
            )
            records.append(
                SocialTradeRecord(
                    series_ticker=market.series_ticker,
                    market_ticker=item_market_ticker,
                    market_id=str(item.get("market_id") or market.market_id),
                    event_ticker=item.get("event_ticker") or market.event_ticker,
                    trade_time=trade_time,
                    trade_id=trade_id,
                    side=item.get("side"),
                    yes_price=self._coerce_price(item.get("yes_price")),
                    no_price=self._coerce_price(item.get("no_price")),
                    count=float(item.get("count")) if item.get("count") is not None else None,
                    payload=item,
                )
            )
        return records

    def resolve_market_uuid_from_bootstrap(self, market: ResolvedWatchMarket) -> Optional[str]:
        try:
            html = self.fetch_text(market.market_url)
            bootstrap = self.extract_bootstrap_market_data(html)
        except Exception:
            return None
        for event in bootstrap.get("events", []):
            for item in event.get("markets", []):
                ticker_name = str(item.get("ticker_name") or "").upper()
                event_ticker = str(event.get("ticker") or "").upper()
                if ticker_name == market.market_ticker.upper() or event_ticker == market.event_ticker.upper():
                    market_id = item.get("id")
                    if market_id:
                        return str(market_id)
        return None

    def fetch_text(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://kalshi.com/",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read().decode("utf-8", "replace")

    def fetch_json(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://kalshi.com/",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8", "replace"))

    def extract_contract_urls(self, html: str, family_url: str, family_code: str) -> list[str]:
        candidates: list[str] = []
        pattern = re.compile(r'href=["\'](?P<href>/markets/[^"\']+)["\']')
        for match in pattern.finditer(html):
            href = match.group("href")
            if family_code and family_code not in href:
                continue
            if href.count("/") < 4:
                continue
            candidates.append(urljoin("https://kalshi.com", href))

        unique: list[str] = []
        seen: set[str] = set()
        for url in candidates:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    def parse_market_snapshot(self, market: ResolvedWatchMarket, html: str) -> NormalizedSnapshot:
        payload = self.extract_embedded_json(html)
        parsed_title = self._first_text(payload, ["title", "subtitle", "marketTitle"]) or market.title
        yes_bid = self._first_number(payload, ["yes_bid", "yesBid", "bid", "bestBidYes", "best_yes_bid"])
        yes_ask = self._first_number(payload, ["yes_ask", "yesAsk", "ask", "bestAskYes", "best_yes_ask"])
        no_bid = self._first_number(payload, ["no_bid", "noBid", "bestBidNo", "best_no_bid"])
        no_ask = self._first_number(payload, ["no_ask", "noAsk", "bestAskNo", "best_no_ask"])

        if yes_bid is None or yes_ask is None:
            raise ValueError("Failed to parse yes bid/ask from market page")

        inferred_no_bid, inferred_no_ask = self._infer_no_quotes(yes_bid, yes_ask)
        no_bid = no_bid if no_bid is not None else inferred_no_bid
        no_ask = no_ask if no_ask is not None else inferred_no_ask

        timestamp = datetime.now(timezone.utc).astimezone()
        last_price = self._first_number(payload, ["last_price", "lastPrice", "last_trade_price", "lastTradedPrice"])
        volume = self._first_number(payload, ["volume", "volume24h", "tradedVolume", "contractVolume"]) or 0.0
        open_interest = self._first_number(payload, ["open_interest", "openInterest"]) or 0.0
        close_time_text = self._first_text(payload, ["closeTime", "expirationTime", "endDate", "settlement_date"])
        seconds_to_resolution = self._seconds_to_resolution(close_time_text, timestamp)
        status = self._first_text(payload, ["status"]) or "open"

        return NormalizedSnapshot(
            timestamp=timestamp,
            platform="kalshi",
            market_id=market.market_id,
            title=parsed_title,
            category=market.category,
            yes_bid=round(yes_bid, 4),
            yes_ask=round(yes_ask, 4),
            no_bid=round(no_bid, 4),
            no_ask=round(no_ask, 4),
            last_price=round(last_price, 4) if last_price is not None else None,
            volume=round(volume, 4),
            open_interest=round(open_interest, 4),
            seconds_to_resolution=seconds_to_resolution,
            status=status,
        )

    def extract_bootstrap_market_data(self, html: str) -> dict[str, Any]:
        marker = 'hydrationData":{"market":'
        index = html.find(marker)
        if index < 0:
            raise ValueError("Could not find hydrationData.market in page source")
        start = index + len(marker)
        market_payload, _ = self._extract_braced_json(html, start)
        return json.loads(market_payload)

    def snapshots_from_bootstrap_market_data(
        self,
        watchlist: WatchlistMarket,
        market_data: dict[str, Any],
    ) -> list[tuple[NormalizedSnapshot, dict[str, Any]]]:
        timestamp = datetime.now(timezone.utc).astimezone()
        snapshots: list[tuple[NormalizedSnapshot, dict[str, Any]]] = []
        for event in market_data.get("events", []):
            for item in event.get("markets", []):
                yes_bid = self._coerce_price(item.get("yes_bid_dollars", item.get("yes_bid")))
                yes_ask = self._coerce_price(item.get("yes_ask_dollars", item.get("yes_ask")))
                last_price = self._coerce_price(item.get("last_price_dollars", item.get("last_price")))
                if yes_bid is None or yes_ask is None:
                    continue
                no_bid, no_ask = self._infer_no_quotes(yes_bid, yes_ask)
                snapshot = NormalizedSnapshot(
                    timestamp=timestamp,
                    platform="kalshi",
                    market_id=str(item["id"]),
                    title=str(event.get("title") or item.get("title") or watchlist.title),
                    category=watchlist.category,
                    yes_bid=round(yes_bid, 4),
                    yes_ask=round(yes_ask, 4),
                    no_bid=round(no_bid, 4),
                    no_ask=round(no_ask, 4),
                    last_price=round(last_price, 4) if last_price is not None else None,
                    volume=float(item.get("volume_fp", item.get("volume", 0.0)) or 0.0),
                    open_interest=float(item.get("open_interest_fp", item.get("open_interest", 0.0)) or 0.0),
                    seconds_to_resolution=self._seconds_to_resolution(
                        str(item.get("close_date") or item.get("expected_expiration_date") or ""),
                        timestamp,
                    ),
                    status=str(item.get("status", "open")).lower(),
                )
                snapshots.append(
                    (
                        snapshot,
                        {
                            "ticker_name": item.get("ticker_name", watchlist.label),
                            "event_ticker": event.get("ticker") or watchlist.label,
                            "series_ticker": event.get("series_ticker") or self.derive_series_ticker(watchlist),
                        },
                    )
                )
        return snapshots[: watchlist.max_active_contracts]

    def extract_embedded_json(self, html: str) -> Any:
        patterns = [
            r'<script id="__NEXT_DATA__" type="application/json">\s*(.*?)\s*</script>',
            r"<script id='__NEXT_DATA__' type='application/json'>\s*(.*?)\s*</script>",
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                return json.loads(match.group(1))

        push_matches = re.findall(r"self\.__next_f\.push\((.*?)\);", html, re.DOTALL)
        if push_matches:
            return {"next_f_push": push_matches}

        raise ValueError("Could not find embedded JSON payload on page")

    def _first_number(self, payload: Any, keys: Iterable[str]) -> Optional[float]:
        value = self._find_first(payload, set(keys))
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            number_match = re.search(r"-?\d+(?:\.\d+)?", value)
            if number_match:
                value = float(number_match.group(0))
            else:
                return None
        if value > 1.0 and value <= 100.0:
            return value / 100.0
        return float(value)

    def _first_text(self, payload: Any, keys: Iterable[str]) -> Optional[str]:
        value = self._find_first(payload, set(keys))
        if value is None:
            return None
        return str(value)

    def _find_first(self, payload: Any, keys: set[str]) -> Any:
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, value in current.items():
                    if key in keys:
                        return value
                    stack.append(value)
            elif isinstance(current, list):
                stack.extend(current)
            elif isinstance(current, str):
                continue
        return None

    def _infer_no_quotes(self, yes_bid: float, yes_ask: float) -> tuple[float, float]:
        return max(0.0, round(1.0 - yes_ask, 4)), min(1.0, round(1.0 - yes_bid, 4))

    def _coerce_price(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, str):
            number_match = re.search(r"-?\d+(?:\.\d+)?", value)
            if not number_match:
                return None
            value = float(number_match.group(0))
        elif isinstance(value, (int, float)):
            value = float(value)
        else:
            return None
        if value > 1.0 and value <= 100.0:
            return round(value / 100.0, 6)
        return round(value, 6)

    def _orderbook_best_bid(self, levels: Any) -> Optional[float]:
        if not isinstance(levels, list) or not levels:
            return None
        first = levels[0]
        if isinstance(first, dict):
            return self._coerce_price(first.get("price"))
        if isinstance(first, list) and first:
            return self._coerce_price(first[0])
        return None

    def derive_series_ticker(self, market: WatchlistMarket) -> str:
        if market.family_code:
            return market.family_code.upper()
        if market.market_id:
            return market.market_id.upper()
        return self._market_id_from_url(market.market_url).upper()

    def _match_fixed_markets(
        self,
        markets: list[dict[str, Any]],
        watchlist: WatchlistMarket,
    ) -> list[dict[str, Any]]:
        candidates = self._candidate_tickers(watchlist)
        if not candidates:
            return []

        matched: list[dict[str, Any]] = []
        for market in markets:
            market_ticker = str(market.get("ticker", "")).upper()
            event_ticker = str(market.get("event_ticker", "")).upper()
            if market_ticker in candidates or event_ticker in candidates:
                matched.append(market)
        return matched

    def _candidate_tickers(self, market: WatchlistMarket) -> set[str]:
        candidates: set[str] = set()
        if market.market_id:
            candidates.add(market.market_id.upper())
        if market.market_url:
            candidates.add(self._market_id_from_url(market.market_url).upper())
        return candidates

    def derive_event_ticker(self, market: WatchlistMarket) -> str:
        if market.market_id:
            return market.market_id.upper()
        return self._market_id_from_url(market.market_url).upper()

    def _extract_close_ts(self, market: dict[str, Any]) -> Optional[float]:
        close_time = market.get("close_time") or market.get("close_date")
        if close_time:
            parsed = self._parse_datetime(str(close_time))
            if parsed:
                return parsed.timestamp()
        close_ts = market.get("close_ts")
        if close_ts is None:
            return None
        return float(close_ts)

    def _extract_braced_json(self, text: str, start: int) -> tuple[str, int]:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1], index + 1
        raise ValueError("Failed to extract braced JSON payload")

    def _seconds_to_resolution(self, close_time_text: Optional[str], timestamp: datetime) -> int:
        if not close_time_text:
            return 0
        parsed = self._parse_datetime(close_time_text)
        if parsed is None:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timestamp.tzinfo)
        return max(0, int((parsed - timestamp).total_seconds()))

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        candidates = [value, value.replace("Z", "+00:00")]
        for candidate in candidates:
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _parse_trade_time(self, payload: dict[str, Any]) -> Optional[datetime]:
        for key in ("create_date", "created_at", "createdAt", "timestamp", "time"):
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone()
            parsed = self._parse_datetime(str(value))
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone()
        return None

    def _market_id_from_social_trades(
        self,
        trades: list[SocialTradeRecord],
        market_ticker: str,
    ) -> Optional[str]:
        for trade in trades:
            if trade.market_ticker.upper() == market_ticker.upper() and self._is_uuid_like(trade.market_id):
                return trade.market_id
        return None

    def _is_uuid_like(self, value: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", value))

    def _family_url(self, market_url: str) -> str:
        parsed = urlparse(market_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 3:
            family_path = "/" + "/".join(parts[:3])
            return f"{parsed.scheme}://{parsed.netloc}{family_path}"
        return market_url

    def _market_id_from_url(self, market_url: str) -> str:
        parts = [part for part in urlparse(market_url).path.split("/") if part]
        if not parts:
            raise ValueError(f"Could not derive market id from url: {market_url}")
        return parts[-1]

    def _write_raw_html(self, market_id: str, html: str, timestamp: datetime) -> None:
        day_dir = self.paths["raw"] / timestamp.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        target = day_dir / f"{market_id}.html"
        target.write_text(html)

    def _write_raw_json(self, stem: str, payload: dict[str, Any], timestamp: datetime) -> None:
        day_dir = self.paths["raw"] / timestamp.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        target = day_dir / f"{stem}.json"
        target.write_text(json.dumps(payload, indent=2, default=str))

    def _log_event(self, event_type: str, key: str, payload: dict[str, Any]) -> None:
        line = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "key": key,
            **payload,
        }
        log_path = self.logs_dir / f"collector-{datetime.now().date().isoformat()}.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
