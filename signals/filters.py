"""Shared filter pipeline — used by both signal generator and backtest engine.

Accepts pre-resolved indicator values (not raw series) so both callers can
supply values however they compute them (live vs point-in-time).
"""
from __future__ import annotations

from typing import List, Literal, Optional

from ..config import MeanReversionConfig

Action = Literal["BUY", "SELL", "HOLD", "SHORT", "COVER", "PARTIAL_SELL", "PARTIAL_COVER"]


def apply_mr_filters(
    raw_action: Action,
    zscore: float,
    cfg: MeanReversionConfig,
    adx_val: Optional[float] = None,
    rsi_val: Optional[float] = None,
    vol_ratio: Optional[float] = None,
    obv_bullish: bool = True,
    sentiment_data: Optional[dict] = None,
    risk_data: Optional[dict] = None,
) -> tuple[Action, List[str]]:
    """Apply all active filters to a raw action, returning (filtered_action, reasons).

    Each filter can only demote BUY/SHORT → HOLD, never promote.
    """
    reasons: List[str] = []
    filtered = raw_action

    # ── ADX sideways market filter — block BUY/SHORT in trending markets ──
    if cfg.adx.enabled and filtered in ("BUY", "SHORT"):
        if adx_val is not None and adx_val >= cfg.adx.max_adx:
            filtered = "HOLD"
            reasons.append(f"adx={adx_val:.1f}>={cfg.adx.max_adx}(trending_market)")
        elif adx_val is not None:
            reasons.append(f"adx={adx_val:.1f}<{cfg.adx.max_adx}(ranging_OK)")

    # ── RSI confirmation (oversold for BUY, overbought for SHORT) ────────
    if cfg.rsi.enabled and filtered == "BUY":
        if rsi_val is not None and rsi_val >= cfg.rsi.oversold:
            filtered = "HOLD"
            reasons.append(f"rsi={rsi_val:.1f}>={cfg.rsi.oversold}(not_oversold)")
        elif rsi_val is not None:
            reasons.append(f"rsi={rsi_val:.1f}OK(oversold)")
    elif cfg.short.rsi_overbought_required and filtered == "SHORT":
        if rsi_val is not None and rsi_val <= cfg.rsi.overbought:
            filtered = "HOLD"
            reasons.append(f"rsi={rsi_val:.1f}<={cfg.rsi.overbought}(not_overbought)")
        elif rsi_val is not None:
            reasons.append(f"rsi={rsi_val:.1f}OK(overbought)")

    # ── Volume confirmation ──────────────────────────────────────────────
    if cfg.volume.enabled and filtered in ("BUY", "SHORT"):
        if vol_ratio is not None and vol_ratio < cfg.volume.min_ratio:
            filtered = "HOLD"
            reasons.append(f"vol_ratio={vol_ratio:.2f}<{cfg.volume.min_ratio}(low_vol)")
        elif vol_ratio is not None:
            reasons.append(f"vol_ratio={vol_ratio:.2f}OK")

    # ── Volume Flow / OBV filter (P2) ─────────────────────────────────────────────────────────────
    if getattr(cfg, 'volume_flow', None) and getattr(cfg.volume_flow, 'enabled', False) and filtered == "BUY":
        if not obv_bullish:
            filtered = "HOLD"
            reasons.append("obv=bearish(distribution)")

    # ── Sentiment filter (DB) ─────────────────────────────────────────────────────────────
    overall_sentiment = (sentiment_data or {}).get("overall_sentiment")
    conf = float((sentiment_data or {}).get("confidence") or 0.0)
    contrarian_signal = (sentiment_data or {}).get("contrarian_signal")

    if filtered == "BUY" and cfg.signal.sentiment_filter_enabled and sentiment_data is not None:
        if conf < cfg.signal.min_sentiment_confidence:
            filtered = "HOLD"
            reasons.append(f"low_conf={conf:.2f}<{cfg.signal.min_sentiment_confidence}")
        elif cfg.signal.block_on_negative_sentiment and overall_sentiment == "negative":
            filtered = "HOLD"
            reasons.append("blocked:negative_sentiment")
        # Contrarian: extreme bullish is cautionary for mean reversion (crowded long)
        elif contrarian_signal == "extreme_bullish_caution":
            filtered = "HOLD"
            reasons.append("contrarian:extreme_bullish_caution")
        # Contrarian: extreme bearish is opportunity for mean reversion (oversold + fear)
        elif contrarian_signal == "extreme_bearish_opportunity":
            reasons.append("contrarian:extreme_bearish_opportunity(enhanced)")

    # ── Risk filter (DB) ─────────────────────────────────────────────────
    risk_score = (risk_data or {}).get("composite_risk_score")

    if filtered == "BUY" and cfg.signal.risk_filter_enabled and risk_score is not None:
        if risk_score > cfg.signal.max_risk_score:
            filtered = "HOLD"
            reasons.append(f"risk={risk_score:.1f}>{cfg.signal.max_risk_score}")

    return filtered, reasons
