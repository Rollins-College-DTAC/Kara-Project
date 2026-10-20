"""Milestone 5 stage 4: the required forecast graph (references/statistics.md).

Forecasts the project's measure (mean emp_rate per published import, the same series the
anomaly trigger watches) with an ETS model (trend + the generator's own documented 12-import
seasonal cycle -- see generator/generate.py's batch_target_rate), compared with a naive "same
as last period" baseline and backtested on held-out data with MAE and MAPE.

This needs real numeric history to mean anything; tests use a short synthetic series, not a
mock, since the point is to check the forecasting logic actually works, not just that it's called.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

SEASONAL_PERIODS = 12


def naive_forecast(history: list[float], horizon: int) -> list[float]:
    """'Same as last period': repeat the last observed value for every future step."""
    return [history[-1]] * horizon


def fit_and_forecast(history: list[float], horizon: int,
                     seasonal_periods: int = SEASONAL_PERIODS) -> tuple[list[float], list[float], list[float]]:
    """Mean forecast, 95% prediction interval lower bound, upper bound -- each length horizon.
    Falls back to a trend-only model when there isn't yet two full seasonal cycles of history."""
    use_seasonal = len(history) >= 2 * seasonal_periods
    series = pd.Series(history, index=pd.RangeIndex(len(history)), dtype=float)
    model = ETSModel(series, trend="add", seasonal="add" if use_seasonal else None,
                     seasonal_periods=seasonal_periods if use_seasonal else None)
    fit = model.fit(disp=False)
    pred = fit.get_prediction(start=len(history), end=len(history) + horizon - 1)
    summary = pred.summary_frame(alpha=0.05)
    return summary["mean"].tolist(), summary["pi_lower"].tolist(), summary["pi_upper"].tolist()


def mae(actual: list[float], predicted: list[float]) -> float:
    return statistics.fmean(abs(a - p) for a, p in zip(actual, predicted))


def mape(actual: list[float], predicted: list[float]) -> float:
    """Percent error. Points where the actual value is 0 are skipped (undefined division)."""
    errors = [abs((a - p) / a) for a, p in zip(actual, predicted) if a]
    return statistics.fmean(errors) * 100 if errors else None


@dataclass
class BacktestResult:
    naive_mae: float
    naive_mape: float | None
    model_mae: float
    model_mape: float | None


def backtest(series: list[float], holdout: int, seasonal_periods: int = SEASONAL_PERIODS) -> BacktestResult:
    """Fit on everything except the last `holdout` points, forecast that far forward, and
    score both the model and the naive baseline against the real held-out values."""
    train, test = series[:-holdout], series[-holdout:]
    naive_pred = naive_forecast(train, holdout)
    model_pred, _, _ = fit_and_forecast(train, holdout, seasonal_periods)
    return BacktestResult(
        naive_mae=mae(test, naive_pred), naive_mape=mape(test, naive_pred),
        model_mae=mae(test, model_pred), model_mape=mape(test, model_pred),
    )
