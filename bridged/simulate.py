"""Simulation utilities: known-truth data for software validation and power.

Two jobs:

1. Generate a dataset where the true correlation, ICC and crosswalk are known,
   so the comparison pipeline can be checked for recovery.
2. Repeat that generation many times at a given n to estimate bias, confidence
   interval coverage and interval width (a sample-size planning tool).

The model is deliberately simple: one shared latent trait, instrument-specific
item loadings, ordinal responses via normal thresholds.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from .compare import equipercentile, icc21

__all__ = [
    "InstrumentSpec",
    "SimConfig",
    "compute_truth",
    "generate",
    "load_config",
    "run_simulation",
]

_NORMAL = NormalDist()


@dataclass
class InstrumentSpec:
    id: str
    items: int
    loadings: list[float]
    levels: int = 5
    missing_rate: float = 0.0


@dataclass
class SimConfig:
    n: int
    seed: int
    replications: int
    a: InstrumentSpec
    b: InstrumentSpec
    latent_r: float = 0.6


def _loadings(spec: dict[str, Any], items: int) -> list[float]:
    if "loadings" in spec:
        values = [float(x) for x in spec["loadings"]]
        if len(values) != items:
            raise ValueError(
                f"{spec.get('id', 'instrument')}: {len(values)} loadings for {items} items"
            )
        return values
    return [float(spec.get("loading", 0.6))] * items


def _spec(name: str, raw: dict[str, Any]) -> InstrumentSpec:
    items = int(raw.get("items", 6))
    spec = InstrumentSpec(
        id=str(raw.get("id", name)),
        items=items,
        loadings=_loadings(raw, items),
        levels=int(raw.get("levels", 5)),
        missing_rate=float(raw.get("missing_rate", 0.0)),
    )
    if spec.levels < 2:
        raise ValueError(f"{spec.id}: levels must be >= 2")
    if any(not 0.0 <= value <= 1.0 for value in spec.loadings):
        raise ValueError(f"{spec.id}: loadings must be in [0, 1]")
    if not 0.0 <= spec.missing_rate < 1.0:
        raise ValueError(f"{spec.id}: missing_rate must be in [0, 1)")
    return spec


def load_config(path: str | Path) -> SimConfig:
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)
    config = SimConfig(
        n=int(raw.get("n", 200)),
        seed=int(raw.get("seed", 0)),
        replications=int(raw.get("replications", 1)),
        a=_spec("instrument_a", raw.get("instrument_a", {})),
        b=_spec("instrument_b", raw.get("instrument_b", {})),
        latent_r=float(raw.get("model", {}).get("latent_r", 0.6)),
    )
    if config.n < 10:
        raise ValueError("n must be >= 10")
    if config.replications < 1:
        raise ValueError("replications must be >= 1")
    if not -1.0 <= config.latent_r <= 1.0:
        raise ValueError("model.latent_r must be in [-1, 1]")
    return config


def _cuts(levels: int) -> list[float]:
    return [_NORMAL.inv_cdf(k / levels) for k in range(1, levels)]


def generate(config: SimConfig, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate one dataset.

    The two instruments measure correlated-but-distinct latents:
    ``latent_r`` controls how much of the shared variance they have, while
    item loadings and ordinals set the instrument-specific structure.
    """
    first = rng.normal(size=n)
    second = rng.normal(size=n)
    theta_a = first
    theta_b = config.latent_r * first + np.sqrt(
        max(0.0, 1.0 - config.latent_r**2)
    ) * second

    out: dict[str, np.ndarray] = {}
    for spec, theta in ((config.a, theta_a), (config.b, theta_b)):
        cuts = _cuts(spec.levels)
        for index, loading in enumerate(spec.loadings, start=1):
            residual = rng.normal(size=n)
            z = loading * theta + np.sqrt(max(0.0, 1.0 - loading**2)) * residual
            values = np.digitize(z, cuts).astype(float)
            if spec.missing_rate > 0:
                mask = rng.random(n) < spec.missing_rate
                values[mask] = np.nan
            out[f"{spec.id}_{index}"] = values
    return pd.DataFrame(out)


def _totals(
    data: pd.DataFrame, config: SimConfig
) -> tuple[pd.Series, pd.Series]:
    a_cols = [f"{config.a.id}_{i}" for i in range(1, config.a.items + 1)]
    b_cols = [f"{config.b.id}_{i}" for i in range(1, config.b.items + 1)]
    return data[a_cols].sum(axis=1, skipna=True), data[b_cols].sum(axis=1, skipna=True)


