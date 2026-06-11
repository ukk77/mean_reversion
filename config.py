"""Strategy configuration and parameters for Mean Reversion."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BollingerConfig:
    """Bollinger Bands — primary entry/exit signal."""
    period: int = 20
    std_dev: float = 2.0
    entry_zscore: float = -2.0    # BUY when z-score <= this (price below lower band)
    exit_zscore: float = 0.5      # EXIT (full) when z-score >= this (price reverts past mean)
    partial_exit_zscore: float = -0.2   # Exit first tranche at this z-score
    partial_exit_fraction: float = 0.5  # Fraction to sell at partial exit (0 = disabled)
    max_hold_days: int = 20       # Time stop - exit if held longer than this (0 = disabled)
    use_vwbb: bool = True         # Upgrade from standard Bollinger Bands to Volume-Weighted Bollinger Bands
    # Scale-in support (P2)
    scale_in_enabled: bool = True
    scale_in_zscore: float = -2.5 # Add 2nd tranche if z-score drops further




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
    trail: bool = True           # Ratchet stop up each day as price rises (never moves down)
    profit_stop_enabled: bool = True  # Trailing profit stop — exit if price falls N×ATR from peak since entry
    profit_stop_atr_mult: float = 3.0  # ATR multiplier for profit stop (wider than stop-loss)
    use_db_stop_when_available: bool = False  # Prefer suggested_stop_loss_pct from risk DB; fall back to local ATR


@dataclass
class VolumeConfig:
    """Volume confirmation — require above-average volume on entry."""
    enabled: bool = True
    period: int = 20
    min_ratio: float = 1.0


@dataclass
class VolatilityRegimeConfig:
    """Volatility regime — scale down position size in high-vol periods."""
    enabled: bool = True
    period: int = 30
    low_vol_threshold: float = 0.15
    high_vol_threshold: float = 0.30
    min_multiplier: float = 0.25


@dataclass
class MultiTimeframeConfig:
    enabled: bool = True
    fast_weeks: int = 4
    slow_weeks: int = 10

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
class PortfolioConstraintsConfig:
    """Cross-ticker portfolio risk and concentration limits.

    Applied only when using run_portfolio_backtest(). The single-ticker
    run_backtest() uses max_position_pct from PositionSizingConfig instead.
    """
    max_open_positions: int = 10           # max simultaneous positions (long+short); 0 = unlimited
    max_sector_exposure_pct: float = 40.0  # max % of NAV in any one sector; 0 = unlimited
    max_gross_exposure_pct: float = 100.0  # max (long+short notional) / NAV; 0 = unlimited
    adv_participation_pct: float = 2.5     # cap order at this % of daily volume; 0 = unlimited


# Sector classification used by portfolio constraint checks
SECTOR_MAP: Dict[str, str] = {
    "KMI": "Energy",
    "EQT": "Energy",
    "AAPL": "Technology",  "MSFT": "Technology",  "GOOGL": "Technology",
    "META": "Technology",  "NVDA": "Technology",  "QQQ":  "Technology",
    "XLK":  "Technology", "SMCI": "Technology",
    "MU": "Technology", "LITE": "Technology", "NVTS": "Technology", "ASML": "Technology",
    "AMZN": "Consumer Discretionary",  "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "MCD": "Consumer Discretionary", "BABA": "Consumer Discretionary",
    "JPM":  "Financials",  "XLF": "Financials", "V": "Financials", "MA": "Financials", "BRK.B": "Financials", "MARA": "Financials",
    "XOM":  "Energy",      "XLE": "Energy",
    "LLY":  "Healthcare",  "UNH": "Healthcare",  "XLV": "Healthcare",
    "ABBV": "Healthcare", "MRK": "Healthcare", "JNJ": "Healthcare",
    "WMT":  "Consumer Staples",         "XLP": "Consumer Staples", "COST": "Consumer Staples",
    "CAT":  "Industrials", "GE": "Industrials", "LMT": "Industrials", "RTX": "Industrials", "BA": "Industrials",
    "FCX": "Materials", "NUE": "Materials", "XLB": "Materials",
    "XLU":  "Utilities",
    "XLRE": "Real Estate",
    "SPY":  "Diversified",  "IWM": "Diversified", "SQQQ": "Inverse",
    "GLD":  "Commodities",
    "TLT": "Fixed Income",
}


@dataclass
class SignalConfig:
    """Signal generation settings."""
    sentiment_filter_enabled: bool = True
    min_sentiment_confidence: float = 0.4
    block_on_negative_sentiment: bool = True

    risk_filter_enabled: bool = True
    max_risk_score: float = 75.0


@dataclass
class PositionSizingConfig:
    """Position sizing settings."""
    base_position_pct: float = 10.0
    max_position_pct: float = 20.0

    sentiment_agree_mult: float = 1.2
    sentiment_neutral_mult: float = 0.8
    sentiment_disagree_mult: float = 0.5

    use_kelly_fraction: bool = True
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
    abs_return_hurdle: float = 0.03  # Cash + hurdle benchmark: rf + this rate


@dataclass
class VolumeFlowConfig:
    enabled: bool = False  # OBV bullish at lower-BB entry is contradictory; opt-in explicitly
    obv_ema_period: int = 10

@dataclass
class MeanReversionConfig:
    """Master configuration combining all sub-configs."""
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    rsi: RSIConfig = field(default_factory=RSIConfig)
    adx: ADXConfig = field(default_factory=ADXConfig)
    atr_stop: ATRStopConfig = field(default_factory=ATRStopConfig)
    volume: VolumeConfig = field(default_factory=VolumeConfig)
    volume_flow: VolumeFlowConfig = field(default_factory=VolumeFlowConfig)
    vol_regime: VolatilityRegimeConfig = field(default_factory=VolatilityRegimeConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    multi_tf: MultiTimeframeConfig = field(default_factory=MultiTimeframeConfig)
    
    # Allow parameter overrides per ticker (P2)
    ticker_overrides: Dict[str, Dict] = field(default_factory=dict)
    short: ShortConfig = field(default_factory=ShortConfig)
    portfolio_constraints: PortfolioConstraintsConfig = field(default_factory=PortfolioConstraintsConfig)
    sector_map: Dict[str, str] = field(default_factory=lambda: dict(SECTOR_MAP))

    tickers: List[str] = field(default_factory=lambda: [
        # Tech / Communication
        "AAPL", "MSFT", "GOOGL", "META", "NVDA",
        "MU", "LITE", "NVTS", "ASML",
        # Financials
        "JPM", "BRK.B",
        # Energy
        "XOM",
        # Healthcare
        "LLY",
        # Consumer Staples
        "WMT",
        # Sector ETFs — range-bound, good MR candidates
        "XLE", "XLU", "XLK", "XLP", "XLF", "XLV", "XLB", "XLRE",
        # Broad market & diversifying ETFs
        "IWM",   # Russell 2000 small caps — low correlation to tech holdings
        "GLD",   # Gold — genuine hedge, near-zero equity correlation
        # Stress tests for extreme dips
        "BA", "BABA"
    ])

    lookback_days: int = 7300  # 20 calendar years → ~5040 trading days


# Default configuration instance
DEFAULT_CONFIG = MeanReversionConfig()
