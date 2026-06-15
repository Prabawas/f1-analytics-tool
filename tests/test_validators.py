"""Unit tests for src/validators.py (lap validation and stint filtering)."""

import pandas as pd
import pytest

from src.validators import (
    ValidationError,
    filter_clean_stint_laps,
    validate_lap_data,
)


# --- validate_lap_data ---
def test_validate_drops_null_laptime(make_laps):
    result = validate_lap_data(make_laps([90.0, None, 92.0]))
    assert len(result) == 2
    assert result["LapTime"].notna().all()


def test_validate_preserves_columns(make_laps):
    laps = make_laps([90.0, 91.0])
    assert list(validate_lap_data(laps).columns) == list(laps.columns)


def test_validate_empty_with_column_returns_empty(make_laps):
    assert validate_lap_data(make_laps([90.0]).iloc[0:0]).empty


def test_validate_missing_column_raises():
    with pytest.raises(ValidationError):
        validate_lap_data(pd.DataFrame({"Driver": ["VER"]}))


# --- filter_clean_stint_laps (each rule proven independently) ---
def test_filter_keeps_valid_stint(make_laps):
    assert len(filter_clean_stint_laps(make_laps([90.0] * 6))) == 6


def test_filter_removes_pit_laps(make_laps):
    laps = make_laps([90.0] * 6, pit_in=[True] + [False] * 5)
    assert len(filter_clean_stint_laps(laps)) == 5


def test_filter_removes_non_green_laps(make_laps):
    laps = make_laps([90.0] * 6, track_status=["4"] + ["1"] * 5)
    result = filter_clean_stint_laps(laps)
    assert len(result) == 5
    assert (result["TrackStatus"] == "1").all()


def test_filter_removes_lap_one(make_laps):
    laps = make_laps([90.0] * 6, lap_numbers=[1, 2, 3, 4, 5, 6])
    result = filter_clean_stint_laps(laps)
    assert len(result) == 5
    assert (result["LapNumber"] != 1).all()


def test_filter_removes_null_laptime(make_laps):
    laps = make_laps([90.0, 90.0, 90.0, 90.0, 90.0, None])
    assert len(filter_clean_stint_laps(laps)) == 5


def test_filter_removes_short_stint(make_laps):
    # Stint 1 has 6 valid laps; stint 2 has only 3 and is dropped entirely.
    laps = make_laps(
        [90.0] * 9,
        stints=[1.0] * 6 + [2.0] * 3,
        tyre_life=list(range(1, 7)) + list(range(1, 4)),
    )
    result = filter_clean_stint_laps(laps)
    assert set(result["Stint"].unique()) == {1.0}
    assert len(result) == 6


def test_filter_custom_min_stint_threshold(make_laps):
    laps = make_laps([90.0] * 4)
    assert filter_clean_stint_laps(laps).empty  # default min 5
    assert len(filter_clean_stint_laps(laps, min_stint_laps=3)) == 4


def test_filter_no_valid_stint_returns_empty(make_laps):
    assert filter_clean_stint_laps(make_laps([90.0, 91.0])).empty


def test_filter_missing_column_raises():
    bad = pd.DataFrame({"LapTime": [pd.Timedelta(seconds=90)]})
    with pytest.raises(ValidationError):
        filter_clean_stint_laps(bad)
