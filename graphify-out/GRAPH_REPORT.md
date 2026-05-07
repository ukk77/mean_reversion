# Graph Report - mean_reversion  (2026-05-06)

## Corpus Check
- 22 files · ~10,341 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 260 nodes · 416 edges · 17 communities (10 shown, 7 thin omitted)
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 73 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]

## God Nodes (most connected - your core abstractions)
1. `Portfolio` - 26 edges
2. `BollingerBands` - 17 edges
3. `ATR` - 17 edges
4. `RSI` - 16 edges
5. `_run_single_ticker()` - 15 edges
6. `ADX` - 15 edges
7. `compute_all_metrics()` - 14 edges
8. `IndicatorResult` - 14 edges
9. `VolatilityRegime` - 14 edges
10. `VolumeConfirmation` - 14 edges

## Surprising Connections (you probably didn't know these)
- `cmd_signals()` --calls--> `generate_signal()`  [INFERRED]
  cli.py → signals/generator.py
- `cmd_backtest()` --calls--> `run_backtest()`  [INFERRED]
  cli.py → backtest/engine.py
- `BacktestResult` --uses--> `MeanReversionConfig`  [INFERRED]
  backtest/engine.py → config.py
- `BacktestSummary` --uses--> `MeanReversionConfig`  [INFERRED]
  backtest/engine.py → config.py
- `Signal` --uses--> `MeanReversionConfig`  [INFERRED]
  signals/generator.py → config.py

## Communities (17 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (17): Portfolio, Simulated portfolio — tracks cash, positions, trades, and equity curve.  All pri, Execute a sell order (partial or full)., Liquidate the entire long position for a ticker., Sell a fraction of the long position (e.g., 0.5 = first tranche)., Open a short position. Cash receives proceeds. Returns True if executed., Record of a single simulated trade., Close (cover) a short position. Returns True if executed. (+9 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (26): cmd_backtest(), cmd_paper(), cmd_positions(), cmd_signals(), Command-line interface for the Mean Reversion strategy.  Usage (run from the tra, Run paper trading — process today's signals and update positions., Show current open paper positions with mark-to-market P&L., Print current BUY/SELL/HOLD signals for all (or one) ticker. (+18 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (21): BacktestResult, BacktestSummary, _get_as_of(), _load_risk_history(), _load_sentiment_history(), Core backtest engine for the Mean Reversion strategy.  Each ticker is simulated, Per-ticker backtest output., Aggregated backtest output across all tickers. (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (24): alpha_vs_benchmark(), avg_holding_days(), cagr(), calmar_ratio(), compute_all_metrics(), _log_returns(), max_drawdown(), profit_factor() (+16 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (11): Indicator, IndicatorResult, Standardised output container for any indicator., ATR, Volatility indicators: ATR (stop loss) and Volatility Regime filter., Return size multiplier [min_mult .. 1.0] based on volatility regime., Average True Range using Wilder smoothing.      Used to compute dynamic stop-los, Compute ATR-based stop price from entry.          Args:             ohlc: OHLCV (+3 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (21): ADXConfig, ATRStopConfig, BacktestConfig, BollingerConfig, PositionSizingConfig, Strategy configuration and parameters for Mean Reversion., Bollinger Bands — primary entry/exit signal., Backtest engine settings. (+13 more)

### Community 6 - "Community 6"
Cohesion: 0.13
Nodes (13): RSI momentum indicator for mean reversion oversold/overbought confirmation., Relative Strength Index using Wilder smoothing.      In mean reversion:, Return +1 when oversold, -1 when overbought, 0 otherwise., RSI, _fetch_latest_risk(), _fetch_latest_sentiment(), generate_all_signals(), generate_signal() (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (11): ABC, compute(), Indicator, Abstract base class for all mean reversion indicators., Common interface for all indicators., Return a normalised signal series in [-1.0, +1.0]., ADX, ADX trend-strength indicator — used as a SIDEWAYS market filter.  In mean revers (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.19
Nodes (18): get_cash_balance(), _get_conn(), get_portfolio_snapshot(), get_positions(), get_trades(), init_db(), log_trade(), SQLite storage for mean reversion paper trading positions and trade history.  DB (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (8): BollingerBands, Bollinger Bands with z-score for mean reversion entry/exit signals.  The z-score, Bollinger Bands with z-score output.      `compute()` returns the z-score series, Return the raw z-score series (not clamped to [-1,1])., Return the most recent z-score value., Return True when z-score <= threshold (price below lower band)., Return True when z-score >= threshold (price has reverted to mean)., Convenience alias for the z-score series.

## Knowledge Gaps
- **110 isolated node(s):** `Command-line interface for the Mean Reversion strategy.  Usage (run from the tra`, `Print current BUY/SELL/HOLD signals for all (or one) ticker.`, `Run a full historical backtest and print results.`, `Run paper trading — process today's signals and update positions.`, `Show current open paper positions with mark-to-market P&L.` (+105 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Portfolio` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.216) - this node is a cross-community bridge._
- **Why does `_run_single_ticker()` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 6`, `Community 7`, `Community 9`?**
  _High betweenness centrality (0.172) - this node is a cross-community bridge._
- **Why does `BacktestSummary` connect `Community 2` to `Community 0`, `Community 1`, `Community 4`, `Community 6`, `Community 7`, `Community 9`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `Portfolio` (e.g. with `BacktestResult` and `BacktestSummary`) actually correct?**
  _`Portfolio` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `BollingerBands` (e.g. with `BacktestResult` and `BacktestSummary`) actually correct?**
  _`BollingerBands` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ATR` (e.g. with `BacktestResult` and `BacktestSummary`) actually correct?**
  _`ATR` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `RSI` (e.g. with `BacktestResult` and `BacktestSummary`) actually correct?**
  _`RSI` has 7 INFERRED edges - model-reasoned connections that need verification._