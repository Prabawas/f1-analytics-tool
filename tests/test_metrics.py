"""Unit tests for src/metrics.py (pure analytical functions)."""

import pandas as pd
import pytest

from src.metrics import (
    MetricError,
    calculate_pace_delta,
    get_best_qualifying_lap,
    get_longest_stint,
    get_observed_degradation_rate,
    get_race_pace,
    get_stint_trendlines,
)


# --- get_best_qualifying_lap ---
def test_best_qualifying_lap_returns_fastest(make_laps):
    laps = make_laps([91.0, 90.0, 92.0], drivers=["VER", "LEC", "NOR"])
    fastest = get_best_qualifying_lap(laps)
    assert fastest["Driver"] == "LEC"
    assert fastest["LapTime"] == pd.Timedelta(seconds=90.0)


def test_best_qualifying_lap_empty_raises(make_laps):
    with pytest.raises(MetricError):
        get_best_qualifying_lap(make_laps([90.0]).iloc[0:0])


def test_best_qualifying_lap_missing_column_raises():
    with pytest.raises(MetricError):
        get_best_qualifying_lap(pd.DataFrame({"Driver": ["VER"]}))


# --- get_race_pace ---
def test_race_pace_is_median_of_non_pit_laps(make_laps):
    # Racing laps 90/91/92 (median 91); the 200s pit lap must be excluded.
    laps = make_laps([90.0, 91.0, 92.0, 200.0], pit_out=[False, False, False, True])
    assert get_race_pace(laps) == pd.Timedelta(seconds=91.0)


def test_race_pace_returns_timedelta(make_laps):
    assert isinstance(get_race_pace(make_laps([90.0, 92.0])), pd.Timedelta)


def test_race_pace_empty_raises(make_laps):
    with pytest.raises(MetricError):
        get_race_pace(make_laps([90.0]).iloc[0:0])


def test_race_pace_all_pit_laps_raises(make_laps):
    with pytest.raises(MetricError):
        get_race_pace(make_laps([90.0, 91.0], pit_in=[True, True]))


# --- calculate_pace_delta ---
def test_pace_delta_positive_when_race_slower(make_laps):
    quali = get_best_qualifying_lap(make_laps([90.0]))
    delta = calculate_pace_delta(quali, pd.Timedelta(seconds=92.0))
    assert delta == pd.Timedelta(seconds=2.0)


def test_pace_delta_negative_when_race_faster(make_laps):
    quali = get_best_qualifying_lap(make_laps([93.0]))
    delta = calculate_pace_delta(quali, pd.Timedelta(seconds=92.0))
    assert delta == pd.Timedelta(seconds=-1.0)


def test_pace_delta_missing_laptime_raises():
    with pytest.raises(MetricError):
        calculate_pace_delta(pd.Series({"Driver": "VER"}), pd.Timedelta(seconds=90.0))


# --- get_observed_degradation_rate ---
def test_degradation_rate_single_stint_exact_slope(make_laps):
    tyre_life = [1, 2, 3, 4, 5]
    laps = make_laps([90 + 0.1 * t for t in tyre_life], tyre_life=tyre_life)
    assert get_observed_degradation_rate(laps) == pytest.approx(0.1)


def test_degradation_rate_lap_weighted_mean(make_laps):
    # Stint 1: 4 laps, slope 0.2; Stint 2: 6 laps, slope 0.05.
    s1_life = [1, 2, 3, 4]
    s2_life = [1, 2, 3, 4, 5, 6]
    laps = make_laps(
        [90 + 0.2 * t for t in s1_life] + [95 + 0.05 * t for t in s2_life],
        stints=[1.0] * 4 + [2.0] * 6,
        tyre_life=s1_life + s2_life,
    )
    expected = (0.2 * 4 + 0.05 * 6) / 10
    assert get_observed_degradation_rate(laps) == pytest.approx(expected)


def test_degradation_rate_negative_slope(make_laps):
    tyre_life = [1, 2, 3, 4, 5]
    laps = make_laps([95 - 0.1 * t for t in tyre_life], tyre_life=tyre_life)
    assert get_observed_degradation_rate(laps) == pytest.approx(-0.1)


def test_degradation_rate_empty_raises(make_laps):
    with pytest.raises(MetricError):
        get_observed_degradation_rate(make_laps([90.0]).iloc[0:0])


# --- get_longest_stint ---
def test_longest_stint_returns_max_lap_count(make_laps):
    laps = make_laps([90.0] * 9, stints=[1.0] * 3 + [2.0] * 6)
    assert get_longest_stint(laps) == 6


def test_longest_stint_empty_raises(make_laps):
    with pytest.raises(MetricError):
        get_longest_stint(make_laps([90.0]).iloc[0:0])


# --- get_stint_trendlines ---
def test_stint_trendlines_structure(make_laps):
    tyre_life = [1, 2, 3, 4, 5]
    laps = make_laps(
        [90 + 0.1 * t for t in tyre_life],
        tyre_life=tyre_life,
        compounds=["SOFT"] * 5,
    )
    lines = get_stint_trendlines(laps)
    assert len(lines) == 1
    line = lines[0]
    assert line["stint"] == 1
    assert line["compound"] == "SOFT"
    assert line["x"] == [1.0, 5.0]
    assert line["y"][0] == pytest.approx(90.1)
    assert line["y"][1] == pytest.approx(90.5)


def test_stint_trendlines_empty_raises(make_laps):
    with pytest.raises(MetricError):
        get_stint_trendlines(make_laps([90.0]).iloc[0:0])
