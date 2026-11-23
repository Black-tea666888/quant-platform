"""Checks for covariance shrinkage, risk parity, factor IC and extra statistics."""
import math

import numpy as np
import pandas as pd
import pytest

from quant_platform.quant_math import (
    calmar_ratio,
    factor_ic,
    ic_summary,
    ledoit_wolf_constant_correlation,
    risk_contributions,
    risk_parity_weights,
    sortino_ratio,
)


def _returns(seed=0, T=300, N=4):
    rng = np.random.default_rng(seed)
    cols = [f"A{i}" for i in range(N)]
    return pd.DataFrame(rng.normal(0, 0.01, size=(T, N)), columns=cols)


# ---- Ledoit-Wolf constant-correlation shrinkage ----

def test_shrunk_covariance_is_symmetric_and_positive_definite():
    cov, delta = ledoit_wolf_constant_correlation(_returns())
    M = cov.to_numpy()
    assert np.allclose(M, M.T)
    assert np.all(np.linalg.eigvalsh(M) > 0)
    assert 0.0 <= delta <= 1.0


def test_shrinkage_intensity_is_within_bounds_for_extreme_inputs():
    rng = np.random.default_rng(1)
    base = rng.normal(0, 0.01, size=(40, 1))
    # strongly correlated assets: the shrinkage target is close to the sample, so delta should be small or moderate
    X = pd.DataFrame(np.hstack([base + rng.normal(0, 1e-4, (40, 1)) for _ in range(5)]))
    _, delta = ledoit_wolf_constant_correlation(X)
    assert 0.0 <= delta <= 1.0


def test_single_asset_returns_sample_variance_and_zero_shrinkage():
    X = _returns(N=1)
    cov, delta = ledoit_wolf_constant_correlation(X)
    sample = float(((X.iloc[:, 0] - X.iloc[:, 0].mean()) ** 2).mean())
    assert delta == 0.0
    assert cov.iloc[0, 0] == pytest.approx(sample)


def test_missing_values_are_rejected():
    X = _returns()
    X.iloc[3, 1] = np.nan
    with pytest.raises(ValueError):
        ledoit_wolf_constant_correlation(X)


def test_too_few_observations_rejected():
    with pytest.raises(ValueError):
        ledoit_wolf_constant_correlation(_returns(T=2))


# ---- risk parity ----

def test_risk_parity_on_diagonal_matrix_is_inverse_volatility():
    vols = np.array([0.1, 0.2, 0.4])
    cov = pd.DataFrame(np.diag(vols ** 2), index=list("abc"), columns=list("abc"))
    w = risk_parity_weights(cov)
    expected = (1 / vols) / (1 / vols).sum()
    assert np.allclose(w.to_numpy(), expected, atol=1e-8)
    assert w.sum() == pytest.approx(1.0)


def test_risk_parity_equalises_risk_shares_with_correlation():
    cov, _ = ledoit_wolf_constant_correlation(_returns(seed=3, T=400, N=5))
    w = risk_parity_weights(cov)
    shares = risk_contributions(cov, w)
    assert np.allclose(shares.to_numpy(), 1 / 5, atol=1e-6)
    assert np.all(w.to_numpy() > 0)


def test_risk_parity_rejects_bad_input():
    with pytest.raises(ValueError):
        risk_parity_weights(pd.DataFrame([[1.0, 2.0], [0.0, 1.0]]))
    with pytest.raises(ValueError):
        risk_parity_weights(pd.DataFrame([[0.0, 0.0], [0.0, 1.0]]))


# ---- factor IC ----

def _factor_frames(seed=0, dates=60, assets=10):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=dates, freq="B")
    cols = [f"S{i}" for i in range(assets)]
    factor = pd.DataFrame(rng.normal(size=(dates, assets)), index=idx, columns=cols)
    return factor, idx, cols


def test_perfectly_monotone_factor_has_ic_one():
    factor, idx, cols = _factor_frames()
    forward = factor * 0.01 + 0.0          # same ordering as the factor
    ic = factor_ic(factor, forward)
    assert len(ic) == len(idx)
    assert np.allclose(ic.to_numpy(), 1.0)


def test_reversed_factor_has_ic_minus_one():
    factor, _, _ = _factor_frames()
    ic = factor_ic(factor, -factor)
    assert np.allclose(ic.to_numpy(), -1.0)


def test_random_factor_has_ic_near_zero_on_average():
    factor, _, _ = _factor_frames(seed=5, dates=400, assets=20)
    rng = np.random.default_rng(99)
    forward = pd.DataFrame(rng.normal(size=factor.shape), index=factor.index, columns=factor.columns)
    summary = ic_summary(factor_ic(factor, forward))
    assert abs(summary["mean_ic"]) < 0.05


def test_ic_skips_dates_with_too_few_assets():
    factor, idx, cols = _factor_frames(dates=5, assets=4)
    factor.iloc[0, 1:] = np.nan            # only one valid asset on the first date
    ic = factor_ic(factor, factor, min_assets=3)
    assert idx[0] not in ic.index


def test_ic_summary_fields():
    s = pd.Series([0.1, 0.2, 0.3, -0.1])
    out = ic_summary(s)
    assert out["n"] == 4
    assert out["mean_ic"] == pytest.approx(0.125)
    assert out["hit_rate"] == pytest.approx(0.75)
    assert out["icir"] == pytest.approx(out["mean_ic"] / out["ic_std"])


def test_ic_summary_too_few_dates_is_nan():
    out = ic_summary(pd.Series([0.2]))
    assert math.isnan(out["mean_ic"]) and out["n"] == 1


# ---- Sortino and Calmar ----

def test_sortino_known_value():
    r = pd.Series([0.02, -0.01, 0.03, -0.02])
    downside = np.minimum(r, 0.0)
    expected = r.mean() / math.sqrt(np.mean(downside ** 2)) * math.sqrt(252)
    assert sortino_ratio(r, 252) == pytest.approx(expected)


def test_sortino_without_downside_is_nan():
    assert math.isnan(sortino_ratio(pd.Series([0.01, 0.02]), 252))


def test_calmar_known_value():
    assert calmar_ratio(0.46, -0.24) == pytest.approx(0.46 / 0.24)


def test_calmar_zero_drawdown_is_nan():
    assert math.isnan(calmar_ratio(0.3, 0.0))
