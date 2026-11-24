"""Post-fit summaries, label checks, and cross-sample item-map comparisons.

All functions in this module operate on coordinates that have already been
estimated. Content labels are never used to fit or rotate an item map.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.linalg import orthogonal_procrustes
from scipy.spatial import ConvexHull
from scipy.spatial.distance import cdist, pdist

from .figure_output import save_figure_pair

COORDINATE_COLUMNS = ["dimension_1", "dimension_2"]


@dataclass
class GroupValidationResult:
    """Post-fit comparison of pre-specified item groups."""

    labeled_coordinates: pd.DataFrame
    group_summary: pd.DataFrame
    pairwise_tests: pd.DataFrame
    metrics: dict[str, Any]


@dataclass
class MapComparisonResult:
    """Procrustes-aligned comparison of two maps with common item IDs."""

    aligned_coordinates: pd.DataFrame
    metrics: dict[str, Any]


def _require_coordinates(frame: pd.DataFrame) -> None:
    missing = [column for column in ["item", *COORDINATE_COLUMNS] if column not in frame]
    if missing:
        raise ValueError(f"coordinate table is missing columns: {missing}")
    if frame["item"].duplicated().any():
        duplicates = frame.loc[frame["item"].duplicated(), "item"].tolist()
        raise ValueError(f"coordinate table has duplicate item identifiers: {duplicates}")
    if not np.isfinite(frame[COORDINATE_COLUMNS].to_numpy(dtype=float)).all():
        raise ValueError("coordinates must be finite")


def summarize_instrument_footprints(
    coordinates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Describe each instrument's projected coverage and between-scale distance."""
    _require_coordinates(coordinates)
    if "instrument" not in coordinates:
        raise ValueError("coordinate table needs an 'instrument' column")

    summaries: list[dict[str, Any]] = []
    point_sets: dict[str, np.ndarray] = {}
    for instrument, subset in coordinates.groupby("instrument", sort=False):
        points = subset[COORDINATE_COLUMNS].to_numpy(dtype=float)
        point_sets[str(instrument)] = points
        centroid = points.mean(axis=0)
        radii = np.linalg.norm(points - centroid, axis=1)
        hull_area: float | None = None
        if len(points) >= 3 and np.linalg.matrix_rank(points - centroid) >= 2:
            hull_area = float(ConvexHull(points).volume)
        summaries.append(
            {
                "instrument": str(instrument),
                "n_items": int(len(points)),
                "centroid_dimension_1": float(centroid[0]),
                "centroid_dimension_2": float(centroid[1]),
                "mean_radius": float(radii.mean()),
                "rms_radius": float(np.sqrt(np.mean(radii**2))),
                "max_radius": float(radii.max()),
                "convex_hull_area": hull_area,
            }
        )

    distances: list[dict[str, Any]] = []
    for first, second in itertools.combinations(point_sets, 2):
        a = point_sets[first]
        b = point_sets[second]
        pairwise = cdist(a, b)
        distances.append(
            {
                "instrument_a": first,
                "instrument_b": second,
                "centroid_distance": float(
                    np.linalg.norm(a.mean(axis=0) - b.mean(axis=0))
                ),
                "mean_cross_item_distance": float(pairwise.mean()),
                "minimum_cross_item_distance": float(pairwise.min()),
                "symmetric_nearest_neighbor_distance": float(
                    (pairwise.min(axis=1).mean() + pairwise.min(axis=0).mean()) / 2
                ),
            }
        )
    distance_columns = [
        "instrument_a",
        "instrument_b",
        "centroid_distance",
        "mean_cross_item_distance",
        "minimum_cross_item_distance",
        "symmetric_nearest_neighbor_distance",
    ]
    return pd.DataFrame(summaries), pd.DataFrame(distances, columns=distance_columns)


