"""Level 2: recovery and interval coverage across data conditions.

Generates data with known truth, applies a missingness mechanism, runs the
BRIDGE-D scoring and comparison functions, and records bias, RMSE, CI
coverage, CI width and crosswalk error.

Run from the repository root:
    python validation/level2/run_grid.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.compare import equipercentile, icc21  # noqa: E402

HERE = Path(__file__).resolve().parent
CALIBRATION = json.loads((HERE / "calibration.json").read_text(encoding="utf-8"))
THRESHOLDS_A = np.array(CALIBRATION["thresholds"])
THRESHOLDS_B = np.array([THRESHOLDS_A[i % len(THRESHOLDS_A)] for i in range(12)])
LOADINGS_A = np.full(9, 0.70)
LOADINGS_B = np.full(12, 0.70)
N_GRID = [42, 100, 200]
LATENT_R_GRID = [0.2, 0.4, 0.6]
MISSING_GRID = ["none", "mcar20", "mnar20"]
REPLICATIONS = 200
TRUTH_N = 100_000
SEED = 20261119


def generate(
    n: int,
    latent_r: float,
    missing: str,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    first = rng.normal(size=n)
    second = rng.normal(size=n)
    theta_a = first
    theta_b = latent_r * first + np.sqrt(max(0.0, 1.0 - latent_r**2)) * second

    def items(theta: np.ndarray, loadings: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
        values = np.empty((n, len(loadings)))
        for index, loading in enumerate(loadings):
            noise = rng.normal(size=n)
            z = loading * theta + np.sqrt(max(0.0, 1.0 - loading**2)) * noise
            values[:, index] = np.digitize(z, thresholds[index])
        return values

    a = items(theta_a, LOADINGS_A, THRESHOLDS_A)
    b = items(theta_b, LOADINGS_B, THRESHOLDS_B)

    if missing != "none":
        rate = 0.20
        if missing == "mcar20":
            mask_a = rng.random(a.shape) < rate
            mask_b = rng.random(b.shape) < rate
        elif missing == "mnar20":
            mask_a = rng.random(a.shape) < rate * (a / 3.0)
            mask_b = rng.random(b.shape) < rate * (b / 3.0)
        else:
            raise ValueError(f"unknown missingness {missing!r}")
        a = a.astype(float)
        b = b.astype(float)
        a[mask_a] = np.nan
        b[mask_b] = np.nan

    return pd.DataFrame(a), pd.DataFrame(b)


def prorate(values: pd.DataFrame, min_answered: int) -> pd.Series:
    answered = values.notna().sum(axis=1)
    total = values.sum(axis=1, skipna=True)
    scored = total * values.shape[1] / answered.replace(0, np.nan)
    return scored.mask(answered < min_answered)


def fisher_interval(r: float, n: int) -> tuple[float, float]:
    if not np.isfinite(r) or n < 4:
        return float("nan"), float("nan")
    clipped = float(np.clip(r, -0.999999, 0.999999))
    z = np.arctanh(clipped)
    half = 1.96 / np.sqrt(n - 3)
    return float(np.tanh(z - half)), float(np.tanh(z + half))


def crosswalk_rmse(estimated: pd.DataFrame, truth: pd.DataFrame) -> float:
    low, high = truth["score_a"].quantile([0.05, 0.95])
    common = truth[
        (truth["score_a"] >= low)
        & (truth["score_a"] <= high)
        & (truth["score_a"] >= estimated["score_a"].min())
        & (truth["score_a"] <= estimated["score_a"].max())
    ]
    if common.empty:
        return float("nan")
    interpolated = np.interp(
        common["score_a"], estimated["score_a"], estimated["linked_b"]
    )
    return float(np.sqrt(np.mean((common["linked_b"] - interpolated) ** 2)))


def build_truth(latent_r: float, missing: str) -> dict[str, object]:
    index = MISSING_GRID.index(missing)
    rng = np.random.default_rng(SEED + int(latent_r * 1000) + index * 7919)
    a, b = generate(TRUTH_N, latent_r, missing, rng)
    total_a = prorate(a, 7)
    total_b = prorate(b, 10)
    pair = pd.concat([total_a, total_b], axis=1).dropna()
    return {
        "r": float(pair.corr().iloc[0, 1]),
        "icc": icc21(total_a, total_b),
        "link": equipercentile(total_a, total_b),
    }


def main() -> None:
    rows: list[dict[str, object]] = []
    truths = {
        (latent_r, missing): build_truth(latent_r, missing)
        for latent_r in LATENT_R_GRID
        for missing in MISSING_GRID
    }
    no_missing_r = {
        latent_r: truths[(latent_r, "none")]["r"] for latent_r in LATENT_R_GRID
    }

    for n in N_GRID:
        for latent_r in LATENT_R_GRID:
            for missing in MISSING_GRID:
                truth = truths[(latent_r, missing)]
                for replication in range(REPLICATIONS):
                    rng = np.random.default_rng(
                        SEED + n * 10_000 + int(latent_r * 1000) + replication
                    )
                    a, b = generate(n, latent_r, missing, rng)
                    total_a = prorate(a, 7)
                    total_b = prorate(b, 10)
                    pair = pd.concat([total_a, total_b], axis=1).dropna()
                    if len(pair) < 5:
                        continue
                    r_value = float(pair.corr().iloc[0, 1])
                    low, high = fisher_interval(r_value, len(pair))
                    try:
                        estimate = equipercentile(total_a, total_b)
                        rmse = crosswalk_rmse(estimate, truth["link"])
                    except ValueError:
                        rmse = float("nan")
                    rows.append(
                        {
                            "n": n,
                            "latent_r": latent_r,
                            "missing": missing,
                            "replication": replication,
                            "n_eff": len(pair),
                            "r": r_value,
                            "ci_low": low,
                            "ci_high": high,
                            "true_r": no_missing_r[latent_r],
                            "true_r_mech": truth["r"],
                            "icc": icc21(total_a, total_b),
                            "true_icc": truth["icc"],
                            "crosswalk_rmse": rmse,
                        }
                    )

    results = pd.DataFrame(rows)
    results.to_csv(HERE / "results.csv", index=False)

    summary_rows = []
    for (n, latent_r, missing), group in results.groupby(
        ["n", "latent_r", "missing"], sort=True
    ):
        summary_rows.append(
            {
                "n": n,
                "latent_r": latent_r,
                "missing": missing,
                "reps": len(group),
                "mean_n_eff": group["n_eff"].mean(),
                "true_r": group["true_r"].iloc[0],
                "true_r_mech": group["true_r_mech"].iloc[0],
                "mean_r": group["r"].mean(),
                "bias_r": group["r"].mean() - group["true_r"].iloc[0],
                "bias_mech": group["r"].mean() - group["true_r_mech"].iloc[0],
                "rmse_r": np.sqrt(np.mean((group["r"] - group["true_r"]) ** 2)),
                "coverage_r": np.mean(
                    (group["ci_low"] <= group["true_r_mech"])
                    & (group["true_r_mech"] <= group["ci_high"])
                ),
                "mean_ci_width": (group["ci_high"] - group["ci_low"]).mean(),
                "true_icc": group["true_icc"].iloc[0],
                "mean_icc": group["icc"].mean(),
                "crosswalk_rmse": np.nanmean(group["crosswalk_rmse"]),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(HERE / "summary.csv", index=False)
    print(summary.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
