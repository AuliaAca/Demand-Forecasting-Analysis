"""Tests for the Phase 04 chart generators."""


from demandflow.analysis.charts import generate_eda_charts, plot_category_bar, plot_daily_trend


def test_plot_daily_trend_writes_a_nonempty_png(tmp_path):
    dates = ["2013-01-01", "2013-01-02", "2013-01-03"]
    totals = [10.0, 12.0, 8.0]
    rolling = [None, None, 10.0]
    out = plot_daily_trend(dates, totals, rolling, tmp_path / "trend.png", "Test trend")
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_category_bar_writes_a_nonempty_png(tmp_path):
    out = plot_category_bar(
        ["A", "B"], [1.0, 2.0], tmp_path / "bar.png", "Test bar", "Value"
    )
    assert out.exists()
    assert out.stat().st_size > 0


def test_generate_eda_charts_produces_all_four_from_a_full_summary(tmp_path):
    summary = {
        "trend": {
            "daily_totals": [
                {"date": "2013-01-01", "total_unit_sales": 10.0, "rolling_mean": None},
                {"date": "2013-01-02", "total_unit_sales": 12.0, "rolling_mean": 11.0},
            ]
        },
        "seasonal_events": {
            "day_of_week": [{"day_of_week": 0, "avg_unit_sales": 5.0}, {"day_of_week": 1, "avg_unit_sales": 3.0}],
            "holiday_effect": [{"is_holiday": False, "avg_unit_sales": 5.0}, {"is_holiday": True, "avg_unit_sales": 2.0}],
        },
        "promotion_effect": {
            "by_promotion_status": [
                {"onpromotion": False, "avg_unit_sales": 5.0},
                {"onpromotion": True, "avg_unit_sales": 6.0},
            ]
        },
    }
    paths = generate_eda_charts(summary, tmp_path / "figures")
    assert set(paths) == {"daily_trend", "day_of_week", "promotion_uplift", "holiday_effect"}
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0


def test_generate_eda_charts_skips_missing_sections_gracefully(tmp_path):
    paths = generate_eda_charts({}, tmp_path / "figures")
    assert paths == {}
