"""Run the whole Phase 01 pipeline end-to-end against the synthetic fixture.

This is NOT a substitute for a real run against the actual Favorita data —
it proves the pipeline's *plumbing* (acquire -> convert -> profile ->
select dev scope -> render dataset card) composes correctly, using data
this repository controls and ships in tests/fixtures/. It writes its output
under reports/phase01/fixture_smoke_test/, never to docs/dataset_card.md,
so it can never be mistaken for a real dataset card.

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

OUTPUT_DIR = REPO_ROOT / "reports" / "phase01" / "fixture_smoke_test"
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
    from demandflow.reporting.generate_dataset_card import generate_and_write
    from demandflow.scope.select_dev_scope import (
        compute_item_stats,
        stratify_and_sample,
        summarize_selection,
        write_dev_scope_csv,
    )
    import duckdb
    import json
    from dataclasses import asdict

    cfg = load_config()
    print(f"[1/6] Data dir for this smoke test: {cfg.paths.data_dir}")

    print("[2/6] 'Acquiring' data (copying the fixture in place of a real Kaggle download)")
    _copy_fixture_as_raw(FIXTURE_DIR, cfg.paths.raw_dir)
    manifest = build_manifest(cfg.paths.raw_dir, cfg.dataset.kaggle_competition_slug)
    write_manifest(manifest, cfg.paths.raw_dir)
    print(f"       {len(manifest.files)} files checksummed")

    print("[3/6] Converting CSV -> Parquet")
    counts = convert_all(cfg)
    print(f"       {counts}")

    print("[4/6] Profiling")
    report = profile(cfg)
    profile_path = OUTPUT_DIR / "profile_summary.json"
    write_report(report, profile_path)
    print(f"       wrote {profile_path}")

    print("[5/6] Selecting the controlled development scope")
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

    print("[6/6] Rendering the dataset card (fixture preview — NOT the real dataset card)")
    card_path = OUTPUT_DIR / "dataset_card_PREVIEW.md"
    generate_and_write(
        profile_path=profile_path,
        dev_scope_summary_path=summary_path,
        out_path=card_path,
        dataset_display_name=cfg.dataset.display_name,
        kaggle_competition_slug=cfg.dataset.kaggle_competition_slug,
    )
    print(f"       wrote {card_path}")
    print("\nSmoke test complete. All outputs are under:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
