"""Lightweight tests for src/charts.py — contract only (Figure type, structure).

Plotly visual internals (colours, pixels) are intentionally not tested; these
confirm each builder returns a Figure with the expected trace structure.
"""

import pandas as pd
import plotly.graph_objects as go

from src.charts import (
    _format_lap_time,
    create_degradation_comparison_chart,
    create_pace_comparison_chart,
    create_race_pace_trend_chart,
    create_tire_scatter_chart,
)


def test_format_lap_time():
    assert _format_lap_time(78.55) == "1:18.550"
    assert _format_lap_time(90.0) == "1:30.000"
    assert _format_lap_time(45.25) == "0:45.250"


def test_pace_comparison_returns_figure_with_two_bars():
    data = pd.DataFrame(
        {
            "driver": ["VER", "LEC"],
            "qualifying_lap": pd.to_timedelta([90.0, 90.5], unit="s"),
            "race_pace": pd.to_timedelta([92.0, 92.5], unit="s"),
        }
    )
    figure = create_pace_comparison_chart(data)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 2


def test_race_trend_one_line_per_driver(make_laps):
    laps = make_laps(
        [90.0, 91.0, 90.0, 91.0],
        drivers=["VER", "VER", "LEC", "LEC"],
        lap_numbers=[1, 2, 1, 2],
    )
    figure = create_race_pace_trend_chart(laps)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 2


def test_degradation_chart_single_bar_trace():
    data = pd.DataFrame({"driver": ["VER", "LEC"], "degradation_rate": [0.05, -0.02]})
    figure = create_degradation_comparison_chart(data)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 1


def test_tire_scatter_two_traces_per_stint(make_laps):
    clean = make_laps(
        [90.0 + 0.1 * t for t in range(1, 6)],
        tyre_life=[1, 2, 3, 4, 5],
        compounds=["SOFT"] * 5,
    )
    trendlines = [{"stint": 1, "compound": "SOFT", "x": [1.0, 5.0], "y": [90.1, 90.5]}]
    figure = create_tire_scatter_chart(clean, trendlines)
    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 2  # markers + trendline


def test_chart_title_is_uppercase():
    data = pd.DataFrame({"driver": ["VER"], "degradation_rate": [0.05]})
    figure = create_degradation_comparison_chart(data)
    assert "OBSERVED PACE DECAY OVER TYRE LIFE" in figure.layout.title.text