def _corr(left: pd.Series, right: pd.Series) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 3:
        return float("nan")
    return float(pair.corr().iloc[0, 1])


def compute_truth(config: SimConfig, n_truth: int = 200_000, offset: int = 10_000) -> dict[str, Any]:
    """Estimate the population values on a very large synthetic sample."""
    rng = np.random.default_rng(config.seed + offset)
    data = generate(config, n_truth, rng)
    total_a, total_b = _totals(data, config)
    crosswalk = equipercentile(total_a, total_b)
    return {
        "n_truth": n_truth,
        "true_r": _corr(total_a, total_b),
        "true_icc": icc21(total_a, total_b),
        "crosswalk": [
            {"score_a": float(row.score_a), "linked_b": float(row.linked_b)}
            for row in crosswalk.itertuples()
        ],
    }


def _crosswalk_rmse(estimated: pd.DataFrame, truth: list[dict[str, float]]) -> float:
    frame = pd.DataFrame(truth)
    if frame.empty or estimated.empty:
        return float("nan")
    window = frame[
        (frame["score_a"] >= estimated["score_a"].min())
        & (frame["score_a"] <= estimated["score_a"].max())
    ]
    if window.empty:
        return float("nan")
    interpolated = np.interp(
        window["score_a"], estimated["score_a"], estimated["linked_b"]
    )
    return float(np.sqrt(np.mean((window["linked_b"] - interpolated) ** 2)))


def _fisher_interval(r: float, n: int) -> tuple[float, float]:
    if not np.isfinite(r) or n < 4:
        return float("nan"), float("nan")
    clipped = float(np.clip(r, -0.999999, 0.999999))
    z = np.arctanh(clipped)
    half = 1.96 / np.sqrt(n - 3)
    return float(np.tanh(z - half)), float(np.tanh(z + half))


def run_simulation(
    config: SimConfig,
    out_dir: str | Path,
    n: int | None = None,
    replications: int | None = None,
) -> dict[str, Any]:
    """Write data.csv, truth.json and (if repeated) recovery.csv + summary.json."""
    n = n or config.n
    reps = replications or config.replications
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    truth = compute_truth(config)
    (out / "truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rng = np.random.default_rng(config.seed)
    sample = generate(config, n, rng)
    sample.to_csv(out / "data.csv", index=False)

    if reps == 1:
        total_a, total_b = _totals(sample, config)
        return {
            "n": n,
            "true_r": truth["true_r"],
            "sample_r": _corr(total_a, total_b),
            "true_icc": truth["true_icc"],
            "sample_icc": icc21(total_a, total_b),
            "files": [str(out / "data.csv"), str(out / "truth.json")],
        }

    rows: list[dict[str, float]] = []
    for rep in range(reps):
        rep_rng = np.random.default_rng(config.seed + rep)
        data = generate(config, n, rep_rng)
        total_a, total_b = _totals(data, config)
        r_hat = _corr(total_a, total_b)
        low, high = _fisher_interval(r_hat, n)
        estimated = equipercentile(total_a, total_b)
        rows.append(
            {
                "replication": rep,
                "r": r_hat,
                "ci_low": low,
                "ci_high": high,
                "icc": icc21(total_a, total_b),
                "crosswalk_rmse": _crosswalk_rmse(estimated, truth["crosswalk"]),
            }
        )

    recovery = pd.DataFrame(rows)
    recovery.to_csv(out / "recovery.csv", index=False)
    coverage = float(
        np.mean(
            (recovery["ci_low"] <= truth["true_r"])
            & (truth["true_r"] <= recovery["ci_high"])
        )
    )
    summary = {
        "n": n,
        "replications": reps,
        "true_r": truth["true_r"],
        "mean_r": float(recovery["r"].mean()),
        "bias_r": float(recovery["r"].mean() - truth["true_r"]),
        "sd_r": float(recovery["r"].std(ddof=1)),
        "ci_coverage": coverage,
        "mean_ci_width": float((recovery["ci_high"] - recovery["ci_low"]).mean()),
        "true_icc": truth["true_icc"],
        "mean_icc": float(recovery["icc"].mean()),
        "mean_crosswalk_rmse": float(recovery["crosswalk_rmse"].mean()),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
