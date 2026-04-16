from __future__ import annotations

import statistics

from .models import MarketHistory, MarketSuitability


def rank_markets(markets: list[MarketHistory]) -> list[MarketSuitability]:
    ranked: list[MarketSuitability] = []
    for market in markets:
        ranked.append(evaluate_market_suitability(market))
    return sorted(ranked, key=lambda item: item.rank_score, reverse=True)


def evaluate_market_suitability(market: MarketHistory) -> MarketSuitability:
    mids = [snapshot.yes_mid for snapshot in market.snapshots]
    spreads = [snapshot.spread for snapshot in market.snapshots]
    volumes = [snapshot.volume for snapshot in market.snapshots]
    returns = [mids[index] - mids[index - 1] for index in range(1, len(mids))]

    volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    average_spread = statistics.fmean(spreads) if spreads else 0.0
    average_volume = statistics.fmean(volumes) if volumes else 0.0
    reversal_rate = _reversal_rate(returns)
    centered_price_rate = _centered_price_rate(mids)
    realistic_fill_rate = _realistic_fill_rate(spreads, volumes)

    notes: list[str] = []
    if volatility < 0.01:
        notes.append("Low short-term volatility may limit mean-reversion entries.")
    if average_spread > 0.09:
        notes.append("Wide spreads may overwhelm edge after fees and slippage.")
    if average_volume < 100:
        notes.append("Thin volume may make fills unrealistic.")
    if centered_price_rate < 0.35:
        notes.append("Prices spend too much time near extremes.")

    rank_score = (
        (volatility * 5.0)
        + (reversal_rate * 2.5)
        + (centered_price_rate * 1.5)
        + min(average_volume / 250.0, 1.5)
        + realistic_fill_rate
        - (average_spread * 6.0)
    )
    return MarketSuitability(
        market_id=market.market_id,
        title=market.title,
        rank_score=rank_score,
        volatility=volatility,
        average_spread=average_spread,
        average_volume=average_volume,
        reversal_rate=reversal_rate,
        centered_price_rate=centered_price_rate,
        realistic_fill_rate=realistic_fill_rate,
        notes=notes,
    )


def _reversal_rate(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    reversals = 0
    comparisons = 0
    for previous, current in zip(returns, returns[1:]):
        if abs(previous) < 1e-6 or abs(current) < 1e-6:
            continue
        comparisons += 1
        if previous * current < 0:
            reversals += 1
    return reversals / comparisons if comparisons else 0.0


def _centered_price_rate(mids: list[float], low: float = 0.15, high: float = 0.85) -> float:
    if not mids:
        return 0.0
    centered = sum(1 for mid in mids if low <= mid <= high)
    return centered / len(mids)


def _realistic_fill_rate(spreads: list[float], volumes: list[float]) -> float:
    if not spreads or not volumes:
        return 0.0
    valid = 0
    for spread, volume in zip(spreads, volumes):
        if spread <= 0.08 and volume >= 100:
            valid += 1
    return valid / len(spreads)
