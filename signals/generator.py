"""Signal generator — layered indicator + sentiment + risk pipeline.

Filter order (each layer can only block/demote a BUY, not promote):
    1.  Bollinger Band z-score       → raw direction (BUY < entry_zscore, SELL >= exit_zscore)
    2.  ADX filter (sideways market) → HOLD if ADX > max_adx (trending, not ranging)
    3.  RSI confirmation             → HOLD on BUY if not oversold
    4.  Volume confirmation          → HOLD if below-average volume
    5.  Sentiment filter (DB)        → HOLD on BUY if negative/low-confidence
    6.  Risk filter (DB)             → HOLD on BUY if risk score too high
    7.  Volatility regime            → position-size multiplier (not a HOLD filter)

Entry logic  (BUY):  z-score <= entry_zscore AND all filters pass
Exit  logic  (SELL): z-score >= exit_zscore  (mean reversion complete)
Stop  logic: ATR-based fixed stop — computed at entry, applied externally
"""
from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

import pandas as pd

from ..config import MeanReversionConfig
from ..indicators.bollinger import BollingerBands, VWBB
from ..indicators.momentum import RSI
from ..indicators.trend_strength import ADX
from ..indicators.volatility import ATR, VolatilityRegime
from ..indicators.volume import VolumeConfirmation, OBV
from .filters import apply_mr_filters, Action

_TRADING_ROOT = Path(__file__).resolve().parents[2]
_SENTIMENT_DB = _TRADING_ROOT / "sentiment_analysis" / "backend" / "sentiment_history.db"
_RISK_DB = _TRADING_ROOT / "risk_calculator" / "backend" / "risk_history.db"


@dataclass
class Signal:
    """Output of the signal generator for one ticker on one date."""
    ticker: str
    date: str
    action: Action
    zscore: float
    filtered_strength: float
    reason: str
    sentiment: Optional[str] = None
    sentiment_confidence: Optional[float] = None
    risk_score: Optional[float] = None
    risk_bucket: Optional[str] = None
    rsi_value: Optional[float] = None
    adx_value: Optional[float] = None
    volume_ratio: Optional[float] = None
    vol_regime_mult: Optional[float] = None
    atr_stop: Optional[float] = None


