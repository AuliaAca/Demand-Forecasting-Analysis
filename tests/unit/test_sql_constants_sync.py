"""Pin test: sql/staging/07_stg_sales.sql hardcodes the same IQR multiplier
as demandflow.quality.rules.EXTREME_VALUE_IQR_MULTIPLIER (SQL text can't
import a Python constant, so the two must be kept in sync by hand -- this
test fails loudly if someone changes one without the other).
"""

from pathlib import Path

from demandflow.quality.rules import EXTREME_VALUE_IQR_MULTIPLIER

REPO_ROOT = Path(__file__).resolve().parents[2]
STG_SALES_SQL = REPO_ROOT / "sql" / "staging" / "07_stg_sales.sql"


def test_extreme_value_multiplier_matches_between_python_and_sql():
    assert EXTREME_VALUE_IQR_MULTIPLIER == 3.0, (
        "This test (and the hardcoded value in 07_stg_sales.sql) assumes 3.0. "
        "If you change EXTREME_VALUE_IQR_MULTIPLIER, update both."
    )
    sql_text = STG_SALES_SQL.read_text(encoding="utf-8")
    assert "3.0 * f.iqr" in sql_text, (
        "07_stg_sales.sql no longer contains the expected '3.0 * f.iqr' term -- "
        "check it still matches demandflow.quality.rules.EXTREME_VALUE_IQR_MULTIPLIER."
    )
