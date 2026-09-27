"""LightGBM global model for Phase 07.

[DECISION] LightGBM, per Phase 00's plan (docs/00_requirement_analysis_and_system_plan.md
Section 9 / ADR 0001) -- a fast, well-established gradient-boosting library
that handles categorical features and missing values natively, matching
features.py's design (gaps left as NaN, never imputed).

[DECISION] "Global" model: one model fit across every (store, item) series
pooled together, not one model per series. This is the specific case for
trying ML here at all -- even a short per-series history contributes rows
to a model that can learn shared patterns across series, which is
established practice for retail panel data (e.g. the M5 competition's
top solutions were global gradient-boosting models). A per-series model
would need far more history per series than this project's development
scope -- let alone the fixture -- can offer.

[DECISION] Hyperparameters are small and fixed, not tuned -- num_leaves/
min_data_in_leaf set low enough to fit on this project's data volumes
(including the tiny fixture) without immediately refusing to split.
Deliberately not tuned, for the same reason Phase 06 didn't tune Croston's
alpha: tuning on this little data would answer "can this be made to look
good on 50 rows" rather than this phase's actual question.
"""

from __future__ import annotations

import lightgbm as lgb
import pandas as pd

from demandflow.forecasting.features import ALL_FEATURE_NAMES, CATEGORICAL_FEATURE_NAMES

DEFAULT_PARAMS = dict(
    objective="regression",
    metric="mae",
    num_leaves=7,
    min_data_in_leaf=3,
    learning_rate=0.1,
    n_estimators=50,
    min_gain_to_split=0.0,
    verbosity=-1,
)

# Below this many training rows, fitting a global model is not meaningful
# (a handful of rows can't support even this phase's small tree depth) --
# report "insufficient training data" rather than fit noise.
MIN_TRAINING_ROWS = 10


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=ALL_FEATURE_NAMES)
    for col in CATEGORICAL_FEATURE_NAMES:
        df[col] = df[col].astype("category")
    return df


def train_model(
    training_rows: list[dict], training_labels: list[float], params: dict | None = None
) -> lgb.LGBMRegressor | None:
    """Returns None (not an exception) when there isn't enough training
    data to fit meaningfully -- the caller treats that as "ML not
    evaluable on this run", not a crash."""
    if len(training_rows) < MIN_TRAINING_ROWS:
        return None
    X = rows_to_frame(training_rows)
    model = lgb.LGBMRegressor(**{**DEFAULT_PARAMS, **(params or {})})
    model.fit(X, training_labels, categorical_feature=CATEGORICAL_FEATURE_NAMES)
    return model


def predict(model: lgb.LGBMRegressor, rows: list[dict]) -> list[float]:
    X = rows_to_frame(rows)
    preds = model.predict(X)
    # Unit sales can't be negative; LightGBM regression is unconstrained,
    # so a point forecast is clamped at zero -- standard practice for
    # demand forecasting, [DECISION] not a JD figure.
    return [max(0.0, float(p)) for p in preds]
