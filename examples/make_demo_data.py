"""Generate a synthetic co-administered cohort for demos and tests.

The numbers are made up. They exist so the tool can be exercised without
touching any real participant data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

N = 160
SEED = 2026


def main() -> None:
    rng = np.random.default_rng(SEED)
    theta = rng.normal(0.0, 1.0, N)

    def likert(base: float, loading: float, noise: float, lo: int, hi: int) -> np.ndarray:
        raw = base + loading * theta + rng.normal(0.0, noise, N)
        return np.clip(np.rint(raw), lo, hi).astype(int)

    data: dict[str, np.ndarray] = {}
    for i in range(1, 10):
        data[f"phq{i}"] = likert(1.1, 0.65, 0.9, 0, 3)
    for i in range(1, 13):
        data[f"ex{i}"] = likert(1.9, 0.85, 1.0, 0, 4)

    # Raw responses of reverse-keyed items run opposite to the trait.
    for item in ("ex5", "ex9"):
        data[item] = 4 - data[item]

    frame = pd.DataFrame(data)
    out = Path(__file__).with_name("demo_cohort.csv")
    frame.to_csv(out, index=False)
    print(f"wrote {out} ({len(frame)} rows, {frame.shape[1]} columns)")


if __name__ == "__main__":
    main()
