"""Integration tests — cross-module compatibility of the analytical pipeline.

Validates that the layers compose end to end (validators -> metrics -> charts)
and that empty data propagates correctly rather than producing silent garbage.
"""

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.charts import (
    create_degradation_comparison_chart,
    create_pace_comparison_chart,
)
from src.metrics import (
    MetricError,
    calculate_pace_delta,
    get_best_qualifying_lap,
    get_observed_degradation_rate,
    get_race_pace,
)
from src.validators import filter_clean_stint_laps, validate_lap_data


def test_tyre_pipeline_end_to_end(make_laps):
    # raw laps -> filter_clean_stint_laps -> degradation rate -> bar chart.
    drivers = {
        "VER": [90 + 0.10 * t for t in range(1, 7)],
        "LEC": [91 + 0.04 * t for t in range(1, 7)],
    }
    rows = []
    for driver, lap_seconds in drivers.items():
        laps = make_laps(lap_seconds, drivers=[driver] * 6, tyre_life=list(range(1, 7)))
        clean = filter_clean_stint_laps(laps)
        rows.append(
            {"driver": driver, "degradation_rate": get_observed_degradation_rate(clean)}
        )

    data = pd.DataFrame(rows)
    figure = create_degradation_comparison_chart(data)
    rates = {row["driver"]: row["degradation_rate"] for row in rows}

    assert isinstance(figure, go.Figure)
    assert rates["VER"] == pytest.approx(0.10)


def test_pace_pipeline_end_to_end(make_laps):
    # raw laps -> validate -> metrics -> pace comparison chart.
    quali = validate_lap_data(make_laps([90.0, 90.5, 91.0]))
    race = validate_lap_data(make_laps([92.0, 92.5, 93.0]))

    best = get_best_qualifying_lap(quali)
    pace = get_race_pace(race)
    delta = calculate_pace_delta(best, pace)

    data = pd.DataFrame(
        {
            "driver": ["VER"],
            "qualifying_lap": [best["LapTime"]],
            "race_pace": [pace],
        }
    )
    figure = create_pace_comparison_chart(data)

    assert isinstance(figure, go.Figure)
    assert delta > pd.Timedelta(0)  # race slower than qualifying


def test_empty_data_propagation_raises(make_laps):
    # Laps too short to form a valid stint -> empty clean frame -> metric raises.
    clean = filter_clean_stint_laps(make_laps([90.0, 91.0]))
    assert clean.empty
    with pytest.raises(MetricError):
        get_observed_degradation_rate(clean)
