"""Command-line interface for the Mean Reversion strategy.

Usage (run from the trading/ root):
    mean_reversion\\venv\\Scripts\\python.exe -m mean_reversion.cli signals
    mean_reversion\\venv\\Scripts\\python.exe -m mean_reversion.cli backtest
    mean_reversion\\venv\\Scripts\\python.exe -m mean_reversion.cli paper
    mean_reversion\\venv\\Scripts\\python.exe -m mean_reversion.cli positions
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_TRADING_ROOT = Path(__file__).resolve().parents[1]
_RISK_BACKEND = _TRADING_ROOT / "risk_calculator" / "backend"
if str(_RISK_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RISK_BACKEND))
if str(_TRADING_ROOT) not in sys.path:
    sys.path.insert(0, str(_TRADING_ROOT))

log = logging.getLogger(__name__)


# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_signals(args) -> None:
    """Print current BUY/SELL/HOLD signals for all (or one) ticker."""
    from app.services.market_data import fetch_ohlcv
    from mean_reversion.config import MeanReversionConfig
    from mean_reversion.signals.generator import generate_signal

    cfg = MeanReversionConfig()
    tickers = [args.ticker.upper()] if args.ticker else cfg.tickers

    results = []
    for ticker in tickers:
        try:
            ohlc = fetch_ohlcv(ticker, cfg.lookback_days)
            sig = generate_signal(ticker, ohlc, cfg)
            results.append(
                {
                    "ticker": sig.ticker,
                    "date": sig.date,
                    "action": sig.action,
                    "zscore": round(sig.zscore, 3),
                    "filtered_strength": round(sig.filtered_strength, 3),
                    "reason": sig.reason,
                    "rsi": round(sig.rsi_value, 1) if sig.rsi_value is not None else None,
                    "adx": round(sig.adx_value, 1) if sig.adx_value is not None else None,
                    "sentiment": sig.sentiment,
                    "sentiment_confidence": (
                        round(sig.sentiment_confidence, 3)
                        if sig.sentiment_confidence is not None else None
                    ),
                    "risk_score": (
                        round(sig.risk_score, 2) if sig.risk_score is not None else None
                    ),
                    "atr_stop": (
                        round(sig.atr_stop, 2) if sig.atr_stop is not None else None
                    ),
                }
            )
        except Exception as exc:
            log.error("Error generating signal for %s: %s", ticker, exc)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print(
        f"\n{'TICKER':<8} {'ACTION':<6} {'Z-SCORE':>8} {'RSI':>6} {'ADX':>6} "
        f"{'SENTIMENT':<12} {'RISK':>6}  REASON"
    )
    print("-" * 100)
    for r in results:
        print(
            f"{r['ticker']:<8} {r['action']:<6} {r['zscore']:>+8.3f} "
            f"{str(r['rsi'] or 'N/A'):>6} {str(r['adx'] or 'N/A'):>6} "
            f"{str(r['sentiment'] or 'N/A'):<12} {str(r['risk_score'] or 'N/A'):>6}  "
            f"{r['reason'][:45]}"
        )


def cmd_backtest(args) -> None:
    """Run a full historical backtest and print results."""
    from app.services.market_data import fetch_ohlcv, fetch_risk_free_rate_annual
    from mean_reversion.config import MeanReversionConfig
    from mean_reversion.backtest.engine import run_backtest

    cfg = MeanReversionConfig()
    if args.bb_period:
        cfg.bollinger.period = args.bb_period
    if args.bb_std:
        cfg.bollinger.std_dev = args.bb_std
    if args.entry_zscore is not None:
        cfg.bollinger.entry_zscore = args.entry_zscore
    if args.exit_zscore is not None:
        cfg.bollinger.exit_zscore = args.exit_zscore
    if args.capital:
        cfg.backtest.initial_capital = args.capital

    tickers = [args.ticker.upper()] if args.ticker else cfg.tickers

    print("Loading price data...")
    ticker_ohlc = {}
    for ticker in tickers:
        try:
            ticker_ohlc[ticker] = fetch_ohlcv(ticker, cfg.lookback_days)
            print(f"  {ticker}: {len(ticker_ohlc[ticker])} rows")
        except Exception as exc:
            print(f"  {ticker}: FAILED — {exc}")

    benchmark_names = [cfg.backtest.benchmark_ticker] + list(ticker_ohlc.keys())
    benchmark_ohlc = {}
    for b in benchmark_names:
        if b not in benchmark_ohlc:
            try:
                benchmark_ohlc[b] = fetch_ohlcv(b, cfg.lookback_days)
            except Exception as exc:
                log.warning("Benchmark %s failed: %s", b, exc)

    try:
        rf = fetch_risk_free_rate_annual()
    except Exception:
        rf = 0.04

    print(
        f"\nRunning backtest | BB({cfg.bollinger.period},{cfg.bollinger.std_dev}) "
        f"| entry_z={cfg.bollinger.entry_zscore} exit_z={cfg.bollinger.exit_zscore}"
        f" | capital=${cfg.backtest.initial_capital:,.0f}\n"
    )
    summary = run_backtest(
        cfg=cfg,
        ticker_ohlc=ticker_ohlc,
        benchmark_ohlc=benchmark_ohlc,
        rf_annual=rf,
        start_date=args.start,
        end_date=args.end,
    )

    if args.json:
        output = {}
        for ticker, result in summary.results.items():
            output[ticker] = result.metrics
        if summary.portfolio_metrics:
            output["_portfolio"] = summary.portfolio_metrics
        print(json.dumps(output, indent=2, default=str))
        return

    def _fmt(v, decimals=2):
        if v is None or abs(v) > 9999:
            return "N/A"
        return f"{v:.{decimals}f}"

    bench = cfg.backtest.benchmark_ticker.lower()
    print(
        f"{'TICKER':<10} {'RETURN%':>8} {'CAGR%':>7} {'SHARPE':>7} {'CALMAR':>7} "
        f"{'MAX_DD%':>8} {'PF':>6} {'AVG_HOLD':>9} {'TRADES':>7} {'WIN%':>6}"
    )
    print("-" * 80)

    rows = list(summary.results.items())
    if summary.portfolio_metrics:
        rows.append(("PORTFOLIO", type("R", (), {"metrics": summary.portfolio_metrics})()))

    for ticker, result in rows:
        m = result.metrics
        hold_str = f"{m.get('avg_holding_days') or 0:.0f}d"
        print(
            f"{ticker:<10} {m['total_return_pct']:>8.1f} {m['cagr_pct']:>7.1f} "
            f"{_fmt(m.get('sharpe')):>7} {_fmt(m.get('calmar')):>7} "
            f"{m['max_drawdown_pct']:>8.1f} {_fmt(m.get('profit_factor')):>6} "
            f"{hold_str:>9} "
            f"{m['total_trades']:>7} {m['win_rate_pct']:>6.1f}"
        )


def cmd_paper(args) -> None:
    """Run paper trading — process today's signals and update positions."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from mean_reversion.paper_trading.tracker import run_paper_trading
    from mean_reversion.config import MeanReversionConfig

    cfg = MeanReversionConfig()
    actions = run_paper_trading(cfg)

    if args.json:
        print(json.dumps(actions, indent=2, default=str))
        return

    print("\n=== MEAN REVERSION PAPER TRADING ACTIONS ===")
    for a in actions:
        tag = f"[{a['action_taken']}]" if a["action_taken"] != "HOLD" else "[ -- ]"
        pnl_str = f"  P&L=${a['pnl']:.2f}" if a.get("pnl") is not None else ""
        price_str = f"@ ${a['price']:.2f}" if a.get("price") else ""
        z_str = f"  z={a['zscore']:+.2f}" if a.get("zscore") is not None else ""
        print(
            f"  {tag} {a['ticker']:<6}  {a['shares']:>5} shares {price_str}{z_str}{pnl_str}"
            f"  | {a['reason'][:50]}"
        )


