"""Shared fixtures for the test suite (synthetic FastF1-style lap data).

Tests run entirely on hand-built DataFrames — no FastF1 calls, no network — so
they are fast and deterministic.
"""

import pandas as pd
import pytest


def _to_pit_times(flags, count):
    """Build a pit-time column: a Timedelta where the flag is True, else NaT."""
    if flags is None:
        return [pd.NaT] * count
    return [pd.Timedelta(seconds=1) if flag else pd.NaT for flag in flags]


@pytest.fixture
def make_laps():
    """Return a factory that builds synthetic lap DataFrames.

    Only ``lap_seconds`` is required. Other columns default to values that pass
    the validators: a single green stint, no pit laps, lap numbers starting at 2
    (so the lap-1 filter is not triggered), and increasing tyre life.
    """

    def _make(
        lap_seconds,
        *,
        drivers=None,
        lap_numbers=None,
        stints=None,
        tyre_life=None,
        compounds=None,
        track_status=None,
        pit_in=None,
        pit_out=None,
    ):
        count = len(lap_seconds)

        def column(values, fill):
            return values if values is not None else [fill] * count

        return pd.DataFrame(
            {
                "Driver": column(drivers, "VER"),
                "LapTime": pd.to_timedelta(lap_seconds, unit="s"),
                "LapNumber": column(lap_numbers, list(range(2, 2 + count))),
                "Stint": column(stints, 1.0),
                "TyreLife": column(tyre_life, list(range(1, 1 + count))),
                "Compound": column(compounds, "SOFT"),
                "TrackStatus": column(track_status, "1"),
                "PitInTime": _to_pit_times(pit_in, count),
                "PitOutTime": _to_pit_times(pit_out, count),
            }
        )

    return _make
