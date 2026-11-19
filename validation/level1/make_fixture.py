"""Create the fixed dataset used by the Level 1 R comparison.

Deterministic, no missing values, no personal data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).with_name("fixture.csv")
N = 120


def likert(values: np.ndarray, lo: int, hi: int) -> np.ndarray:
    return np.clip(np.rint(values), lo, hi).astype(int)


def main() -> None:
    rng = np.random.default_rng(20261119)
    theta = rng.normal(size=N)

    data: dict[str, np.ndarray] = {}
    for i in range(1, 10):
        data[f"phq{i}"] = likert(
            1.2 + 0.70 * theta + rng.normal(0, 0.8, N), 0, 3
        )
    for i in range(1, 13):
        data[f"ex{i}"] = likert(
            2.0 + 0.85 * theta + rng.normal(0, 0.9, N), 0, 4
        )
    for item in ("ex5", "ex9"):
        data[item] = 4 - data[item]

    frame = pd.DataFrame(data)
    frame.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(frame)} rows)")


if __name__ == "__main__":
    main()
