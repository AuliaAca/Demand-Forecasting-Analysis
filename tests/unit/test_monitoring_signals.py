"""Unit tests for Phase 10's monitoring signal functions (pure logic, no DB)."""


from demandflow.forecasting.backtest import ForecastRecord
from demandflow.monitoring.signals import (
    BREACH,
    OK,
    UNKNOWN,
    WARN,
    anomaly_signal,
    data_quality_signal,
    forecast_accuracy_signal,
    forecast_deterioration_signal,
    overall_status,
)
from demandflow.quality.rules import DQFinding


# --- overall_status ------------------------------------------------------


def test_overall_status_picks_the_worst():
    assert overall_status([OK, WARN, OK]) == WARN
    assert overall_status([OK, WARN, BREACH]) == BREACH


def test_overall_status_ranks_unknown_above_ok():
    assert overall_status([OK, UNKNOWN]) == UNKNOWN


def test_overall_status_empty_list_is_unknown():
    assert overall_status([]) == UNKNOWN


# --- forecast_accuracy_signal ----------------------------------------------


def test_forecast_accuracy_signal_ok_below_warn_threshold():
    result = forecast_accuracy_signal({"naive": {"wape": 0.8}}, "naive")
    assert result["status"] == OK


def test_forecast_accuracy_signal_warn_between_thresholds():
    result = forecast_accuracy_signal({"naive": {"wape": 1.1}}, "naive")
    assert result["status"] == WARN


def test_forecast_accuracy_signal_breach_above_breach_threshold():
    result = forecast_accuracy_signal({"naive": {"wape": 1.6}}, "naive")
    assert result["status"] == BREACH


def test_forecast_accuracy_signal_unknown_without_champion():
    result = forecast_accuracy_signal({"naive": {"wape": 0.5}}, None)
    assert result["status"] == UNKNOWN


def test_forecast_accuracy_signal_unknown_when_wape_missing():
    result = forecast_accuracy_signal({"naive": {"wape": None}}, "naive")
    assert result["status"] == UNKNOWN


# --- forecast_deterioration_signal -----------------------------------------


def _record(as_of, target_date, model, actual, forecast, is_scored=True):
    return ForecastRecord(
        as_of_date=as_of, horizon_step=1, target_date=target_date, store_nbr=1, item_nbr=100,
        model=model, forecast=forecast, actual=actual, is_scored=is_scored,
    )


def test_forecast_deterioration_signal_unknown_with_one_as_of_date():
    records = [_record("2013-01-07", "2013-01-08", "naive", 5.0, 5.0)]
    result = forecast_deterioration_signal(records, "naive")
    assert result["status"] == UNKNOWN


def test_forecast_deterioration_signal_ok_when_recent_period_is_better():
    records = [
        _record("2013-01-07", "2013-01-08", "naive", 10.0, 5.0),   # prior: |10-5|/10 = 0.5
        _record("2013-01-14", "2013-01-15", "naive", 10.0, 9.0),   # final: |10-9|/10 = 0.1
    ]
    result = forecast_deterioration_signal(records, "naive")
    assert result["status"] == OK
    assert result["ratio"] < 1.0


def test_forecast_deterioration_signal_warn_when_recent_period_is_worse():
    records = [
        _record("2013-01-07", "2013-01-08", "naive", 10.0, 9.0),   # prior wape 0.1
        _record("2013-01-14", "2013-01-15", "naive", 10.0, 8.75),  # final wape 0.125 -> ratio 1.25
    ]
    result = forecast_deterioration_signal(records, "naive")
    assert result["status"] == WARN


def test_forecast_deterioration_signal_breach_when_recent_period_is_much_worse():
    records = [
        _record("2013-01-07", "2013-01-08", "naive", 10.0, 9.0),   # prior wape 0.1
        _record("2013-01-14", "2013-01-15", "naive", 10.0, 5.0),   # final wape 0.5 -> ratio 5.0
    ]
    result = forecast_deterioration_signal(records, "naive")
    assert result["status"] == BREACH


def test_forecast_deterioration_signal_unknown_without_champion():
    result = forecast_deterioration_signal([], None)
    assert result["status"] == UNKNOWN


def test_forecast_deterioration_signal_ignores_unscored_records():
    records = [
        _record("2013-01-07", "2013-01-08", "naive", 10.0, 9.0, is_scored=True),
        _record("2013-01-14", "2013-01-15", "naive", None, 8.0, is_scored=False),
    ]
    result = forecast_deterioration_signal(records, "naive")
    # only one as-of date has a SCORED naive forecast -> not enough history
    assert result["status"] == UNKNOWN


# --- data_quality_signal -----------------------------------------------------


def _finding(rule_id, severity):
    return DQFinding(
        rule_id=rule_id, category="values", description="d", metrics={}, severity=severity,
        consequence="c", handling_decision="h",
    )


def test_data_quality_signal_ok_when_everything_passes():
    findings = [_finding("r1", "PASS"), _finding("r2", "LOW"), _finding("r3", "INFO")]
    result = data_quality_signal(findings)
    assert result["status"] == OK
    assert result["driving_rules"] == []


def test_data_quality_signal_warn_on_medium():
    findings = [_finding("r1", "PASS"), _finding("r2", "MEDIUM")]
    result = data_quality_signal(findings)
    assert result["status"] == WARN
    assert result["driving_rules"] == ["r2"]


def test_data_quality_signal_breach_on_critical_or_high():
    findings = [_finding("r1", "MEDIUM"), _finding("r2", "CRITICAL"), _finding("r3", "HIGH")]
    result = data_quality_signal(findings)
    assert result["status"] == BREACH
    assert set(result["driving_rules"]) == {"r2", "r3"}


def test_data_quality_signal_unknown_with_no_findings():
    result = data_quality_signal([])
    assert result["status"] == UNKNOWN


# --- anomaly_signal ---------------------------------------------------------


def test_anomaly_signal_ok_with_no_recent_anomalies():
    daily_totals = [{"date": "2013-01-19"}, {"date": "2013-01-20"}]
    result = anomaly_signal(daily_totals, [])
    assert result["status"] == OK


def test_anomaly_signal_warn_with_one_recent_anomaly():
    daily_totals = [{"date": "2013-01-19"}, {"date": "2013-01-20"}]
    anomalies = [{"date": "2013-01-20", "total_unit_sales": 84.0, "z_score": 4.1}]
    result = anomaly_signal(daily_totals, anomalies)
    assert result["status"] == WARN
    assert result["recent_anomaly_count"] == 1


def test_anomaly_signal_breach_with_two_or_more_recent_anomalies():
    daily_totals = [{"date": "2013-01-19"}, {"date": "2013-01-20"}]
    anomalies = [
        {"date": "2013-01-18", "total_unit_sales": 84.0, "z_score": 4.1},
        {"date": "2013-01-20", "total_unit_sales": 90.0, "z_score": 4.5},
    ]
    result = anomaly_signal(daily_totals, anomalies)
    assert result["status"] == BREACH


def test_anomaly_signal_excludes_anomalies_outside_the_recent_window():
    daily_totals = [{"date": f"2013-01-{d:02d}"} for d in range(1, 21)]
    anomalies = [{"date": "2013-01-01", "total_unit_sales": 84.0, "z_score": 4.1}]  # far outside a 7-day window ending 01-20
    result = anomaly_signal(daily_totals, anomalies, recent_days=7)
    assert result["status"] == OK
    assert result["recent_anomaly_count"] == 0


def test_anomaly_signal_unknown_with_no_daily_totals():
    result = anomaly_signal([], [])
    assert result["status"] == UNKNOWN
