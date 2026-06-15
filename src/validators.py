"""
Data validation and lap-filtering utilities.

Responsibilities:
- ``validate_lap_data``: drop laps with no recorded lap time (pace analysis)
- ``filter_clean_stint_laps``: keep clean green racing laps from stints long
  enough for tyre analysis (excludes pit / safety-car / lap-1 laps and short
  stints)

All failures are wrapped in ``ValidationError`` so callers catch a single type.
"""

from __future__ import annotations

import pandas as pd


class ValidationError(Exception):
    """Raised when lap data cannot be validated.

    Parallels ``DataLoadError`` in the data layer: gives callers a single,
    UI-friendly exception type to catch for validation failures.
    """


def validate_lap_data(laps: pd.DataFrame) -> pd.DataFrame:
    """Return only the laps that are valid for pace analysis.

    Applies a single explicit filtering rule and keeps a lap only if it passes.
    No lap-time values are transformed and no columns are added or removed —
    only rows are filtered.

    Filtering rule (removes rows; intentionally explicit and traceable rather
    than silent):
        1. Missing lap times removed   -> keep ``LapTime`` not null

    The ``Deleted`` flag is intentionally NOT applied: runtime inspection showed
    FastF1 stores ``None`` (dtype ``object``) rather than boolean ``False`` in
    this column, so ``Deleted == False`` removed every lap. Until the column's
    semantics are understood, validation is kept minimal for the MVP.

    The ``IsAccurate`` flag is likewise NOT applied here, to avoid discarding
    potentially useful race-pace laps too early; whether to use it is deferred
    to the metrics phase.

    Args:
        laps: A FastF1 lap table (e.g. from the data-loading layer).

    Returns:
        The subset of ``laps`` with a recorded lap time, with all original
        columns preserved, as a ``pandas.DataFrame``.

    Raises:
        ValidationError: If a required column is missing or the data cannot be
            validated.
    """
    try:
        # Rule 1: drop laps with no recorded lap time.
        has_lap_time = laps["LapTime"].notna()

        return laps[has_lap_time]
    except KeyError as exc:
        raise ValidationError(f"Lap data is missing a required column: {exc}.") from exc
    except Exception as exc:  # unexpected validation failure
        raise ValidationError("Could not validate the lap data.") from exc


def filter_clean_stint_laps(
    laps: pd.DataFrame, min_stint_laps: int = 5
) -> pd.DataFrame:
    """Return clean green racing laps from stints long enough for tyre analysis.

    Stricter than :func:`validate_lap_data`: this prepares laps for the
    "observed pace trend over tyre life" analysis, where confounded or
    unrepresentative laps must be removed before any slope is fitted. Operates
    on a single driver's race laps (e.g. from ``filter_laps_by_drivers``); stint
    grouping assumes single-driver input.

    Filtering rules (applied in order; each removes rows — explicit and
    traceable, never silent):
        1. Pit laps removed         -> ``PitInTime`` and ``PitOutTime`` both null
        2. Non-green laps removed   -> keep ``TrackStatus == "1"`` (fully green;
           any yellow/SC/VSC/red during the lap yields a different value)
        3. Race-start lap removed   -> drop ``LapNumber == 1``
        4. Missing lap times removed -> keep ``LapTime`` not null
        5. Short stints removed     -> after the above, drop any ``Stint`` left
           with fewer than ``min_stint_laps`` laps

    ``TyreLife`` is preserved (the metric needs it) but is not used for
    filtering; ``FreshTyre`` is intentionally ignored.

    Args:
        laps: One driver's race laps.
        min_stint_laps: Minimum clean laps a stint must retain to be kept.

    Returns:
        The clean laps belonging only to stints meeting the length threshold,
        with all original columns preserved. An empty ``DataFrame`` is returned
        when no stint qualifies — this is valid, not an error.

    Raises:
        ValidationError: If a required column is missing or filtering fails.
    """
    try:
        # Rule 1: drop pit in-laps and out-laps.
        not_pit = laps["PitInTime"].isna() & laps["PitOutTime"].isna()
        # Rule 2: keep only fully green laps (TrackStatus is a string).
        green = laps["TrackStatus"] == "1"
        # Rule 3: drop the standing-start lap.
        not_start = laps["LapNumber"] != 1
        # Rule 4: drop laps with no recorded lap time.
        has_lap_time = laps["LapTime"].notna()

        clean_laps = laps[not_pit & green & not_start & has_lap_time]

        # Rule 5: keep only stints that retain enough clean laps.
        stint_lap_counts = clean_laps.groupby("Stint")["Stint"].transform("size")
        return clean_laps[stint_lap_counts >= min_stint_laps]
    except KeyError as exc:
        raise ValidationError(f"Lap data is missing a required column: {exc}.") from exc
    except Exception as exc:  # unexpected filtering failure
        raise ValidationError("Could not filter clean stint laps.") from exc
