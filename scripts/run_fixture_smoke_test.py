"""Run the whole pipeline built so far, end-to-end, against the synthetic fixture.

This is NOT a substitute for a real run against the actual Favorita data —
it proves the pipeline's *plumbing* composes correctly, using data this
repository controls and ships in tests/fixtures/. It writes its output under
reports/fixture_smoke_test/ (git-ignored), never to docs/dataset_card.md or
docs/data_quality/dq_report.md, so it can never be mistaken for real output.

Covers, as of Phase 03:
    acquire -> convert -> profile -> select dev scope -> render dataset card
    -> run DQ rules -> render DQ report -> build the SQL warehouse
    (staging -> intermediate -> marts) -> reconciliation checks

Usage:
    python scripts/run_fixture_smoke_test.py
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import os  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "reports" / "fixture_smoke_test"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "favorita_sample"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    data_dir = OUTPUT_DIR / "data"
    os.environ["DEMANDFLOW_DATA_DIR"] = str(data_dir)

    # Import after setting the env var, so config.load_config() picks it up.
    from demandflow.config import load_config
    from demandflow.ingest.acquire_favorita import (
        _copy_fixture_as_raw,
        build_manifest,
        write_manifest,
    )
    from demandflow.ingest.convert_to_parquet import convert_all
    from demandflow.profiling.profile_favorita import profile, write_report
    from demandflow.quality.rules import findings_to_dicts, run_all_rules
    from demandflow.reporting.generate_dataset_card import generate_and_write as generate_dataset_card
    from demandflow.reporting.generate_dq_report import generate_and_write as generate_dq_report
    from demandflow.scope.select_dev_scope import (
        compute_item_stats,
        stratify_and_sample,
        summarize_selection,
        write_dev_scope_csv,
    )
    import duckdb
    import json

    cfg = load_config()
    print(f"[1/9] Data dir for this smoke test: {cfg.paths.data_dir}")

    print("[2/9] 'Acquiring' data (copying the fixture in place of a real Kaggle download)")
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    manifest = build_manifest(cfg.paths.raw_dir, cfg.dataset.kaggle_competition_slug)
    write_manifest(manifest, cfg.paths.raw_dir)
    print(f"       {len(manifest.files)} files checksummed")

    print("[3/9] Converting CSV -> Parquet")
    counts = convert_all(cfg)
    print(f"       {counts}")

    print("[4/9] Profiling")
    report = profile(cfg)
    profile_path = OUTPUT_DIR / "profile_summary.json"
    write_report(report, profile_path)
    print(f"       wrote {profile_path}")

    print("[5/9] Selecting the controlled development scope")
    con = duckdb.connect()
    stats = compute_item_stats(
        con, cfg.paths.parquet_dir / "train.parquet", cfg.paths.parquet_dir / "items.parquet", cfg.dev_scope
    )
    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    summary = summarize_selection(selection)
    dev_scope_csv_path = OUTPUT_DIR / "dev_scope_items.csv"
    write_dev_scope_csv(selection, dev_scope_csv_path)
    summary_path = OUTPUT_DIR / "dev_scope_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    con.close()
    print(f"       selected {summary['selected_items']}/{summary['total_items']} items -> {dev_scope_csv_path}")

    print("[6/9] Rendering the dataset card (fixture preview — NOT the real dataset card)")
    card_path = OUTPUT_DIR / "dataset_card_PREVIEW.md"
    generate_dataset_card(
        profile_path=profile_path,
        dev_scope_summary_path=summary_path,
        out_path=card_path,
        dataset_display_name=cfg.dataset.display_name,
        kaggle_competition_slug=cfg.dataset.kaggle_competition_slug,
    )
    print(f"       wrote {card_path}")

    print("[7/9] Running the Phase 02 data-quality rule catalog")
    con = duckdb.connect()
    available_tables = [p.stem for p in cfg.paths.parquet_dir.glob("*.parquet")]
    findings = run_all_rules(
        con,
        cfg.paths.parquet_dir / "train.parquet",
        cfg.paths.parquet_dir / "stores.parquet",
        cfg.paths.parquet_dir / "items.parquet",
        available_tables=available_tables,
    )
    con.close()
    findings_path = OUTPUT_DIR / "dq_findings.json"
    findings_path.write_text(json.dumps(findings_to_dicts(findings), indent=2), encoding="utf-8")
    severities = ", ".join(f"{f.rule_id}={f.severity}" for f in findings)
    print(f"       {severities}")

    print("[8/9] Rendering the DQ report (fixture preview — NOT the real DQ report)")
    dq_report_path = OUTPUT_DIR / "dq_report_PREVIEW.md"
    generate_dq_report(findings_path, dq_report_path, cfg.dataset.display_name)
    print(f"       wrote {dq_report_path}")

    print("[9/9] Building the SQL warehouse (staging -> intermediate -> marts) and reconciling")
    from demandflow.transform.build_warehouse import build_warehouse

    warehouse_con, checks = build_warehouse(
        cfg, db_path=OUTPUT_DIR / "warehouse.duckdb", dev_scope_csv_path=dev_scope_csv_path
    )
    warehouse_con.close()
    for c in checks:
        print(f"       [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    failed = [c for c in checks if not c.passed]

    print("\nSmoke test complete. All outputs are under:", OUTPUT_DIR)
    if failed:
        raise SystemExit(f"{len(failed)} reconciliation check(s) failed: {[c.name for c in failed]}")


if __name__ == "__main__":
    main()
