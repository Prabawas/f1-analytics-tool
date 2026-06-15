"""
Plotly visualisation layer.

Chart builders (each returns a ``plotly.graph_objects.Figure``; no Streamlit
calls in this module):
- ``create_pace_comparison_chart``: grouped bar, quali best vs median race pace
- ``create_race_pace_trend_chart``: multi-driver lap-time-vs-lap-number lines
- ``create_degradation_comparison_chart``: per-driver observed pace-decay bars
- ``create_tire_scatter_chart``: single-driver TyreLife-vs-LapTime scatter with
  per-stint regression lines

All charts share a dark, transparent-background theme via ``_apply_base_layout``.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Distinct, colour-blind-safe colours so the two sessions are easy to tell apart.
_QUALIFYING_COLOR = "#1f77b4"  # blue
_RACE_COLOR = "#ff7f0e"  # orange

# Shared visual styling, applied to every chart for a consistent, professional look.
# Dark theme (matches the app's F1 dark palette); chart backgrounds are
# transparent so they blend into the Streamlit container.
_CHART_HEIGHT = 480
_FONT_FAMILY = "Helvetica, Arial, sans-serif"
_TEXT_COLOR = "#F5F5F5"
_GRID_COLOR = "#3A3A45"
_LEGEND_BG_COLOR = "rgba(31, 31, 43, 0.85)"
_LEGEND_BORDER_COLOR = "#3A3A45"

# Degradation bar colours: sign encodes pace getting slower vs improving.
_DECAY_COLOR = "#D62728"  # positive slope: pace decays with tyre age
_IMPROVEMENT_COLOR = "#2CA02C"  # negative slope: pace improves (fuel-masked)

# Official-style F1 tyre compound colours for the scatter markers.
_COMPOUND_COLORS = {
    "SOFT": "#DA291C",  # red
    "MEDIUM": "#FFD12E",  # yellow
    "HARD": "#FFFFFF",  # white
    "INTERMEDIATE": "#43B02A",  # green
    "WET": "#0067AD",  # blue
}
_DEFAULT_COMPOUND_COLOR = "#999999"  # unknown compound fallback
_MARKER_LINE_COLOR = "#15151E"  # dark outline separates markers on the dark plot
_MARKER_LINE_WIDTH = 1.5  # thicker outline keeps HARD readable in the legend
_TRENDLINE_COLOR = "#CCCCCC"  # light line stays visible on the dark plot


def _format_lap_time(total_seconds: float) -> str:
    """Format a lap time in seconds as a human-readable ``M:SS.mmm`` string.

    Used for on-bar labels and hover text so users read real lap times
    (e.g. ``1:18.550``) instead of raw seconds (e.g. ``78.55``).

    Args:
        total_seconds: Lap time in seconds.

    Returns:
        The lap time formatted as ``minutes:seconds.milliseconds``.
    """
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:06.3f}"


def _apply_base_layout(
    figure: go.Figure,
    *,
    title: str,
    xaxis_title: str,
    yaxis_title: str,
    legend_title: str,
) -> go.Figure:
    """Apply shared styling (theme, size, fonts, legend, gridlines) to a figure.

    Centralises the visual layout so both charts look consistent and
    portfolio-ready. Chart-specific settings (e.g. ``barmode``, ``hovermode``)
    are applied by the individual chart functions after this call.
    """
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        height=_CHART_HEIGHT,
        margin=dict(l=40, r=24, t=64, b=48),
        font=dict(family=_FONT_FAMILY, size=14, color=_TEXT_COLOR),
        title=dict(
            text=f"<b>{title.upper()}</b>",
            font=dict(size=18, color=_TEXT_COLOR),
            x=0,
            xanchor="left",
        ),
        xaxis_title=xaxis_title.upper(),
        yaxis_title=yaxis_title.upper(),
        legend=dict(
            title=legend_title.upper(),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=14, color=_TEXT_COLOR),
            bgcolor=_LEGEND_BG_COLOR,
            bordercolor=_LEGEND_BORDER_COLOR,
            borderwidth=1,
        ),
    )
    figure.update_xaxes(
        gridcolor=_GRID_COLOR,
        gridwidth=1,
        zeroline=False,
        tickfont=dict(color=_TEXT_COLOR),
    )
    figure.update_yaxes(
        gridcolor=_GRID_COLOR,
        gridwidth=1,
        zeroline=False,
        tickfont=dict(color=_TEXT_COLOR),
    )
    return figure


def create_pace_comparison_chart(data: pd.DataFrame) -> go.Figure:
    """Build a grouped bar chart comparing qualifying pace vs race pace.

    Purpose:
        Show, for each driver, their single best qualifying lap next to their
        median race pace, so a viewer can compare one-lap pace against sustained
        race pace across the field at a glance.

    Expected input:
        A ``DataFrame`` with one row per driver and the columns:
            - ``driver``: driver identifier (categorical X-axis value)
            - ``qualifying_lap``: best qualifying lap (``pandas.Timedelta``)
            - ``race_pace``: median race pace (``pandas.Timedelta``)

    Rendering notes:
        Plotly bar heights must be numeric, so the ``Timedelta`` values are
        converted to total seconds *for plotting only* (the data layer is not
        modified). Bar labels and hover text are formatted back to ``M:SS.mmm``
        so the times stay human-readable.

    Args:
        data: Per-driver pace comparison table (see "Expected input").

    Returns:
        A ``plotly.graph_objects.Figure`` containing two grouped bars per driver
        ("Best Qualifying Lap" and "Race Pace").
    """
    drivers = data["driver"]
    quali_seconds = data["qualifying_lap"].dt.total_seconds()
    race_seconds = data["race_pace"].dt.total_seconds()

    quali_labels = [_format_lap_time(value) for value in quali_seconds]
    race_labels = [_format_lap_time(value) for value in race_seconds]

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=drivers,
            y=quali_seconds,
            name="Best Qualifying Lap",
            marker_color=_QUALIFYING_COLOR,
            text=quali_labels,
            textposition="outside",
            hovertemplate="%{x}<br>Best Qualifying Lap: %{text}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            x=drivers,
            y=race_seconds,
            name="Race Pace",
            marker_color=_RACE_COLOR,
            text=race_labels,
            textposition="outside",
            hovertemplate="%{x}<br>Race Pace: %{text}<extra></extra>",
        )
    )
    _apply_base_layout(
        figure,
        title="Qualifying Pace vs Race Pace",
        xaxis_title="Driver",
        yaxis_title="Lap Time (sec)",
        legend_title="Session",
    )
    figure.update_layout(barmode="group")
    return figure


def create_race_pace_trend_chart(race_laps: pd.DataFrame) -> go.Figure:
    """Build a line chart of lap-by-lap race pace, one line per driver.

    Purpose:
        Show how each selected driver's lap times evolved across the race, so
        viewers can compare consistency, degradation, and pace swings between
        drivers on a shared axis.

    Expected input:
        A lap-level ``DataFrame`` for the selected drivers, with the columns:
            - ``Driver``: driver code (one line per unique value)
            - ``LapNumber``: lap sequence (X-axis)
            - ``LapTime``: lap time (``pandas.Timedelta``, Y-axis)

    Rendering notes:
        Plotly needs numeric Y values, so ``LapTime`` is converted to total
        seconds *for plotting only* (the data layer is untouched). Hover text is
        formatted back to ``M:SS.mmm`` to stay human-readable. Each driver gets a
        distinct line via Plotly's default colour cycle.

    Args:
        race_laps: Lap-level race data for the selected drivers.

    Returns:
        A ``plotly.graph_objects.Figure`` with one line per driver.
    """
    figure = go.Figure()
    for driver in race_laps["Driver"].unique():
        driver_laps = race_laps[race_laps["Driver"] == driver]
        lap_seconds = driver_laps["LapTime"].dt.total_seconds()
        formatted_times = [_format_lap_time(value) for value in lap_seconds]

        figure.add_trace(
            go.Scatter(
                x=driver_laps["LapNumber"],
                y=lap_seconds,
                mode="lines+markers",
                name=driver,
                marker=dict(size=5),
                customdata=formatted_times,
                hovertemplate="Lap %{x}: %{customdata}<extra>%{fullData.name}</extra>",
            )
        )

    _apply_base_layout(
        figure,
        title="Race Pace Trend",
        xaxis_title="Lap Number",
        yaxis_title="Lap Time (sec)",
        legend_title="Driver",
    )
    figure.update_layout(hovermode="x unified")
    return figure


def create_degradation_comparison_chart(data: pd.DataFrame) -> go.Figure:
    """Build a bar chart comparing observed pace decay per driver.

    Purpose:
        Compare drivers' observed pace change over tyre life at a glance.
        Bars are sorted best-to-worst; colour encodes the sign so the honest
        "decay vs improvement" framing is visible, with a zero baseline.

    Expected input:
        A ``DataFrame`` with one row per driver and the columns:
            - ``driver``: driver code (X-axis)
            - ``degradation_rate``: observed pace change in seconds per lap

    Framing:
        Positive = lap times rise with tyre age (decay); negative = pace
        improves (fuel burn / track evolution outweighs degradation). This is
        observed, not fuel-corrected.

    Args:
        data: Per-driver degradation table (see "Expected input").

    Returns:
        A ``plotly.graph_objects.Figure`` bar chart.
    """
    sorted_data = data.sort_values("degradation_rate")
    rates = sorted_data["degradation_rate"]
    bar_colors = [_DECAY_COLOR if rate >= 0 else _IMPROVEMENT_COLOR for rate in rates]
    bar_labels = [f"{rate:+.3f}" for rate in rates]

    figure = go.Figure(
        go.Bar(
            x=sorted_data["driver"],
            y=rates,
            marker_color=bar_colors,
            text=bar_labels,
            textposition="outside",
            hovertemplate="%{x}: %{y:+.3f} s/lap<extra></extra>",
        )
    )
    _apply_base_layout(
        figure,
        title="Observed Pace Decay Over Tyre Life",
        xaxis_title="Driver",
        yaxis_title="Pace Decay (sec/lap)",
        legend_title="",
    )
    figure.update_layout(showlegend=False)
    figure.add_hline(y=0, line_width=1, line_color="#888888")
    return figure


def create_tire_scatter_chart(
    clean_laps: pd.DataFrame, trendlines: list[dict]
) -> go.Figure:
    """Build a TyreLife-vs-LapTime scatter with one regression line per stint.

    Purpose:
        Show, for a single driver, how lap time changes with tyre age within
        each stint — making visible where the degradation slope comes from.

    Expected input:
        - ``clean_laps``: one driver's clean stint laps (``Stint``, ``TyreLife``,
          ``LapTime``), e.g. from ``filter_clean_stint_laps``.
        - ``trendlines``: per-stint line endpoints from
          ``metrics.get_stint_trendlines`` (keys ``stint``, ``compound``,
          ``x``, ``y``). This module performs no regression itself.

    Rendering notes:
        ``LapTime`` is converted to seconds *for plotting only*. Markers are
        coloured by tyre compound (official-style F1 colours) with a dark
        outline so white/yellow stay distinct; each stint's trend line uses a
        uniform light colour (a compound colour such as white would otherwise
        be invisible on the dark plot).

    Args:
        clean_laps: A single driver's clean stint laps.
        trendlines: Per-stint regression line endpoints from the metrics layer.

    Returns:
        A ``plotly.graph_objects.Figure`` scatter with per-stint trend lines.
    """
    figure = go.Figure()
    for line in trendlines:
        stint = line["stint"]
        compound = line["compound"]
        compound_color = _COMPOUND_COLORS.get(compound, _DEFAULT_COMPOUND_COLOR)

        stint_points = clean_laps[clean_laps["Stint"] == stint]
        lap_seconds = stint_points["LapTime"].dt.total_seconds()
        formatted_times = [_format_lap_time(value) for value in lap_seconds]

        figure.add_trace(
            go.Scatter(
                x=stint_points["TyreLife"],
                y=lap_seconds,
                mode="markers",
                name=f"Stint {stint} ({compound})",
                marker=dict(
                    color=compound_color,
                    size=8,
                    line=dict(width=_MARKER_LINE_WIDTH, color=_MARKER_LINE_COLOR),
                ),
                customdata=formatted_times,
                hovertemplate=(
                    "Tyre life %{x}<br>%{customdata}" "<extra>%{fullData.name}</extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=line["x"],
                y=line["y"],
                mode="lines",
                line=dict(color=_TRENDLINE_COLOR, width=2),
                showlegend=False,
                hoverinfo="skip",
            )
        )

    _apply_base_layout(
        figure,
        title="Observed Pace Over Tyre Life",
        xaxis_title="Tyre Life (laps)",
        yaxis_title="Lap Time (sec)",
        legend_title="Stint",
    )
    return figure
