"""Run the end-to-end BRIDGE-D pipeline on NHANES PHQ-9 plus a synthetic companion.

Stage 1 uses real public NHANES data and checks scoring, internal consistency
and the score distribution. Stage 2 adds a synthetic 12-item companion scale so
the comparison, linking and report path can run on a co-administered-like file.

The companion is synthetic. This script tests the software pipeline; it does
not produce empirical evidence about any real instrument.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.compare import cronbach_alpha, icc21  # noqa: E402
from bridged.docx_report import build_docx  # noqa: E402
from bridged.instrument import Instrument  # noqa: E402
from bridged.report import build_report  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "nhanes_phq9.csv"
OUTPUT = HERE / "output"
SEED = 20261119
RHO = 0.6


def synthesize_companion(phq_total: pd.Series, rng: np.random.Generator) -> pd.DataFrame:
    """Create 12 items correlated with the observed PHQ-9 total.

    The latent score is a noisy function of the standardized PHQ-9 total. This
    produces a co-administered-like table for pipeline testing only.
    """
    z = (phq_total - phq_total.mean()) / phq_total.std(ddof=1)
    z = z.fillna(0.0)
    theta = RHO * z.to_numpy() + np.sqrt(1.0 - RHO**2) * rng.normal(size=len(z))
    items: dict[str, np.ndarray] = {}
    for index in range(1, 13):
        raw = 2.0 + 0.9 * theta + rng.normal(0.0, 0.9, len(z))
        items[f"ex{index}"] = np.clip(np.rint(raw), 0, 4).astype(int)
    for item in ("ex5", "ex9"):
        items[item] = 4 - items[item]
    return pd.DataFrame(items)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    phq9 = Instrument.load(ROOT / "instruments" / "phq9.toml")
    companion = Instrument.load(ROOT / "instruments" / "example_new.toml")

    raw = pd.read_csv(DATA)
    scores = phq9.score(raw)
    total = scores["phq9_total"]
    print("== stage 1: NHANES PHQ-9 ==")
    print(f"n = {len(raw)}, scored = {total.notna().sum()}")
    print(f"mean = {total.mean():.2f}, sd = {total.std(ddof=1):.2f}")
    print(f"alpha = {cronbach_alpha(phq9.item_values(raw)):.3f}")

    rng = np.random.default_rng(SEED)
    synthetic = synthesize_companion(total, rng)
    cohort = pd.concat([raw.reset_index(drop=True), synthetic], axis=1)
    cohort.to_csv(OUTPUT / "cohort_with_companion.csv", index=False)

    total_b = companion.score(cohort)["example_new_total"]
    pair = pd.concat([total, total_b], axis=1).dropna()
    print("\n== stage 2: synthetic companion ==")
    print(f"n = {len(pair)}")
    print(f"pearson = {pair.corr().iloc[0, 1]:.3f}")
    print(f"icc21 = {icc21(total, total_b):.3f}")

    report = build_report(phq9, companion, cohort, n_boot=200, lang="zh")
    (OUTPUT / "application_report.md").write_text(report, encoding="utf-8")
    build_docx(
        phq9,
        companion,
        cohort,
        n_boot=200,
        lang="zh",
        path=OUTPUT / "application_report.docx",
    )
    scores.to_csv(OUTPUT / "nhanes_phq9_scores.csv", index=False)

    print("\nwrote:")
    for name in (
        "cohort_with_companion.csv",
        "nhanes_phq9_scores.csv",
        "application_report.md",
        "application_report.docx",
    ):
        print(f"  {OUTPUT / name}")


if __name__ == "__main__":
    main()
