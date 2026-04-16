from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .config import ResearchConfig, default_config
from .data_loader import load_market_histories
from .market_filter import rank_markets
from .models import StrategyEvaluation
from .scoring import score_strategy
from .simulator import simulate_market
from .snapshot_store import (
    ensure_storage_layout,
    ingest_manual_capture_file,
    load_watchlist,
    summarize_dataset,
    write_default_watchlist,
    write_manual_capture_template,
)
from .collector import KalshiCollector
from .strategy import generate_strategy_params


def run_research(config: ResearchConfig) -> list[StrategyEvaluation]:
    markets = load_market_histories(config)
    ranked_markets = rank_markets(markets)
    top_market_ids = {item.market_id for item in ranked_markets[: config.top_market_count]}
    selected_markets = [market for market in markets if market.market_id in top_market_ids]
    params_grid = generate_strategy_params(config)

    evaluations: list[StrategyEvaluation] = []
    for market in selected_markets:
        for params in params_grid:
            metrics, _ = simulate_market(market, params, config.fees)
            score = score_strategy(metrics, config.score_weights)
            evaluations.append(
                StrategyEvaluation(
                    market_id=market.market_id,
                    market_title=market.title,
                    params=params,
                    metrics=metrics,
                    score=score,
                )
            )
    print_report(ranked_markets, evaluations)
    return evaluations


