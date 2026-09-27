"""Small, consistent matplotlib chart helpers for the Phase 04 EDA report.

Palette and mark specs are the validated defaults from this project's
dataviz skill (references/palette.md, marks-and-anatomy.md): categorical
hues assigned in fixed order (never cycled), one hue for a single-series
chart, 2px lines, hairline recessive gridlines, text in ink tokens rather
than the data color, no dual-axis charts. Static PNG output only (no
interactive layer needed here).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402

# --- Palette (light mode only; this is a static report, not a themed UI) ---
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES_1_BLUE = "#2a78d6"
SERIES_2_ORANGE = "#eb6834"
CRITICAL_RED = "#d03b3b"

FIGSIZE = (8, 4)
DPI = 120


def _new_axes():
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    return fig, ax


def _finish(fig, ax, title: str, out_path: Path) -> Path:
    ax.set_title(title, color=INK_PRIMARY, fontsize=11, loc="left", pad=10)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(INK_SECONDARY)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)
    return out_path


def plot_daily_trend(
    dates: list, totals: list[float], rolling_mean: list[float | None], out_path: Path, title: str
) -> Path:
    """A single line chart: daily total plus its rolling-mean trend line.

    Two series here means color IS the identity channel, so both are
    labeled in a legend (mark spec: legend always present for >=2 series).
    """
    # Parse ISO date strings (as they come from the JSON summary) into real
    # date objects, so matplotlib treats the x-axis as a genuine time axis
    # rather than categorical labels that merely look date-shaped.
    parsed_dates = [d if isinstance(d, datetime.date) else datetime.date.fromisoformat(d) for d in dates]

    fig, ax = _new_axes()
    ax.plot(parsed_dates, totals, linewidth=2, color=SERIES_1_BLUE, solid_capstyle="round", label="Daily total")
    if any(v is not None for v in rolling_mean):
        ax.plot(
            parsed_dates, rolling_mean, linewidth=2, color=SERIES_2_ORANGE,
            solid_capstyle="round", label="Rolling mean (trend)",
        )
    ax.set_ylabel("Total unit sales", color=INK_SECONDARY, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK_SECONDARY, loc="upper left")
    fig.autofmt_xdate(rotation=30)
    return _finish(fig, ax, title, out_path)


def plot_category_bar(
    labels: list[str], values: list[float], out_path: Path, title: str, ylabel: str
) -> Path:
    """A single-hue bar chart comparing a metric across categories.

    One series (one measure, compared across category labels on the x-axis)
    -> one hue, no legend box needed (mark spec: a single series needs no
    legend; the title/axis label already say what's plotted).
    """
    fig, ax = _new_axes()
    x = range(len(labels))
    ax.bar(x, values, width=0.6, color=SERIES_1_BLUE, zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel, color=INK_SECONDARY, fontsize=9)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
    return _finish(fig, ax, title, out_path)


def generate_eda_charts(eda_summary: dict, out_dir: Path) -> dict[str, Path]:
    """Renders the small, fixed set of Phase 04 charts from an EDA summary dict
    (the same shape written to reports/phase04/eda_summary.json). Returns a
    dict of {chart_name: path}, so the report generator can reference them by
    relative path without hard-coding filenames in two places.
    """
    paths: dict[str, Path] = {}

    trend = eda_summary.get("trend", {})
    daily = trend.get("daily_totals", [])
    if daily:
        dates = [row["date"] for row in daily]
        totals = [row["total_unit_sales"] for row in daily]
        rolling = [row.get("rolling_mean") for row in daily]
        paths["daily_trend"] = plot_daily_trend(
            dates, totals, rolling, out_dir / "daily_trend.png",
            "Daily total unit sales (development scope)",
        )

    dow = eda_summary.get("seasonal_events", {}).get("day_of_week", [])
    if dow:
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        labels = [day_names[row["day_of_week"]] for row in dow]
        values = [row["avg_unit_sales"] for row in dow]
        paths["day_of_week"] = plot_category_bar(
            labels, values, out_dir / "day_of_week.png",
            "Average unit sales by day of week", "Avg unit sales",
        )

    promo = eda_summary.get("promotion_effect", {}).get("by_promotion_status", [])
    if promo:
        labels = ["Not promoted" if not row["onpromotion"] else "Promoted" for row in promo]
        values = [row["avg_unit_sales"] for row in promo]
        paths["promotion_uplift"] = plot_category_bar(
            labels, values, out_dir / "promotion_uplift.png",
            "Average unit sales: promoted vs. not promoted", "Avg unit sales",
        )

    holiday = eda_summary.get("seasonal_events", {}).get("holiday_effect", [])
    if holiday:
        labels = ["Holiday" if row["is_holiday"] else "Non-holiday" for row in holiday]
        values = [row["avg_unit_sales"] for row in holiday]
        paths["holiday_effect"] = plot_category_bar(
            labels, values, out_dir / "holiday_effect.png",
            "Average unit sales: holiday vs. non-holiday", "Avg unit sales",
        )

    return paths
