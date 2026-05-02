"""ADX trend-strength indicator — used as a SIDEWAYS market filter.

In mean reversion, ADX is used in reverse compared to trend following:
    - LOW ADX  (< threshold) → ranging/sideways market → ALLOW entries
    - HIGH ADX (> threshold) → strong trend → BLOCK entries

Mean reversion signals are unreliable in strongly trending markets.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import Indicator, IndicatorResult


class ADX(Indicator):
    """Average Directional Index.

    Used to detect ranging (low ADX) vs trending (high ADX) markets.
    For mean reversion: only enter when ADX < max_adx.
    """

    def __init__(self, period: int = 14, threshold: float = 25.0) -> None:
        self._period = period
        self._threshold = threshold

    @property
    def name(self) -> str:
        return f"ADX({self._period})"

    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        high = ohlc["High"]
        low = ohlc["Low"]
        close = ohlc["Close"]

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=ohlc.index,
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=ohlc.index,
        )

        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)

        atr = tr.ewm(alpha=1.0 / self._period, adjust=False).mean()
        smooth_plus = plus_dm.ewm(alpha=1.0 / self._period, adjust=False).mean()
        smooth_minus = minus_dm.ewm(alpha=1.0 / self._period, adjust=False).mean()

        plus_di = 100.0 * smooth_plus / atr.replace(0.0, np.nan)
        minus_di = 100.0 * smooth_minus / atr.replace(0.0, np.nan)
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
        adx = dx.ewm(alpha=1.0 / self._period, adjust=False).mean()
        adx.iloc[: self._period * 2] = np.nan

        return IndicatorResult(values=adx, name=self.name)

    def latest_value(self, ohlc: pd.DataFrame) -> Optional[float]:
        adx = self.compute(ohlc).values.dropna()
        return float(adx.iloc[-1]) if not adx.empty else None

    def is_ranging(self, ohlc: pd.DataFrame) -> bool:
        """Return True when ADX < threshold (market is ranging — allow MR entry)."""
        v = self.latest_value(ohlc)
        return v is not None and v < self._threshold

    def is_trending(self, ohlc: pd.DataFrame) -> bool:
        """Return True when ADX >= threshold (market is trending — block MR entry)."""
        v = self.latest_value(ohlc)
        return v is not None and v >= self._threshold
