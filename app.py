"""
APEX Telemetry — Formula 1 qualifying vs race pace analytics dashboard.

Streamlit entry point and orchestration only (no analytics logic lives here).
Flow: sidebar selectors (season, Grand Prix, drivers) -> load qualifying and
race laps (cached) -> per-driver pace metrics with KPI cards and the
comparison/trend charts -> a tyre-analysis section presenting observed pace
change over tyre life (not fuel-corrected). A failing driver is skipped with a
warning (graceful degradation); fatal states render a branded panel.
"""

from typing import cast

import pandas as pd
import streamlit as st

from src.charts import (
    create_degradation_comparison_chart,
    create_pace_comparison_chart,
    create_race_pace_trend_chart,
    create_tire_scatter_chart,
)
from src.data_loader import (
    DataLoadError,
    extract_session_laps,
    filter_laps_by_drivers,
    get_available_events,
    initialize_fastf1_cache,
    load_qualifying_session,
    load_race_session,
)
from src.metrics import (
    MetricError,
    get_best_qualifying_lap,
    get_longest_stint,
    get_observed_degradation_rate,
    get_race_pace,
    get_stint_trendlines,
)
from src.validators import (
    ValidationError,
    filter_clean_stint_laps,
    validate_lap_data,
)

st.set_page_config(
    page_title="APEX Telemetry",
    page_icon="🏎️",
    layout="wide",
)

# Single contained style block (race-engineering aesthetic: dark, square,
# thin red accents, telemetry mono numerals). Styling targets our own classes
# and standard elements only — no fragile Streamlit internal selectors.
_CUSTOM_CSS = """
<style>
:root {
  --f1-red: #E10600;
  --card: #1F1F2B;
  --line: #2E2E3A;
  --text: #F5F5F5;
  --muted: #9A9AA8;
  --green: #2CA02C;
  --sans: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: "SF Mono", Menlo, Consolas, "Roboto Mono", monospace;
}
.stApp { font-family: var(--sans); }
.stApp hr { border-color: var(--line); margin: 1.1rem 0; }
.hero {
  border-left: 4px solid var(--f1-red);
  padding: 0.1rem 0 0.1rem 1rem;
  margin-bottom: 0.3rem;
}
.hero-mark {
  font-size: 2.6rem;
  font-weight: 800;
  letter-spacing: 3px;
  line-height: 1;
  color: var(--text);
}
.hero-mark .accent { color: var(--f1-red); }
.hero-rule {
  height: 2px;
  width: 220px;
  background: var(--f1-red);
  margin: 0.55rem 0 0.5rem 0;
}
.hero-tag {
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 4px;
  text-transform: uppercase;
  color: var(--f1-red);
}
.hero-desc {
  font-size: 0.9rem;
  letter-spacing: 1px;
  color: var(--muted);
  margin-top: 0.15rem;
}
.section-head {
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0.45rem;
  margin: 1.7rem 0 1rem 0;
}
.section-index {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 1rem;
  color: var(--f1-red);
}
.section-title {
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--text);
}
.sub-label {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0.5rem 0 0.2rem 0;
}
.kpi-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-left: 4px solid var(--f1-red);
  border-radius: 0;
  padding: 0.85rem 1rem 0.95rem 1rem;
  height: 100%;
}
.kpi-label {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 1.6px;
  text-transform: uppercase;
  color: var(--muted);
}
.kpi-value {
  font-family: var(--mono);
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
.kpi-sub {
  font-family: var(--mono);
  font-size: 0.95rem;
  color: var(--f1-red);
  font-variant-numeric: tabular-nums;
}
.kpi-help {
  margin-left: 0.4rem;
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: normal;
  color: var(--muted);
  cursor: help;
}
.kpi-help:hover {
  color: var(--f1-red);
}
.hero-meta {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 1.5px;
  color: var(--muted);
  margin-top: 0.35rem;
}
.side-brand {
  font-size: 1.2rem;
  font-weight: 800;
  letter-spacing: 2px;
  color: var(--text);
}
.side-brand .accent { color: var(--f1-red); }
.side-brand-sub {
  font-size: 0.66rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  margin-top: 0.1rem;
}
.side-section {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--f1-red);
  border-left: 3px solid var(--f1-red);
  padding-left: 0.5rem;
  margin: 0.4rem 0 0.7rem 0;
}
.state-panel {
  background: var(--card);
  border: 1px solid var(--line);
  border-left: 4px solid var(--f1-red);
  padding: 1.1rem 1.3rem;
  margin: 1rem 0;
}
.state-title {
  font-family: var(--mono);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--f1-red);
}
.state-msg {
  font-size: 0.9rem;
  color: var(--text);
  margin-top: 0.4rem;
}
.state-hint {
  font-size: 0.8rem;
  color: var(--muted);
  margin-top: 0.25rem;
}
.footer {
  border-top: 1px solid var(--line);
  margin-top: 2.5rem;
  padding-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.footer-info {
  font-size: 0.75rem;
  color: var(--muted);
  letter-spacing: 0.5px;
  line-height: 1.7;
}
.footer-info .accent { color: var(--f1-red); }
.cta-link {
  display: inline-block;
  border: 1px solid var(--f1-red);
  color: var(--f1-red);
  padding: 0.45rem 1rem;
  text-decoration: none;
  font-family: var(--mono);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
.cta-link:hover {
  background: var(--f1-red);
  color: #ffffff;
}
.status-strip { margin-top: 1rem; }
.status-title {
  font-family: var(--mono);
  font-size: 0.66rem;
  letter-spacing: 2px;
  color: var(--muted);
  margin-bottom: 0.35rem;
}
.status-item {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--text);
  margin-right: 1.4rem;
}
.status-dot {
  color: var(--green);
  margin-right: 0.35rem;
}
.footer-disclaimer {
  font-size: 0.68rem;
  color: var(--muted);
  letter-spacing: 0.5px;
  margin-top: 0.9rem;
}
@media (max-width: 768px) {
  .hero-mark { font-size: 2rem; letter-spacing: 2px; }
  .section-title { font-size: 0.95rem; letter-spacing: 2px; }
  .kpi-value { font-size: 1.65rem; }
}
@media (max-width: 480px) {
  .hero-mark { font-size: 1.6rem; letter-spacing: 1px; }
  .hero-rule { width: 150px; }
  .hero-tag { letter-spacing: 2.5px; font-size: 0.72rem; }
  .kpi-value { font-size: 1.5rem; }
}
</style>
"""