def _fetch_latest_sentiment(ticker: str) -> Optional[dict]:
    """Look up the most recent sentiment snapshot from the API."""
    url = os.getenv("SENTIMENT_API_URL", "http://localhost:8000")
    try:
        resp = requests.get(f"{url}/api/history/{ticker}?limit=1", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("snapshots") and len(data["snapshots"]) > 0:
                return data["snapshots"][0]
    except Exception:
        pass
    return None


def _fetch_latest_risk(ticker: str) -> Optional[dict]:
    """Look up the most recent risk snapshot from the API."""
    url = os.getenv("RISK_API_URL", "http://localhost:8100")
    try:
        resp = requests.get(f"{url}/api/history/{ticker}?limit=1", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("snapshots") and len(data["snapshots"]) > 0:
                return data["snapshots"][0]
    except Exception:
        pass
    return None


def generate_signal(
    ticker: str,
    ohlc: pd.DataFrame,
    cfg: MeanReversionConfig,
    sentiment_override: Optional[dict] = None,
    risk_override: Optional[dict] = None,
) -> Signal:
    """Generate a mean reversion trading signal for one ticker.

    Args:
        ticker: Stock symbol.
        ohlc: OHLCV DataFrame indexed by datetime.
        cfg: Strategy configuration.
        sentiment_override: Pre-loaded sentiment dict (skips DB lookup).
        risk_override: Pre-loaded risk dict (skips DB lookup).

    Returns:
        Signal with action, z-score, filtered strength, indicators, and reason chain.
    """
    today_str = datetime.now(timezone.utc).date().isoformat()
    reasons: List[str] = []

    # ── Layer 1: Bollinger Band z-score ───────────────────────────────────────
    if getattr(cfg.bollinger, 'use_vwbb', False):
        bb = VWBB(period=cfg.bollinger.period, std_dev=cfg.bollinger.std_dev)
    else:
        bb = BollingerBands(period=cfg.bollinger.period, std_dev=cfg.bollinger.std_dev)
    zscore = bb.latest_zscore(ohlc) or 0.0
    reasons.append(f"bb={bb.name} z={zscore:+.2f}")

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

    # ── Layer 2-4: Compute indicator snapshot values ────────────────────────
    adx_value: Optional[float] = None
    if cfg.adx.enabled:
        adx_ind = ADX(period=cfg.adx.period, threshold=cfg.adx.max_adx)
        adx_value = adx_ind.latest_value(ohlc)

    rsi_value: Optional[float] = None
    rsi_ind = RSI(period=cfg.rsi.period, oversold=cfg.rsi.oversold, overbought=cfg.rsi.overbought)
    if cfg.rsi.enabled or cfg.short.rsi_overbought_required:
        rsi_value = rsi_ind.latest_value(ohlc)

    volume_ratio: Optional[float] = None
    if cfg.volume.enabled:
        vol_ind = VolumeConfirmation(period=cfg.volume.period, min_ratio=cfg.volume.min_ratio)
        volume_ratio = vol_ind.latest_ratio(ohlc)

    obv_bullish: bool = True
    if getattr(cfg, 'volume_flow', None) and getattr(cfg.volume_flow, 'enabled', False):
        obv_ind = OBV(ema_period=cfg.volume_flow.obv_ema_period)
        obv_bullish = obv_ind.is_bullish(ohlc)

    # ── Layer 5-6: Shared filter pipeline ──────────────────────────────────
    sentiment_data = sentiment_override or _fetch_latest_sentiment(ticker)
    risk_data = risk_override or _fetch_latest_risk(ticker)

    filtered_action, filter_reasons = apply_mr_filters(
        raw_action=filtered_action,
        zscore=zscore,
        cfg=cfg,
        adx_val=adx_value,
        rsi_val=rsi_value,
        vol_ratio=volume_ratio,
        obv_bullish=obv_bullish,
        sentiment_data=sentiment_data,
        risk_data=risk_data,
    )
    reasons.extend(filter_reasons)

    overall_sentiment = (sentiment_data or {}).get("overall_sentiment")
    conf = float((sentiment_data or {}).get("confidence") or 0.0)
    risk_score = (risk_data or {}).get("composite_risk_score")
    risk_bucket = (risk_data or {}).get("risk_bucket")

    # ── Layer 7: Volatility regime — position-size multiplier ────────────────
    vol_regime_mult: Optional[float] = None
    if cfg.vol_regime.enabled:
        vr = VolatilityRegime(
            period=cfg.vol_regime.period,
            low_vol_threshold=cfg.vol_regime.low_vol_threshold,
            high_vol_threshold=cfg.vol_regime.high_vol_threshold,
            min_multiplier=cfg.vol_regime.min_multiplier,
        )
        vol_regime_mult = vr.latest_multiplier(ohlc)
        if vol_regime_mult < 1.0:
            reasons.append(f"vol_regime_mult={vol_regime_mult:.2f}")

    # ── ATR stop price (informational) ────────────────────────────────────────
    atr_stop: Optional[float] = None
    if cfg.atr_stop.enabled:
        atr_ind = ATR(period=cfg.atr_stop.period)
        current_price = float(ohlc["Close"].iloc[-1])
        atr_stop = atr_ind.stop_price(
            ohlc, current_price, cfg.atr_stop.multiplier, direction="long"
        )

    # ── Compute final position strength ───────────────────────────────────────
    if filtered_action == "HOLD":
        strength = 0.0
    elif filtered_action in ("BUY", "SHORT"):
        ps = cfg.position_sizing
        if overall_sentiment == "positive" and conf >= cfg.signal.min_sentiment_confidence:
            sent_mult = ps.sentiment_agree_mult if filtered_action == "BUY" else ps.sentiment_disagree_mult
            reasons.append(f"sent=positive(x{sent_mult})")
        elif overall_sentiment == "negative":
            sent_mult = ps.sentiment_disagree_mult if filtered_action == "BUY" else ps.sentiment_agree_mult
            reasons.append(f"sent=negative(x{sent_mult})")
        else:
            sent_mult = ps.sentiment_neutral_mult
            reasons.append(f"sent=neutral(x{sent_mult})")
        ref_zscore = cfg.bollinger.entry_zscore if filtered_action == "BUY" else cfg.short.entry_zscore
        strength = min(abs(zscore / ref_zscore) * sent_mult * (vol_regime_mult or 1.0), 1.0)
    elif filtered_action in ("PARTIAL_SELL", "PARTIAL_COVER"):
        strength = cfg.bollinger.partial_exit_fraction
    else:  # SELL / COVER
        ref = cfg.bollinger.exit_zscore if filtered_action == "SELL" else cfg.short.exit_zscore
        strength = min(abs(zscore / ref) if ref != 0 else 1.0, 1.0)

    return Signal(
        ticker=ticker,
        date=today_str,
        action=filtered_action,
        zscore=zscore,
        filtered_strength=strength,
        reason=" | ".join(reasons),
        sentiment=overall_sentiment,
        sentiment_confidence=conf if conf > 0 else None,
        risk_score=risk_score,
        risk_bucket=risk_bucket,
        rsi_value=rsi_value,
        adx_value=adx_value,
        volume_ratio=volume_ratio,
        vol_regime_mult=vol_regime_mult,
        atr_stop=atr_stop,
    )


def generate_all_signals(
    ohlc_map: Dict[str, pd.DataFrame],
    cfg: MeanReversionConfig,
) -> List[Signal]:
    """Generate signals for all tickers in cfg.tickers."""
    signals = []
    for ticker in cfg.tickers:
        if ticker not in ohlc_map:
            continue
        sig = generate_signal(ticker, ohlc_map[ticker], cfg)
        signals.append(sig)
    return signals
