from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FeeModel:
    per_contract: float = 0.01
    slippage_bps: float = 25.0


@dataclass
class StrategySearchSpace:
    entry_spread_thresholds: list[float] = field(default_factory=lambda: [0.04, 0.06, 0.08])
    exit_spread_thresholds: list[float] = field(default_factory=lambda: [0.02, 0.03, 0.05])
    max_hold_times: list[int] = field(default_factory=lambda: [3, 6, 12])
    min_volume_filters: list[float] = field(default_factory=lambda: [80.0, 150.0, 250.0])
    price_bands: list[tuple[float, float]] = field(
        default_factory=lambda: [(0.15, 0.85), (0.20, 0.80), (0.25, 0.75)]
    )
    mean_reversion_modes: list[bool] = field(default_factory=lambda: [True, False])
    pseudo_arb_modes: list[bool] = field(default_factory=lambda: [False, True])
    max_combinations: int = 72


@dataclass
class ScoreWeights:
    profit: float = 1.0
    drawdown_penalty: float = 3.0
    variance_penalty: float = 1.8
    win_rate_bonus: float = 0.5
    inactivity_penalty: float = 0.25


@dataclass
class ResearchConfig:
    sample_data_seed: int = 7
    sample_market_count: int = 6
    snapshots_per_market: int = 72
    top_market_count: int = 4
    dataset_root: Path = Path("data/kalshi")
    watchlist_path: Path = Path("data/kalshi/watchlist.json")
    collector_interval_seconds: int = 60
    search: StrategySearchSpace = field(default_factory=StrategySearchSpace)
    fees: FeeModel = field(default_factory=FeeModel)
    score_weights: ScoreWeights = field(default_factory=ScoreWeights)
    data_path: Path | None = None


def default_config() -> ResearchConfig:
    return ResearchConfig()
