"""Statistical comparisons for co-administered instruments.

Only numpy/pandas are used on purpose: the tool should install anywhere
a researcher already has a scientific Python stack.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "bland_altman",
    "cohen_kappa",
    "cronbach_alpha",
    "descriptives",
    "equipercentile",
    "icc21",
    "pairwise_complete",
]


def pairwise_complete(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Drop rows where either series is missing, keeping alignment."""
    frame = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    return frame["a"], frame["b"]


def descriptives(scores: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for name, series in scores.items():
        valid = series.dropna()
        rows.append(
            {
                "scale": name,
                "n": int(valid.size),
                "mean": float(valid.mean()) if valid.size else np.nan,
                "sd": float(valid.std(ddof=1)) if valid.size > 1 else np.nan,
                "median": float(valid.median()) if valid.size else np.nan,
                "min": float(valid.min()) if valid.size else np.nan,
                "max": float(valid.max()) if valid.size else np.nan,
                "missing": int(series.isna().sum()),
            }
        )
    return pd.DataFrame(rows)


def cronbach_alpha(items: pd.DataFrame) -> float:
    """Cronbach's alpha over complete cases."""
    items = items.dropna()
    k = items.shape[1]
    if k < 2 or len(items) < 2:
        return float("nan")
    item_variance = items.var(axis=0, ddof=1).sum()
    total_variance = items.sum(axis=1).var(ddof=1)
    if total_variance == 0:
        return float("nan")
    return float(k / (k - 1) * (1 - item_variance / total_variance))


def icc21(a: pd.Series, b: pd.Series) -> float:
    """ICC(2,1): two-way random effects, absolute agreement, single measure."""
    a, b = pairwise_complete(a, b)
    data = np.column_stack([a.to_numpy(float), b.to_numpy(float)])
    n, k = data.shape
    if n < 2 or k < 2:
        return float("nan")
    grand = data.mean()
    row_means = data.mean(axis=1)
    col_means = data.mean(axis=0)
    ss_between = k * ((row_means - grand) ** 2).sum()
    ss_rater = n * ((col_means - grand) ** 2).sum()
    ss_error = ((data - row_means[:, None] - col_means[None, :] + grand) ** 2).sum()
    ms_between = ss_between / (n - 1)
    ms_rater = ss_rater / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))
    denominator = ms_between + (k - 1) * ms_error + k * (ms_rater - ms_error) / n
    if denominator == 0:
        return float("nan")
    return float((ms_between - ms_error) / denominator)


def bland_altman(a: pd.Series, b: pd.Series) -> dict[str, float]:
    """Bland-Altman summary on the raw metric (same units required)."""
    a, b = pairwise_complete(a, b)
    diff = a - b
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1))
    return {
        "n": int(diff.size),
        "mean_diff": mean_diff,
        "sd_diff": sd_diff,
        "loa_lower": mean_diff - 1.96 * sd_diff,
        "loa_upper": mean_diff + 1.96 * sd_diff,
    }


def cohen_kappa(a: pd.Series, b: pd.Series) -> dict[str, float]:
    """Cohen's kappa for two categorical labellings."""
    frame = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if frame.empty:
        return {"n": 0, "kappa": float("nan"), "agreement": float("nan")}
    labels = sorted(set(frame["a"]) | set(frame["b"]), key=str)
    index = {label: i for i, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=float)
    for left, right in zip(frame["a"], frame["b"], strict=True):
        matrix[index[left], index[right]] += 1
    n = matrix.sum()
    observed = np.trace(matrix) / n
    expected = float((matrix.sum(axis=0) * matrix.sum(axis=1)).sum() / n**2)
    kappa = float("nan") if expected == 1 else (observed - expected) / (1 - expected)
    return {"n": int(n), "kappa": kappa, "agreement": float(observed)}


def equipercentile(
    a: pd.Series,
    b: pd.Series,
    n_boot: int = 0,
    seed: int = 0,
) -> pd.DataFrame:
    """Equipercentile linking of scale A onto scale B.

    Both series must come from the *same* subjects. Returns one row per
    observed score of A with the linked B score at the same mid-percentile.
    The convention is mid-percentile rank followed by NumPy's linear target
    quantile interpolation. It differs from equate's half-interval convention.
    """
    a, b = pairwise_complete(a, b)
    a_values = a.to_numpy(float)
    b_values = b.to_numpy(float)
    if a_values.size < 10:
        raise ValueError("equipercentile linking needs at least 10 complete pairs")

    result = _equipercentile_once(a_values, b_values)
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        samples = []
        for _ in range(n_boot):
            idx = rng.integers(0, a_values.size, a_values.size)
            boot = _equipercentile_once(a_values[idx], b_values[idx])
            samples.append(boot.set_index("score_a")["linked_b"])
        boot_frame = pd.concat(samples, axis=1)
        result["ci_low"] = result["score_a"].map(boot_frame.quantile(0.025, axis=1))
        result["ci_high"] = result["score_a"].map(boot_frame.quantile(0.975, axis=1))
    return result


def _equipercentile_once(a_values: np.ndarray, b_values: np.ndarray) -> pd.DataFrame:
    scores = np.unique(a_values)
    percentiles = []
    for score in scores:
        below = np.sum(a_values < score)
        equal = np.sum(a_values == score)
        percentiles.append((below + 0.5 * equal) / a_values.size)
    linked = np.quantile(b_values, percentiles, method="linear")
    return pd.DataFrame(
        {
            "score_a": scores,
            "percentile": percentiles,
            "linked_b": linked,
        }
    )
