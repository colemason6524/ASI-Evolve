from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import (
    ForecastHistoryPoint,
    MarketHistory,
    MarketSnapshot,
    NormalizedSnapshot,
    SocialTradeRecord,
    WatchlistMarket,
)


DEFAULT_WATCHLIST = [
    WatchlistMarket(
        label="mlb-family",
        title="Professional baseball game family",
        category="sports",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxmlbgame/professional-baseball-game/kxmlbgame-26apr151840sfcin",
        family_code="kxmlbgame",
        priority=1,
        max_active_contracts=2,
        resolution_hours_min=1,
        resolution_hours_max=24,
        notes="Track 1-3 active MLB contracts with visible liquidity.",
    ),
    WatchlistMarket(
        label="atp-challenger-family",
        title="ATP challenger tennis family",
        category="sports",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxatpchallengermatch/challenger-atp-/kxatpchallengermatch-26apr15rybbos",
        family_code="kxatpchallengermatch",
        priority=2,
        max_active_contracts=2,
        resolution_hours_min=1,
        resolution_hours_max=24,
        notes="Tennis family for shorter event-driven markets.",
    ),
    WatchlistMarket(
        label="cs2-family",
        title="Counter-Strike 2 match family",
        category="esports",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxcs2game/counterstrike-2-game/kxcs2game-26apr151630mouzfuria",
        family_code="kxcs2game",
        priority=2,
        max_active_contracts=2,
        resolution_hours_min=1,
        resolution_hours_max=24,
        notes="Track active CS2 matches for fast-moving esports behavior.",
    ),
    WatchlistMarket(
        label="lol-family",
        title="League of Legends match family",
        category="esports",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxlolgame/league-of-legends-game/kxlolgame-26apr151700dsgsen",
        family_code="kxlolgame",
        priority=2,
        max_active_contracts=2,
        resolution_hours_min=1,
        resolution_hours_max=24,
        notes="Track active LoL contracts as a second esports comparison.",
    ),
    WatchlistMarket(
        label="artist-streams-family",
        title="Artist weekly streams family",
        category="entertainment",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxartiststreamsu/will-artist-have-more-streams-this-week/kxartiststreamsu-biebs26apr16",
        family_code="kxartiststreamsu",
        priority=3,
        max_active_contracts=2,
        resolution_hours_min=24,
        resolution_hours_max=168,
        notes="Entertainment family with medium-duration markets.",
    ),
    WatchlistMarket(
        label="btc-15m-family",
        title="Bitcoin 15-minute move family",
        category="crypto",
        selection_mode="family",
        market_url="https://kalshi.com/markets/kxbtc15m/bitcoin-price-up-down/kxbtc15m-26apr151830",
        family_code="kxbtc15m",
        priority=1,
        max_active_contracts=2,
        resolution_hours_min=0,
        resolution_hours_max=6,
        notes="High-frequency crypto family; useful for fast market comparison.",
    ),
    WatchlistMarket(
        label="powell-leaving",
        title="Will Powell leave the Fed before 2025 ends?",
        category="politics",
        market_url="https://kalshi.com/markets/kxleavepowell/powell-leaving/leavepowell-25",
        market_id="leavepowell-25",
        family_code="kxleavepowell",
        priority=1,
        resolution_hours_min=24,
        resolution_hours_max=6000,
        notes="Longer-lived macro-politics control market.",
    ),
    WatchlistMarket(
        label="aliens",
        title="Will aliens be publicly confirmed by 2027?",
        category="science_tech",
        market_url="https://kalshi.com/markets/kxaliens/aliens/kxaliens-27",
        market_id="kxaliens-27",
        family_code="kxaliens",
        priority=4,
        resolution_hours_min=24,
        resolution_hours_max=12000,
        notes="Very long-dated novelty science/tech control.",
    ),
    WatchlistMarket(
        label="a100-weekly",
        title="Will the A100 weekly price finish above threshold?",
        category="science_tech",
        market_url="https://kalshi.com/markets/kxa100w/a100-weekly-price/kxa100w-26apr17",
        market_id="kxa100w-26apr17",
        family_code="kxa100w",
        priority=3,
        resolution_hours_min=24,
        resolution_hours_max=168,
        notes="Weekly tech market with medium-duration resolution.",
    ),
    WatchlistMarket(
        label="nuclear-reactor-license",
        title="Will the US grant a license for a new nuclear reactor by 2026-12-31?",
        category="science_tech",
        market_url="https://kalshi.com/markets/kxreactor/us-grants-license-for-new-nuclear-reactor/kxreactor-26dec31",
        market_id="kxreactor-26dec31",
        family_code="kxreactor",
        priority=2,
        resolution_hours_min=24,
        resolution_hours_max=10000,
        notes="Long-duration policy/science market.",
    ),
    WatchlistMarket(
        label="psychedelic-fda-approval",
        title="Will the FDA approve a psychedelic treatment by 2027?",
        category="science_tech",
        market_url="https://kalshi.com/markets/kxfdaapprovalpsychedelic/fda-approval-psychedelic/kxfdaapprovalpsychedelic-27",
        market_id="kxfdaapprovalpsychedelic-27",
        family_code="kxfdaapprovalpsychedelic",
        priority=2,
        resolution_hours_min=24,
        resolution_hours_max=12000,
        notes="Long-duration FDA approval market.",
    ),
    WatchlistMarket(
        label="blue-origin-vs-spacex-moon",
        title="Will Blue Origin beat SpaceX to the moon by 2030?",
        category="science_tech",
        market_url="https://kalshi.com/markets/kxbluespacex/blue-origin-spacex-moon/kxbluespacex-30",
        market_id="kxbluespacex-30",
        family_code="kxbluespacex",
        priority=4,
        resolution_hours_min=24,
        resolution_hours_max=30000,
        notes="Very long-duration space race control market.",
    ),
    WatchlistMarket(
        label="virginia-redistricting",
        title="Will the Virginia redistricting referendum pass?",
        category="elections",
        market_url="https://kalshi.com/markets/kxvirginiaredistricting/will-the-virginia-redistricting-referendum-pass/kxvirginiaredistricting-26",
        market_id="kxvirginiaredistricting-26",
        family_code="kxvirginiaredistricting",
        priority=3,
        resolution_hours_min=24,
        resolution_hours_max=10000,
        notes="Election-style policy market.",
    ),
    WatchlistMarket(
        label="fisa-reauthorization",
        title="Will Congress reauthorize FISA before expiration?",
        category="politics",
        market_url="https://kalshi.com/markets/kxfisaextend/will-congress-reauthorize-fisa-before-it-expires/kxfisaextend-26mar",
        market_id="kxfisaextend-26mar",
        family_code="kxfisaextend",
        priority=1,
        resolution_hours_min=24,
        resolution_hours_max=5000,
        notes="Congressional process market with policy sensitivity.",
    ),
    WatchlistMarket(
        label="recession-nber",
        title="Will the NBER call a recession in 2026?",
        category="economics",
        market_url="https://kalshi.com/markets/kxrecssnber/recession/kxrecssnber-26",
        market_id="kxrecssnber-26",
        family_code="kxrecssnber",
        priority=1,
        resolution_hours_min=24,
        resolution_hours_max=10000,
        notes="Economics control market for slower-moving pricing.",
    ),
    WatchlistMarket(
        label="fed-emergency-meeting",
        title="Will the Fed hold an emergency meeting by 2027?",
        category="economics",
        market_url="https://kalshi.com/markets/kxfedmeet/fed-emergency-meeting/kxfedmeet-27",
        market_id="kxfedmeet-27",
        family_code="kxfedmeet",
        priority=1,
        resolution_hours_min=24,
        resolution_hours_max=12000,
        notes="Macro surprise event market.",
    ),
]