st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)


def render_section_header(index: str, title: str) -> None:
    """Render a telemetry-style section header (e.g. ``01 / PACE ANALYSIS``)."""
    st.markdown(
        f'<div class="section-head">'
        f'<span class="section-index">{index} /</span>'
        f'<span class="section-title">{title}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_kpi_card(column, label: str, value: str, sub: str, tooltip: str) -> None:
    """Render a square, red-accented KPI card with mono numerals into a column.

    The ``tooltip`` is attached to a small "?" helper icon beside the label via
    the native HTML ``title`` attribute (no custom CSS tooltip), so the hover
    target is the icon rather than the whole card.
    """
    column.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}'
        f'<span class="kpi-help" title="{tooltip}">?</span>'
        f"</div>"
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_state_panel(title: str, message: str, hint: str = "") -> None:
    """Render a branded empty/error state panel (matches the dashboard style)."""
    hint_html = f'<div class="state-hint">{hint}</div>' if hint else ""
    st.markdown(
        f'<div class="state-panel">'
        f'<div class="state-title">{title}</div>'
        f'<div class="state-msg">{message}</div>'
        f"{hint_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


# Season options are static; Grand Prix and drivers are loaded dynamically.
SEASONS = [2023, 2024, 2025]

# GitHub repository link for the footer CTA.
GITHUB_URL = "https://github.com/Prabawas/f1-analytics-tool"


@st.cache_data(show_spinner="FETCHING RACE CALENDAR...")
def load_events(year: int) -> list[str]:
    """Return real Grand Prix events for a season, cached so it is fetched once.

    Non-race entries (e.g. "Pre-Season Testing") are removed by keeping only
    events whose name contains "Grand Prix" — the naming convention for every
    championship race weekend.
    """
    events = get_available_events(year)
    return [event for event in events if "grand prix" in event.lower()]


@st.cache_data(show_spinner="FETCHING DRIVER LINEUP...")
def load_drivers(year: int, grand_prix: str) -> list[str]:
    """Return the drivers who appear in the qualifying session, sorted.

    Qualifying (not race) is the source of the driver list, per spec. The driver
    codes come from the verified ``Driver`` column of the session laps. Cached so
    the qualifying session is only loaded once per (season, Grand Prix).
    """
    initialize_fastf1_cache()
    session = load_qualifying_session(year, grand_prix)
    laps = extract_session_laps(session)
    return sorted(laps["Driver"].dropna().unique().tolist())


@st.cache_data(show_spinner=False, ttl=21600, max_entries=15)
def load_qualifying_laps(year: int, grand_prix: str) -> pd.DataFrame:
    """Return the qualifying session laps, cached per (season, Grand Prix).

    Caches the extracted lap table so repeated Streamlit reruns (e.g. changing a
    selector) reuse it instead of reloading the FastF1 session each time.
    """
    initialize_fastf1_cache()
    session = load_qualifying_session(year, grand_prix)
    return extract_session_laps(session)


@st.cache_data(show_spinner=False, ttl=21600, max_entries=15)
def load_race_laps(year: int, grand_prix: str) -> pd.DataFrame:
    """Return the race session laps, cached per (season, Grand Prix).

    Caches the extracted lap table so repeated Streamlit reruns reuse it instead
    of reloading the FastF1 session each time.
    """
    initialize_fastf1_cache()
    session = load_race_session(year, grand_prix)
    return extract_session_laps(session)


def format_lap_time(value: pd.Timedelta) -> str:
    """Format a lap-time Timedelta as a human-readable ``M:SS.mmm`` string."""
    total_seconds = value.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:06.3f}"