def merge_group_labels(
    coordinates: pd.DataFrame, groups: pd.DataFrame
) -> pd.DataFrame:
    """Join a post-fit group table by stable item ID or instrument/item_id."""
    _require_coordinates(coordinates)
    if "group" not in groups:
        raise ValueError("group table needs a 'group' column")
    if "item" in groups:
        keys = ["item"]
    elif {"instrument", "item_id"}.issubset(groups.columns):
        keys = ["instrument", "item_id"]
    else:
        raise ValueError(
            "group table needs either 'item', or both 'instrument' and 'item_id'"
        )
    selected = groups[[*keys, "group"]].dropna(subset=["group"]).copy()
    selected["group"] = selected["group"].astype(str)
    if selected.duplicated(keys).any():
        raise ValueError("group table contains duplicate item labels")
    merged = coordinates.merge(selected, on=keys, how="inner", validate="one_to_one")
    if len(merged) < 4:
        raise ValueError("group validation needs at least four labeled items")
    counts = merged["group"].value_counts()
    if len(counts) < 2 or counts.min() < 2:
        raise ValueError("group validation needs at least two groups with two items each")
    return merged


def _eta_squared(points: np.ndarray, labels: np.ndarray) -> float:
    grand = points.mean(axis=0)
    total = float(np.sum((points - grand) ** 2))
    if total <= np.finfo(float).eps:
        raise ValueError("group validation needs coordinate spread")
    between = 0.0
    for label in np.unique(labels):
        subset = points[labels == label]
        between += len(subset) * float(np.sum((subset.mean(axis=0) - grand) ** 2))
    return between / total


def _pairwise_permutation(
    points: np.ndarray,
    first_size: int,
    observed: float,
    *,
    permutations: int,
    seed: int,
    exact_limit: int,
) -> tuple[float, str, int]:
    total_partitions = math.comb(len(points), first_size)
    tolerance = 1e-12

    def statistic(mask: np.ndarray) -> float:
        return float(np.linalg.norm(points[mask].mean(axis=0) - points[~mask].mean(axis=0)))

    if total_partitions <= exact_limit:
        exceed = 0
        for indices in itertools.combinations(range(len(points)), first_size):
            mask = np.zeros(len(points), dtype=bool)
            mask[list(indices)] = True
            exceed += statistic(mask) >= observed - tolerance
        return exceed / total_partitions, "exact", total_partitions

    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(permutations):
        mask = np.zeros(len(points), dtype=bool)
        mask[rng.choice(len(points), size=first_size, replace=False)] = True
        exceed += statistic(mask) >= observed - tolerance
    return (exceed + 1) / (permutations + 1), "monte_carlo", permutations


