"""Volume confirmation indicator."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import Indicator, IndicatorResult


class VolumeConfirmation(Indicator):
    """Volume confirmation — require above-average volume on signal.

    Computes a rolling average volume ratio:
        ratio = current_volume / rolling_avg_volume

    A ratio >= min_ratio confirms the signal has volume backing.
    """

    def __init__(self, period: int = 20, min_ratio: float = 1.0) -> None:
        self._period = period
        self._min_ratio = min_ratio

    @property
    def name(self) -> str:
        return f"Volume({self._period},{self._min_ratio})"

    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        volume = ohlc["Volume"].astype(float)
        avg_vol = volume.rolling(self._period, min_periods=self._period).mean()
        ratio = volume / avg_vol.replace(0.0, float("nan"))
        return IndicatorResult(
            values=ratio,
            raw=pd.DataFrame({"volume": volume, "avg_volume": avg_vol, "ratio": ratio}),
            name=self.name,
        )

    def latest_ratio(self, ohlc: pd.DataFrame) -> Optional[float]:
        ratio = self.compute(ohlc).values.dropna()
        return float(ratio.iloc[-1]) if not ratio.empty else None

    def is_confirmed(self, ohlc: pd.DataFrame) -> bool:
        """Return True when current volume >= min_ratio * rolling average."""
        r = self.latest_ratio(ohlc)
        return r is not None and r >= self._min_ratio

class OBV(Indicator):
    """On-Balance Volume (OBV)."""

    def __init__(self, ema_period: int = 10) -> None:
        self._ema_period = ema_period

    @property
    def name(self) -> str:
        return f"OBV({self._ema_period})"

    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        close = ohlc["Close"]
        vol = ohlc["Volume"]
        change = close.diff()
        
        direction = change.map(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (direction * vol).cumsum()
        
        obv_ema = obv.ewm(span=self._ema_period, adjust=False).mean()
        return IndicatorResult(values=obv, raw=pd.DataFrame({"obv": obv, "obv_ema": obv_ema}), name=self.name)

    def is_bullish(self, ohlc: pd.DataFrame) -> bool:
        """Return True if OBV is above its EMA (accumulation)."""
        res = self.compute(ohlc)
        obv_df = res.raw.dropna()
        if obv_df.empty: return False
        last = obv_df.iloc[-1]
        return float(last["obv"]) > float(last["obv_ema"])
