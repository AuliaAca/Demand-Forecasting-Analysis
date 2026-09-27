"""Unit tests for CSV -> Parquet conversion against the synthetic fixture."""

import shutil
from pathlib import Path

import duckdb
import pytest

from demandflow.config import load_config
from demandflow.ingest.convert_to_parquet import convert_all

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"

EXPECTED_ROW_COUNTS = {
    "train": 51,
    "stores": 5,
    "items": 10,
    "holidays_events": 3,
    "oil": 10,
    "transactions": 16,
}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path))
    config = load_config()
    config.paths.raw_dir.mkdir(parents=True, exist_ok=True)
    for csv_file in FIXTURE_DIR.glob("*.csv"):
        shutil.copy2(csv_file, config.paths.raw_dir / csv_file.name)
    return config


def test_convert_all_produces_expected_row_counts(cfg):
    counts = convert_all(cfg)
    assert counts == EXPECTED_ROW_COUNTS


def test_convert_all_skips_absent_tables_without_error(cfg):
    # test.csv and sample_submission.csv are not in the fixture; convert_all
    # must skip them (they log, they don't raise).
    counts = convert_all(cfg)
    assert "test" not in counts
    assert "sample_submission" not in counts


def test_parquet_files_are_readable_and_match_csv_row_counts(cfg):
    convert_all(cfg)
    con = duckdb.connect()
    for table, expected in EXPECTED_ROW_COUNTS.items():
        parquet_path = cfg.paths.parquet_dir / f"{table}.parquet"
        assert parquet_path.exists()
        (n,) = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')"
        ).fetchone()
        assert n == expected
    con.close()
