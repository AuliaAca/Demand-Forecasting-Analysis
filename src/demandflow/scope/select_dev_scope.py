"""Stratified, reproducible selection of the controlled development scope.

Implements the methodology in docs/decisions/0001-phase00-decisions-and-scope.md
§2: every store and the full date range are kept; only the item/SKU dimension
is subsetted, stratified by family × perishable × sales-volume tier × promotion
intensity, with a fixed seed, so fast movers, slow/intermittent movers,
promoted items, and every product family all stay represented in the
development scope — not just top sellers.

[DECISION] Sampling parameters (target fraction, quantile count, promo
threshold, minimum items per cell) live in configs/project.yaml, not here.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb

from demandflow.config import DevScopeConfig
from demandflow.profiling.checks import scan_expr


@dataclass(frozen=True)
class ItemStratumStats:
    item_nbr: int
    family: str
    item_class: int
    perishable: int
    total_unit_sales: float
    observed_days: int
    promo_days: int
    promo_share: float
    volume_quantile: int
    promo_flag: bool
    selected: bool


def compute_item_stats(
    con: duckdb.DuckDBPyConnection,
    sales_path: Path,
    items_path: Path,
    dev_scope_cfg: DevScopeConfig,
) -> list[dict[str, Any]]:
    """One row per item: family/class/perishable + volume and promo signals."""
    sales, items = scan_expr(sales_path), scan_expr(items_path)
    rows = con.execute(
        f"""
        WITH item_totals AS (
            SELECT
                it.item_nbr,
                it.family,
                it.class AS item_class,
                it.perishable,
                COALESCE(SUM(s.unit_sales), 0) AS total_unit_sales,
                COUNT(s.unit_sales) AS observed_days,
                COALESCE(SUM(CASE WHEN s.onpromotion THEN 1 ELSE 0 END), 0) AS promo_days
            FROM {items} it
            LEFT JOIN {sales} s ON s.item_nbr = it.item_nbr
            GROUP BY it.item_nbr, it.family, it.class, it.perishable
        )
        SELECT
            item_nbr, family, item_class, perishable,
            total_unit_sales, observed_days, promo_days,
            CASE WHEN observed_days > 0 THEN promo_days::DOUBLE / observed_days ELSE 0.0 END AS promo_share,
            NTILE({dev_scope_cfg.volume_quantiles}) OVER (
                PARTITION BY family ORDER BY total_unit_sales
            ) AS volume_quantile
        FROM item_totals
        ORDER BY family, item_nbr
        """
    ).fetchall()
    columns = [
        "item_nbr", "family", "item_class", "perishable", "total_unit_sales",
        "observed_days", "promo_days", "promo_share", "volume_quantile",
    ]
    return [dict(zip(columns, row)) for row in rows]


def _stratum_key(row: dict[str, Any], promo_flag: bool) -> str:
    return f"{row['family']}|{row['perishable']}|{row['volume_quantile']}|{promo_flag}"


def stratify_and_sample(
    item_stats: list[dict[str, Any]],
    dev_scope_cfg: DevScopeConfig,
    seed: int,
) -> list[ItemStratumStats]:
    """Deterministic stratified sampling.

    Each stratum cell gets its own `random.Random`, seeded from the global
    seed plus the cell's own key (as a string) — so adding, removing, or
    resizing one cell never perturbs the draw made in any other cell.
    """
    for row in item_stats:
        row["promo_flag"] = row["promo_share"] > dev_scope_cfg.promo_intensity_threshold

    cells: dict[str, list[dict[str, Any]]] = {}
    for row in item_stats:
        key = _stratum_key(row, row["promo_flag"])
        cells.setdefault(key, []).append(row)

    results: list[ItemStratumStats] = []
    for key, cell_rows in cells.items():
        n = len(cell_rows)
        target = max(
            dev_scope_cfg.min_items_per_stratum_cell,
            round(n * dev_scope_cfg.target_item_fraction),
        )
        target = min(target, n)
        rng = random.Random(f"{seed}:{key}")
        ordered = sorted(cell_rows, key=lambda r: r["item_nbr"])  # deterministic input order
        selected_items = set(rng.sample([r["item_nbr"] for r in ordered], k=target))
        for row in ordered:
            results.append(
                ItemStratumStats(
                    item_nbr=row["item_nbr"],
                    family=row["family"],
                    item_class=row["item_class"],
                    perishable=row["perishable"],
                    total_unit_sales=row["total_unit_sales"],
                    observed_days=row["observed_days"],
                    promo_days=row["promo_days"],
                    promo_share=row["promo_share"],
                    volume_quantile=row["volume_quantile"],
                    promo_flag=row["promo_flag"],
                    selected=row["item_nbr"] in selected_items,
                )
            )
    return sorted(results, key=lambda r: r.item_nbr)


def summarize_selection(selection: list[ItemStratumStats]) -> dict[str, Any]:
    total_items = len(selection)
    selected = [r for r in selection if r.selected]
    total_sales_all = sum(r.total_unit_sales for r in selection)
    total_sales_selected = sum(r.total_unit_sales for r in selected)
    return {
        "total_items": total_items,
        "selected_items": len(selected),
        "selected_item_fraction": len(selected) / total_items if total_items else 0.0,
        "total_unit_sales_all_items": total_sales_all,
        "total_unit_sales_selected_items": total_sales_selected,
        "selected_share_of_total_unit_sales": (
            total_sales_selected / total_sales_all if total_sales_all else 0.0
        ),
        "stratum_cells": len({_stratum_key(asdict(r), r.promo_flag) for r in selection}),
        "perishable_selected": sum(1 for r in selected if r.perishable == 1),
        "non_perishable_selected": sum(1 for r in selected if r.perishable == 0),
        "families_represented_in_selection": sorted({r.family for r in selected}),
    }


def write_dev_scope_csv(selection: list[ItemStratumStats], out_path: Path) -> Path:
    import csv

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(selection[0]).keys()) if selection else [])
        writer.writeheader()
        for row in selection:
            writer.writerow(asdict(row))
    return out_path


def _main() -> None:
    import json
    import logging

    import duckdb as _duckdb

    from demandflow.config import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()

    train_path = cfg.paths.parquet_dir / "train.parquet"
    items_path = cfg.paths.parquet_dir / "items.parquet"
    if not train_path.exists() or not items_path.exists():
        raise FileNotFoundError(
            f"Expected {train_path} and {items_path} to exist. "
            "Run demandflow.ingest.convert_to_parquet first."
        )

    con = _duckdb.connect()
    stats = compute_item_stats(con, train_path, items_path, cfg.dev_scope)
    con.close()

    selection = stratify_and_sample(stats, cfg.dev_scope, seed=cfg.random_seed)
    summary = summarize_selection(selection)

    # [DECISION] The frozen item list is committed (ADR 0001 §2.4) — it is a
    # short list of item IDs, not raw data — while the fuller per-item CSV
    # and the JSON summary are run outputs kept under reports/, not git.
    dev_scope_csv_path = cfg.paths.configs_dir / "dev_scope_items.csv"
    write_dev_scope_csv(selection, dev_scope_csv_path)

    summary_path = cfg.paths.reports_dir / "phase01" / "dev_scope_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Selected {summary['selected_items']}/{summary['total_items']} items")
    print(f"Wrote {dev_scope_csv_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    _main()