def validate_map_groups(
    coordinates: pd.DataFrame,
    groups: pd.DataFrame,
    *,
    permutations: int = 9999,
    seed: int = 0,
    exact_limit: int = 100_000,
) -> GroupValidationResult:
    """Test whether pre-specified content groups separate on a fitted map."""
    if permutations < 1:
        raise ValueError("permutations must be positive")
    labeled = merge_group_labels(coordinates, groups)
    points = labeled[COORDINATE_COLUMNS].to_numpy(dtype=float)
    labels = labeled["group"].to_numpy()
    observed_eta = _eta_squared(points, labels)
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(permutations):
        exceed += _eta_squared(points, rng.permutation(labels)) >= observed_eta - 1e-12
    global_p = (exceed + 1) / (permutations + 1)

    summaries: list[dict[str, Any]] = []
    for label, subset in labeled.groupby("group", sort=False):
        group_points = subset[COORDINATE_COLUMNS].to_numpy(dtype=float)
        centroid = group_points.mean(axis=0)
        radii = np.linalg.norm(group_points - centroid, axis=1)
        summaries.append(
            {
                "group": str(label),
                "n_items": int(len(group_points)),
                "centroid_dimension_1": float(centroid[0]),
                "centroid_dimension_2": float(centroid[1]),
                "rms_radius": float(np.sqrt(np.mean(radii**2))),
            }
        )
    summary = pd.DataFrame(summaries)

    pairwise_rows: list[dict[str, Any]] = []
    group_order = summary["group"].tolist()
    for pair_index, (first, second) in enumerate(itertools.combinations(group_order, 2)):
        subset = labeled[labeled["group"].isin([first, second])]
        pair_points = subset[COORDINATE_COLUMNS].to_numpy(dtype=float)
        pair_labels = subset["group"].to_numpy()
        first_mask = pair_labels == first
        vector = pair_points[first_mask].mean(axis=0) - pair_points[~first_mask].mean(axis=0)
        observed = float(np.linalg.norm(vector))
        p_value, method, evaluated = _pairwise_permutation(
            pair_points,
            int(first_mask.sum()),
            observed,
            permutations=permutations,
            seed=seed + pair_index + 1,
            exact_limit=exact_limit,
        )
        pairwise_rows.append(
            {
                "group_a": first,
                "group_b": second,
                "n_a": int(first_mask.sum()),
                "n_b": int((~first_mask).sum()),
                "centroid_difference_dimension_1": float(vector[0]),
                "centroid_difference_dimension_2": float(vector[1]),
                "centroid_distance": observed,
                "permutation_p": float(p_value),
                "permutation_method": method,
                "partitions_or_draws": int(evaluated),
            }
        )

    metrics = {
        "purpose": "post-fit validation against pre-specified item groups",
        "labels_used_to_fit_map": False,
        "n_labeled_items": int(len(labeled)),
        "n_groups": int(len(summary)),
        "global_eta_squared": float(observed_eta),
        "global_permutation_p": float(global_p),
        "global_permutation_draws": int(permutations),
        "seed": int(seed),
    }
    return GroupValidationResult(labeled, summary, pd.DataFrame(pairwise_rows), metrics)


def _align_points(points: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, float]:
    points_centered = points - points.mean(axis=0)
    reference_centered = reference - reference.mean(axis=0)
    points_norm = float(np.linalg.norm(points_centered))
    reference_norm = float(np.linalg.norm(reference_centered))
    if points_norm == 0 or reference_norm == 0:
        raise ValueError("cannot align an item map with no coordinate spread")
    scale_factor = reference_norm / points_norm
    scaled = points_centered * scale_factor
    rotation, _ = orthogonal_procrustes(scaled, reference_centered)
    return scaled @ rotation + reference.mean(axis=0), scale_factor


def compare_item_maps(
    reference: pd.DataFrame, candidate: pd.DataFrame
) -> MapComparisonResult:
    """Align and compare common items from two independently fitted maps."""
    _require_coordinates(reference)
    _require_coordinates(candidate)
    ref = reference[["item", *COORDINATE_COLUMNS]].rename(
        columns={column: f"reference_{column}" for column in COORDINATE_COLUMNS}
    )
    cand = candidate[["item", *COORDINATE_COLUMNS]].rename(
        columns={column: f"candidate_{column}" for column in COORDINATE_COLUMNS}
    )
    merged = ref.merge(cand, on="item", how="inner", validate="one_to_one")
    if len(merged) < 3:
        raise ValueError("map comparison needs at least three common items")
    reference_points = merged[[f"reference_{column}" for column in COORDINATE_COLUMNS]].to_numpy()
    candidate_points = merged[[f"candidate_{column}" for column in COORDINATE_COLUMNS]].to_numpy()
    aligned, scale_factor = _align_points(candidate_points, reference_points)
    merged["aligned_dimension_1"] = aligned[:, 0]
    merged["aligned_dimension_2"] = aligned[:, 1]
    residuals = aligned - reference_points
    reference_centered = reference_points - reference_points.mean(axis=0)
    def correlation(first: np.ndarray, second: np.ndarray) -> float | None:
        if np.std(first) <= np.finfo(float).eps or np.std(second) <= np.finfo(float).eps:
            return None
        return float(np.corrcoef(first, second)[0, 1])

    metrics = {
        "method": "translation, isotropic scaling, and orthogonal Procrustes rotation/reflection",
        "n_common_items": int(len(merged)),
        "n_reference_items": int(len(reference)),
        "n_candidate_items": int(len(candidate)),
        "candidate_scale_factor": float(scale_factor),
        "aligned_dimension_1_correlation": correlation(
            reference_points[:, 0], aligned[:, 0]
        ),
        "aligned_dimension_2_correlation": correlation(
            reference_points[:, 1], aligned[:, 1]
        ),
        "coordinate_rmse": float(np.sqrt(np.mean(residuals**2))),
        "normalized_procrustes_residual": float(
            np.sum(residuals**2) / np.sum(reference_centered**2)
        ),
        "pairwise_distance_correlation": correlation(
            pdist(reference_points), pdist(candidate_points)
        ),
    }
    return MapComparisonResult(merged, metrics)


