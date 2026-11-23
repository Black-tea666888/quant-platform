"""Covariance estimation, risk-parity weights, factor IC and extra return statistics.

Formulas follow the cited papers. Each function is checked by tests in tests/test_quant_math.py.

References:
- Ledoit, O. & Wolf, M. (2003). Honey, I shrunk the sample covariance matrix. (constant-correlation target)
- Spinu, F. (2013). Risk budgeting portfolios via cyclical coordinate descent (closed-form per-asset update).
- Spearman rank IC as used in factor research (IC = rank correlation of factor value with forward return).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def ledoit_wolf_constant_correlation(returns: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Shrink the sample covariance toward a constant-correlation target.

    returns: T x N table of periodic returns (rows = dates, columns = assets).
    Returns (shrunk covariance DataFrame, shrinkage intensity delta in [0, 1]).
    """
    if returns.isna().any().any():
        raise ValueError("returns contain missing values; align or fill them first")
    X = returns.to_numpy(dtype=float)
    T, N = X.shape
    if T < 3 or N < 1:
        raise ValueError("need at least 3 observations and 1 asset")
    X = X - X.mean(axis=0)
    S = X.T @ X / T                                  # sample covariance (1/T convention)
    s = np.sqrt(np.diag(S))
    corr = S / np.outer(s, s)
    if N == 1:
        return pd.DataFrame(S, index=returns.columns, columns=returns.columns), 0.0
    off = corr[np.triu_indices(N, k=1)]
    rbar = float(off.mean())
    F = rbar * np.outer(s, s)
    np.fill_diagonal(F, np.diag(S))

    # pi: sum of asymptotic variances of the sample covariance entries
    pi_mat = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            pi_mat[i, j] = np.mean((X[:, i] * X[:, j] - S[i, j]) ** 2)
    pi_hat = float(pi_mat.sum())

    # rho: asymptotic covariance between sample entries and the constant-correlation target
    rho_hat = float(np.trace(pi_mat))
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            theta_ii = np.mean((X[:, i] ** 2 - S[i, i]) * (X[:, i] * X[:, j] - S[i, j]))
            theta_jj = np.mean((X[:, j] ** 2 - S[j, j]) * (X[:, i] * X[:, j] - S[i, j]))
            rho_hat += (rbar / 2.0) * (math.sqrt(S[j, j] / S[i, i]) * theta_ii
                                        + math.sqrt(S[i, i] / S[j, j]) * theta_jj)

    gamma_hat = float(((F - S) ** 2).sum())
    if gamma_hat <= 0:
        delta = 1.0
    else:
        kappa = (pi_hat - rho_hat) / gamma_hat
        delta = max(0.0, min(1.0, kappa / T))

    shrunk = delta * F + (1.0 - delta) * S
    return pd.DataFrame(shrunk, index=returns.columns, columns=returns.columns), float(delta)


def risk_parity_weights(cov: pd.DataFrame, tol: float = 1e-10, max_iter: int = 1000) -> pd.Series:
    """Long-only weights where every asset contributes the same share of portfolio variance.

    Cyclical coordinate descent (Spinu 2013): for asset i, the target risk contribution is
    c = (w' Sigma w) / N, and w_i is set so that w_i * (Sigma w)_i = c. That gives
    a*x^2 + b*x - c = 0 with a = Sigma_ii and b = sum_{j != i} Sigma_ij * w_j.
    The target is recomputed from the current weights, so every update uses the same scale.
    Weights are renormalised to sum to 1 after each sweep.
    """
    S = cov.to_numpy(dtype=float)
    N = S.shape[0]
    if S.shape != (N, N) or not np.allclose(S, S.T):
        raise ValueError("cov must be a square symmetric matrix")
    if np.any(np.diag(S) <= 0):
        raise ValueError("every asset needs positive variance")
    w = np.full(N, 1.0 / N)
    for _ in range(max_iter):
        previous = w.copy()
        for i in range(N):
            a = S[i, i]
            b = float(S[i] @ w - S[i, i] * w[i])
            c = float(w @ S @ w) / N
            w[i] = (-b + math.sqrt(b * b + 4.0 * a * c)) / (2.0 * a)
        w = w / w.sum()
        if np.max(np.abs(w - previous)) < tol:
            break
    return pd.Series(w, index=cov.index, name="weight")


def risk_contributions(cov: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Each asset's share of portfolio variance (sums to 1)."""
    w = weights.reindex(cov.index).to_numpy(dtype=float)
    S = cov.to_numpy(dtype=float)
    marginal = S @ w
    total = float(w @ marginal)
    if total <= 0:
        raise ValueError("portfolio variance must be positive")
    return pd.Series(w * marginal / total, index=cov.index, name="risk_share")


def factor_ic(factor: pd.DataFrame, forward_returns: pd.DataFrame, min_assets: int = 3) -> pd.Series:
    """Per-date Spearman rank correlation between a factor and the next-period return.

    factor, forward_returns: dates x assets, aligned on the same index and columns.
    Dates with fewer than `min_assets` valid pairs are skipped.
    """
    f, r = factor.align(forward_returns, join="inner")
    out = {}
    for date in f.index:
        pair = pd.concat([f.loc[date], r.loc[date]], axis=1).dropna()
        if len(pair) < min_assets:
            continue
        rf = pair.iloc[:, 0].rank()
        rr = pair.iloc[:, 1].rank()
        if rf.std(ddof=0) == 0 or rr.std(ddof=0) == 0:
            continue
        out[date] = float(np.corrcoef(rf, rr)[0, 1])
    return pd.Series(out, dtype=float, name="ic")


def ic_summary(ic: pd.Series) -> dict:
    """Mean IC, its t-statistic, IC information ratio and hit rate. NaN when there are too few dates."""
    values = ic.dropna()
    n = len(values)
    if n < 2:
        return {"n": n, "mean_ic": math.nan, "ic_std": math.nan, "icir": math.nan, "t_stat": math.nan, "hit_rate": math.nan}
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    return {
        "n": n,
        "mean_ic": mean,
        "ic_std": std,
        "icir": mean / std if std > 0 else math.nan,
        "t_stat": mean / (std / math.sqrt(n)) if std > 0 else math.nan,
        "hit_rate": float((values > 0).mean()),
    }


def sortino_ratio(returns: pd.Series, periods_per_year: int, target: float = 0.0) -> float:
    """Annualised mean excess return over downside deviation (uses returns below target only)."""
    r = returns.dropna().astype(float)
    if r.empty:
        return math.nan
    downside = np.minimum(r - target, 0.0)
    dd = math.sqrt(float(np.mean(downside ** 2)))
    if dd == 0:
        return math.nan
    return float((r.mean() - target) / dd * math.sqrt(periods_per_year))


def calmar_ratio(cagr: float, max_drawdown: float) -> float:
    """CAGR divided by the absolute maximum drawdown. max_drawdown is negative, e.g. -0.24."""
    if max_drawdown is None or math.isnan(max_drawdown) or max_drawdown == 0:
        return math.nan
    return float(cagr / abs(max_drawdown))
