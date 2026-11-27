"""Prepare the public NHANES 2017-2018 PHQ-9 file for BRIDGE-D.

Reads DPQ_J.XPT, cleans the nine items, and writes a CSV whose columns match
instruments/phq9.toml. The raw XPT stays in the public dataset folder.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_XPT = Path("DPQ_J.XPT")
ITEMS = [f"DPQ{i:02d}0" for i in range(1, 10)]


def clean(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    # SAS zero arrives as 5.4e-79; keep true NaN as missing.
    values = values.mask(values < 0.5, 0.0)
    return values.where(values.isin([0.0, 1.0, 2.0, 3.0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xpt", default=str(DEFAULT_XPT))
    parser.add_argument("--out", default=str(HERE / "data" / "nhanes_phq9.csv"))
    args = parser.parse_args()

    frame = pd.read_sas(args.xpt, format="xport")
    output = pd.DataFrame(
        {f"phq{i}": clean(frame[column]) for i, column in enumerate(ITEMS, start=1)}
    )
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False)

    print(f"wrote {destination}")
    print(f"rows: {len(output)}")
    print(f"any missing: {output.isna().any(axis=1).mean():.4f}")
    print(output.describe().round(2).to_string())


if __name__ == "__main__":
    main()