def _plot_group_validation(
    result: GroupValidationResult, path: Path
) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9, 7))
    for label, subset in result.labeled_coordinates.groupby("group", sort=False):
        axis.scatter(
            subset["dimension_1"], subset["dimension_2"], s=70, label=label,
            edgecolor="black", linewidth=0.5,
        )
        centroid = subset[COORDINATE_COLUMNS].mean().to_numpy()
        axis.scatter(*centroid, marker="X", s=150, edgecolor="white", linewidth=0.8)
    for row in result.labeled_coordinates.itertuples():
        label = getattr(row, "item_id", row.item)
        axis.annotate(label, (row.dimension_1, row.dimension_2), xytext=(4, 4),
                      textcoords="offset points", fontsize=8)
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    axis.set_xlabel("Empirical dimension 1")
    axis.set_ylabel("Empirical dimension 2")
    axis.set_title("Post-fit item-group validation")
    axis.legend(title="Pre-specified group")
    axis.text(0.01, 0.01, "Group labels were not used to fit the coordinates.",
              transform=axis.transAxes, fontsize=8, color="0.35")
    figure.tight_layout()
    written = save_figure_pair(figure, path)
    plt.close(figure)
    return written


def write_group_validation(
    result: GroupValidationResult, out_dir: str | Path
) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = [
        out / "labeled_item_coordinates.csv",
        out / "group_summary.csv",
        out / "group_pairwise_tests.csv",
        out / "map_validation.json",
    ]
    result.labeled_coordinates.to_csv(paths[0], index=False)
    result.group_summary.to_csv(paths[1], index=False)
    result.pairwise_tests.to_csv(paths[2], index=False)
    paths[3].write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    paths.extend(_plot_group_validation(result, out / "map_validation.png"))
    return paths


def _plot_map_comparison(
    result: MapComparisonResult, path: Path
) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    frame = result.aligned_coordinates
    figure, axis = plt.subplots(figsize=(9, 7))
    axis.scatter(frame["reference_dimension_1"], frame["reference_dimension_2"],
                 label="reference", s=70)
    axis.scatter(frame["aligned_dimension_1"], frame["aligned_dimension_2"],
                 label="aligned candidate", s=55, marker="x")
    for row in frame.itertuples():
        axis.plot([row.reference_dimension_1, row.aligned_dimension_1],
                  [row.reference_dimension_2, row.aligned_dimension_2],
                  color="0.7", linewidth=0.8)
        axis.annotate(row.item.split("/")[-1],
                      (row.reference_dimension_1, row.reference_dimension_2),
                      xytext=(4, 4), textcoords="offset points", fontsize=8)
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    axis.set_xlabel("Reference dimension 1")
    axis.set_ylabel("Reference dimension 2")
    axis.set_title("Cross-sample item-map comparison")
    axis.legend()
    figure.tight_layout()
    written = save_figure_pair(figure, path)
    plt.close(figure)
    return written


def write_map_comparison(
    result: MapComparisonResult, out_dir: str | Path
) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = [
        out / "aligned_item_coordinates.csv",
        out / "map_comparison.json",
    ]
    result.aligned_coordinates.to_csv(paths[0], index=False)
    paths[1].write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    paths.extend(_plot_map_comparison(result, out / "map_comparison.png"))
    return paths
