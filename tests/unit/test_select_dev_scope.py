"""Unit tests for the stratified development-scope sampler, against the fixture."""

from pathlib import Path

import duckdb
import pytest

from demandflow.config import DevScopeConfig
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    summarize_selection,
    write_dev_scope_csv,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


@pytest.fixture
def con():
    connection = duckdb.connect()
    yield connection
    connection.close()


@pytest.fixture
def dev_scope_cfg():
    # A larger fraction and fewer quantiles than the real project.yaml
    # defaults, sized for this 10-item fixture rather than ~4,100 real items.
    return DevScopeConfig(
        target_item_fraction=0.5,
        min_items_per_stratum_cell=1,
        volume_quantiles=2,
        promo_intensity_threshold=0.05,
    )


def test_compute_item_stats_covers_every_item(con, dev_scope_cfg):
    stats = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    assert {row["item_nbr"] for row in stats} == set(range(100, 110))
    for row in stats:
        assert row["family"] in {"GROCERY", "DAIRY", "PRODUCE"}
        assert row["volume_quantile"] in {1, 2}


def test_stratify_and_sample_is_deterministic(con, dev_scope_cfg):
    stats_a = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    stats_b = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)

    selection_a = stratify_and_sample(stats_a, dev_scope_cfg, seed=42)
    selection_b = stratify_and_sample(stats_b, dev_scope_cfg, seed=42)

    selected_a = {r.item_nbr for r in selection_a if r.selected}
    selected_b = {r.item_nbr for r in selection_b if r.selected}
    assert selected_a == selected_b
    assert len(selected_a) > 0
    assert selected_a.issubset(set(range(100, 110)))


def test_stratify_and_sample_keeps_every_item_in_output(con, dev_scope_cfg):
    stats = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    selection = stratify_and_sample(stats, dev_scope_cfg, seed=1)
    assert {r.item_nbr for r in selection} == set(range(100, 110))


def test_every_family_has_at_least_one_selected_item(con, dev_scope_cfg):
    # With min_items_per_stratum_cell=1 and 3 non-empty families, no family
    # should be silently dropped from the development scope.
    stats = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    selection = stratify_and_sample(stats, dev_scope_cfg, seed=7)
    selected_families = {r.family for r in selection if r.selected}
    assert selected_families == {"GROCERY", "DAIRY", "PRODUCE"}


def test_summarize_selection_totals_are_consistent(con, dev_scope_cfg):
    stats = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    selection = stratify_and_sample(stats, dev_scope_cfg, seed=42)
    summary = summarize_selection(selection)

    assert summary["total_items"] == 10
    assert 0 < summary["selected_items"] <= 10
    assert 0.0 < summary["selected_item_fraction"] <= 1.0
    assert 0.0 <= summary["selected_share_of_total_unit_sales"] <= 1.0
    assert set(summary["families_represented_in_selection"]).issubset({"GROCERY", "DAIRY", "PRODUCE"})


def test_write_dev_scope_csv_row_count_matches(con, dev_scope_cfg, tmp_path):
    stats = compute_item_stats(con, FIXTURE_DIR / "train.csv", FIXTURE_DIR / "items.csv", dev_scope_cfg)
    selection = stratify_and_sample(stats, dev_scope_cfg, seed=42)
    out_path = write_dev_scope_csv(selection, tmp_path / "dev_scope_items.csv")

    lines = out_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 + len(selection)  # header + one row per item
