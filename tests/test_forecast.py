"""Tests for agent/forecast.py: the required forecast graph.

Fits a real ETS model against a short synthetic series (trend + 12-import seasonal cycle +
noise, matching generator/generate.py's own batch_target_rate design) -- the point is to check
the forecasting logic actually works end to end, not just that statsmodels gets called.
"""

import math
import random

import pytest

from agent.forecast import backtest, fit_and_forecast, mae, mape, naive_forecast


def synthetic_series(n: int, seed: int = 3) -> list[float]:
    r = random.Random(seed)
    return [0.5 + 0.002 * i + 0.05 * math.sin(2 * math.pi * i / 12) + r.gauss(0, 0.01) for i in range(n)]


def test_naive_forecast_repeats_the_last_value():
    assert naive_forecast([1.0, 2.0, 3.0], horizon=4) == [3.0, 3.0, 3.0, 3.0]


def test_mae_and_mape_known_values():
    assert mae([10.0, 20.0], [12.0, 18.0]) == 2.0
    assert mape([10.0, 20.0], [11.0, 18.0]) == pytest.approx((10 + 10) / 2, abs=0.01)


def test_mape_skips_zero_actuals_instead_of_dividing_by_zero():
    assert mape([0.0, 10.0], [1.0, 11.0]) == pytest.approx(10.0, abs=0.01)


def test_mape_is_none_when_every_actual_is_zero():
    assert mape([0.0, 0.0], [1.0, 1.0]) is None


def test_fit_and_forecast_returns_the_right_shape():
    history = synthetic_series(40)
    mean, lo, hi = fit_and_forecast(history, horizon=6)
    assert len(mean) == len(lo) == len(hi) == 6
    assert all(a <= b for a, b in zip(lo, hi))  # the interval doesn't invert


def test_fit_and_forecast_prediction_interval_contains_the_point_forecast():
    history = synthetic_series(40)
    mean, lo, hi = fit_and_forecast(history, horizon=4)
    assert all(l <= m <= h for l, m, h in zip(lo, mean, hi))


def test_fit_and_forecast_falls_back_without_two_full_seasonal_cycles():
    short_history = synthetic_series(18)  # less than 2 * 12
    mean, lo, hi = fit_and_forecast(short_history, horizon=3)
    assert len(mean) == 3  # doesn't raise; just skips the seasonal component


def test_backtest_beats_naive_on_a_clearly_trending_seasonal_series():
    series = synthetic_series(60)
    result = backtest(series, holdout=12)
    assert result.model_mae < result.naive_mae
