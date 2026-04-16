from __future__ import annotations

import itertools

from .config import ResearchConfig
from .models import MarketHistory, Position, StrategyParams


def generate_strategy_params(config: ResearchConfig) -> list[StrategyParams]:
    search = config.search
    combinations = itertools.product(
        search.entry_spread_thresholds,
        search.exit_spread_thresholds,
        search.max_hold_times,
        search.min_volume_filters,
        search.price_bands,
        search.mean_reversion_modes,
        search.pseudo_arb_modes,
    )
    params: list[StrategyParams] = []
    for entry_spread, exit_spread, max_hold, min_volume, band, mean_reversion, pseudo_arb in combinations:
        if exit_spread >= entry_spread:
            continue
        params.append(
            StrategyParams(
                entry_spread_threshold=entry_spread,
                exit_spread_threshold=exit_spread,
                max_hold_time=max_hold,
                min_volume_filter=min_volume,
                price_band_low=band[0],
                price_band_high=band[1],
                use_mean_reversion=mean_reversion,
                use_pseudo_arb=pseudo_arb,
            )
        )
        if len(params) >= search.max_combinations:
            break
    return params


def should_open_positions(
    market: MarketHistory,
    snapshot_index: int,
    params: StrategyParams,
) -> list[tuple[str, str]]:
    snapshot = market.snapshots[snapshot_index]
    if snapshot.volume < params.min_volume_filter:
        return []
    if not (params.price_band_low <= snapshot.yes_mid <= params.price_band_high):
        return []
    if snapshot.spread > params.entry_spread_threshold:
        return []

    ideas: list[tuple[str, str]] = []
    if params.use_mean_reversion:
        signal = _mean_reversion_signal(market, snapshot_index)
        if signal == "buy_yes":
            ideas.append(("yes", "mean_reversion"))
        elif signal == "buy_no":
            ideas.append(("no", "mean_reversion"))
    if params.use_pseudo_arb and snapshot.two_sided_cost < 0.985:
        ideas.append(("yes", "pseudo_arb_pair"))
        ideas.append(("no", "pseudo_arb_pair"))
    return ideas


def should_close_position(
    market: MarketHistory,
    snapshot_index: int,
    position: Position,
    params: StrategyParams,
) -> bool:
    snapshot = market.snapshots[snapshot_index]
    held_steps = snapshot_index - position.entry_index
    if held_steps >= params.max_hold_time:
        return True
    if snapshot.spread <= params.exit_spread_threshold:
        return True
    current_exit_price = snapshot.yes_bid if position.side == "yes" else snapshot.no_bid
    if current_exit_price >= position.entry_price + params.exit_spread_threshold:
        return True
    if position.reason == "mean_reversion":
        reversal = _mean_reversion_signal(market, snapshot_index)
        if position.side == "yes" and reversal == "buy_no":
            return True
        if position.side == "no" and reversal == "buy_yes":
            return True
    if position.reason == "pseudo_arb_pair" and snapshot.two_sided_cost >= 0.995:
        return True
    return False


def _mean_reversion_signal(market: MarketHistory, snapshot_index: int) -> str | None:
    if snapshot_index < 3:
        return None
    recent = [market.snapshots[index].yes_mid for index in range(snapshot_index - 3, snapshot_index + 1)]
    latest = recent[-1]
    baseline = sum(recent[:-1]) / len(recent[:-1])
    delta = latest - baseline
    if delta <= -0.03:
        return "buy_yes"
    if delta >= 0.03:
        return "buy_no"
    return None
