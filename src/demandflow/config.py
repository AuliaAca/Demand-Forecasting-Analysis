"""Project configuration loading.

[DECISION] A single YAML file (configs/project.yaml) plus one environment
variable override (DEMANDFLOW_DATA_DIR) for the data root. This lets the
exact same code run in a disposable sandbox and on the project owner's own
machine, where the data root is a path under D:\\ (see ADR 0001 §4.3) — only
the environment variable differs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "project.yaml"


@dataclass(frozen=True)
class Paths:
    data_dir: Path
    raw_dir: Path
    parquet_dir: Path
    reports_dir: Path
    configs_dir: Path


@dataclass(frozen=True)
class DevScopeConfig:
    target_item_fraction: float
    min_items_per_stratum_cell: int
    volume_quantiles: int
    promo_intensity_threshold: float


@dataclass(frozen=True)
class DatasetConfig:
    kaggle_competition_slug: str
    display_name: str
    files: list[str]


@dataclass(frozen=True)
class ProjectConfig:
    random_seed: int
    dataset: DatasetConfig
    paths: Paths
    dev_scope: DevScopeConfig
    raw: dict[str, Any]


def _resolve_data_dir(raw_paths: dict[str, Any]) -> Path:
    env_var = raw_paths["data_dir_env_var"]
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser().resolve()
    return (REPO_ROOT / raw_paths["default_data_dir"]).resolve()


def load_config(config_path: Path | None = None) -> ProjectConfig:
    """Load configs/project.yaml, applying the DEMANDFLOW_DATA_DIR override.

    Raises FileNotFoundError with a clear message if the YAML file is missing,
    rather than silently falling back to hard-coded defaults.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Project config not found at {path}. Expected configs/project.yaml "
            "in the repository root."
        )
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    data_dir = _resolve_data_dir(raw["paths"])
    paths = Paths(
        data_dir=data_dir,
        raw_dir=data_dir / raw["paths"]["raw_subdir"],
        parquet_dir=data_dir / raw["paths"]["parquet_subdir"],
        reports_dir=REPO_ROOT / "reports",
        configs_dir=REPO_ROOT / "configs",
    )

    dataset = DatasetConfig(
        kaggle_competition_slug=raw["dataset"]["kaggle_competition_slug"],
        display_name=raw["dataset"]["display_name"],
        files=list(raw["dataset"]["files"]),
    )

    dev_scope = DevScopeConfig(
        target_item_fraction=float(raw["dev_scope"]["target_item_fraction"]),
        min_items_per_stratum_cell=int(raw["dev_scope"]["min_items_per_stratum_cell"]),
        volume_quantiles=int(raw["dev_scope"]["volume_quantiles"]),
        promo_intensity_threshold=float(raw["dev_scope"]["promo_intensity_threshold"]),
    )

    return ProjectConfig(
        random_seed=int(raw["random_seed"]),
        dataset=dataset,
        paths=paths,
        dev_scope=dev_scope,
        raw=raw,
    )
