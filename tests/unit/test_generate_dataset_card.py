"""Tests for the dataset-card generator, using a real profile of the fixture."""

import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from demandflow.config import load_config
from demandflow.profiling.profile_favorita import profile
from demandflow.reporting.generate_dataset_card import render_dataset_card

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path))
    config = load_config()
    config.paths.raw_dir.mkdir(parents=True, exist_ok=True)
    for csv_file in FIXTURE_DIR.glob("*.csv"):
        shutil.copy2(csv_file, config.paths.raw_dir / csv_file.name)
    return config


def test_render_dataset_card_includes_key_sections(cfg):
    report = asdict(profile(cfg))
    card = render_dataset_card(
        report,
        dev_scope_summary=None,
        dataset_display_name="Corporación Favorita Grocery Sales Forecasting",
        kaggle_competition_slug="favorita-grocery-sales-forecasting",
    )
    assert "# Dataset Card" in card
    assert "Pricing | **No**" in card
    assert "Duplicate rows on this key: 1" in card
    assert "Missing calendar dates" in card
    assert "2013-01-10" in card
    assert "Not yet run" in card  # dev_scope_summary was None


def test_render_dataset_card_includes_dev_scope_when_provided(cfg):
    report = asdict(profile(cfg))
    dev_scope_summary = {
        "total_items": 10,
        "selected_items": 5,
        "selected_item_fraction": 0.5,
        "selected_share_of_total_unit_sales": 0.6,
        "stratum_cells": 3,
        "families_represented_in_selection": ["DAIRY", "GROCERY", "PRODUCE"],
    }
    card = render_dataset_card(
        report,
        dev_scope_summary=dev_scope_summary,
        dataset_display_name="Corporación Favorita Grocery Sales Forecasting",
        kaggle_competition_slug="favorita-grocery-sales-forecasting",
    )
    assert "Items selected: 5 of 10" in card
    assert "DAIRY" in card and "GROCERY" in card and "PRODUCE" in card
