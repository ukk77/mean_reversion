---
description: Generate BUY/SELL/HOLD signals for the Mean Reversion strategy
---

1. Ask the user if they want signals for all configured tickers or a specific ticker (e.g. AAPL).

2. Run from the trading root `c:\Users\ukard\OneDrive\Desktop\trading`:
   - All tickers: `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli signals`
   - Single ticker: `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli signals --ticker <TICKER>`
   - JSON output: append `--json` to either command above.

3. The output columns are: TICKER, ACTION (BUY/SELL/HOLD), Z-SCORE, RSI, ADX, SENTIMENT, RISK, REASON.

4. Summarize any BUY or SELL signals — note the z-score direction (negative = oversold entry candidate), RSI confirmation, and sentiment label.
