"""Run the PCA construct-map prototype on the Granwald public dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.construct_map import fit_construct_map, write_construct_map  # noqa: E402
from bridged.instrument import Instrument  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = (
    ROOT.parents[1]
    / "公开数据集"
    / "granwald_2025_PHQ9_CESD_SDS"
    / "extracted_data_networkPriors.csv"
)
OUTPUT = HERE / "output_pca"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    return parser.parse_args(argv)


def prepare_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    rename = {
        **{f"PHQ_{i}": f"phq{i}" for i in range(1, 10)},
        **{f"CESD_{i}": f"cesd{i}" for i in range(1, 21)},
        **{f"SDS_{i}": f"sds{i}" for i in range(1, 21)},
    }
    data = data.rename(columns=rename)
    data["sample"] = np.where(data["subjID"] < 2000, "sample_1", "sample_2")
    return data.loc[data["AC_fails"] <= 2].reset_index(drop=True)


def upper_triangle(frame: pd.DataFrame) -> np.ndarray:
    index = np.triu_indices(len(frame), k=1)
    return frame.to_numpy()[index]


def fit_one(
    label: str,
    data: pd.DataFrame,
    instruments: list[Instrument],
    bootstrap: int,
    output: Path,
):
    result = fit_construct_map(
        instruments,
        data,
        embedding="pca",
        bootstrap=bootstrap,
        seed=20261120,
    )
    write_construct_map(result, output / label)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_path = args.data.resolve()
    output = args.out.resolve()
    if not data_path.exists():
        raise FileNotFoundError(
            f"Granwald data not found: {data_path}. Pass --data PATH."
        )
    instruments = [
        Instrument.load(ROOT / "instruments" / "phq9.toml"),
        Instrument.load(HERE / "instruments" / "cesd20.toml"),
        Instrument.load(HERE / "instruments" / "sds20.toml"),
    ]
    data = prepare_data(data_path)
    sample_1 = data[data["sample"] == "sample_1"].reset_index(drop=True)
    sample_2 = data[data["sample"] == "sample_2"].reset_index(drop=True)

    full = fit_one("full", data, instruments, bootstrap=100, output=output)
    first = fit_one("sample_1", sample_1, instruments, bootstrap=50, output=output)
    second = fit_one("sample_2", sample_2, instruments, bootstrap=50, output=output)

    association_reproducibility = float(
        np.corrcoef(
            upper_triangle(first.associations),
            upper_triangle(second.associations),
        )[0, 1]
    )
    distance_reproducibility = float(
        np.corrcoef(
            upper_triangle(first.distances),
            upper_triangle(second.distances),
        )[0, 1]
    )
    pc1_reproducibility = abs(
        float(
            np.corrcoef(
                first.coordinates["dimension_1"], second.coordinates["dimension_1"]
            )[0, 1]
        )
    )
    pc2_reproducibility = abs(
        float(
            np.corrcoef(
                first.coordinates["dimension_2"], second.coordinates["dimension_2"]
            )[0, 1]
        )
    )
    if first.metrics["clusters"] > 1 and second.metrics["clusters"] > 1:
        cluster_reproducibility = float(
            adjusted_rand_score(
                first.coordinates["cluster"], second.coordinates["cluster"]
            )
        )
        cluster_note = "calculated from two non-singleton cluster solutions"
    else:
        cluster_reproducibility = None
        cluster_note = (
            "not calculated because automatic clustering found no "
            "non-singleton multi-cluster solution"
        )

    coordinate_comparison = full.coordinates[
        ["item", "instrument", "item_id", "dimension_1", "dimension_2", "cluster"]
    ].rename(
        columns={
            "dimension_1": "full_pc1",
            "dimension_2": "full_pc2",
            "cluster": "full_cluster",
        }
    )
    for label, result in [("sample1", first), ("sample2", second)]:
        subset = result.coordinates[
            ["item", "dimension_1", "dimension_2", "cluster"]
        ].copy()
        # Component signs are arbitrary. Align each split-sample axis to the
        # full-sample axis before writing the comparison table.
        for axis in ["dimension_1", "dimension_2"]:
            reference = full.coordinates[axis].to_numpy()
            candidate = subset[axis].to_numpy()
            if np.corrcoef(reference, candidate)[0, 1] < 0:
                subset[axis] *= -1
        subset = subset.rename(
            columns={
                "dimension_1": f"{label}_pc1",
                "dimension_2": f"{label}_pc2",
                "cluster": f"{label}_cluster",
            }
        )
        coordinate_comparison = coordinate_comparison.merge(subset, on="item")
    output.mkdir(parents=True, exist_ok=True)
    coordinate_comparison.to_csv(
        output / "split_coordinate_comparison.csv", index=False
    )

    source_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    summary = {
        "source": str(data_path),
        "source_sha256": source_hash,
        "exclusion": "AC_fails > 2",
        "n_full": len(data),
        "n_sample_1": len(sample_1),
        "n_sample_2": len(sample_2),
        "full_metrics": full.metrics,
        "sample_1_metrics": first.metrics,
        "sample_2_metrics": second.metrics,
        "split_association_matrix_correlation": association_reproducibility,
        "split_distance_matrix_correlation": distance_reproducibility,
        "split_pc1_loading_abs_correlation": pc1_reproducibility,
        "split_pc2_loading_abs_correlation": pc2_reproducibility,
        "split_cluster_adjusted_rand": cluster_reproducibility,
        "split_cluster_note": cluster_note,
    }
    (output / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