def cmd_positions(args) -> None:
    """Show current open paper positions with mark-to-market P&L."""
    from app.services.market_data import fetch_ohlcv
    from mean_reversion.paper_trading import db as paper_db
    from mean_reversion.config import MeanReversionConfig

    cfg = MeanReversionConfig()
    positions = paper_db.get_positions()

    if not positions:
        print("No open mean reversion paper positions.")
        return

    current_prices = {}
    for pos in positions:
        try:
            ohlc = fetch_ohlcv(pos["ticker"], 5)
            current_prices[pos["ticker"]] = float(ohlc["Close"].iloc[-1])
        except Exception:
            current_prices[pos["ticker"]] = pos["avg_cost"]

    pv = paper_db.get_portfolio_snapshot(current_prices)

    if args.json:
        print(json.dumps(pv, indent=2))
        return

    print(
        f"\n{'TICKER':<8} {'SHARES':>6} {'AVG_COST':>10} {'CUR_PRICE':>10} "
        f"{'MKT_VAL':>10} {'UNREAL_PNL':>12} {'PNL%':>7} {'ENTRY_Z':>8} {'STOP':>8}"
    )
    print("-" * 85)
    for p in pv["positions"]:
        entry_z = p.get("entry_zscore")
        atr_stop = p.get("atr_stop")
        print(
            f"{p['ticker']:<8} {p['shares']:>6} {p['avg_cost']:>10.2f} "
            f"{p['current_price']:>10.2f} {p['market_value']:>10.2f} "
            f"{p['unrealised_pnl']:>+12.2f} {p['unrealised_pnl_pct']:>+6.1f}% "
            f"{f'{entry_z:+.2f}' if entry_z is not None else 'N/A':>8} "
            f"{f'{atr_stop:.2f}' if atr_stop is not None else 'N/A':>8}"
        )
    print("-" * 85)
    print(f"  Total market value : ${pv['total_market_value']:>12,.2f}")
    print(f"  Total cost basis   : ${pv['total_cost_basis']:>12,.2f}")
    print(f"  Unrealised P&L     : ${pv['total_unrealised_pnl']:>+12,.2f}  "
          f"({pv['total_unrealised_pnl_pct']:>+.1f}%)")

    recent = paper_db.get_trades(limit=10)
    if recent:
        print(f"\n  Recent trades (last {len(recent)}):")
        for t in recent:
            pnl_str = f"  P&L=${t['pnl']:.2f}" if t.get("pnl") is not None else ""
            z_str = f"  z={t['zscore']:+.2f}" if t.get("zscore") is not None else ""
            print(
                f"    [{t['action']}] {t['ticker']} {t['shares']} @ ${t['price']:.2f}"
                f"{z_str}  {t['executed_at'][:10]}{pnl_str}"
            )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mean Reversion strategy — signals, backtest, paper trading"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    subs = parser.add_subparsers(dest="command", required=True)

    # signals
    p_sig = subs.add_parser("signals", help="Generate current BUY/SELL/HOLD signals")
    p_sig.add_argument("--ticker", help="Single ticker (default: all)")
    p_sig.set_defaults(func=cmd_signals)

    # backtest
    p_bt = subs.add_parser("backtest", help="Run historical backtest")
    p_bt.add_argument("--ticker", help="Single ticker (default: all)")
    p_bt.add_argument("--start", help="Start date YYYY-MM-DD")
    p_bt.add_argument("--end", help="End date YYYY-MM-DD")
    p_bt.add_argument("--bb-period", dest="bb_period", type=int, help="Bollinger period (default: 20)")
    p_bt.add_argument("--bb-std", dest="bb_std", type=float, help="Bollinger std dev (default: 2.0)")
    p_bt.add_argument(
        "--entry-zscore", dest="entry_zscore", type=float,
        help="Z-score BUY entry threshold (default: -2.0)",
    )
    p_bt.add_argument(
        "--exit-zscore", dest="exit_zscore", type=float,
        help="Z-score SELL exit threshold (default: 0.0)",
    )
    p_bt.add_argument("--capital", type=float, help="Initial capital (default: 100000)")
    p_bt.set_defaults(func=cmd_backtest)

    # paper
    p_paper = subs.add_parser("paper", help="Run paper trading for today")
    p_paper.set_defaults(func=cmd_paper)

    # positions
    p_pos = subs.add_parser("positions", help="Show current paper positions")
    p_pos.set_defaults(func=cmd_positions)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
