from __future__ import annotations

import statistics

from .config import FeeModel
from .models import MarketHistory, Position, SimulationMetrics, TradeRecord, StrategyParams
from .strategy import should_close_position, should_open_positions


def simulate_market(
    market: MarketHistory,
    params: StrategyParams,
    fees: FeeModel,
) -> tuple[SimulationMetrics, list[TradeRecord]]:
    open_positions: list[Position] = []
    trades: list[TradeRecord] = []
    realized_pnl: list[float] = []
    equity_curve = [0.0]
    warnings: list[str] = []

    for snapshot_index, snapshot in enumerate(market.snapshots):
        closable = [
            position
            for position in open_positions
            if should_close_position(market, snapshot_index, position, params)
        ]
        for position in closable:
            pnl = _close_position(snapshot, position, fees)
            realized_pnl.append(pnl)
            trades.append(
                TradeRecord(
                    market_id=market.market_id,
                    side=position.side,
                    entry_time=position.entry_time,
                    exit_time=snapshot.timestamp,
                    pnl=pnl,
                    hold_steps=snapshot_index - position.entry_index,
                    entry_reason=position.reason,
                )
            )
            open_positions.remove(position)
            equity_curve.append(equity_curve[-1] + pnl)

        if snapshot.seconds_to_resolution <= 1800:
            continue

        ideas = should_open_positions(market, snapshot_index, params)
        if ideas and len(open_positions) >= 4:
            warnings.append("Position cap reached; some signals were ignored.")
            ideas = []

        for side, reason in ideas:
            if reason == "pseudo_arb_pair" and any(
                position.reason == "pseudo_arb_pair" and position.entry_index == snapshot_index
                for position in open_positions
            ):
                if side == "no":
                    open_positions.append(_open_position(market.market_id, side, snapshot_index, snapshot, reason, fees))
                continue
            if reason == "mean_reversion" and any(position.side == side for position in open_positions):
                continue
            open_positions.append(_open_position(market.market_id, side, snapshot_index, snapshot, reason, fees))

    final_snapshot = market.snapshots[-1]
    for position in list(open_positions):
        pnl = _close_position(final_snapshot, position, fees)
        realized_pnl.append(pnl)
        trades.append(
            TradeRecord(
                market_id=market.market_id,
                side=position.side,
                entry_time=position.entry_time,
                exit_time=final_snapshot.timestamp,
                pnl=pnl,
                hold_steps=max(0, len(market.snapshots) - 1 - position.entry_index),
                entry_reason=position.reason,
            )
        )
        open_positions.remove(position)
        equity_curve.append(equity_curve[-1] + pnl)

    if not trades:
        warnings.append("No trades fired under the selected parameters.")

    metrics = SimulationMetrics(
        total_profit=sum(realized_pnl),
        number_of_trades=len(trades),
        win_rate=(sum(1 for pnl in realized_pnl if pnl > 0) / len(realized_pnl)) if realized_pnl else 0.0,
        max_drawdown=_max_drawdown(equity_curve),
        profit_variance=statistics.pvariance(realized_pnl) if len(realized_pnl) > 1 else 0.0,
        average_hold_time=(sum(trade.hold_steps for trade in trades) / len(trades)) if trades else 0.0,
        equity_curve=equity_curve,
        warnings=_dedupe_warnings(warnings),
    )
    return metrics, trades


def _open_position(
    market_id: str,
    side: str,
    snapshot_index: int,
    snapshot,
    reason: str,
    fees: FeeModel,
) -> Position:
    raw_price = snapshot.yes_ask if side == "yes" else snapshot.no_ask
    entry_price = raw_price + _slippage(raw_price, fees.slippage_bps)
    return Position(
        market_id=market_id,
        side=side,
        entry_index=snapshot_index,
        entry_time=snapshot.timestamp,
        entry_price=entry_price + fees.per_contract,
        quantity=1,
        reason=reason,
    )


def _close_position(snapshot, position: Position, fees: FeeModel) -> float:
    raw_exit = snapshot.yes_bid if position.side == "yes" else snapshot.no_bid
    exit_price = max(0.0, raw_exit - _slippage(raw_exit, fees.slippage_bps))
    net_exit = max(0.0, exit_price - fees.per_contract)
    return round((net_exit - position.entry_price) * position.quantity, 6)


def _slippage(price: float, bps: float) -> float:
    return price * (bps / 10000.0)


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        max_drawdown = max(max_drawdown, peak - value)
    return max_drawdown


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            unique.append(warning)
    return unique
