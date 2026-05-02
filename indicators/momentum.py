"""RSI momentum indicator for mean reversion oversold/overbought confirmation."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import Indicator, IndicatorResult


class RSI(Indicator):
    """Relative Strength Index using Wilder smoothing.

    In mean reversion:
        - BUY confirmation: RSI < oversold  (e.g. 35) — confirms price is depressed
        - EXIT confirmation: RSI > overbought (e.g. 65) — optional exit signal
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 35.0,
        overbought: float = 65.0,
    ) -> None:
        self._period = period
        self._oversold = oversold
        self._overbought = overbought

    @property
    def name(self) -> str:
        return f"RSI({self._period})"

    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        close = ohlc["Close"]
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        avg_gain = gain.ewm(alpha=1.0 / self._period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / self._period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi.iloc[: self._period] = np.nan
        return IndicatorResult(values=rsi, name=self.name)

    def signal_series(self, ohlc: pd.DataFrame) -> pd.Series:
        """Return +1 when oversold, -1 when overbought, 0 otherwise."""
        rsi = self.compute(ohlc).values

        def _sig(v):
            if pd.isna(v):
                return 0.0
            if v < self._oversold:
                return 1.0
            if v > self._overbought:
                return -1.0
            return 0.0

        return rsi.map(_sig)

    def latest_value(self, ohlc: pd.DataFrame) -> Optional[float]:
        rsi = self.compute(ohlc).values.dropna()
        return float(rsi.iloc[-1]) if not rsi.empty else None

    def is_oversold(self, ohlc: pd.DataFrame) -> bool:
        v = self.latest_value(ohlc)
        return v is not None and v < self._oversold

    def is_overbought(self, ohlc: pd.DataFrame) -> bool:
        v = self.latest_value(ohlc)
        return v is not None and v > self._overbought
