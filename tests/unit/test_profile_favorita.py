"""End-to-end profiling test: profile() run against the synthetic fixture."""

import json
import shutil
from pathlib import Path

import pytest

from demandflow.config import load_config
from demandflow.profiling.profile_favorita import profile, write_report

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path))
    config = load_config()
    config.paths.raw_dir.mkdir(parents=True, exist_ok=True)
    for csv_file in FIXTURE_DIR.glob("*.csv"):
        shutil.copy2(csv_file, config.paths.raw_dir / csv_file.name)
    return config


def test_profile_matches_hand_counted_fixture_facts(cfg):
    report = profile(cfg)

    assert report.row_counts["train"] == 51
    assert report.row_counts["stores"] == 5
    assert report.row_counts["items"] == 10

    assert report.sales_grain["duplicate_rows"] == 1
    assert report.sales_grain["is_unique"] is False

    assert report.sales_date_coverage["missing_dates_count"] == 1
    assert report.sales_date_coverage["missing_dates_sample"] == ["2013-01-10"]

    assert report.sales_value_validity["negative_unit_sales_count"] == 1
    assert report.sales_value_validity["fractional_unit_sales_count"] == 1
    assert report.sales_value_validity["onpromotion_null_count"] == 5

    assert report.referential_integrity["sales_rows_with_unknown_item"] == 1
    assert report.referential_integrity["sales_rows_with_unknown_store"] == 0

    assert report.dimension_coverage["items"]["distinct_families"] == 3


def test_write_report_round_trips_as_json(cfg, tmp_path):
    report = profile(cfg)
    out_path = write_report(report, tmp_path / "profile_summary.json")
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["row_counts"]["train"] == 51
    assert loaded["tables_present"] == sorted(
        ["train", "stores", "items", "holidays_events", "oil", "transactions"]
    )