def format_pace_delta(value: pd.Timedelta) -> str:
    """Format a pace-delta Timedelta as a signed seconds string, e.g. ``+5.122s``."""
    return f"{value.total_seconds():+.3f}s"


with st.sidebar:
    st.markdown(
        '<div class="side-brand">🏎️ APEX <span class="accent">TELEMETRY</span></div>'
        '<div class="side-brand-sub">Race Intelligence Platform</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(
        '<div class="side-section">Race Selection</div>', unsafe_allow_html=True
    )
    YEAR = cast(
        int,
        st.selectbox(
            "Season", SEASONS, index=1, help="Championship season to analyse."
        ),
    )

    try:
        available_events = load_events(YEAR)
    except DataLoadError:
        render_state_panel(
            "⚠ CALENDAR UNAVAILABLE",
            f"Could not load the race calendar for {YEAR}.",
            "Check your connection and try again.",
        )
        st.stop()

    GRAND_PRIX = cast(
        str,
        st.selectbox(
            "Grand Prix",
            available_events,
            help="Race weekend for the selected season.",
        ),
    )

    try:
        available_drivers = load_drivers(YEAR, GRAND_PRIX)
    except DataLoadError:
        render_state_panel(
            "⚠ DRIVER DATA UNAVAILABLE",
            f"Could not load the driver lineup for {GRAND_PRIX} {YEAR}.",
            "Try a different Grand Prix.",
        )
        st.stop()

    DRIVERS = st.multiselect(
        "Drivers",
        available_drivers,
        default=available_drivers[:3],
        help="Select 2 to 5 drivers to compare.",
    )

st.markdown(
    '<div class="hero">'
    '<div class="hero-mark">APEX <span class="accent">TELEMETRY</span></div>'
    '<div class="hero-rule"></div>'
    '<div class="hero-tag">Race Intelligence Platform</div>'
    '<div class="hero-desc">Formula 1 Performance Analytics Dashboard</div>'
    '<div class="hero-meta">'
    "TRACK PERFORMANCE INTELLIGENCE · FASTF1 DATA · 2023–2025"
    "</div>"
    "</div>",
    unsafe_allow_html=True,
)
st.caption(f"{GRAND_PRIX} {YEAR} · Drivers: {', '.join(DRIVERS)}")

# --- Enforce driver-count rules (2-5) before any expensive loading ---
if len(DRIVERS) < 2:
    render_state_panel(
        "⚠ SELECT DRIVERS",
        "Choose at least 2 drivers to begin the comparison.",
    )
    st.stop()

