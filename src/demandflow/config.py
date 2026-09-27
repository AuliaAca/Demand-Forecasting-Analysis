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
class ForecastingConfig:
    horizon_days: int
    season_length_days: int
    as_of_cadence_days: int
    min_history_days: int


@dataclass(frozen=True)
class ProjectConfig:
    random_seed: int
    dataset: DatasetConfig
    paths: Paths
    dev_scope: DevScopeConfig
    forecasting: ForecastingConfig
    raw: dict[str, Any]


def _resolve_data_dir(raw_paths: dict[str, Any]) -> Path:
    env_var = raw_paths["data_dir_env_var"]
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser().resolve()
    return (REPO_ROOT / raw_paths["default_data_dir"]).resolve()


class ConfigError(ValueError):
    """Raised for a project.yaml that parses but is missing a required key
    or has a value outside its valid range -- distinct from FileNotFoundError
    (file missing) and yaml.YAMLError (file present but not valid YAML),
    so callers can tell "config absent" apart from "config wrong"."""


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in raw:
        raise ConfigError(f"project.yaml is missing the required '{name}' section.")
    return raw[name]


def _positive_int(section: dict[str, Any], key: str, section_name: str) -> int:
    value = int(section[key])
    if value <= 0:
        raise ConfigError(f"{section_name}.{key} must be a positive integer, got {value}.")
    return value


def _unit_fraction(section: dict[str, Any], key: str, section_name: str) -> float:
    value = float(section[key])
    if not (0.0 < value <= 1.0):
        raise ConfigError(f"{section_name}.{key} must be in (0, 1], got {value}.")
    return value


def load_config(config_path: Path | None = None) -> ProjectConfig:
    """Load configs/project.yaml, applying the DEMANDFLOW_DATA_DIR override.

    Raises FileNotFoundError if the YAML file is missing, and ConfigError if
    it parses but a required section is absent or a value is out of range
    (e.g. a negative horizon_days) -- rather than either silently falling
    back to hard-coded defaults or letting a downstream phase fail later
    with a confusing, indirect error (CLAUDE.md Section 14: validation,
    failure handling).
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Project config not found at {path}. Expected configs/project.yaml "
            "in the repository root."
        )
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} did not parse to a mapping -- got {type(raw).__name__}.")

    if "random_seed" not in raw:
        raise ConfigError("project.yaml is missing the required 'random_seed' key.")
    random_seed = int(raw["random_seed"])
    if random_seed < 0:
        raise ConfigError(f"random_seed must be >= 0, got {random_seed}.")

    try:
        paths_section = _section(raw, "paths")
        data_dir = _resolve_data_dir(paths_section)
        paths = Paths(
            data_dir=data_dir,
            raw_dir=data_dir / paths_section["raw_subdir"],
            parquet_dir=data_dir / paths_section["parquet_subdir"],
            reports_dir=REPO_ROOT / "reports",
            configs_dir=REPO_ROOT / "configs",
        )

        dataset_section = _section(raw, "dataset")
        dataset = DatasetConfig(
            kaggle_competition_slug=dataset_section["kaggle_competition_slug"],
            display_name=dataset_section["display_name"],
            files=list(dataset_section["files"]),
        )

        dev_scope_section = _section(raw, "dev_scope")
        dev_scope = DevScopeConfig(
            target_item_fraction=_unit_fraction(dev_scope_section, "target_item_fraction", "dev_scope"),
            min_items_per_stratum_cell=_positive_int(dev_scope_section, "min_items_per_stratum_cell", "dev_scope"),
            volume_quantiles=_positive_int(dev_scope_section, "volume_quantiles", "dev_scope"),
            promo_intensity_threshold=_unit_fraction(dev_scope_section, "promo_intensity_threshold", "dev_scope"),
        )

        forecasting_section = _section(raw, "forecasting")
        forecasting = ForecastingConfig(
            horizon_days=_positive_int(forecasting_section, "horizon_days", "forecasting"),
            season_length_days=_positive_int(forecasting_section, "season_length_days", "forecasting"),
            as_of_cadence_days=_positive_int(forecasting_section, "as_of_cadence_days", "forecasting"),
            min_history_days=_positive_int(forecasting_section, "min_history_days", "forecasting"),
        )
    except KeyError as e:
        raise ConfigError(f"project.yaml is missing required key: {e}") from e

    return ProjectConfig(
        random_seed=random_seed,
        dataset=dataset,
        paths=paths,
        dev_scope=dev_scope,
        forecasting=forecasting,
        raw=raw,
    )
