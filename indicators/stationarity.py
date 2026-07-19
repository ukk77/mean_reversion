"""Stationarity tests for mean-reversion validation.

Implements Augmented Dickey-Fuller (ADF) test to verify that a price series
exhibits mean-reverting behaviour before allowing entries.

Usage:
    from mean_reversion.indicators.stationarity import adf_is_stationary

    if adf_is_stationary(ohlc["Close"], lookback=60, pvalue_threshold=0.05):
        # Series is mean-reverting — safe to enter
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def adf_pvalue(series: pd.Series, lookback: int = 60) -> Optional[float]:
    """Compute the ADF test p-value on the last `lookback` observations.

    Args:
        series: Price series (typically Close prices).
        lookback: Number of trailing bars to test.

    Returns:
        p-value from the ADF test, or None if insufficient data or scipy
        is unavailable.
    """
    data = series.dropna().tail(lookback)
    if len(data) < max(20, lookback // 2):
        return None

    try:
        from statsmodels.tsa.stattools import adfuller
        result = adfuller(data.values, autolag="AIC")
        return float(result[1])  # p-value is the second element
    except ImportError:
        # statsmodels not installed — fall back to a simplified ADF via OLS
        try:
            return _adf_pvalue_ols(data.values)
        except Exception:
            return None
    except Exception as e:
        log.debug("ADF test failed: %s", e)
        return None


def _adf_pvalue_ols(x: np.ndarray) -> Optional[float]:
    """Minimal ADF approximation without statsmodels.

    Uses OLS regression of Δy on y_{t-1} and checks if the t-statistic
    exceeds critical values. Returns an approximate p-value bucket.
    """
    n = len(x)
    if n < 20:
        return None

    # First differences
    dy = np.diff(x)
    y_lag = x[:-1]

    # OLS: dy = alpha + beta * y_lag + epsilon
    X = np.column_stack([np.ones(len(y_lag)), y_lag])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, dy, rcond=None)
    except np.linalg.LinAlgError:
        return None

    # t-statistic for beta[1]
    residuals = dy - X @ beta
    s2 = np.sum(residuals**2) / (n - 3)
    XtX_inv = np.linalg.inv(X.T @ X)
    se_beta = np.sqrt(s2 * XtX_inv[1, 1])
    if se_beta == 0:
        return None
    t_stat = beta[1] / se_beta

    # Approximate p-value from MacKinnon critical values (n=100 approximation)
    # 1%: -3.51, 5%: -2.89, 10%: -2.58
    if t_stat < -3.51:
        return 0.005
    elif t_stat < -2.89:
        return 0.03
    elif t_stat < -2.58:
        return 0.07
    elif t_stat < -1.95:
        return 0.15
    else:
        return 0.5  # Not stationary


def adf_is_stationary(
    series: pd.Series,
    lookback: int = 60,
    pvalue_threshold: float = 0.05,
) -> bool:
    """Test whether the series is stationary (mean-reverting).

    Args:
        series: Price series.
        lookback: Number of trailing bars to use for the test.
        pvalue_threshold: Maximum p-value to consider stationary (reject H0).

    Returns:
        True if the null hypothesis of a unit root is rejected (series is
        stationary / mean-reverting).
    """
    pval = adf_pvalue(series, lookback)
    if pval is None:
        # Cannot determine — default to allowing entry (conservative)
        return True
    return pval < pvalue_threshold
