"""Calibrate the Level 2 simulation from public NHANES PHQ-9 data.

Reads the NHANES 2017-2018 DPQ_J.XPT file, cleans the item responses, and
writes aggregate parameters (thresholds, means, SDs, missing rate) to
calibration.json. No individual-level data is written to the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_XPT = Path(r"F:\科研\5.抑郁量表基础设施\库\公开数据集\DPQ_J.XPT")
ITEMS = [f"DPQ{i:02d}0" for i in range(1, 10)]
NORMAL = NormalDist()


def clean(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    # SAS zero arrives as 5.4e-79; keep true NaN as missing.
    values = values.mask(values < 0.5, 0.0)
    values = values.where(values.isin([0.0, 1.0, 2.0, 3.0]))
    return values


def main() -> None:
    frame = pd.read_sas(DEFAULT_XPT, format="xport")
    items = frame[ITEMS].apply(clean)

    thresholds = []
    means = []
    sds = []
    for column in ITEMS:
        values = items[column].dropna()
        means.append(float(values.mean()))
        sds.append(float(values.std(ddof=1)))
        cumulative = [float((values <= level).mean()) for level in (0, 1, 2)]
        thresholds.append([NORMAL.inv_cdf(p) for p in cumulative])

    missing_rate = float(items.isna().any(axis=1).mean())
    calibration = {
        "source": "NHANES 2017-2018 DPQ_J (public domain)",
        "n_rows": int(len(frame)),
        "n_complete": int(items.dropna().shape[0]),
        "items": ITEMS,
        "thresholds": thresholds,
        "item_means": means,
        "item_sds": sds,
        "any_missing_rate": missing_rate,
    }
    (HERE / "calibration.json").write_text(
        json.dumps(calibration, indent=2), encoding="utf-8"
    )
    pd.DataFrame(
        {
            "item": ITEMS,
            "mean": means,
            "sd": sds,
            "threshold_0": [t[0] for t in thresholds],
            "threshold_1": [t[1] for t in thresholds],
            "threshold_2": [t[2] for t in thresholds],
        }
    ).to_csv(HERE / "nhanes_summary.csv", index=False)
    print(json.dumps({k: calibration[k] for k in ("n_rows", "n_complete", "any_missing_rate")}, indent=2))
    print("wrote calibration.json and nhanes_summary.csv")


if __name__ == "__main__":
    main()
