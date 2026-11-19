"""Run Level 1 and compare with the R reference results.

Run from the repository root:
    python validation/level1/make_fixture.py
    Rscript validation/level1/reference.R
    python validation/level1/run_level1.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.compare import (  # noqa: E402
    cohen_kappa,
    cronbach_alpha,
    equipercentile,
    icc21,
)

HERE = Path(__file__).resolve().parent
TOLERANCE = {"alpha_phq": 1e-6, "alpha_ex": 1e-6, "icc21": 1e-4, "kappa": 1e-6}


def classify(score: pd.Series, cutoffs: list[float], labels: list[str]) -> pd.Series:
    out = pd.Series([labels[0]] * len(score), index=score.index, dtype=object)
    for cutoff, label in zip(cutoffs, labels, strict=True):
        out[score >= cutoff] = label
    return out


def main() -> int:
    data = pd.read_csv(HERE / "fixture.csv")
    r_results = json.loads((HERE / "r_results.json").read_text(encoding="utf-8"))

    phq_items = data[[f"phq{i}" for i in range(1, 10)]]
    ex_items = data[[f"ex{i}" for i in range(1, 13)]]
    phq_total = phq_items.sum(axis=1)
    ex_total = ex_items.sum(axis=1)

    phq_labels = classify(
        phq_total, [0, 5, 10, 15, 20],
        ["minimal", "mild", "moderate", "moderately_severe", "severe"],
    )
    ex_labels = classify(
        ex_total, [0, 12, 24, 36], ["low", "moderate", "high", "very_high"]
    )

    python_results = {
        "alpha_phq": cronbach_alpha(phq_items),
        "alpha_ex": cronbach_alpha(ex_items),
        "icc21": icc21(phq_total, ex_total),
        "kappa": cohen_kappa(phq_labels, ex_labels)["kappa"],
    }

    print(f"{'metric':12s} {'python':>12s} {'R':>12s} {'abs diff':>12s}  status")
    failed = False
    for metric, tolerance in TOLERANCE.items():
        py_value = float(python_results[metric])
        r_value = float(r_results[metric])
        difference = abs(py_value - r_value)
        ok = difference <= tolerance
        failed = failed or not ok
        print(
            f"{metric:12s} {py_value:12.8f} {r_value:12.8f} "
            f"{difference:12.2e}  {'ok' if ok else 'FAIL'}"
        )

    # Linking check. BRIDGE-D uses mid-percentile quantile interpolation;
    # equate uses half-interval linear interpolation, so the linked scores
    # are compared with a tolerance rather than bitwise.
    table = equipercentile(phq_total, ex_total)
    py_link = dict(zip(table["score_a"], table["linked_b"], strict=True))
    py_pct = dict(zip(table["score_a"], table["percentile"], strict=True))
    r_link = dict(zip(r_results["link_x"], r_results["link_y"], strict=True))
    r_pct = dict(zip(r_results["link_x"], r_results["percentile"], strict=True))
    common = sorted(set(py_link) & set(r_link))
    link_diffs = [abs(py_link[x] - r_link[x]) for x in common]
    pct_diffs = [abs(py_pct[x] - r_pct[x]) for x in common]
    max_link = max(link_diffs)
    mean_link = sum(link_diffs) / len(link_diffs)
    max_pct = max(pct_diffs)

    linking = {
        "link_max": (max_link, 1.0),
        "link_mean": (mean_link, 0.5),
        "percentile_max": (max_pct, 1e-10),
    }
    print()
    for metric, (value, tolerance) in linking.items():
        ok = value <= tolerance
        failed = failed or not ok
        print(
            f"{metric:12s} {value:12.8f} {tolerance:12.2e} "
            f"{'ok' if ok else 'FAIL'}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
