---
description: Lint and validate the Mean Reversion strategy codebase
---

1. Verify the package imports cleanly from `c:\Users\ukard\OneDrive\Desktop\trading`:
   `mean_reversion\venv\Scripts\python.exe -c "import mean_reversion; from mean_reversion.config import MeanReversionConfig; from mean_reversion.signals.generator import generate_signal; print('All imports OK')"`

2. Confirm the CLI entry point is reachable:
   `mean_reversion\venv\Scripts\python.exe -m mean_reversion.cli --help`

3. Run flake8 linting if installed (skip otherwise):
   `mean_reversion\venv\Scripts\python.exe -m flake8 mean_reversion --select=E,W --max-line-length=120 --statistics --count`
   If flake8 is not installed: `mean_reversion\venv\Scripts\python.exe -m pip install flake8 --quiet` then re-run.

4. There are no formal pytest test files in this project. If the user wants to add tests, suggest creating `mean_reversion/tests/` and running:
   `mean_reversion\venv\Scripts\python.exe -m pytest mean_reversion/tests/ -v`

5. Report any import errors, CLI failures, or lint violations found.
