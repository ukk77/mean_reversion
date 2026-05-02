"""Core backtest engine for the Mean Reversion strategy.

Each ticker is simulated in its own isolated portfolio (independent capital).
A combined portfolio equity curve is produced by equal-weight averaging the
normalised returns across all tickers.

Signal logic:
    BUY  when Bollinger Band z-score <= entry_zscore (price below lower band)
         AND all active filters pass (ADX ranging, RSI oversold, volume OK)
    SELL when z-score >= exit_zscore (price reverts to mean)
         OR ATR stop loss is hit

Sentiment + risk data are loaded from the existing SQLite history DBs using
point-in-time lookups (no look-ahead bias).
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_TRADING_ROOT = Path(__file__).resolve().parents[2]
_RISK_BACKEND = _TRADING_ROOT / "risk_calculator" / "backend"
if str(_RISK_BACKEND) not in sys.path:
    sys.path.insert(0, str(_RISK_BACKEND))

from ..config import MeanReversionConfig
from ..indicators.bollinger import BollingerBands
from ..indicators.momentum import RSI
from ..indicators.trend_strength import ADX
from ..indicators.volatility import ATR, VolatilityRegime
from ..indicators.volume import VolumeConfirmation
from ..position_sizing.sizer import shares_to_buy
from ..signals.generator import Action, Signal
from .metrics import compute_all_metrics
from .portfolio import Portfolio


# ── History DB helpers ────────────────────────────────────────────────────────

def _load_sentiment_history(ticker: str) -> pd.DataFrame:
    """Load all sentiment snapshots for a ticker as a date-indexed DataFrame."""
    db_path = _TRADING_ROOT / "sentiment_analysis" / "backend" / "sentiment_history.db"
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            df = pd.read_sql_query(
                "SELECT captured_at, overall_sentiment, confidence "
                "FROM sentiment_snapshots WHERE UPPER(ticker)=UPPER(?)",
                conn,
                params=(ticker.upper(),),
            )
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["captured_at"]).dt.date
        df = df.sort_values("date").drop_duplicates("date", keep="last")
        return df.set_index("date")
    except Exception:
        return pd.DataFrame()


def _load_risk_history(ticker: str) -> pd.DataFrame:
    """Load all risk snapshots for a ticker as a date-indexed DataFrame."""
    db_path = _TRADING_ROOT / "risk_calculator" / "backend" / "risk_history.db"
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(str(db_path)) as conn:
            df = pd.read_sql_query(
                "SELECT captured_at, composite_risk_score, risk_bucket, "
                "kelly_fraction_capped, suggested_stop_loss_pct "
                "FROM risk_snapshots WHERE UPPER(ticker)=UPPER(?)",
                conn,
                params=(ticker.upper(),),
            )
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["captured_at"]).dt.date
        df = df.sort_values("date").drop_duplicates("date", keep="last")
        return df.set_index("date")
    except Exception:
        return pd.DataFrame()


def _get_as_of(df: pd.DataFrame, as_of_date) -> Optional[dict]:
    """Return the most recent row up to and including as_of_date."""
    if df.empty:
        return None
    past = df[df.index <= as_of_date]
    if past.empty:
        return None
    return past.iloc[-1].to_dict()


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """Per-ticker backtest output."""
    ticker: str
    equity_curve: pd.Series
    trades_df: pd.DataFrame
    metrics: Dict
    benchmark_equity: Dict[str, pd.Series]


@dataclass
class BacktestSummary:
    """Aggregated backtest output across all tickers."""
    results: Dict[str, BacktestResult] = field(default_factory=dict)
    portfolio_equity: Optional[pd.Series] = None
    portfolio_metrics: Optional[Dict] = None


# ── Main engine ───────────────────────────────────────────────────────────────

def _run_single_ticker(
    ticker: str,
    ohlc: pd.DataFrame,
    cfg: MeanReversionConfig,
    sentiment_hist: pd.DataFrame,
    risk_hist: pd.DataFrame,
    benchmark_ohlc: Dict[str, pd.DataFrame],
    rf_annual: float,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Optional[BacktestResult]:
    """Run the mean reversion backtest for a single ticker."""

    if start_date:
        ohlc = ohlc[ohlc.index >= pd.Timestamp(start_date)]
    if end_date:
        ohlc = ohlc[ohlc.index <= pd.Timestamp(end_date)]

    min_bars = max(
        cfg.bollinger.period,
        cfg.rsi.period,
        cfg.adx.period * 2,
        cfg.volume.period,
        cfg.atr_stop.period,
    ) + 10
    if ohlc.empty or len(ohlc) < min_bars:
        return None

    # ── Precompute all indicator series (no look-ahead bias) ──────────────────
    bb = BollingerBands(period=cfg.bollinger.period, std_dev=cfg.bollinger.std_dev)
    zscore_series = bb.zscore_series(ohlc)

    rsi_series = (
        RSI(period=cfg.rsi.period, oversold=cfg.rsi.oversold, overbought=cfg.rsi.overbought)
        .compute(ohlc).values
        if cfg.rsi.enabled else None
    )
    adx_series = (
        ADX(period=cfg.adx.period, threshold=cfg.adx.max_adx).compute(ohlc).values
        if cfg.adx.enabled else None
    )
    vol_ratio_series = (
        VolumeConfirmation(period=cfg.volume.period, min_ratio=cfg.volume.min_ratio)
        .compute(ohlc).raw["ratio"]
        if cfg.volume.enabled else None
    )
    vol_regime_series = (
        VolatilityRegime(
            period=cfg.vol_regime.period,
            low_vol_threshold=cfg.vol_regime.low_vol_threshold,
            high_vol_threshold=cfg.vol_regime.high_vol_threshold,
            min_multiplier=cfg.vol_regime.min_multiplier,
        ).signal_series(ohlc)
        if cfg.vol_regime.enabled else None
    )
    atr_series = (
        ATR(period=cfg.atr_stop.period).atr_series(ohlc)
        if cfg.atr_stop.enabled else None
    )

    def _val(series, dt, default=None):
        """Safe point-in-time value lookup."""
        if series is None or dt not in series.index:
            return default
        v = series.loc[dt]
        return default if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)

    portfolio = Portfolio(cfg.backtest.initial_capital, cfg.backtest.commission_pct)
    slippage = cfg.backtest.slippage
    daily_rf = (1.0 + rf_annual) ** (1.0 / 252) - 1.0

    # Fixed ATR stop prices — long stops below price, short stops above price
    atr_stops: dict = {}       # ticker -> long stop (stop-out if price <= stop)
    short_stops: dict = {}     # ticker -> short stop (stop-out if price >= stop)

    valid_dates = zscore_series.dropna().index

    for dt in valid_dates:
        dt_date = dt.date()
        date_str = dt_date.isoformat()
        current_price = float(ohlc.loc[dt, "Close"])
        zscore = _val(zscore_series, dt, 0.0)

        # Point-in-time sentiment + risk
        sent_snap = _get_as_of(sentiment_hist, dt_date)
        risk_snap = _get_as_of(risk_hist, dt_date)
        overall_sentiment = (sent_snap or {}).get("overall_sentiment")
        conf = float((sent_snap or {}).get("confidence") or 0.0)
        risk_score = (risk_snap or {}).get("composite_risk_score")
        kelly_fraction = (risk_snap or {}).get("kelly_fraction_capped")
        db_suggested_stop_pct = (risk_snap or {}).get("suggested_stop_loss_pct")

        # ── Cash interest on idle capital ──────────────────────────────────────
        if cfg.backtest.model_cash_interest:
            portfolio.accrue_cash_interest(daily_rf)

        # ── ATR stop check on long positions ──────────────────────────────────
        if cfg.atr_stop.enabled and portfolio.is_invested(ticker):
            if ticker in atr_stops and current_price <= atr_stops[ticker]:
                exec_price = current_price * (1.0 - slippage)
                portfolio.sell_all(ticker, exec_price, date_str)
                atr_stops.pop(ticker, None)
                portfolio.record_equity(date_str, {ticker: current_price})
                continue

            # Trail the stop upward if enabled (optional for MR)
            if cfg.atr_stop.trail:
                atr_val = _val(atr_series, dt, 0.0)
                if atr_val > 0:
                    candidate = current_price - cfg.atr_stop.multiplier * atr_val
                    if ticker in atr_stops:
                        atr_stops[ticker] = max(atr_stops[ticker], candidate)

        # ── ATR stop check on short positions ─────────────────────────────────
        if cfg.atr_stop.enabled and portfolio.is_short(ticker):
            if ticker in short_stops and current_price >= short_stops[ticker]:
                exec_price = current_price * (1.0 + slippage)
                portfolio.cover_all(ticker, exec_price, date_str)
                short_stops.pop(ticker, None)
                portfolio.record_equity(date_str, {ticker: current_price})
                continue

        # ── Determine raw action from z-score ─────────────────────────────────
        if zscore <= cfg.bollinger.entry_zscore:
            filtered_action: Action = "BUY"
        elif zscore >= cfg.bollinger.exit_zscore and zscore < (cfg.short.entry_zscore if cfg.short.enabled else 9999):
            filtered_action = "SELL"
        elif cfg.short.enabled and zscore >= cfg.short.entry_zscore:
            filtered_action = "SHORT"
        elif cfg.short.enabled and zscore <= cfg.short.exit_zscore:
            filtered_action = "COVER"
        elif cfg.bollinger.partial_exit_fraction > 0 and zscore >= cfg.bollinger.partial_exit_zscore:
            filtered_action = "PARTIAL_SELL"
        elif cfg.short.enabled and cfg.short.partial_exit_fraction > 0 and zscore <= cfg.short.partial_exit_zscore:
            filtered_action = "PARTIAL_COVER"
        else:
            filtered_action = "HOLD"

        # ── ADX filter — block BUY/SHORT in trending markets ──────────────────
        if cfg.adx.enabled and filtered_action in ("BUY", "SHORT"):
            adx_val = _val(adx_series, dt, 0.0)
            if adx_val >= cfg.adx.max_adx:
                filtered_action = "HOLD"

        # ── RSI filter ────────────────────────────────────────────────────────
        if cfg.rsi.enabled and filtered_action == "BUY":
            rsi_val = _val(rsi_series, dt, 50.0)
            if rsi_val >= cfg.rsi.oversold:
                filtered_action = "HOLD"
        if cfg.short.rsi_overbought_required and filtered_action == "SHORT":
            rsi_val = _val(rsi_series, dt, 50.0)
            if rsi_val <= cfg.rsi.overbought:
                filtered_action = "HOLD"

        # ── Volume confirmation ────────────────────────────────────────────────
        if cfg.volume.enabled and filtered_action in ("BUY", "SHORT"):
            vol_ratio = _val(vol_ratio_series, dt, 1.0)
            if vol_ratio < cfg.volume.min_ratio:
                filtered_action = "HOLD"

        # ── Sentiment filter ───────────────────────────────────────────────────
        if filtered_action == "BUY" and cfg.signal.sentiment_filter_enabled and sent_snap is not None:
            if conf < cfg.signal.min_sentiment_confidence:
                filtered_action = "HOLD"
            elif cfg.signal.block_on_negative_sentiment and overall_sentiment == "negative":
                filtered_action = "HOLD"

        # ── Risk filter ────────────────────────────────────────────────────────
        if filtered_action == "BUY" and cfg.signal.risk_filter_enabled and risk_score is not None:
            if risk_score > cfg.signal.max_risk_score:
                filtered_action = "HOLD"

        # ── Vol regime multiplier ──────────────────────────────────────────────
        vol_mult = _val(vol_regime_series, dt, 1.0) if cfg.vol_regime.enabled else 1.0

        # ── Execution prices ───────────────────────────────────────────────────
        if filtered_action in ("BUY", "COVER", "PARTIAL_COVER"):
            exec_price = current_price * (1.0 + slippage)
        elif filtered_action in ("SELL", "SHORT", "PARTIAL_SELL"):
            exec_price = current_price * (1.0 - slippage)
        else:
            exec_price = current_price

        sig = Signal(
            ticker=ticker,
            date=date_str,
            action=filtered_action,
            zscore=zscore,
            filtered_strength=abs(zscore / cfg.bollinger.entry_zscore) * vol_mult
            if filtered_action not in ("HOLD",) else 0.0,
            reason="",
            sentiment=overall_sentiment,
            sentiment_confidence=conf if conf > 0 else None,
            risk_score=risk_score,
        )

        current_portfolio_value = portfolio.equity({ticker: current_price})

        if filtered_action == "BUY" and not portfolio.is_invested(ticker) and not portfolio.is_short(ticker):
            n_shares = shares_to_buy(sig, current_portfolio_value, exec_price, cfg,
                                     kelly_fraction=kelly_fraction)
            if n_shares > 0 and portfolio.buy(ticker, n_shares, exec_price, date_str):
                if cfg.atr_stop.enabled:
                    stop_price = None
                    if cfg.atr_stop.use_db_stop_when_available and db_suggested_stop_pct is not None:
                        stop_price = exec_price * (1.0 + db_suggested_stop_pct)
                    if stop_price is None:
                        atr_val = _val(atr_series, dt, 0.0)
                        if atr_val > 0:
                            stop_price = exec_price - cfg.atr_stop.multiplier * atr_val
                    if stop_price is not None:
                        atr_stops[ticker] = stop_price

        elif filtered_action == "PARTIAL_SELL" and portfolio.is_invested(ticker):
            portfolio.partial_sell(ticker, cfg.bollinger.partial_exit_fraction, exec_price, date_str)

        elif filtered_action == "SELL" and portfolio.is_invested(ticker):
            portfolio.sell_all(ticker, exec_price, date_str)
            atr_stops.pop(ticker, None)

        elif filtered_action == "SHORT" and not portfolio.is_short(ticker) and not portfolio.is_invested(ticker):
            n_shares = shares_to_buy(sig, current_portfolio_value, exec_price, cfg,
                                     kelly_fraction=kelly_fraction)
            if n_shares > 0 and portfolio.short(ticker, n_shares, exec_price, date_str):
                if cfg.atr_stop.enabled:
                    atr_val = _val(atr_series, dt, 0.0)
                    if atr_val > 0:
                        short_stops[ticker] = exec_price + cfg.atr_stop.multiplier * atr_val

        elif filtered_action == "PARTIAL_COVER" and portfolio.is_short(ticker):
            portfolio.partial_cover(ticker, cfg.short.partial_exit_fraction, exec_price, date_str)

        elif filtered_action == "COVER" and portfolio.is_short(ticker):
            portfolio.cover_all(ticker, exec_price, date_str)
            short_stops.pop(ticker, None)

        portfolio.record_equity(date_str, {ticker: current_price})

    trades_df = portfolio.to_trades_df()
    equity = portfolio.equity_series()

    bench_equities: Dict[str, pd.Series] = {}
    for b_name, b_ohlc in benchmark_ohlc.items():
        b_filtered = b_ohlc.copy()
        if start_date:
            b_filtered = b_filtered[b_filtered.index >= pd.Timestamp(start_date)]
        if end_date:
            b_filtered = b_filtered[b_filtered.index <= pd.Timestamp(end_date)]
        b_close = b_filtered["Close"].dropna()
        if not b_close.empty:
            bench_equities[b_name] = cfg.backtest.initial_capital * (b_close / b_close.iloc[0])

    metrics = compute_all_metrics(
        equity=equity,
        initial_capital=cfg.backtest.initial_capital,
        trades_df=trades_df,
        benchmarks=bench_equities,
        rf_annual=rf_annual,
    )

    return BacktestResult(
        ticker=ticker,
        equity_curve=equity,
        trades_df=trades_df,
        metrics=metrics,
        benchmark_equity=bench_equities,
    )


def run_backtest(
    cfg: MeanReversionConfig,
    ticker_ohlc: Dict[str, pd.DataFrame],
    benchmark_ohlc: Dict[str, pd.DataFrame],
    rf_annual: float = 0.04,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> BacktestSummary:
    """Run the mean reversion backtest across all tickers.

    Args:
        cfg: Strategy configuration.
        ticker_ohlc: Dict of ticker -> OHLCV DataFrame.
        benchmark_ohlc: Dict of benchmark_name -> OHLCV DataFrame.
        rf_annual: Annualised risk-free rate.
        start_date: ISO date string for backtest start (optional).
        end_date: ISO date string for backtest end (optional).

    Returns:
        BacktestSummary with per-ticker results and combined portfolio metrics.
    """
    summary = BacktestSummary()

    for ticker, ohlc in ticker_ohlc.items():
        sentiment_hist = _load_sentiment_history(ticker)
        risk_hist = _load_risk_history(ticker)

        result = _run_single_ticker(
            ticker=ticker,
            ohlc=ohlc,
            cfg=cfg,
            sentiment_hist=sentiment_hist,
            risk_hist=risk_hist,
            benchmark_ohlc=benchmark_ohlc,
            rf_annual=rf_annual,
            start_date=start_date,
            end_date=end_date,
        )
        if result is not None:
            summary.results[ticker] = result

    valid_curves = [
        r.equity_curve for r in summary.results.values() if not r.equity_curve.empty
    ]
    if valid_curves:
        normalised = [c / c.iloc[0] for c in valid_curves]
        combined_norm = pd.concat(normalised, axis=1).ffill().mean(axis=1)
        combined_equity = cfg.backtest.initial_capital * combined_norm
        summary.portfolio_equity = combined_equity

        bench_equities: Dict[str, pd.Series] = {}
        for b_name, b_ohlc in benchmark_ohlc.items():
            b_filtered = b_ohlc.copy()
            if start_date:
                b_filtered = b_filtered[b_filtered.index >= pd.Timestamp(start_date)]
            if end_date:
                b_filtered = b_filtered[b_filtered.index <= pd.Timestamp(end_date)]
            b_close = b_filtered["Close"].dropna()
            if not b_close.empty:
                bench_equities[b_name] = (
                    cfg.backtest.initial_capital * (b_close / b_close.iloc[0])
                )

        all_trades: List[pd.DataFrame] = [
            r.trades_df for r in summary.results.values() if not r.trades_df.empty
        ]
        combined_trades = (
            pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
        )

        summary.portfolio_metrics = compute_all_metrics(
            equity=combined_equity,
            initial_capital=cfg.backtest.initial_capital,
            trades_df=combined_trades,
            benchmarks=bench_equities,
            rf_annual=rf_annual,
        )

    return summary
