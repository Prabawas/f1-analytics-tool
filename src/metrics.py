"""
Pace and tyre metrics calculation layer.

Responsibilities (single-driver, pure functions):
- Best qualifying lap (``get_best_qualifying_lap``)
- Median race pace, pit laps excluded (``get_race_pace``)
- Pace delta, race vs qualifying (``calculate_pace_delta``)
- Observed pace change over tyre life (``get_observed_degradation_rate``)
- Longest stint length (``get_longest_stint``)
- Per-stint regression endpoints for the tyre scatter (``get_stint_trendlines``)

All failures are wrapped in ``MetricError`` so callers catch a single type.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class MetricError(Exception):
    """Raised when a pace metric cannot be calculated.

    Parallels ``DataLoadError`` and ``ValidationError`` in the other layers:
    gives callers a single, UI-friendly exception type for metric failures.
    """


def get_best_qualifying_lap(laps: pd.DataFrame) -> pd.Series:
    """Return the single fastest qualifying lap.

    What is calculated:
        The fastest lap in the provided (validated) qualifying laps — i.e. the
        lap with the minimum ``LapTime``.

    Why this method:
        Best qualifying pace is, by definition, a driver's single quickest lap,
        so the metric is the minimum of ``LapTime``. ``idxmin`` locates that
        lap's row index directly, letting us return the *full* lap record
        rather than just the time value, with no transformation of the data.

    Assumptions:
        - ``laps`` has already been validated (deleted laps and null lap times
          removed), so the minimum ``LapTime`` is a genuine, recorded lap.
        - ``laps`` contains at least one lap; an empty table is treated as an
          error rather than returning nothing.
        - If two laps share the exact minimum time, the first occurrence is
          returned.

    Args:
        laps: Validated qualifying laps for analysis.

    Returns:
        The full lap record of the fastest lap, as a ``pandas.Series`` (one row,
        original columns preserved).

    Raises:
        MetricError: If ``laps`` is empty, ``LapTime`` is missing, or there are
            no laps to evaluate.
    """
    if laps.empty:
        raise MetricError(
            "Cannot find best qualifying lap; no laps available (empty input)."
        )

    try:
        fastest_index = laps["LapTime"].idxmin()
        return laps.loc[fastest_index]
    except KeyError as exc:
        raise MetricError(
            f"Cannot find best qualifying lap; missing column: {exc}."
        ) from exc
    except ValueError as exc:  # empty lap table -> idxmin has nothing to compare
        raise MetricError(
            "Cannot find best qualifying lap; no laps available."
        ) from exc


def get_race_pace(laps: pd.DataFrame) -> pd.Timedelta:
    """Return the race pace as the median of non-pit lap times.

    What is calculated:
        The median ``LapTime`` over racing laps only — pit in-laps and out-laps
        are excluded first. A single representative pace value, not a lap record.

    Why this method:
        Race pace should reflect competitive on-track performance, not
        operational anomalies. Pit in/out laps include the pit-lane drive-through
        (and the slow approach/exit), which are dramatically slower than green
        laps and inflate the pace if left in. Excluding them is why this metric
        is refined beyond a plain median of all laps. The median is then used
        because the remaining racing laps still contain outliers (safety-car
        laps, traffic, mistakes), and the median is robust to them.

    Filtering rule (before the median is taken):
        A lap is treated as a pit lap, and excluded, if either
        ``PitInTime`` is not null (in-lap) OR ``PitOutTime`` is not null
        (out-lap).

    Assumptions:
        - ``laps`` has already been validated (null lap times removed), so the
          median is taken over genuine recorded laps.
        - A non-null ``PitInTime``/``PitOutTime`` marks a pit in/out lap.
        - At least one racing lap remains after excluding pit laps; otherwise
          there is no representative pace to report and an error is raised
          rather than returning an undefined value.

    Args:
        laps: Validated race laps for analysis.

    Returns:
        The median racing-lap time as a ``pandas.Timedelta`` (a single value,
        with no transformation of the underlying times).

    Raises:
        MetricError: If ``laps`` is empty, a required column is missing, or no
            racing laps remain after excluding pit laps.
    """
    if laps.empty:
        raise MetricError(
            "Cannot calculate race pace; no laps available (empty input)."
        )

    try:
        # Rule 17: exclude pit in/out laps (operational anomalies, not pace).
        is_pit_lap = laps["PitInTime"].notna() | laps["PitOutTime"].notna()
        racing_laps = laps[~is_pit_lap]
    except KeyError as exc:
        raise MetricError(
            f"Cannot calculate race pace; missing column: {exc}."
        ) from exc

    if racing_laps.empty:
        raise MetricError(
            "Cannot calculate race pace; no racing laps remain after excluding "
            "pit laps."
        )

    return racing_laps["LapTime"].median()


def calculate_pace_delta(
    qualifying_lap: pd.Series, race_pace: pd.Timedelta
) -> pd.Timedelta:
    """Return the pace delta between race pace and best qualifying pace.

    What is calculated:
        ``race_pace - qualifying_lap["LapTime"]`` — how much slower (or faster)
        a driver's typical race pace is compared to their single best
        qualifying lap.

    Why this method / interpretation:
        Subtracting in this direction gives an intuitive, human-readable sign:
        a POSITIVE delta means race pace is slower than qualifying pace (the
        normal case, since race laps carry fuel and tyre wear); a negative
        delta would mean race pace is faster than the best qualifying lap.

    Assumptions:
        - ``qualifying_lap`` is a single lap record (e.g. from
          :func:`get_best_qualifying_lap`) containing a ``LapTime`` value.
        - ``race_pace`` is a representative race pace value (e.g. from
          :func:`get_race_pace`).
        - Both times are native ``Timedelta`` values, so the result is a native
          ``Timedelta`` with no formatting or unit conversion applied.

    Args:
        qualifying_lap: The fastest qualifying lap record (``pandas.Series``).
        race_pace: The median race pace (``pandas.Timedelta``).

    Returns:
        The pace delta as a ``pandas.Timedelta`` (positive = race slower than
        qualifying).

    Raises:
        MetricError: If ``qualifying_lap`` has no ``LapTime`` value or the two
            inputs cannot be subtracted.
    """
    try:
        return race_pace - qualifying_lap["LapTime"]
    except KeyError as exc:
        raise MetricError(
            "Cannot calculate pace delta; qualifying lap has no 'LapTime'."
        ) from exc
    except TypeError as exc:
        raise MetricError(
            "Cannot calculate pace delta; inputs are not compatible time values."
        ) from exc


def _fit_stint(stint_laps: pd.DataFrame) -> tuple[float, float]:
    """Fit ``LapTime`` (seconds) against ``TyreLife`` for one stint.

    Shared by :func:`get_observed_degradation_rate` and
    :func:`get_stint_trendlines` so the per-stint regression is computed in
    exactly one place (no duplicated polyfit logic).

    Args:
        stint_laps: Clean laps for a single stint (``TyreLife`` and ``LapTime``).

    Returns:
        The ``(slope, intercept)`` of the least-squares line — seconds per lap
        and seconds, respectively.
    """
    tyre_life = stint_laps["TyreLife"]
    lap_seconds = stint_laps["LapTime"].dt.total_seconds()
    slope, intercept = np.polyfit(tyre_life, lap_seconds, 1)
    return float(slope), float(intercept)


def get_observed_degradation_rate(clean_laps: pd.DataFrame) -> float:
    """Return a driver's observed pace change over tyre life (seconds per lap).

    What is calculated:
        A single rate (s/lap) summarising how a driver's lap time changes with
        tyre age. For each stint, a linear least-squares slope of ``LapTime``
        (in seconds) against ``TyreLife`` is fitted with ``numpy.polyfit``; the
        per-stint slopes are then combined into one driver-level value by a
        lap-weighted mean.

    Why this method:
        - Per-stint slopes (not a whole-race fit): ``TyreLife`` resets each stint
          and compounds differ, so only within-stint trends are meaningful.
        - Lap-weighted mean (weight = each stint's clean-lap count): the variance
          of an OLS slope shrinks sharply with stint length, so longer stints are
          far more reliable and should count more. Weighting by lap count is the
          interpretable balance; full inverse-variance weighting is a possible
          future refinement.

    Assumptions / framing:
        - ``clean_laps`` is a single driver's output from
          ``filter_clean_stint_laps`` (pit/SC/lap-1 laps removed; only stints
          with enough clean laps; ``TyreLife`` and ``LapTime`` present).
        - This is an OBSERVED pace trend, NOT fuel-corrected. A positive value
          means lap times rise with tyre age (degradation); a negative value
          means fuel burn / track evolution outweighs degradation.

    Args:
        clean_laps: Validated clean stint laps for a single driver.

    Returns:
        The lap-weighted mean per-stint slope, in seconds per lap, as a float.

    Raises:
        MetricError: If there are no laps/stints to fit or a required column is
            missing.
    """
    if clean_laps.empty:
        raise MetricError(
            "Cannot compute degradation rate; no clean stint laps available."
        )

    try:
        weighted_slope_sum = 0.0
        total_laps = 0
        for _, stint_laps in clean_laps.groupby("Stint"):
            stint_slope, _ = _fit_stint(stint_laps)
            stint_lap_count = len(stint_laps)
            weighted_slope_sum += stint_slope * stint_lap_count
            total_laps += stint_lap_count
    except KeyError as exc:
        raise MetricError(
            f"Cannot compute degradation rate; missing column: {exc}."
        ) from exc

    return float(weighted_slope_sum / total_laps)


def get_longest_stint(race_laps: pd.DataFrame) -> int:
    """Return the driver's longest stint length, in laps.

    What is calculated:
        The maximum number of laps run on a single set of tyres — the largest
        ``Stint`` group by lap count.

    Why this input:
        Computed from the raw race laps (NOT the cleaned tyre-analysis laps):
        the cleaned laps drop pit/SC/short-stint laps and would undercount the
        true stint length. Counting laps per ``Stint`` group (rather than using
        ``max(TyreLife)``) avoids over-counting stints started on used tyres.

    Args:
        race_laps: A single driver's race laps.

    Returns:
        The longest stint length in laps, as an ``int``.

    Raises:
        MetricError: If ``race_laps`` is empty or ``Stint`` is missing.
    """
    if race_laps.empty:
        raise MetricError("Cannot determine longest stint; no laps available.")

    try:
        stint_lengths = race_laps.groupby("Stint")["Stint"].size()
    except KeyError as exc:
        raise MetricError(
            f"Cannot determine longest stint; missing column: {exc}."
        ) from exc

    return int(stint_lengths.max())


def get_stint_trendlines(clean_laps: pd.DataFrame) -> list[dict]:
    """Return per-stint regression line endpoints for the tyre scatter.

    What is calculated:
        For each stint, the fitted ``LapTime``-vs-``TyreLife`` line (via the
        shared :func:`_fit_stint` helper), reduced to its two endpoints, plus the
        stint number and tyre compound. This lets ``charts.py`` draw the trend
        line and label it without performing any regression itself.

    Args:
        clean_laps: A single driver's clean stint laps (from
            ``filter_clean_stint_laps``).

    Returns:
        One dict per stint with keys: ``stint`` (int), ``compound`` (str),
        ``x`` (``[tyre_life_min, tyre_life_max]``), and ``y`` (the fitted lap
        time in seconds at those two points).

    Raises:
        MetricError: If ``clean_laps`` is empty or a required column is missing.
    """
    if clean_laps.empty:
        raise MetricError(
            "Cannot build stint trendlines; no clean stint laps available."
        )

    try:
        trendlines: list[dict] = []
        for stint, stint_laps in clean_laps.groupby("Stint"):
            slope, intercept = _fit_stint(stint_laps)
            tyre_life_min = float(stint_laps["TyreLife"].min())
            tyre_life_max = float(stint_laps["TyreLife"].max())
            trendlines.append(
                {
                    "stint": int(stint),
                    "compound": stint_laps["Compound"].iloc[0],
                    "x": [tyre_life_min, tyre_life_max],
                    "y": [
                        slope * tyre_life_min + intercept,
                        slope * tyre_life_max + intercept,
                    ],
                }
            )
    except KeyError as exc:
        raise MetricError(
            f"Cannot build stint trendlines; missing column: {exc}."
        ) from exc

    return trendlines
