from __future__ import annotations

from .config import ScoreWeights
from .models import SimulationMetrics


def score_strategy(metrics: SimulationMetrics, weights: ScoreWeights) -> float:
    score = (
        (metrics.total_profit * weights.profit)
        - (metrics.max_drawdown * weights.drawdown_penalty)
        - (metrics.profit_variance * weights.variance_penalty)
        + (metrics.win_rate * weights.win_rate_bonus)
    )
    if metrics.number_of_trades == 0:
        score -= weights.inactivity_penalty
    return score
