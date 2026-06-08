---
description: Check all trading results and report a summary of findings across all 4 services
---

Run the cross-service results summary from the trading root. This queries all 4 SQLite databases (mean_reversion, trend_following, sentiment_analysis, risk_calculator) and prints a full report with anomaly detection.

1. Run the results summary script:
   `mean_reversion\venv\Scripts\python.exe get_result_data.py`
   Run from `c:\Users\ukard\OneDrive\Desktop\trading`.

2. Review the output sections:
   - **MEAN REVERSION** — daily run status, open positions, last 10 trades, realised P&L
   - **TREND FOLLOWING** — last trade date, open positions, last 10 trades, realised P&L
   - **SENTIMENT ANALYSIS** — total snapshots, staleness check, latest sentiment per ticker
   - **RISK CALCULATOR** — total snapshots, staleness check, latest score/bucket/Kelly per ticker
   - **ANOMALIES** — flagged issues requiring action (missing runs, stale data, high-risk tickers, large losses)

3. Act on any anomalies reported:
   - "MR has NOT run today" → run `/paper-trade` workflow
   - "TF no trades in N days" → check trend_following scheduler or run TF paper trade manually
   - "Sentiment/Risk data stale" → start the relevant FastAPI service and re-run `/signals`
   - "HIGH risk bucket" → review that ticker before allowing new entries
