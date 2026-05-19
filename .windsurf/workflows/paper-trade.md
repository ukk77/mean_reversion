---
description: Process today's paper trading signals and show positions for Mean Reversion
---

1. Process today's signals and update paper positions. Run from `c:\Users\ukard\OneDrive\Desktop\trading`:
   `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli paper`
   This evaluates current signals against open positions and executes BUY/SELL/HOLD actions in the paper portfolio (`mr_paper_trades.db`).

2. Show current open positions with mark-to-market P&L:
   `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli positions`

3. Summarize:
   - Actions taken today (BUY/SELL with ticker, shares, price, z-score)
   - Any realised P&L from closed trades
   - Total portfolio unrealised P&L and position count
