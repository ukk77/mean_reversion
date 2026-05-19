---
description: Run a historical backtest for the Mean Reversion strategy
---

1. Ask the user for any of the following optional parameters (skip any not provided):
   - `--ticker TICKER` — single symbol, or all configured tickers by default
   - `--start YYYY-MM-DD` — backtest start date
   - `--end YYYY-MM-DD` — backtest end date (default: today)
   - `--bb-period N` — Bollinger Band period (default: 20)
   - `--bb-std N` — Bollinger Band std dev multiplier (default: 2.0)
   - `--entry-zscore N` — z-score threshold to enter long (default: -2.0)
   - `--exit-zscore N` — z-score threshold to exit long (default: 0.0)
   - `--capital N` — initial capital in USD (default: 100000)

2. Build and run the command from `c:\Users\ukard\OneDrive\Desktop\trading`:
   `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli backtest [--ticker TICKER] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--bb-period N] [--bb-std N] [--entry-zscore N] [--exit-zscore N] [--capital N]`

3. The results table shows per-ticker: RETURN%, CAGR%, SHARPE, CALMAR, MAX_DD%, PF (profit factor), AVG_HOLD, TRADES, WIN%.

4. Summarize key findings — flag any tickers with Sharpe < 0.5, max drawdown > 20%, or profit factor < 1.0 as needing review.
