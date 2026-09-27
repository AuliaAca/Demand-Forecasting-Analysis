"""Download the Favorita competition data from Kaggle and checksum it.

STATUS — NOT YET RUN AGAINST THE REAL KAGGLE FILES.
This session's network policy blocks kaggle.com, and no Kaggle credentials
are configured in this sandbox, so this module has only been exercised
against the tiny synthetic fixture in tests/fixtures/favorita_sample/, not
against the real competition files. See docs/phase_reports/phase01.md for
what that means and what still needs to happen before Phase 01's dataset
card can be filled in with real numbers.

Usage (once Kaggle access is available — either in this session or on the
project owner's machine, per ADR 0001 §4.3):

    export KAGGLE_USERNAME=...
    export KAGGLE_KEY=...
    export DEMANDFLOW_DATA_DIR="D:\\dev\\demandflow-data"   # Windows example
    python -m demandflow.ingest.acquire_favorita

This requires accepting the competition's rules on kaggle.com first — the
Kaggle API refuses the download otherwise. [VERIFY] the competition's exact
license/redistribution terms when accepting; this is why raw data is never
committed to this repository (see .gitignore).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from demandflow.config import ProjectConfig, load_config

logger = logging.getLogger(__name__)

CHECKSUM_CHUNK_SIZE = 1024 * 1024  # 1 MiB


@dataclass(frozen=True)
class FileManifestEntry:
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class AcquisitionManifest:
    competition_slug: str
    downloaded_at_utc: str
    files: list[FileManifestEntry]


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHECKSUM_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_nested_archives(raw_dir: Path) -> None:
    """Extract .7z members if present.

    [VERIFY] Public write-ups of this competition report that Kaggle originally
    shipped the large CSVs (train.csv, test.csv) 7z-compressed inside the
    competition's outer zip. This has not been confirmed against a live
    download in this session. py7zr is a pure-Python dependency (no external
    7z binary needed), chosen specifically so this works unmodified on the
    project owner's Windows machine.
    """
    sevenzip_files = sorted(raw_dir.glob("*.7z"))
    if not sevenzip_files:
        return
    import py7zr  # imported lazily: only needed if .7z members actually exist

    for archive_path in sevenzip_files:
        logger.info("Extracting 7z archive: %s", archive_path.name)
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=raw_dir)
        archive_path.unlink()


def download_favorita(config: ProjectConfig | None = None, force: bool = False) -> Path:
    """Download and unpack the Favorita competition files via the Kaggle API.

    Returns the directory containing the raw, unpacked files. Idempotent:
    if the raw directory already has files and `force` is False, the
    existing download is reused rather than re-fetched.
    """
    cfg = config or load_config()
    raw_dir = cfg.paths.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)

    existing = [p for p in raw_dir.glob("*.csv") if p.is_file()]
    if existing and not force:
        logger.info(
            "Raw files already present in %s (%d .csv files); skipping download. "
            "Pass force=True to re-download.",
            raw_dir,
            len(existing),
        )
        return raw_dir

    # Imported lazily: the `kaggle` package reads ~/.kaggle/kaggle.json or
    # KAGGLE_USERNAME/KAGGLE_KEY at import time and raises if neither is
    # configured, so importing it unconditionally at module load would break
    # every other function in this module (including the parts that are
    # perfectly runnable offline, e.g. checksum verification of files that
    # already exist).
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    logger.info(
        "Downloading competition files for '%s' into %s",
        cfg.dataset.kaggle_competition_slug,
        raw_dir,
    )
    api.competition_download_files(
        cfg.dataset.kaggle_competition_slug, path=str(raw_dir), quiet=False
    )

    outer_zip = raw_dir / f"{cfg.dataset.kaggle_competition_slug}.zip"
    if outer_zip.exists():
        with zipfile.ZipFile(outer_zip) as zf:
            zf.extractall(raw_dir)
        outer_zip.unlink()

    _extract_nested_archives(raw_dir)

    return raw_dir


def build_manifest(raw_dir: Path, competition_slug: str) -> AcquisitionManifest:
    """Checksum every raw file present, independent of how it got there.

    This is safe to run against the real download or against the test
    fixture — it does not assume anything about *how* the files arrived,
    only that they are plain files in raw_dir.
    """
    entries = []
    for path in sorted(raw_dir.glob("*")):
        if not path.is_file():
            continue
        entries.append(
            FileManifestEntry(
                filename=path.name,
                size_bytes=path.stat().st_size,
                sha256=_sha256_of(path),
            )
        )
    return AcquisitionManifest(
        competition_slug=competition_slug,
        downloaded_at_utc=datetime.now(timezone.utc).isoformat(),
        files=entries,
    )


def write_manifest(manifest: AcquisitionManifest, raw_dir: Path) -> Path:
    manifest_path = raw_dir / "manifest.json"
    payload = asdict(manifest)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def acquire_and_checksum(config: ProjectConfig | None = None, force: bool = False) -> Path:
    """End-to-end: download (if needed), checksum, write manifest.json."""
    cfg = config or load_config()
    raw_dir = download_favorita(cfg, force=force)
    manifest = build_manifest(raw_dir, cfg.dataset.kaggle_competition_slug)
    manifest_path = write_manifest(manifest, raw_dir)
    logger.info("Wrote manifest with %d files to %s", len(manifest.files), manifest_path)
    return raw_dir


def _copy_fixture_as_raw(fixture_dir: Path, raw_dir: Path) -> None:
    """Test/demo helper: populate raw_dir from the small synthetic fixture.

    Used only by tests and by anyone who wants to exercise the rest of the
    Phase 01 pipeline (profiling, dev-scope selection, dataset-card
    generation) without real Kaggle access. Never used by acquire_and_checksum
    itself, so there is no risk of silently substituting fake data for real
    data in a real run.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    for src in fixture_dir.glob("*.csv"):
        shutil.copy2(src, raw_dir / src.name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    acquire_and_checksum()