def ensure_storage_layout(dataset_root: Path) -> dict[str, Path]:
    raw_dir = dataset_root / "raw"
    normalized_dir = dataset_root / "normalized"
    forecast_dir = dataset_root / "forecast"
    trades_dir = dataset_root / "social_trades"
    scratch_dir = dataset_root / "scratch"
    for path in (dataset_root, raw_dir, normalized_dir, forecast_dir, trades_dir, scratch_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "dataset_root": dataset_root,
        "raw": raw_dir,
        "normalized": normalized_dir,
        "forecast": forecast_dir,
        "social_trades": trades_dir,
        "scratch": scratch_dir,
    }


def save_watchlist(path: Path, markets: list[WatchlistMarket]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"markets": [asdict(market) for market in markets]}
    path.write_text(json.dumps(payload, indent=2))


def load_watchlist(path: Path) -> list[WatchlistMarket]:
    raw = json.loads(path.read_text())
    markets = []
    for market in raw.get("markets", []):
        payload = {
            "label": market.get("label") or market.get("market_id") or market.get("family_code") or "unnamed-market",
            "title": market["title"],
            "category": market["category"],
            "selection_mode": market.get("selection_mode", "fixed"),
            "market_type": market.get("market_type", "binary"),
            "market_url": market.get("market_url", ""),
            "market_id": market.get("market_id"),
            "family_code": market.get("family_code"),
            "priority": int(market.get("priority", 3)),
            "max_active_contracts": int(market.get("max_active_contracts", 1)),
            "resolution_hours_min": market.get("resolution_hours_min"),
            "resolution_hours_max": market.get("resolution_hours_max"),
            "notes": market.get("notes", ""),
            "active": bool(market.get("active", True)),
        }
        markets.append(WatchlistMarket(**payload))
    return markets


