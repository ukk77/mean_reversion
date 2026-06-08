"""Live paper trading tracker for Mean Reversion strategy.

Processes today's Bollinger Band z-score signals and updates simulated
paper positions stored in mr_paper_trades.db.

Designed to be called daily, either:
  - standalone: python -m mean_reversion.paper_trading.tracker
  - via CLI:    python cli.py paper
  - via runner: run_paper_trading_mr.py (at trading root)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

_TRADING_ROOT = Path(__file__).resolve().parents[2]
_RISK_BACKEND = _TRADING_ROOT / "risk_calculator" / "backend"
if str(_RISK_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RISK_BACKEND))

from ..config import MeanReversionConfig
from ..indicators.volatility import ATR
from ..signals.generator import generate_signal
from ..position_sizing.sizer import shares_to_buy
from . import db as paper_db

log = logging.getLogger(__name__)

TICKER_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "TSLA": "Tesla Inc.",
    "META": "Meta Platforms Inc.",
    "NVDA": "NVIDIA Corporation",
    "JPM": "JPMorgan Chase & Co.",
    "XOM": "Exxon Mobil Corporation",
    "LLY": "Eli Lilly and Company",
    "UNH": "UnitedHealth Group",
    "WMT": "Walmart Inc.",
    "XLF": "Financial Select Sector SPDR",
    "XLE": "Energy Select Sector SPDR",
    "XLV": "Health Care Select Sector SPDR",
    "XLU": "Utilities Select Sector SPDR",
    "XLK": "Technology Select Sector SPDR",
    "XLP": "Consumer Staples Select Sector SPDR",
}

_TF_DB_PATH = Path(__file__).resolve().parents[2] / "trend_following" / "paper_trades.db"


def _tf_position_size(ticker: str) -> int:
    """Return shares held in trend_following for this ticker (0 if not held)."""
    if not _TF_DB_PATH.exists():
        return 0
    try:
        import sqlite3 as _sqlite3
        with _sqlite3.connect(str(_TF_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT shares FROM paper_positions WHERE UPPER(ticker)=UPPER(?)",
                (ticker.upper(),),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _fetch_ohlc(ticker: str, lookback_days: int):
    """Load OHLCV data via the risk_calculator market_data service."""
    from app.services.market_data import fetch_ohlcv
    return fetch_ohlcv(ticker, lookback_days)


def run_paper_trading(
    cfg: Optional[MeanReversionConfig] = None,
    force: bool = False,
) -> List[Dict]:
    """Process today's mean reversion signals and update paper positions.

    Args:
        cfg:   Strategy configuration (uses defaults if None).
        force: If True, skip the already-ran-today guard and run regardless.

    Returns:
        List of action dicts: one per ticker with signal, action taken, and P&L.
    """
    if cfg is None:
        cfg = MeanReversionConfig()

    paper_db.init_db()

    if not force and paper_db.has_run_today():
        log.warning(
            "Paper trading already ran today — skipping. Pass force=True to override."
        )
        return []
    actions = []

    # ── Compute current portfolio value (cash + cost basis of open positions) ─
    _positions_snapshot = paper_db.get_positions()
    _cash = paper_db.get_cash_balance(cfg.backtest.initial_capital)
    _invested = sum(p["shares"] * p["avg_cost"] for p in _positions_snapshot)
    portfolio_value = _cash + _invested
    if portfolio_value <= 0:
        portfolio_value = cfg.backtest.initial_capital
    log.info(
        "Portfolio value: $%.2f  (cash=$%.2f  invested=$%.2f)",
        portfolio_value, _cash, _invested,
    )

    for ticker in cfg.tickers:
        log.info("== %s ==", ticker)

        try:
            ohlc = _fetch_ohlc(ticker, cfg.lookback_days)
        except Exception as exc:
            log.warning("  No price data for %s: %s — skipping", ticker, exc)
            actions.append(
                {
                    "ticker": ticker,
                    "signal": "ERROR",
                    "action_taken": "SKIP",
                    "shares": 0,
                    "price": None,
                    "pnl": None,
                    "reason": str(exc),
                }
            )
            continue

        current_price = float(ohlc["Close"].iloc[-1])
        positions = {p["ticker"]: p for p in paper_db.get_positions(side="LONG")}
        pos = positions.get(ticker.upper(), {})
        held = pos.get("shares", 0)
        avg_cost = pos.get("avg_cost", 0.0)
        stored_stop = pos.get("atr_stop")

        action_taken = "HOLD"
        shares_traded = 0
        pnl = None

        # ── ATR stop check on LONG positions ──────────────────────────────────
        if cfg.atr_stop.enabled and held > 0 and stored_stop is not None:
            if current_price <= stored_stop:
                gross_pnl = (current_price - avg_cost) * held
                commission = current_price * held * cfg.backtest.commission_pct
                net_pnl = gross_pnl - commission
                paper_db.log_trade(
                    ticker=ticker, action="SELL", shares=held, price=current_price,
                    commission=commission, pnl=net_pnl, reason="ATR_STOP_HIT",
                    signal_strength=0.0,
                )
                paper_db.upsert_position(ticker, 0, 0.0, side="LONG")
                action_taken = "STOP_SELL"
                shares_traded = held
                pnl = net_pnl
                log.info(
                    "  ATR STOP HIT: sold %d shares @ $%.2f (stop=%.2f) | Net P&L: $%.2f",
                    held, current_price, stored_stop, net_pnl,
                )
                actions.append({"ticker": ticker, "signal": "STOP", "action_taken": action_taken,
                                 "shares": shares_traded, "price": current_price, "pnl": pnl,
                                 "reason": "ATR_STOP_HIT", "sentiment": None, "risk_score": None, "zscore": None})
                continue

            # Time stop — exit if held too long
            if cfg.bollinger.max_hold_days > 0:
                opened_str = pos.get("opened_at", "")
                if opened_str:
                    try:
                        from datetime import datetime as _dt
                        opened_date = _dt.fromisoformat(opened_str.replace("Z", "+00:00")).date()
                        days_held = (_dt.utcnow().date() - opened_date).days
                        if days_held >= cfg.bollinger.max_hold_days:
                            gross_pnl = (current_price - avg_cost) * held
                            commission = current_price * held * cfg.backtest.commission_pct
                            net_pnl = gross_pnl - commission
                            paper_db.log_trade(
                                ticker=ticker, action="SELL", shares=held, price=current_price,
                                commission=commission, pnl=net_pnl, reason="TIME_STOP",
                                signal_strength=0.0,
                            )
                            paper_db.upsert_position(ticker, 0, 0.0, side="LONG")
                            action_taken = "TIME_SELL"
                            shares_traded = held
                            pnl = net_pnl
                            log.info("  TIME STOP: sold %d @ $%.2f (held %d days) | P&L: $%.2f",
                                     held, current_price, days_held, net_pnl)
                            actions.append({"ticker": ticker, "signal": "STOP", "action_taken": action_taken,
                                             "shares": shares_traded, "price": current_price, "pnl": pnl,
                                             "reason": "TIME_STOP", "sentiment": None, "risk_score": None, "zscore": None})
                            continue
                    except (ValueError, TypeError):
                        pass

            if cfg.atr_stop.trail:
                atr_ind = ATR(period=cfg.atr_stop.period)
                atr_val = atr_ind.latest_atr(ohlc)
                if atr_val > 0:
                    candidate = current_price - cfg.atr_stop.multiplier * atr_val
                    if candidate > stored_stop:
                        paper_db.update_atr_stop(ticker, candidate, side="LONG")
                        log.info("  ATR TRAIL updated: %.2f → %.2f", stored_stop, candidate)

        # ── ATR stop check on SHORT positions ────────────────────────────────
        short_pos = next(
            (p for p in paper_db.get_positions(side="SHORT") if p["ticker"] == ticker.upper()), {}
        )
        short_held = short_pos.get("shares", 0)
        short_cost = short_pos.get("avg_cost", 0.0)
        short_stop = short_pos.get("atr_stop")
        if cfg.atr_stop.enabled and short_held > 0 and short_stop is not None:
            if current_price >= short_stop:
                gross_pnl = (short_cost - current_price) * short_held
                commission = current_price * short_held * cfg.backtest.commission_pct
                net_pnl = gross_pnl - commission
                paper_db.log_trade(
                    ticker=ticker, action="COVER", shares=short_held, price=current_price,
                    commission=commission, pnl=net_pnl, reason="SHORT_ATR_STOP_HIT",
                    signal_strength=0.0,
                )
                paper_db.upsert_position(ticker, 0, 0.0, side="SHORT")
                log.info(
                    "  SHORT ATR STOP HIT: covered %d @ $%.2f (stop=%.2f) | Net P&L: $%.2f",
                    short_held, current_price, short_stop, net_pnl,
                )
                actions.append({"ticker": ticker, "signal": "STOP", "action_taken": "STOP_COVER",
                                 "shares": short_held, "price": current_price, "pnl": net_pnl,
                                 "reason": "SHORT_ATR_STOP_HIT", "sentiment": None, "risk_score": None, "zscore": None})
                continue

        signal = generate_signal(ticker, ohlc, cfg)
        log.info(
            "  Signal: %s (z=%+.2f, strength=%.2f) | %s",
            signal.action,
            signal.zscore,
            signal.filtered_strength,
            signal.reason,
        )

        # ── Cross-strategy correlation: reduce size if TF holds same ticker ─────
        tf_held = _tf_position_size(ticker)
        position_mult = 0.5 if tf_held > 0 else 1.0
        if tf_held > 0:
            log.info("  TF overlap: TF holds %d shares of %s — halving MR position size", tf_held, ticker)

        atr_ind = ATR(period=cfg.atr_stop.period)

        if signal.action == "BUY" and held == 0 and short_held == 0:
            n_shares = shares_to_buy(signal, portfolio_value, current_price, cfg)
            n_shares = max(1, int(n_shares * position_mult))
            if n_shares > 0:
                commission = current_price * n_shares * cfg.backtest.commission_pct
                atr_stop_price: Optional[float] = None
                if cfg.atr_stop.enabled:
                    atr_stop_price = atr_ind.stop_price(ohlc, current_price, cfg.atr_stop.multiplier, "long")
                paper_db.log_trade(
                    ticker=ticker, action="BUY", shares=n_shares, price=current_price,
                    commission=commission, zscore=signal.zscore, reason=signal.reason,
                    sentiment=signal.sentiment, risk_score=signal.risk_score,
                    signal_strength=signal.filtered_strength,
                )
                paper_db.upsert_position(ticker, n_shares, current_price,
                                         atr_stop=atr_stop_price, entry_zscore=signal.zscore, side="LONG")
                action_taken = "BUY"
                shares_traded = n_shares
                log.info("  PAPER BUY: %d shares @ $%.2f (z=%+.2f, stop=%.2f)",
                         n_shares, current_price, signal.zscore, atr_stop_price or 0.0)

        elif signal.action == "PARTIAL_SELL" and held > 0:
            sell_shares = max(1, int(held * cfg.bollinger.partial_exit_fraction))
            gross_pnl = (current_price - avg_cost) * sell_shares
            commission = current_price * sell_shares * cfg.backtest.commission_pct
            net_pnl = gross_pnl - commission
            paper_db.log_trade(
                ticker=ticker, action="SELL", shares=sell_shares, price=current_price,
                commission=commission, pnl=net_pnl, zscore=signal.zscore, reason="PARTIAL_EXIT",
                signal_strength=signal.filtered_strength,
            )
            remaining = held - sell_shares
            if remaining > 0:
                paper_db.upsert_position(ticker, remaining, avg_cost,
                                         atr_stop=stored_stop, entry_zscore=pos.get("entry_zscore"), side="LONG")
            else:
                paper_db.upsert_position(ticker, 0, 0.0, side="LONG")
            action_taken = "PARTIAL_SELL"
            shares_traded = sell_shares
            pnl = net_pnl
            log.info("  PARTIAL SELL: %d/%d shares @ $%.2f (z=%+.2f) | P&L: $%.2f",
                     sell_shares, held, current_price, signal.zscore, net_pnl)

        elif signal.action == "SELL" and held > 0:
            gross_pnl = (current_price - avg_cost) * held
            commission = current_price * held * cfg.backtest.commission_pct
            net_pnl = gross_pnl - commission
            paper_db.log_trade(
                ticker=ticker, action="SELL", shares=held, price=current_price,
                commission=commission, pnl=net_pnl, zscore=signal.zscore, reason=signal.reason,
                sentiment=signal.sentiment, risk_score=signal.risk_score,
                signal_strength=signal.filtered_strength,
            )
            paper_db.upsert_position(ticker, 0, 0.0, side="LONG")
            action_taken = "SELL"
            shares_traded = held
            pnl = net_pnl
            log.info("  PAPER SELL: %d shares @ $%.2f (z=%+.2f) | Net P&L: $%.2f",
                     held, current_price, signal.zscore, net_pnl)

        elif signal.action == "SHORT" and short_held == 0 and held == 0:
            n_shares = shares_to_buy(signal, portfolio_value, current_price, cfg)
            n_shares = max(1, int(n_shares * position_mult))
            if n_shares > 0:
                commission = current_price * n_shares * cfg.backtest.commission_pct
                short_stop_price: Optional[float] = None
                if cfg.atr_stop.enabled:
                    atr_val = atr_ind.latest_atr(ohlc)
                    if atr_val:
                        short_stop_price = current_price + cfg.atr_stop.multiplier * atr_val
                paper_db.log_trade(
                    ticker=ticker, action="SHORT", shares=n_shares, price=current_price,
                    commission=commission, zscore=signal.zscore, reason=signal.reason,
                    sentiment=signal.sentiment, risk_score=signal.risk_score,
                    signal_strength=signal.filtered_strength,
                )
                paper_db.upsert_position(ticker, n_shares, current_price,
                                         atr_stop=short_stop_price, entry_zscore=signal.zscore, side="SHORT")
                action_taken = "SHORT"
                shares_traded = n_shares
                log.info("  PAPER SHORT: %d shares @ $%.2f (z=%+.2f, stop=%.2f)",
                         n_shares, current_price, signal.zscore, short_stop_price or 0.0)

        elif signal.action == "PARTIAL_COVER" and short_held > 0:
            cover_shares = max(1, int(short_held * cfg.short.partial_exit_fraction))
            gross_pnl = (short_cost - current_price) * cover_shares
            commission = current_price * cover_shares * cfg.backtest.commission_pct
            net_pnl = gross_pnl - commission
            paper_db.log_trade(
                ticker=ticker, action="COVER", shares=cover_shares, price=current_price,
                commission=commission, pnl=net_pnl, zscore=signal.zscore, reason="PARTIAL_COVER",
                signal_strength=signal.filtered_strength,
            )
            remaining = short_held - cover_shares
            if remaining > 0:
                paper_db.upsert_position(ticker, remaining, short_cost,
                                         atr_stop=short_stop, entry_zscore=short_pos.get("entry_zscore"), side="SHORT")
            else:
                paper_db.upsert_position(ticker, 0, 0.0, side="SHORT")
            action_taken = "PARTIAL_COVER"
            shares_traded = cover_shares
            pnl = net_pnl
            log.info("  PARTIAL COVER: %d/%d shares @ $%.2f | P&L: $%.2f",
                     cover_shares, short_held, current_price, net_pnl)

        elif signal.action == "COVER" and short_held > 0:
            gross_pnl = (short_cost - current_price) * short_held
            commission = current_price * short_held * cfg.backtest.commission_pct
            net_pnl = gross_pnl - commission
            paper_db.log_trade(
                ticker=ticker, action="COVER", shares=short_held, price=current_price,
                commission=commission, pnl=net_pnl, zscore=signal.zscore, reason=signal.reason,
                signal_strength=signal.filtered_strength,
            )
            paper_db.upsert_position(ticker, 0, 0.0, side="SHORT")
            action_taken = "COVER"
            shares_traded = short_held
            pnl = net_pnl
            log.info("  PAPER COVER: %d shares @ $%.2f (z=%+.2f) | Net P&L: $%.2f",
                     short_held, current_price, signal.zscore, net_pnl)

        actions.append(
            {
                "ticker": ticker,
                "signal": signal.action,
                "action_taken": action_taken,
                "shares": shares_traded,
                "price": current_price,
                "pnl": pnl,
                "reason": signal.reason,
                "sentiment": signal.sentiment,
                "risk_score": signal.risk_score,
                "zscore": signal.zscore,
            }
        )

    paper_db.record_daily_run(tickers_processed=len(cfg.tickers))
    return actions
