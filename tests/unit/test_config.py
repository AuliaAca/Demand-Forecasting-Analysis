"""Tests for demandflow.config -- Phase 15 (configuration validation).

Before this phase, load_config() had no direct unit tests at all: a
malformed project.yaml (missing section, negative horizon_days) would
either raise a bare, unhelpful KeyError or -- worse -- load silently and
fail much later, deep inside whichever phase first used the bad value.
These tests pin the fail-fast behavior added in Phase 15.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from demandflow.config import ConfigError, load_config

VALID_CONFIG: dict = {
    "random_seed": 42,
    "dataset": {
        "kaggle_competition_slug": "favorita-grocery-sales-forecasting",
        "display_name": "Corporación Favorita Grocery Sales Forecasting",
        "files": ["train.csv"],
    },
    "paths": {
        "data_dir_env_var": "DEMANDFLOW_DATA_DIR",
        "default_data_dir": "data",
        "raw_subdir": "raw/favorita",
        "parquet_subdir": "parquet/favorita",
    },
    "dev_scope": {
        "target_item_fraction": 0.10,
        "min_items_per_stratum_cell": 1,
        "volume_quantiles": 4,
        "promo_intensity_threshold": 0.05,
    },
    "forecasting": {
        "horizon_days": 14,
        "season_length_days": 7,
        "as_of_cadence_days": 7,
        "min_history_days": 7,
    },
}


def _write_config(tmp_path: Path, overrides: dict) -> Path:
    import copy

    cfg = copy.deepcopy(VALID_CONFIG)
    for section, values in overrides.items():
        if values is None:
            cfg.pop(section, None)
        elif isinstance(values, dict):
            cfg[section].update(values)
        else:
            cfg[section] = values
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_load_config_reads_the_real_project_yaml():
    # The actual repository config must itself pass every validation rule
    # added below -- this is the guard against the tests and the real file
    # silently drifting apart.
    cfg = load_config()
    assert cfg.random_seed == 42
    assert cfg.forecasting.horizon_days > 0


def test_load_config_accepts_a_well_formed_config(tmp_path):
    path = _write_config(tmp_path, {})
    cfg = load_config(path)
    assert cfg.dataset.kaggle_competition_slug == "favorita-grocery-sales-forecasting"
    assert cfg.dev_scope.volume_quantiles == 4


def test_load_config_raises_file_not_found_for_a_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_load_config_rejects_a_non_mapping_document(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize("missing_section", ["dataset", "paths", "dev_scope", "forecasting"])
def test_load_config_raises_config_error_for_a_missing_section(tmp_path, missing_section):
    path = _write_config(tmp_path, {missing_section: None})
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_config_raises_config_error_for_a_missing_random_seed(tmp_path):
    path = _write_config(tmp_path, {"random_seed": None})
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_config_raises_config_error_for_a_negative_random_seed(tmp_path):
    path = _write_config(tmp_path, {"random_seed": -1})
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize(
    "key", ["horizon_days", "season_length_days", "as_of_cadence_days", "min_history_days"]
)
@pytest.mark.parametrize("bad_value", [0, -1])
def test_load_config_rejects_a_non_positive_forecasting_value(tmp_path, key, bad_value):
    path = _write_config(tmp_path, {"forecasting": {key: bad_value}})
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize("bad_value", [0, -0.1, 1.5])
def test_load_config_rejects_an_out_of_range_target_item_fraction(tmp_path, bad_value):
    path = _write_config(tmp_path, {"dev_scope": {"target_item_fraction": bad_value}})
    with pytest.raises(ConfigError):
        load_config(path)


def test_load_config_rejects_a_missing_key_within_a_present_section(tmp_path):
    cfg = {**VALID_CONFIG, "forecasting": {"horizon_days": 14}}  # season_length_days etc. missing
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