def write_default_watchlist(path: Path) -> Path:
    save_watchlist(path, DEFAULT_WATCHLIST)
    return path


def write_manual_capture_template(path: Path, watchlist: list[WatchlistMarket]) -> Path:
    template = {
        "captured_at": datetime.utcnow().isoformat(),
        "snapshots": [
            {
                "platform": "kalshi",
                "market_id": market.market_id,
                "title": market.title,
                "category": market.category,
                "watchlist_label": market.label,
                "yes_bid": 0.0,
                "yes_ask": 0.0,
                "no_bid": 0.0,
                "no_ask": 0.0,
                "last_price": None,
                "volume": 0.0,
                "open_interest": 0.0,
                "seconds_to_resolution": 0,
                "status": "open",
            }
            for market in watchlist
            if market.active and market.selection_mode == "fixed" and market.market_id
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, indent=2))
    return path


def normalized_snapshot_from_dict(payload: dict) -> NormalizedSnapshot:
    return NormalizedSnapshot(
        timestamp=datetime.fromisoformat(payload["timestamp"]) if "timestamp" in payload else datetime.utcnow(),
        platform=payload.get("platform", "kalshi"),
        market_id=payload["market_id"],
        title=payload["title"],
        category=payload.get("category", "unknown"),
        yes_bid=float(payload["yes_bid"]),
        yes_ask=float(payload["yes_ask"]),
        no_bid=float(payload["no_bid"]),
        no_ask=float(payload["no_ask"]),
        last_price=float(payload["last_price"]) if payload.get("last_price") is not None else None,
        volume=float(payload.get("volume", 0.0)),
        open_interest=float(payload.get("open_interest", 0.0)),
        seconds_to_resolution=int(payload.get("seconds_to_resolution", 0)),
        status=payload.get("status", "open"),
    )


def append_snapshot(dataset_root: Path, snapshot: NormalizedSnapshot) -> Path:
    paths = ensure_storage_layout(dataset_root)
    day = snapshot.timestamp.date().isoformat()
    market_file = paths["normalized"] / day / f"{snapshot.market_id}.jsonl"
    market_file.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(snapshot)
    payload["timestamp"] = snapshot.timestamp.isoformat()
    with market_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return market_file


def append_snapshots(dataset_root: Path, snapshots: list[NormalizedSnapshot]) -> list[Path]:
    written: list[Path] = []
    for snapshot in snapshots:
        written.append(append_snapshot(dataset_root, snapshot))
    return written


def append_forecast_history_points(dataset_root: Path, points: list[ForecastHistoryPoint]) -> list[Path]:
    paths = ensure_storage_layout(dataset_root)
    written: list[Path] = []
    grouped: dict[str, list[ForecastHistoryPoint]] = {}
    for point in points:
        grouped.setdefault(point.market_ticker, []).append(point)
    for market_ticker, bucket in grouped.items():
        target = paths["forecast"] / f"{market_ticker}.jsonl"
        _append_unique_jsonl(
            target,
            [_forecast_point_to_payload(point) for point in bucket],
            lambda payload: f"{payload['market_id']}|{payload['end_time']}|{payload['period_interval']}",
        )
        written.append(target)
    return written


