"""Bollinger Bands with z-score for mean reversion entry/exit signals.

The z-score measures how many standard deviations the current price is from
its N-period rolling mean:

    z = (price - rolling_mean) / rolling_std

Mean reversion logic:
    BUY  when z-score <= entry_zscore  (e.g. -2.0 → price below lower band)
    EXIT when z-score >= exit_zscore   (e.g.  0.0 → price reverts to mean)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import Indicator, IndicatorResult


class BollingerBands(Indicator):
    """Bollinger Bands with z-score output.

    `compute()` returns the z-score series as `values`, plus a `raw` DataFrame
    containing: middle, upper, lower, zscore, std.
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self._period = period
        self._std_dev = std_dev

    @property
    def name(self) -> str:
        return f"BB({self._period},{self._std_dev})"

    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        close = ohlc["Close"]
        middle = close.rolling(self._period, min_periods=self._period).mean()
        std = close.rolling(self._period, min_periods=self._period).std(ddof=1)
        upper = middle + self._std_dev * std
        lower = middle - self._std_dev * std
        zscore = (close - middle) / std.replace(0.0, np.nan)
        return IndicatorResult(
            values=zscore,
            raw=pd.DataFrame(
                {
                    "middle": middle,
                    "upper": upper,
                    "lower": lower,
                    "zscore": zscore,
                    "std": std,
                }
            ),
            name=self.name,
        )

    def signal_series(self, ohlc: pd.DataFrame) -> pd.Series:
        """Return the raw z-score series (not clamped to [-1,1])."""
        return self.compute(ohlc).values

    def latest_zscore(self, ohlc: pd.DataFrame) -> Optional[float]:
        """Return the most recent z-score value."""
        zs = self.compute(ohlc).values.dropna()
        return float(zs.iloc[-1]) if not zs.empty else None

    def is_below_lower_band(
        self, ohlc: pd.DataFrame, threshold: float = -2.0
    ) -> bool:
        """Return True when z-score <= threshold (price below lower band)."""
        zs = self.latest_zscore(ohlc)
        return zs is not None and zs <= threshold

    def is_at_or_above_mean(
        self, ohlc: pd.DataFrame, threshold: float = 0.0
    ) -> bool:
        """Return True when z-score >= threshold (price has reverted to mean)."""
        zs = self.latest_zscore(ohlc)
        return zs is not None and zs >= threshold

    def zscore_series(self, ohlc: pd.DataFrame) -> pd.Series:
        """Convenience alias for the z-score series."""
        return self.compute(ohlc).values