if len(DRIVERS) > 5:
    render_state_panel(
        "⚠ DRIVER LIMIT",
        "Select a maximum of 5 drivers.",
    )
    st.stop()

# --- Expensive work: load sessions + compute per-driver metrics ---
with st.spinner(
    "FETCHING OFFICIAL FORMULA 1 SESSION DATA…  \n"
    "First load may take 10–20 seconds; subsequent loads are cached."
):
    # Load session laps once, cached so reruns do not reload FastF1 sessions.
    try:
        quali_laps = load_qualifying_laps(YEAR, GRAND_PRIX)
        race_laps = load_race_laps(YEAR, GRAND_PRIX)
    except DataLoadError:
        render_state_panel(
            "⚠ DATA UNAVAILABLE",
            "Selected race data could not be processed.",
            "Try a different Grand Prix or season.",
        )
        st.stop()

    # Per-driver processing with graceful degradation (Rule 18).
    rows: list[dict] = []
    driver_race_frames: list[pd.DataFrame] = []
    for driver in DRIVERS:
        try:
            driver_quali = validate_lap_data(
                filter_laps_by_drivers(quali_laps, [driver])
            )
            best_qualifying_lap = get_best_qualifying_lap(driver_quali)

            driver_race = validate_lap_data(filter_laps_by_drivers(race_laps, [driver]))
            race_pace = get_race_pace(driver_race)

            rows.append(
                {
                    "driver": driver,
                    "qualifying_lap": best_qualifying_lap["LapTime"],
                    "race_pace": race_pace,
                }
            )
            driver_race_frames.append(driver_race)
        except (DataLoadError, ValidationError, MetricError) as exc:
            st.warning(f"Skipping {driver}: {exc}")

# --- Guard: nothing succeeded ---
if not rows:
    render_state_panel(
        "⚠ NO DATA",
        "None of the selected drivers could be processed.",
        "Try different drivers or another race.",
    )
    st.stop()

# --- Build comparison table ---
comparison_data = pd.DataFrame(rows)

# --- KPI summary cards ---
fastest_quali = comparison_data.loc[comparison_data["qualifying_lap"].idxmin()]
best_race = comparison_data.loc[comparison_data["race_pace"].idxmin()]
pace_deltas = comparison_data["race_pace"] - comparison_data["qualifying_lap"]
smallest_delta_index = pace_deltas.idxmin()
smallest_delta_driver = comparison_data.loc[smallest_delta_index, "driver"]

render_section_header("01", "Pace Analysis")
kpi_quali, kpi_race, kpi_delta = st.columns(3)
render_kpi_card(
    kpi_quali,
    "Fastest Qualifying",
    fastest_quali["driver"],
    format_lap_time(fastest_quali["qualifying_lap"]),
    "Driver with the fastest single qualifying lap.",
)
render_kpi_card(
    kpi_race,
    "Best Race Pace",
    best_race["driver"],
    format_lap_time(best_race["race_pace"]),
    "Driver with the fastest median race pace (pit laps excluded).",
)
render_kpi_card(
    kpi_delta,
    "Smallest Pace Delta",
    smallest_delta_driver,
    format_pace_delta(pace_deltas.loc[smallest_delta_index]),
    "Driver whose race pace is closest to their qualifying pace.",
)

# --- Render comparison chart ---
st.divider()
figure = create_pace_comparison_chart(comparison_data)
st.plotly_chart(figure, use_container_width=True)

# --- Render race pace trend chart (below the bar chart) ---
st.divider()
trend_data = pd.concat(driver_race_frames, ignore_index=True)
trend_figure = create_race_pace_trend_chart(trend_data)
st.plotly_chart(trend_figure, use_container_width=True)

# =====================================================================
# Tyre Analysis — additive section; pace analysis above is unchanged.
# =====================================================================
render_section_header("02", "Tyre Analysis")
st.caption("Observed pace change over tyre life — not fuel-corrected.")