def print_report(ranked_markets, evaluations: list[StrategyEvaluation]) -> None:
    print("=== Research Restatement ===")
    print(
        "Build a small local framework that ranks binary markets, paper-trades a risk-first "
        "strategy template, and helps decide whether the arbitrage/mean-reversion idea is viable."
    )

    print("\n=== Weak Assumptions To Pressure-Test ===")
    print("- Buying both sides is only attractive when total cost, fees, slippage, and exit realism all line up.")
    print("- High volatility is not automatically good if it arrives with wide spreads or poor liquidity.")
    print("- A historical mid-price reversal does not guarantee a tradable fill at bid/ask.")
    print("- Markets pinned near 0 or 1 may look low-risk but often have poor upside for short-horizon trading.")
    print("- Mocked results can validate framework logic, but not execution quality or true exchange microstructure.")

    print("\n=== Lean Architecture ===")
    print("- data_loader: loads JSON later or generates deterministic mock markets now.")
    print("- market_filter: ranks markets by volatility, reversals, spread, liquidity, and fill realism.")
    print("- strategy: defines parameter combinations plus entry and exit rules.")
    print("- simulator: paper-trades one market with fees and slippage.")
    print("- scoring: turns performance into a configurable risk-first score.")
    print("- main: runs ranking, bounded parameter search, and prints conclusions.")

    print("\n=== Top Candidate Markets ===")
    for item in ranked_markets[:5]:
        notes = f" Notes: {'; '.join(item.notes)}" if item.notes else ""
        print(
            f"- {item.market_id}: rank={item.rank_score:.3f}, vol={item.volatility:.4f}, "
            f"spread={item.average_spread:.4f}, volume={item.average_volume:.1f}, "
            f"reversal={item.reversal_rate:.2%}, fill={item.realistic_fill_rate:.2%}.{notes}"
        )

    best_overall = sorted(evaluations, key=lambda item: item.score, reverse=True)[:5]
    best_active = [item for item in sorted(evaluations, key=lambda item: item.score, reverse=True) if item.metrics.number_of_trades > 0][:5]

    print("\n=== Best Active Parameter Combinations ===")
    for result in best_active:
        params = result.params
        metrics = result.metrics
        print(
            f"- {result.market_id} | score={result.score:.4f} | profit={metrics.total_profit:.4f} | "
            f"drawdown={metrics.max_drawdown:.4f} | variance={metrics.profit_variance:.5f} | "
            f"win_rate={metrics.win_rate:.2%} | trades={metrics.number_of_trades} | "
            f"entry_spread={params.entry_spread_threshold:.3f} | exit_spread={params.exit_spread_threshold:.3f} | "
            f"hold={params.max_hold_time} | min_volume={params.min_volume_filter:.0f} | "
            f"band=({params.price_band_low:.2f},{params.price_band_high:.2f}) | "
            f"mean_reversion={params.use_mean_reversion} | pseudo_arb={params.use_pseudo_arb}"
        )
    if not best_active:
        print("- No traded strategies cleared the entry rules under current assumptions.")

    print("\n=== Best Overall Configurations ===")
    for result in best_overall:
        params = result.params
        metrics = result.metrics
        print(
            f"- {result.market_id} | score={result.score:.4f} | profit={metrics.total_profit:.4f} | "
            f"drawdown={metrics.max_drawdown:.4f} | variance={metrics.profit_variance:.5f} | "
            f"win_rate={metrics.win_rate:.2%} | trades={metrics.number_of_trades} | "
            f"entry_spread={params.entry_spread_threshold:.3f} | exit_spread={params.exit_spread_threshold:.3f} | "
            f"hold={params.max_hold_time} | min_volume={params.min_volume_filter:.0f} | "
            f"band=({params.price_band_low:.2f},{params.price_band_high:.2f}) | "
            f"mean_reversion={params.use_mean_reversion} | pseudo_arb={params.use_pseudo_arb}"
        )

    print("\n=== Scoring Breakdown ===")
    if best_overall:
        top = best_overall[0]
        metrics = top.metrics
        print(
            "score = "
            f"{metrics.total_profit:.4f}"
            f" - 3.0*{metrics.max_drawdown:.4f}"
            f" - 1.8*{metrics.profit_variance:.5f}"
            f" + 0.5*{metrics.win_rate:.4f}"
            f" - inactivity_penalty({1 if metrics.number_of_trades == 0 else 0}*0.25)"
            f" = {top.score:.4f}"
        )

    print("\n=== Warnings And Limitations ===")
    warnings = {
        "Results use mocked data unless a JSON path is supplied.",
        "Slippage, fees, and volume are simplified heuristics rather than exchange-verified fills.",
        "Pseudo-arbitrage here is mark-to-market logic, not guaranteed risk-free settlement capture.",
        "No live orders, no exchange auth, and no account execution are implemented.",
        "Cross-platform discrepancy analysis is intentionally left as a placeholder.",
    }
    for evaluation in (best_active[:3] or best_overall[:3]):
        warnings.update(evaluation.metrics.warnings)
    for warning in sorted(warnings):
        print(f"- {warning}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lightweight Kalshi-style market research prototype")
    subparsers = parser.add_subparsers(dest="command")

    research_parser = subparsers.add_parser("research", help="Run ranking and paper-trading research")
    research_parser.add_argument("--data-path", type=str, default=None, help="Optional JSON file or dataset directory")
    research_parser.add_argument("--top-markets", type=int, default=4, help="How many markets to keep after ranking")
    research_parser.add_argument("--sample-markets", type=int, default=6, help="Mock market count when no data path is supplied")
    research_parser.add_argument("--snapshots", type=int, default=72, help="Snapshots per mock market")

    init_parser = subparsers.add_parser("init-watchlist", help="Create the initial Kalshi watchlist and folder layout")
    init_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")
    init_parser.add_argument("--watchlist-path", type=str, default="data/kalshi/watchlist.json", help="Watchlist JSON path")

    template_parser = subparsers.add_parser("capture-template", help="Write a manual capture template for the current watchlist")
    template_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")
    template_parser.add_argument("--watchlist-path", type=str, default="data/kalshi/watchlist.json", help="Watchlist JSON path")
    template_parser.add_argument("--output", type=str, default="data/kalshi/scratch/manual_capture_template.json", help="Template output path")

    ingest_parser = subparsers.add_parser("ingest-manual", help="Ingest a manual capture JSON file into normalized JSONL storage")
    ingest_parser.add_argument("input_path", type=str, help="Path to a filled-in manual capture JSON file")
    ingest_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")

    summary_parser = subparsers.add_parser("dataset-summary", help="Show how much normalized market data has been collected")
    summary_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")

    collect_once_parser = subparsers.add_parser("collect-once", help="Fetch one snapshot cycle for the Kalshi watchlist")
    collect_once_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")
    collect_once_parser.add_argument("--watchlist-path", type=str, default="data/kalshi/watchlist.json", help="Watchlist JSON path")

    collect_loop_parser = subparsers.add_parser("collect-loop", help="Run the Kalshi collector on a timed loop")
    collect_loop_parser.add_argument("--dataset-root", type=str, default="data/kalshi", help="Dataset root directory")
    collect_loop_parser.add_argument("--watchlist-path", type=str, default="data/kalshi/watchlist.json", help="Watchlist JSON path")
    collect_loop_parser.add_argument("--interval-seconds", type=int, default=60, help="Polling interval in seconds")
    collect_loop_parser.add_argument("--max-cycles", type=int, default=None, help="Optional cap on collection cycles for testing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "init-watchlist":
        dataset_root = Path(args.dataset_root)
        watchlist_path = Path(args.watchlist_path)
        ensure_storage_layout(dataset_root)
        write_default_watchlist(watchlist_path)
        print(f"Initialized dataset layout at {dataset_root}")
        print(f"Wrote watchlist to {watchlist_path}")
        return

    if args.command == "capture-template":
        dataset_root = Path(args.dataset_root)
        watchlist_path = Path(args.watchlist_path)
        ensure_storage_layout(dataset_root)
        if not watchlist_path.exists():
            write_default_watchlist(watchlist_path)
        watchlist = load_watchlist(watchlist_path)
        output_path = write_manual_capture_template(Path(args.output), watchlist)
        print(f"Wrote manual capture template to {output_path}")
        print("Fill in the quotes and re-ingest it with the ingest-manual command.")
        return

    if args.command == "ingest-manual":
        dataset_root = Path(args.dataset_root)
        ensure_storage_layout(dataset_root)
        written = ingest_manual_capture_file(dataset_root, Path(args.input_path))
        print(f"Ingested manual capture into {len(set(written))} market file(s).")
        return

    if args.command == "dataset-summary":
        dataset_root = Path(args.dataset_root)
        summary = summarize_dataset(dataset_root)
        print("=== Dataset Summary ===")
        for key, value in summary.items():
            print(f"{key}: {value}")
        return

    if args.command == "collect-once":
        collector = KalshiCollector(Path(args.dataset_root), Path(args.watchlist_path))
        result = collector.collect_once()
        print("=== Collection Result ===")
        print(f"resolved_count: {result.resolved_count}")
        print(f"collected_count: {result.collected_count}")
        print(f"forecast_point_count: {result.forecast_point_count}")
        print(f"social_trade_count: {result.social_trade_count}")
        print(f"rate_limited: {result.rate_limited}")
        for failure in result.failures:
            print(f"- {failure}")
        return

    if args.command == "collect-loop":
        collector = KalshiCollector(Path(args.dataset_root), Path(args.watchlist_path))
        collector.run_loop(args.interval_seconds, args.max_cycles)
        return

    config = default_config()
    config = replace(
        config,
        data_path=getattr(args, "data_path", None) and Path(args.data_path),
        top_market_count=getattr(args, "top_markets", config.top_market_count),
        sample_market_count=getattr(args, "sample_markets", config.sample_market_count),
        snapshots_per_market=getattr(args, "snapshots", config.snapshots_per_market),
    )
    run_research(config)


if __name__ == "__main__":
    main()
