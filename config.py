"""Strategy configuration and parameters for Mean Reversion."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BollingerConfig:
    """Bollinger Bands — primary entry/exit signal."""
    period: int = 20
    std_dev: float = 2.0
    entry_zscore: float = -2.0    # BUY when z-score <= this (price below lower band)
    exit_zscore: float = 0.0      # EXIT (full) when z-score >= this (price reverts to mean)
    partial_exit_zscore: float = -0.5   # Exit first tranche at this z-score
    partial_exit_fraction: float = 0.5  # Fraction to sell at partial exit (0 = disabled)


@dataclass
class RSIConfig:
    """RSI oversold confirmation on entry."""
    enabled: bool = True
    period: int = 14
    oversold: float = 35.0        # Confirm BUY when RSI < this
    overbought: float = 65.0      # Optional exit confirmation


@dataclass
class ADXConfig:
    """Sideways market filter — block entries when market is strongly trending."""
    enabled: bool = True
    period: int = 14
    max_adx: float = 25.0         # Block BUY entries when ADX > this (trending)


@dataclass
class ATRStopConfig:
    """ATR-based dynamic stop loss."""
    enabled: bool = True
    period: int = 14
    multiplier: float = 2.5       # Wider than trend following — allow oscillation
    trail: bool = False           # No trailing for mean reversion (fixed stop from entry)
    use_db_stop_when_available: bool = False


@dataclass
class VolumeConfig:
    """Volume confirmation — require above-average volume on entry."""
    enabled: bool = True
    period: int = 20
    min_ratio: float = 1.0


@dataclass
class VolatilityRegimeConfig:
    """Volatility regime — scale down position size in high-vol periods."""
    enabled: bool = False
    period: int = 30
    low_vol_threshold: float = 0.15
    high_vol_threshold: float = 0.30
    min_multiplier: float = 0.25


@dataclass
class ShortConfig:
    """Short-side mean reversion — fade extreme overbought moves."""
    enabled: bool = True
    entry_zscore: float = 2.0      # SHORT when z-score >= this (price above upper band)
    exit_zscore: float = 0.0       # COVER when z-score <= this (price reverts to mean)
    partial_exit_zscore: float = 0.5   # Cover first tranche at this z-score
    partial_exit_fraction: float = 0.5
    rsi_overbought_required: bool = True  # Confirm SHORT when RSI overbought
    adx_filter: bool = True        # Block SHORT when market is trending


@dataclass
class SignalConfig:
    """Signal generation settings."""
    sentiment_filter_enabled: bool = False
    min_sentiment_confidence: float = 0.4
    block_on_negative_sentiment: bool = True

    risk_filter_enabled: bool = False
    max_risk_score: float = 75.0


@dataclass
class PositionSizingConfig:
    """Position sizing settings."""
    base_position_pct: float = 10.0
    max_position_pct: float = 20.0

    sentiment_agree_mult: float = 1.2
    sentiment_neutral_mult: float = 0.8
    sentiment_disagree_mult: float = 0.5

    use_kelly_fraction: bool = False
    kelly_cap: float = 0.25

    vol_regime_db_enabled: bool = False


@dataclass
class BacktestConfig:
    """Backtest engine settings."""
    initial_capital: float = 100_000.0
    commission_per_trade: float = 0.0
    commission_pct: float = 0.001
    slippage: float = 0.0005
    model_cash_interest: bool = True  # Accrue T-bill yield on uninvested cash

    benchmark_ticker: str = "SPY"
    compare_buy_and_hold: bool = True


@dataclass
class MeanReversionConfig:
    """Master configuration combining all sub-configs."""
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    rsi: RSIConfig = field(default_factory=RSIConfig)
    adx: ADXConfig = field(default_factory=ADXConfig)
    atr_stop: ATRStopConfig = field(default_factory=ATRStopConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    vol_regime: VolatilityRegimeConfig = field(default_factory=VolatilityRegimeConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    short: ShortConfig = field(default_factory=ShortConfig)

    tickers: List[str] = field(default_factory=lambda: [
        # Tech / Communication
        "AAPL", "MSFT", "GOOGL", "META", "NVDA",
        # Consumer Discretionary
        "TSLA",
        # Financials
        "JPM",
        # Energy
        "XOM",
        # Healthcare
        "LLY", "UNH",
        # Consumer Staples
        "WMT",
        # Sector ETFs — more range-bound, better mean reversion candidates
        "XLF", "XLE", "XLV", "XLU", "XLK", "XLP",
        # Removed: AMZN (trends during drawdowns, PF 0.71), CAT (PF 0.56, win rate 52%)
    ])

    lookback_days: int = 7300  # 20 calendar years → ~5040 trading days


# Default configuration instance
DEFAULT_CONFIG = MeanReversionConfig()
