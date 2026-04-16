from __future__ import annotations

import json
import math
import random
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from .config import ResearchConfig
from .models import MarketHistory, MarketSnapshot
from .snapshot_store import load_market_histories_from_dataset_root


def load_market_histories(config: ResearchConfig) -> list[MarketHistory]:
    if config.data_path:
        return load_market_histories_from_json(config.data_path)
    return generate_mock_market_histories(config)


def load_market_histories_from_json(path: Path) -> list[MarketHistory]:
    if path.is_dir():
        return load_market_histories_from_dataset_root(path)
    raw = json.loads(path.read_text())
    markets: list[MarketHistory] = []
    for market in raw:
        snapshots = [
            MarketSnapshot(
                timestamp=datetime.fromisoformat(snapshot["timestamp"]),
                yes_bid=float(snapshot["yes_bid"]),
                yes_ask=float(snapshot["yes_ask"]),
                no_bid=float(snapshot["no_bid"]),
                no_ask=float(snapshot["no_ask"]),
                volume=float(snapshot["volume"]),
                open_interest=float(snapshot["open_interest"]),
                seconds_to_resolution=int(snapshot["seconds_to_resolution"]),
            )
            for snapshot in market["snapshots"]
        ]
        markets.append(
            MarketHistory(
                market_id=market["market_id"],
                title=market["title"],
                category=market.get("category", "unknown"),
                platform=market.get("platform", "mock"),
                snapshots=snapshots,
            )
        )
    return markets


def generate_mock_market_histories(config: ResearchConfig) -> list[MarketHistory]:
    rng = random.Random(config.sample_data_seed)
    base_time = datetime(2026, 4, 1, 9, 0, 0)
    profiles = [
        ("KALSHI-CPI-MAY", "Will CPI print above consensus?", "macro", 0.52, 0.020, 220.0, 0.045),
        ("KALSHI-FED-JUNE", "Will the Fed hold in June?", "macro", 0.63, 0.013, 300.0, 0.032),
        ("KALSHI-BTC-WEEK", "Will BTC finish the week above 95k?", "crypto", 0.48, 0.026, 180.0, 0.055),
        ("KALSHI-NFP-MONTH", "Will payrolls beat estimate?", "macro", 0.58, 0.018, 260.0, 0.038),
        ("KALSHI-WEATHER-NYC", "Will NYC rainfall exceed 1 inch tomorrow?", "weather", 0.34, 0.031, 120.0, 0.070),
        ("KALSHI-POLITICS-APPROVAL", "Will approval end above 46%?", "politics", 0.45, 0.022, 160.0, 0.050),
    ]
    markets: list[MarketHistory] = []
    for market_id, title, category, anchor, noise_scale, volume_anchor, spread_anchor in profiles[: config.sample_market_count]:
        snapshots: list[MarketSnapshot] = []
        for index in range(config.snapshots_per_market):
            wave = math.sin(index / 4.5) * 0.06 + math.sin(index / 9.0) * 0.03
            shock = rng.gauss(0.0, noise_scale)
            mean_pull = (anchor - 0.5) * 0.10
            yes_mid = min(0.92, max(0.08, anchor + wave + shock + mean_pull))
            spread = max(0.01, spread_anchor + abs(rng.gauss(0.0, spread_anchor / 4)))
            yes_bid = max(0.01, yes_mid - spread / 2.0)
            yes_ask = min(0.99, yes_mid + spread / 2.0)
            no_mid = 1.0 - yes_mid + rng.gauss(0.0, 0.01)
            no_bid = max(0.01, min(0.99, no_mid - spread / 2.2))
            no_ask = max(no_bid + 0.01, min(0.99, no_mid + spread / 2.2))
            volume = max(10.0, volume_anchor + rng.gauss(0.0, volume_anchor * 0.22))
            open_interest = max(volume * 1.2, volume_anchor * 2 + rng.gauss(0.0, volume_anchor))
            seconds_to_resolution = max(600, (config.snapshots_per_market - index) * 3600)
            snapshots.append(
                MarketSnapshot(
                    timestamp=base_time + timedelta(hours=index),
                    yes_bid=round(yes_bid, 4),
                    yes_ask=round(yes_ask, 4),
                    no_bid=round(no_bid, 4),
                    no_ask=round(no_ask, 4),
                    volume=round(volume, 2),
                    open_interest=round(open_interest, 2),
                    seconds_to_resolution=seconds_to_resolution,
                )
            )
        markets.append(
            MarketHistory(
                market_id=market_id,
                title=title,
                category=category,
                platform="kalshi_mock",
                snapshots=snapshots,
            )
        )
    return markets


def export_market_histories_to_json(markets: list[MarketHistory], path: Path) -> None:
    payload = []
    for market in markets:
        payload.append(
            {
                "market_id": market.market_id,
                "title": market.title,
                "category": market.category,
                "platform": market.platform,
                "snapshots": [
                    {
                        **asdict(snapshot),
                        "timestamp": snapshot.timestamp.isoformat(),
                    }
                    for snapshot in market.snapshots
                ],
            }
        )
    path.write_text(json.dumps(payload, indent=2, default=str))


class KalshiDataSourcePlaceholder:
    """Reserved hook for later real Kalshi ingestion."""

    def fetch(self) -> list[MarketHistory]:
        raise NotImplementedError("Real Kalshi integration is intentionally deferred.")


class PolymarketDataSourcePlaceholder:
    """Reserved hook for later cross-platform comparison."""

    def fetch(self) -> list[MarketHistory]:
        raise NotImplementedError("Real Polymarket integration is intentionally deferred.")
