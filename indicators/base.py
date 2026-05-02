"""Abstract base class for all mean reversion indicators."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class IndicatorResult:
    """Standardised output container for any indicator."""
    values: pd.Series
    raw: Optional[pd.DataFrame] = None
    name: str = ""


class Indicator(ABC):
    """Common interface for all indicators."""

    @abstractmethod
    def compute(self, ohlc: pd.DataFrame) -> IndicatorResult:
        """Compute the indicator from OHLCV DataFrame."""
        ...

    def signal_series(self, ohlc: pd.DataFrame) -> pd.Series:
        """Return a normalised signal series in [-1.0, +1.0]."""
        result = self.compute(ohlc)
        return result.values.map(
            lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)
        )

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable indicator name."""
        ...