with st.spinner("COMPUTING TYRE PERFORMANCE MODEL..."):
    tyre_rows: list[dict] = []
    driver_clean_laps: dict[str, pd.DataFrame] = {}
    for driver in DRIVERS:
        try:
            driver_race_laps = filter_laps_by_drivers(race_laps, [driver])
            clean_stint_laps = filter_clean_stint_laps(driver_race_laps)
            degradation_rate = get_observed_degradation_rate(clean_stint_laps)
            longest_stint = get_longest_stint(driver_race_laps)
            tyre_rows.append(
                {
                    "driver": driver,
                    "degradation_rate": degradation_rate,
                    "longest_stint": longest_stint,
                }
            )
            driver_clean_laps[driver] = clean_stint_laps
        except (DataLoadError, ValidationError, MetricError) as exc:
            st.warning(f"Tyre analysis skipped for {driver}: {exc}")

if not tyre_rows:
    render_state_panel(
        "⚠ TYRE DATA UNAVAILABLE",
        "Not enough clean stint data for the selected drivers.",
        "Try drivers with longer green-flag stints.",
    )
else:
    tyre_data = pd.DataFrame(tyre_rows)
    best_management = tyre_data.loc[tyre_data["degradation_rate"].idxmin()]
    highest_wear = tyre_data.loc[tyre_data["degradation_rate"].idxmax()]
    longest = tyre_data.loc[tyre_data["longest_stint"].idxmax()]

    tyre_kpi_low, tyre_kpi_high, tyre_kpi_stint = st.columns(3)
    render_kpi_card(
        tyre_kpi_low,
        "Lowest Pace Decay",
        best_management["driver"],
        f"{best_management['degradation_rate']:+.3f} sec/lap",
        "Driver whose pace changes least (or improves) over tyre life.",
    )
    render_kpi_card(
        tyre_kpi_high,
        "Highest Pace Decay",
        highest_wear["driver"],
        f"{highest_wear['degradation_rate']:+.3f} sec/lap",
        "Driver whose pace decays most over tyre life.",
    )
    render_kpi_card(
        tyre_kpi_stint,
        "Longest Stint",
        longest["driver"],
        f"{int(longest['longest_stint'])} laps",
        "Driver who ran the most laps on a single set of tyres.",
    )

    # --- Degradation comparison bar chart ---
    st.divider()
    degradation_figure = create_degradation_comparison_chart(tyre_data)
    st.plotly_chart(degradation_figure, use_container_width=True)

    # --- Single-driver tyre scatter (detail view) ---
    st.divider()
    st.markdown('<div class="sub-label">Stint Detail</div>', unsafe_allow_html=True)
    scatter_driver = cast(
        str,
        st.selectbox(
            "Driver",
            list(driver_clean_laps.keys()),
            help="View one driver's stint-by-stint tyre detail.",
        ),
    )
    try:
        scatter_trendlines = get_stint_trendlines(driver_clean_laps[scatter_driver])
        scatter_figure = create_tire_scatter_chart(
            driver_clean_laps[scatter_driver], scatter_trendlines
        )
        st.plotly_chart(scatter_figure, use_container_width=True)
    except MetricError as exc:
        st.warning(f"Cannot render tyre scatter for {scatter_driver}: {exc}")


# =====================================================================
# Footer — attribution, GitHub CTA, system status, disclaimer.
# Rendered only on the success path, so the status indicators are truthful.
# =====================================================================
st.markdown(
    f'<div class="footer">'
    f'<div class="footer-info">'
    f'POWERED BY <span class="accent">FASTF1</span> · '
    f"BUILT WITH STREAMLIT + PLOTLY<br>"
    f"Portfolio project by Afdoni Prabawa Said"
    f"</div>"
    f'<a class="cta-link" href="{GITHUB_URL}" target="_blank">'
    f"⟶ Source Code on GitHub</a>"
    f"</div>"
    f'<div class="status-strip">'
    f'<div class="status-title">SYSTEM STATUS</div>'
    f'<span class="status-item"><span class="status-dot">●</span>'
    f"FASTF1 CACHE READY</span>"
    f'<span class="status-item"><span class="status-dot">●</span>'
    f"SESSION DATA LOADED</span>"
    f'<span class="status-item"><span class="status-dot">●</span>'
    f"ANALYTICS ENGINE ACTIVE</span>"
    f"</div>"
    f'<div class="footer-disclaimer">'
    f"Not affiliated with Formula 1 companies. "
    f"F1 data via the FastF1 project."
    f"</div>",
    unsafe_allow_html=True,
)