def append_social_trade_records(dataset_root: Path, trades: list[SocialTradeRecord]) -> list[Path]:
    paths = ensure_storage_layout(dataset_root)
    written: list[Path] = []
    grouped: dict[str, list[SocialTradeRecord]] = {}
    for trade in trades:
        grouped.setdefault(trade.market_ticker or trade.series_ticker, []).append(trade)
    for key, bucket in grouped.items():
        target = paths["social_trades"] / f"{key}.jsonl"
        _append_unique_jsonl(
            target,
            [_social_trade_to_payload(trade) for trade in bucket],
            lambda payload: payload["trade_id"],
        )
        written.append(target)
    return written


def ingest_manual_capture_file(dataset_root: Path, input_path: Path, captured_at: datetime | None = None) -> list[Path]:
    raw = json.loads(input_path.read_text())
    timestamp = captured_at or datetime.fromisoformat(raw["captured_at"])
    snapshots = []
    for item in raw.get("snapshots", []):
        payload = dict(item)
        payload["timestamp"] = payload.get("timestamp", timestamp.isoformat())
        snapshots.append(normalized_snapshot_from_dict(payload))
    return append_snapshots(dataset_root, snapshots)


def load_market_histories_from_dataset_root(dataset_root: Path) -> list[MarketHistory]:
    normalized_dir = dataset_root / "normalized"
    histories: dict[str, MarketHistory] = {}
    if not normalized_dir.exists():
        return []

    for jsonl_path in sorted(normalized_dir.rglob("*.jsonl")):
        for line in jsonl_path.read_text().splitlines():
            if not line.strip():
                continue
            snapshot = normalized_snapshot_from_dict(json.loads(line))
            history = histories.get(snapshot.market_id)
            market_snapshot = MarketSnapshot(
                timestamp=snapshot.timestamp,
                yes_bid=snapshot.yes_bid,
                yes_ask=snapshot.yes_ask,
                no_bid=snapshot.no_bid,
                no_ask=snapshot.no_ask,
                volume=snapshot.volume,
                open_interest=snapshot.open_interest,
                seconds_to_resolution=snapshot.seconds_to_resolution,
            )
            if history is None:
                histories[snapshot.market_id] = MarketHistory(
                    market_id=snapshot.market_id,
                    title=snapshot.title,
                    category=snapshot.category,
                    platform=snapshot.platform,
                    snapshots=[market_snapshot],
                )
            else:
                history.snapshots.append(market_snapshot)

    markets = list(histories.values())
    for market in markets:
        market.snapshots.sort(key=lambda item: item.timestamp)
    return markets


def summarize_dataset(dataset_root: Path) -> dict[str, int]:
    markets = load_market_histories_from_dataset_root(dataset_root)
    snapshot_count = sum(len(market.snapshots) for market in markets)
    active_days = {snapshot.timestamp.date().isoformat() for market in markets for snapshot in market.snapshots}
    forecast_point_count = _count_jsonl_rows(dataset_root / "forecast")
    social_trade_count = _count_jsonl_rows(dataset_root / "social_trades")
    return {
        "market_count": len(markets),
        "snapshot_count": snapshot_count,
        "active_day_count": len(active_days),
        "forecast_point_count": forecast_point_count,
        "social_trade_count": social_trade_count,
    }


def _forecast_point_to_payload(point: ForecastHistoryPoint) -> dict:
    payload = asdict(point)
    payload["end_time"] = point.end_time.isoformat()
    return payload


def _social_trade_to_payload(trade: SocialTradeRecord) -> dict:
    payload = asdict(trade)
    payload["trade_time"] = trade.trade_time.isoformat()
    return payload


def _append_unique_jsonl(path: Path, rows: list[dict], key_fn) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            seen.add(key_fn(payload))

    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            key = key_fn(row)
            if key in seen:
                continue
            seen.add(key)
            handle.write(json.dumps(row) + "\n")


def _count_jsonl_rows(root: Path) -> int:
    if not root.exists():
        return 0
    count = 0
    for jsonl_path in root.rglob("*.jsonl"):
        count += sum(1 for line in jsonl_path.read_text().splitlines() if line.strip())
    return count
