from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class WatchlistMarket:
    label: str
    title: str
    category: str
    selection_mode: str = "fixed"
    market_type: str = "binary"
    market_url: str = ""
    market_id: Optional[str] = None
    family_code: Optional[str] = None
    priority: int = 3
    max_active_contracts: int = 1
    resolution_hours_min: Optional[int] = None
    resolution_hours_max: Optional[int] = None
    notes: str = ""
    active: bool = True


@dataclass
class NormalizedSnapshot:
    timestamp: datetime
    platform: str
    market_id: str
    title: str
    category: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    last_price: Optional[float]
    volume: float
    open_interest: float
    seconds_to_resolution: int
    status: str = "open"


@dataclass
class ForecastHistoryPoint:
    series_ticker: str
    event_ticker: str
    market_ticker: str
    market_id: str
    end_time: datetime
    period_interval: int
    numerical_forecast: float
    raw_numerical_forecast: Optional[float] = None
    formatted_forecast: Optional[str] = None


@dataclass
class SocialTradeRecord:
    series_ticker: str
    market_ticker: str
    market_id: str
    event_ticker: Optional[str]
    trade_time: datetime
    trade_id: str
    side: Optional[str] = None
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    count: Optional[float] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketSnapshot:
    timestamp: datetime
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    volume: float
    open_interest: float
    seconds_to_resolution: int

    @property
    def yes_mid(self) -> float:
        return (self.yes_bid + self.yes_ask) / 2.0

    @property
    def spread(self) -> float:
        return max(0.0, self.yes_ask - self.yes_bid)

    @property
    def two_sided_cost(self) -> float:
        return self.yes_ask + self.no_ask


@dataclass
class MarketHistory:
    market_id: str
    title: str
    category: str
    platform: str
    snapshots: list[MarketSnapshot]


@dataclass
class MarketSuitability:
    market_id: str
    title: str
    rank_score: float
    volatility: float
    average_spread: float
    average_volume: float
    reversal_rate: float
    centered_price_rate: float
    realistic_fill_rate: float
    notes: list[str] = field(default_factory=list)


@dataclass
class StrategyParams:
    entry_spread_threshold: float
    exit_spread_threshold: float
    max_hold_time: int
    min_volume_filter: float
    price_band_low: float
    price_band_high: float
    use_mean_reversion: bool
    use_pseudo_arb: bool


@dataclass
class Position:
    market_id: str
    side: str
    entry_index: int
    entry_time: datetime
    entry_price: float
    quantity: int
    reason: str


@dataclass
class TradeRecord:
    market_id: str
    side: str
    entry_time: datetime
    exit_time: datetime
    pnl: float
    hold_steps: int
    entry_reason: str


@dataclass
class SimulationMetrics:
    total_profit: float
    number_of_trades: int
    win_rate: float
    max_drawdown: float
    profit_variance: float
    average_hold_time: float
    equity_curve: list[float]
    warnings: list[str] = field(default_factory=list)


@dataclass
class StrategyEvaluation:
    market_id: str
    market_title: str
    params: StrategyParams
    metrics: SimulationMetrics
    score: float
