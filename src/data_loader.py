"""
FastF1 data loading layer.

Responsibilities:
- Initialise the FastF1 on-disk cache
- Retrieve available Grand Prix events for a season (for UI selection)
- Load qualifying and race sessions
- Extract raw lap data from a session
- Filter laps to selected drivers (FastF1 ``pick_drivers``)

All failures are wrapped in ``DataLoadError`` so callers catch a single type.
"""

from __future__ import annotations

from pathlib import Path

import fastf1
import pandas as pd
from fastf1.core import Session

# Project-local FastF1 cache directory (project_root/cache), anchored to this
# file so it resolves correctly regardless of the current working directory.
_CACHE_DIR: Path = Path(__file__).resolve().parent.parent / "cache"


class DataLoadError(Exception):
    """Raised when F1 session data cannot be retrieved or loaded.

    Wraps the various underlying FastF1 / network failures in a single,
    UI-friendly error type so callers only need to catch one exception.
    """


def initialize_fastf1_cache() -> None:
    """Enable FastF1's on-disk cache in the project-local cache directory.

    Creates the cache directory (``project_root/cache``) if it does not yet
    exist, then enables FastF1's official caching mechanism so subsequent
    session loads are served from disk instead of re-downloading.

    Should be called once at application start-up, before any session is loaded.

    Raises:
        DataLoadError: If the cache directory cannot be created or FastF1
            caching cannot be enabled.
    """
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(_CACHE_DIR))
    except Exception as exc:  # filesystem / FastF1 cache configuration failure
        raise DataLoadError(
            f"Could not initialise the FastF1 cache at {_CACHE_DIR}."
        ) from exc


def get_available_events(year: int) -> list[str]:
    """Return the Grand Prix event names for a given season.

    Used to populate the Grand Prix selector in the UI.

    Args:
        year: Four-digit championship season (e.g. 2024).

    Returns:
        Grand Prix event names in calendar order (e.g. ``["Bahrain Grand Prix", ...]``).

    Raises:
        DataLoadError: If the season is invalid or the schedule cannot be
            retrieved (e.g. FastF1 API/network failure).
    """
    try:
        schedule = fastf1.get_event_schedule(year)
    except ValueError as exc:
        raise DataLoadError(f"Invalid or unavailable season: {year}.") from exc
    except Exception as exc:  # network / FastF1 API failure
        raise DataLoadError(
            f"Could not retrieve the event schedule for {year}."
        ) from exc

    events = schedule["EventName"].tolist()
    if not events:
        raise DataLoadError(f"No Grand Prix events found for season {year}.")
    return events


def load_qualifying_session(year: int, grand_prix: str) -> Session:
    """Load the qualifying session for a given Grand Prix.

    Args:
        year: Four-digit championship season (e.g. 2024).
        grand_prix: Grand Prix event name, as returned by
            :func:`get_available_events` (e.g. ``"Monaco Grand Prix"``).

    Returns:
        A loaded FastF1 ``Session`` for qualifying.

    Raises:
        DataLoadError: If the season/Grand Prix is invalid, the FastF1 API
            fails, or the qualifying session has no data.
    """
    return _load_session(year, grand_prix, "Q")


def load_race_session(year: int, grand_prix: str) -> Session:
    """Load the race session for a given Grand Prix.

    Args:
        year: Four-digit championship season (e.g. 2024).
        grand_prix: Grand Prix event name, as returned by
            :func:`get_available_events` (e.g. ``"Monaco Grand Prix"``).

    Returns:
        A loaded FastF1 ``Session`` for the race.

    Raises:
        DataLoadError: If the season/Grand Prix is invalid, the FastF1 API
            fails, or the race session has no data.
    """
    return _load_session(year, grand_prix, "R")


def extract_session_laps(session: Session) -> pd.DataFrame:
    """Return the raw lap data from a loaded FastF1 session.

    Provides direct access to FastF1's official ``session.laps`` table without
    any filtering, cleaning, validation, or transformation — those belong to
    later phases. The returned object is FastF1's ``Laps`` table, which is a
    ``pandas.DataFrame`` subclass, so its column structure is whatever FastF1
    provides for the session (no column names are assumed here).

    Args:
        session: A loaded FastF1 ``Session`` (see :func:`load_qualifying_session`
            or :func:`load_race_session`).

    Returns:
        The session's raw lap data as a ``pandas.DataFrame``.

    Raises:
        DataLoadError: If lap data cannot be accessed (e.g. the session was not
            loaded).
    """
    try:
        return session.laps
    except Exception as exc:  # session not loaded / lap data unavailable
        raise DataLoadError(
            "Could not extract lap data; the session may not be loaded."
        ) from exc


def filter_laps_by_drivers(
    laps: pd.DataFrame, selected_drivers: list[str]
) -> pd.DataFrame:
    """Return only the laps belonging to the selected drivers.

    Uses FastF1's official ``Laps.pick_drivers`` helper, which accepts driver
    abbreviations (e.g. ``["VER", "NOR", "LEC"]``) and is the supported way to
    select drivers from a lap table. No cleaning, validation, or removal of
    deleted/inaccurate laps is performed here — this only narrows the rows to
    the chosen drivers.

    Args:
        laps: A FastF1 lap table, as returned by :func:`extract_session_laps`.
        selected_drivers: Driver abbreviations to keep (e.g. ``["VER", "NOR"]``).

    Returns:
        The subset of ``laps`` for the selected drivers, as a
        ``pandas.DataFrame``.

    Raises:
        DataLoadError: If the laps cannot be filtered (e.g. an unexpected lap
            object that does not support driver selection).
    """
    try:
        return laps.pick_drivers(selected_drivers)
    except Exception as exc:  # unexpected object / FastF1 filtering failure
        raise DataLoadError("Could not filter laps by the selected drivers.") from exc


def _load_session(year: int, grand_prix: str, identifier: str) -> Session:
    """Resolve and load a single session for a Grand Prix.

    Shared implementation behind :func:`load_qualifying_session` and
    :func:`load_race_session`. ``identifier`` follows the FastF1 convention
    (``"Q"`` for qualifying, ``"R"`` for race).

    Args:
        year: Four-digit championship season.
        grand_prix: Grand Prix event name.
        identifier: FastF1 session identifier (``"Q"`` or ``"R"``).

    Returns:
        A loaded FastF1 ``Session``.

    Raises:
        DataLoadError: On invalid season/Grand Prix, API failure, or missing
            session data.
    """
    try:
        session = fastf1.get_session(year, grand_prix, identifier)
    except ValueError as exc:
        raise DataLoadError(
            f"Could not find session '{identifier}' for {grand_prix} {year}."
        ) from exc
    except Exception as exc:  # network / FastF1 API failure
        raise DataLoadError(
            f"FastF1 failed to resolve {grand_prix} {year} ({identifier})."
        ) from exc

    try:
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as exc:  # missing data / network failure during load
        raise DataLoadError(
            f"No data available for {grand_prix} {year} ({identifier})."
        ) from exc

    return session
