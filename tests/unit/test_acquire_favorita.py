"""Tests for the parts of acquisition that don't need real Kaggle access:
checksumming and manifest writing. The actual Kaggle download function is
NOT exercised here — see docs/phase_reports/phase01.md for why, and
tests/unit/test_convert_to_parquet.py / test_profile_favorita.py for how
the rest of the pipeline is validated end-to-end via the synthetic fixture.
"""

import hashlib
import json
from pathlib import Path

from demandflow.ingest.acquire_favorita import (
    _copy_fixture_as_raw,
    build_manifest,
    write_manifest,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "favorita_sample"


def test_copy_fixture_as_raw_copies_every_csv(tmp_path):
    raw_dir = tmp_path / "raw"
    _copy_fixture_as_raw(FIXTURE_DIR, raw_dir)
    fixture_names = {p.name for p in FIXTURE_DIR.glob("*.csv")}
    raw_names = {p.name for p in raw_dir.glob("*.csv")}
    assert fixture_names == raw_names


def test_build_manifest_checksums_match_hashlib(tmp_path):
    raw_dir = tmp_path / "raw"
    _copy_fixture_as_raw(FIXTURE_DIR, raw_dir)

    manifest = build_manifest(raw_dir, competition_slug="favorita-grocery-sales-forecasting")

    assert manifest.competition_slug == "favorita-grocery-sales-forecasting"
    assert len(manifest.files) == len(list(raw_dir.glob("*.csv")))

    for entry in manifest.files:
        file_path = raw_dir / entry.filename
        expected_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert entry.sha256 == expected_sha256
        assert entry.size_bytes == file_path.stat().st_size


def test_write_manifest_round_trips_as_json(tmp_path):
    raw_dir = tmp_path / "raw"
    _copy_fixture_as_raw(FIXTURE_DIR, raw_dir)
    manifest = build_manifest(raw_dir, competition_slug="favorita-grocery-sales-forecasting")

    manifest_path = write_manifest(manifest, raw_dir)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert loaded["competition_slug"] == "favorita-grocery-sales-forecasting"
    assert len(loaded["files"]) == len(manifest.files)
