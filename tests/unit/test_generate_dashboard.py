"""Tests for the Phase 14 dashboard generator, using real runs of Phases
04/08/09/10/11 against the fixture warehouse."""

from html.parser import HTMLParser
from pathlib import Path

import duckdb
import pytest

from demandflow.alerts.run_alerts import run_and_write as run_alerts
from demandflow.analysis.run_eda import run_and_write as run_eda
from demandflow.config import load_config
from demandflow.evaluation.run_evaluation import run_and_write as run_evaluation
from demandflow.ingest.acquire_favorita import _copy_fixture_as_raw
from demandflow.ingest.convert_to_parquet import convert_all
from demandflow.monitoring.run_monitoring import run_and_write as run_monitoring
from demandflow.rca.run_rca import run_and_write as run_rca
from demandflow.reporting.generate_dashboard import collect_inputs, generate_and_write, render_dashboard
from demandflow.scope.select_dev_scope import (
    compute_item_stats,
    stratify_and_sample,
    write_dev_scope_csv,
)
from demandflow.transform.build_warehouse import build_warehouse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


class _TagBalanceChecker(HTMLParser):
    """Confirms every opened tag is properly closed -- this file is
    assembled from many f-strings, so a stray unclosed <div> is a real,
    easy-to-introduce bug, not a hypothetical one."""

    VOID_ELEMENTS = {"br", "img", "hr", "input", "meta", "link", "rect", "circle", "path"}

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        # Self-closing void elements (e.g. <rect ... />) never get pushed,
        # so the default HTMLParser behavior of also firing handle_endtag
        # for them must be ignored here rather than treated as a mismatch.
        if tag in self.VOID_ELEMENTS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"mismatched close tag: {tag!r} (stack: {self.stack})")
        else:
            self.stack.pop()


def _assert_well_formed(html_content: str) -> None:
    checker = _TagBalanceChecker()
    checker.feed(html_content)
    assert checker.errors == [], f"HTML errors: {checker.errors}"
    assert checker.stack == [], f"unclosed tags at EOF: {checker.stack}"


@pytest.fixture
def full_reports_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDFLOW_DATA_DIR", str(tmp_path / "data"))
    cfg = load_config()
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    convert_all(cfg)

    con = duckdb.connect()
    stats = compute_item_stats(
        con, cfg.paths.parquet_dir / "train.parquet", cfg.paths.parquet_dir / "items.parquet", cfg.dev_scope
    )
    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    con.close()
    dev_scope_csv = tmp_path / "dev_scope_items.csv"
    write_dev_scope_csv(selection, dev_scope_csv)

    db_path = tmp_path / "warehouse.duckdb"
    warehouse_con, checks = build_warehouse(cfg, db_path=db_path, dev_scope_csv_path=dev_scope_csv)
    assert all(c.passed for c in checks)
    warehouse_con.close()

    reports_root = tmp_path / "reports"
    run_eda(cfg, db_path=db_path, out_dir=reports_root / "phase04")
    run_evaluation(cfg, db_path=db_path, out_dir=reports_root / "phase08")
    run_rca(cfg, db_path=db_path, out_dir=reports_root / "phase09")
    run_monitoring(cfg, db_path=db_path, out_dir=reports_root / "phase10")
    run_alerts(cfg, db_path=db_path, out_dir=reports_root / "phase11")

    return cfg, reports_root


# --- collect_inputs -----------------------------------------------------


def test_collect_inputs_finds_all_five_when_present(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    assert set(inputs) == {"eda", "evaluation", "rca", "monitoring", "alerts"}
    assert all(v is not None for v in inputs.values())


def test_collect_inputs_returns_none_for_missing_files(tmp_path):
    inputs = collect_inputs(tmp_path / "does_not_exist")
    assert all(v is None for v in inputs.values())


# --- render_dashboard: real data -----------------------------------------


def test_render_dashboard_is_well_formed_html(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    _assert_well_formed(content)


def test_render_dashboard_includes_every_section(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    for section_id in ["demand", "accuracy", "discrepancies", "monitoring", "alerts", "findings"]:
        assert f'id="{section_id}"' in content


def test_render_dashboard_states_the_real_champion_and_status(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    assert "Seasonal Naive" in content
    assert "0.908" in content  # hand-verified overall WAPE on this fixture
    assert "pill-breach" in content  # hand-verified overall monitoring status


def test_render_dashboard_includes_the_fixture_disclosure_banner(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    assert "synthetic fixture" in content
    assert "never real Favorita data" in content


def test_render_dashboard_escapes_special_characters(full_reports_root):
    # Monitoring reasons contain literal ">=" (e.g. "WARN >= 1.0") -- these
    # must be HTML-escaped, not injected raw.
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    assert "&gt;=" in content


def test_render_dashboard_charts_are_proportionally_scaled(full_reports_root):
    import re

    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    content = render_dashboard(inputs, "Test Dataset")
    svgs = re.findall(r"<svg.*?</svg>", content, re.S)
    assert len(svgs) >= 1
    # every rect width must be a positive number (no NaN/negative bars)
    widths = [float(w) for w in re.findall(r'<rect[^>]*width="([\d.]+)"', content)]
    assert widths
    assert all(w > 0 for w in widths)


# --- render_dashboard: missing inputs -------------------------------------


def test_render_dashboard_handles_all_inputs_missing_without_crashing():
    inputs = {"eda": None, "evaluation": None, "rca": None, "monitoring": None, "alerts": None}
    content = render_dashboard(inputs, "Test Dataset")
    _assert_well_formed(content)
    assert "has not been run yet" in content


def test_render_dashboard_handles_partial_inputs(full_reports_root):
    cfg, reports_root = full_reports_root
    inputs = collect_inputs(reports_root)
    inputs["rca"] = None
    inputs["alerts"] = None
    content = render_dashboard(inputs, "Test Dataset")
    _assert_well_formed(content)
    assert "Phase 09 root-cause analysis has not been run yet." in content
    assert "Phase 11 alerts/tracker has not been run yet." in content
    assert "Seasonal Naive" in content  # evaluation data still renders


# --- generate_and_write ---------------------------------------------------


def test_generate_and_write_writes_the_file(full_reports_root, tmp_path):
    cfg, reports_root = full_reports_root
    out_path = tmp_path / "out" / "dashboard.html"
    result = generate_and_write(reports_root, out_path, "Test Dataset")
    assert result == out_path
    assert out_path.exists()
    _assert_well_formed(out_path.read_text(encoding="utf-8"))


def test_generate_and_write_title_is_present_in_first_8kb(full_reports_root, tmp_path):
    cfg, reports_root = full_reports_root
    out_path = tmp_path / "dashboard.html"
    generate_and_write(reports_root, out_path, "Test Dataset")
    head = out_path.read_text(encoding="utf-8")[:8000]
    assert "<title>DemandFlow Dashboard</title>" in head
