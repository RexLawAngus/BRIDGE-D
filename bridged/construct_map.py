"""Data-driven item maps for co-administered instruments.

The map describes empirical response similarity. Its coordinates are not
named psychological axes and should not be interpreted as latent-trait truth.
"""

from __future__ import annotations

import inspect
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.linalg import orthogonal_procrustes
from scipy.spatial.distance import squareform
from sklearn.manifold import MDS
from sklearn.metrics import silhouette_score

from .figure_output import save_figure_pair
from .instrument import Instrument
from .map_analysis import summarize_instrument_footprints

__all__ = [
    "ConstructMapResult",
    "collect_item_values",
    "fit_construct_map",
    "spearman_associations",
    "write_construct_map",
]


@dataclass
class ConstructMapResult:
    """All reusable outputs from one empirical construct-map fit."""

    items: pd.DataFrame
    associations: pd.DataFrame
    distances: pd.DataFrame
    pairwise_n: pd.DataFrame
    coordinates: pd.DataFrame
    instrument_footprints: pd.DataFrame
    instrument_distances: pd.DataFrame
    linkage_matrix: np.ndarray
    coassignment: pd.DataFrame | None
    metrics: dict[str, Any]


def collect_item_values(
    instruments: Sequence[Instrument], data: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collect scored item responses and stable item metadata."""
    if not instruments:
        raise ValueError("construct map needs at least one instrument")
    instrument_ids = [instrument.id for instrument in instruments]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise ValueError("construct map instrument ids must be unique")

    series: dict[str, pd.Series] = {}
    metadata: list[dict[str, Any]] = []
    for instrument in instruments:
        values = instrument.item_values(data)
        for item in instrument.items:
            if item.kind == "column":
                continue
            key = f"{instrument.id}@{instrument.version}/{item.id}"
            series[key] = values[item.id]
            metadata.append(
                {
                    "item": key,
                    "instrument": instrument.id,
                    "instrument_version": instrument.version,
                    "item_id": item.id,
                    "construct": item.construct or "",
                    "rater": str(instrument.meta.get("rater", "")),
                    "recall": str(instrument.meta.get("recall", "")),
                }
            )
    if len(series) < 3:
        raise ValueError("construct map needs at least three item-based variables")
    return pd.DataFrame(series, index=data.index), pd.DataFrame(metadata)


def spearman_associations(
    item_values: pd.DataFrame, min_pairs: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairwise Spearman correlations and complete-pair counts."""
    if min_pairs < 3:
        raise ValueError("min_pairs must be at least 3")
    constant = [
        column
        for column in item_values.columns
        if item_values[column].dropna().nunique() < 2
    ]
    if constant:
        raise ValueError(f"items have fewer than two observed values: {constant}")

    valid = item_values.notna().astype(int)
    pairwise_n = valid.T @ valid
    associations = item_values.corr(method="spearman", min_periods=min_pairs)
    missing = np.argwhere(associations.isna().to_numpy())
    missing = [(i, j) for i, j in missing if i < j]
    if missing:
        pairs = [
            f"{associations.index[i]} vs {associations.columns[j]}"
            for i, j in missing[:5]
        ]
        suffix = " ..." if len(missing) > 5 else ""
        raise ValueError(
            "some item pairs lack enough usable observations: "
            + "; ".join(pairs)
            + suffix
        )
    # pandas 3 may expose DataFrame arrays as read-only.  Work on an explicit
    # copy because NumPy's fill_diagonal mutates its input in place.
    association_values = associations.to_numpy(copy=True)
    np.fill_diagonal(association_values, 1.0)
    associations = pd.DataFrame(
        association_values,
        index=associations.index,
        columns=associations.columns,
    )
    return associations, pairwise_n


def _correlation_distance(associations: pd.DataFrame) -> pd.DataFrame:
    distance = (1.0 - associations).clip(lower=0.0, upper=2.0)
    values = (distance.to_numpy() + distance.to_numpy().T) / 2.0
    np.fill_diagonal(values, 0.0)
    return pd.DataFrame(values, index=distance.index, columns=distance.columns)


def _fit_mds(distance: pd.DataFrame, seed: int) -> tuple[np.ndarray, float]:
    values = distance.to_numpy(copy=True)
    # Non-metric MDS treats zero off-diagonal dissimilarities as missing.
    zero = (values == 0.0) & ~np.eye(len(values), dtype=bool)
    values[zero] = np.finfo(float).eps
    mds_options: dict[str, Any] = {
        "n_components": 2,
        "random_state": seed,
        "n_init": 8,
        "max_iter": 500,
        "eps": 1e-6,
        "normalized_stress": "auto",
    }
    if "metric_mds" in inspect.signature(MDS).parameters:
        # scikit-learn 1.9 split the old ``metric`` option into the input
        # distance metric and a separate metric/non-metric MDS switch.
        mds_options.update(metric="precomputed", metric_mds=False, init="random")
    else:
        mds_options.update(metric=False, dissimilarity="precomputed")
    model = MDS(
        **mds_options,
    )
    coordinates = model.fit_transform(values)
    return coordinates, float(model.stress_)


def _orient_axes(coordinates: np.ndarray) -> np.ndarray:
    """Give otherwise arbitrary component signs a deterministic orientation."""
    oriented = coordinates.copy()
    for axis in range(oriented.shape[1]):
        pivot = int(np.argmax(np.abs(oriented[:, axis])))
        if oriented[pivot, axis] < 0:
            oriented[:, axis] *= -1
    return oriented


def _fit_pca(associations: pd.DataFrame) -> tuple[np.ndarray, dict[str, float | int]]:
    """Place items at their first two Spearman-correlation PCA loadings."""
    values = associations.to_numpy(copy=True)
    values = (values + values.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(values)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    nonnegative = np.clip(eigenvalues, 0.0, None)
    if len(nonnegative) < 2 or nonnegative[1] <= np.finfo(float).eps:
        raise ValueError("PCA calibration needs at least two positive eigenvalues")
    total = float(nonnegative.sum())
    coordinates = eigenvectors[:, :2] * np.sqrt(nonnegative[:2])
    coordinates = _orient_axes(coordinates)
    explained = nonnegative / total
    diagnostics: dict[str, float | int] = {
        "pc1_eigenvalue": float(eigenvalues[0]),
        "pc2_eigenvalue": float(eigenvalues[1]),
        "pc1_explained_variance": float(explained[0]),
        "pc2_explained_variance": float(explained[1]),
        "pc12_explained_variance": float(explained[:2].sum()),
        "negative_eigenvalues": int((eigenvalues < -1e-10).sum()),
        "minimum_eigenvalue": float(eigenvalues.min()),
    }
    return coordinates, diagnostics


def _fit_embedding(
    associations: pd.DataFrame,
    distance: pd.DataFrame,
    embedding: str,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    if embedding == "mds":
        coordinates, stress = _fit_mds(distance, seed)
        return coordinates, {"stress": stress}
    if embedding == "pca":
        coordinates, diagnostics = _fit_pca(associations)
        return coordinates, diagnostics
    raise ValueError("embedding must be 'mds' or 'pca'")


def _cluster(
    distance: pd.DataFrame, cluster_count: int | None = None
) -> tuple[np.ndarray, np.ndarray, int, float]:
    n_items = len(distance)
    distance_values = distance.to_numpy(copy=True)
    condensed = squareform(distance_values, checks=False)
    tree = linkage(condensed, method="average")
    if n_items < 3:
        labels = np.ones(n_items, dtype=int)
        return tree, labels, 1, float("nan")

    if cluster_count is None:
        candidates = range(2, min(6, n_items - 1) + 1)
        scored: list[tuple[float, int, np.ndarray]] = []
        for candidate in candidates:
            labels = fcluster(tree, t=candidate, criterion="maxclust")
            if len(set(labels)) < 2:
                continue
            # Silhouette can favor a partition that merely peels off one
            # unusual item. A singleton is useful as an outlier flag, but it
            # is not enough evidence for an empirical construct cluster.
            if pd.Series(labels).value_counts().min() < 2:
                continue
            score = float(
                silhouette_score(
                    distance_values.copy(), labels, metric="precomputed"
                )
            )
            scored.append((score, candidate, labels))
        if not scored:
            labels = np.ones(n_items, dtype=int)
            return tree, labels, 1, float("nan")
        silhouette, cluster_count, labels = max(scored, key=lambda row: row[0])
        return tree, labels, cluster_count, silhouette

    if not 2 <= cluster_count < n_items:
        raise ValueError(f"clusters must be between 2 and {n_items - 1}")
    labels = fcluster(tree, t=cluster_count, criterion="maxclust")
    silhouette = float(
        silhouette_score(distance_values.copy(), labels, metric="precomputed")
    )
    return tree, labels, cluster_count, silhouette


def _align_to_reference(points: np.ndarray, reference: np.ndarray) -> np.ndarray:
    points_centered = points - points.mean(axis=0)
    reference_centered = reference - reference.mean(axis=0)
    points_norm = np.linalg.norm(points_centered)
    reference_norm = np.linalg.norm(reference_centered)
    if points_norm == 0 or reference_norm == 0:
        raise ValueError("cannot align a construct map with no coordinate spread")
    scaled = points_centered * (reference_norm / points_norm)
    rotation, _ = orthogonal_procrustes(scaled, reference_centered)
    return scaled @ rotation + reference.mean(axis=0)


def fit_construct_map(
    instruments: Sequence[Instrument],
    data: pd.DataFrame,
    *,
    min_pairs: int = 10,
    clusters: int | None = None,
    bootstrap: int = 0,
    seed: int = 0,
    embedding: str = "mds",
) -> ConstructMapResult:
    """Fit an empirical item map from co-administered ordinal responses."""
    if bootstrap < 0:
        raise ValueError("bootstrap must be non-negative")
    item_values, items = collect_item_values(instruments, data)
    associations, pairwise_n = spearman_associations(item_values, min_pairs)
    distances = _correlation_distance(associations)
    reference, embedding_metrics = _fit_embedding(
        associations, distances, embedding, seed
    )
    tree, labels, cluster_count, silhouette = _cluster(distances, clusters)

    coordinates = items.copy()
    coordinates["dimension_1"] = reference[:, 0]
    coordinates["dimension_2"] = reference[:, 1]
    coordinates["cluster"] = labels
    coordinates["dimension_1_sd"] = np.nan
    coordinates["dimension_2_sd"] = np.nan
    coordinates["cluster_stability"] = np.nan

    coassignment: pd.DataFrame | None = None
    valid_bootstrap = 0
    if bootstrap:
        rng = np.random.default_rng(seed)
        aligned_maps: list[np.ndarray] = []
        coassign_sum = np.zeros((len(items), len(items)), dtype=float)
        for replication in range(bootstrap):
            row_index = rng.integers(0, len(item_values), len(item_values))
            sample = item_values.iloc[row_index].reset_index(drop=True)
            try:
                sample_assoc, _ = spearman_associations(sample, min_pairs)
                sample_dist = _correlation_distance(sample_assoc)
                sample_map, _ = _fit_embedding(
                    sample_assoc,
                    sample_dist,
                    embedding,
                    seed + replication + 1,
                )
                aligned = _align_to_reference(sample_map, reference)
                if cluster_count == 1:
                    sample_labels = np.ones(len(items), dtype=int)
                else:
                    _, sample_labels, _, _ = _cluster(sample_dist, cluster_count)
            except (ValueError, FloatingPointError):
                continue
            aligned_maps.append(aligned)
            coassign_sum += sample_labels[:, None] == sample_labels[None, :]
            valid_bootstrap += 1

        if valid_bootstrap:
            stacked = np.stack(aligned_maps)
            ddof = 1 if valid_bootstrap > 1 else 0
            coordinates["dimension_1_sd"] = stacked[:, :, 0].std(axis=0, ddof=ddof)
            coordinates["dimension_2_sd"] = stacked[:, :, 1].std(axis=0, ddof=ddof)
            coassign_values = coassign_sum / valid_bootstrap
            coassignment = pd.DataFrame(
                coassign_values, index=associations.index, columns=associations.columns
            )
            stability = []
            for index, label in enumerate(labels):
                peers = np.flatnonzero(labels == label)
                peers = peers[peers != index]
                stability.append(
                    float(coassign_values[index, peers].mean()) if len(peers) else 1.0
                )
            coordinates["cluster_stability"] = stability

    embedding_label = {
        "mds": "nonmetric MDS",
        "pca": "PCA item loadings",
    }.get(embedding, embedding)
    metrics = {
        "method": f"spearman + {embedding_label} + average-linkage clustering",
        "embedding": embedding,
        "n_subjects": int(len(data)),
        "n_items": int(len(items)),
        "min_pairs": int(min_pairs),
        "clusters": int(cluster_count),
        "smallest_cluster": int(pd.Series(labels).value_counts().min()),
        "silhouette": silhouette if np.isfinite(silhouette) else None,
        "bootstrap_requested": int(bootstrap),
        "bootstrap_valid": int(valid_bootstrap),
        "seed": int(seed),
        **embedding_metrics,
    }
    footprints, instrument_distances = summarize_instrument_footprints(coordinates)
    return ConstructMapResult(
        items=items,
        associations=associations,
        distances=distances,
        pairwise_n=pairwise_n,
        coordinates=coordinates,
        instrument_footprints=footprints,
        instrument_distances=instrument_distances,
        linkage_matrix=tree,
        coassignment=coassignment,
        metrics=metrics,
    )


def _write_plot(result: ConstructMapResult, path: Path) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm

    frame = result.coordinates
    figure, axis = plt.subplots(figsize=(9, 7))
    instruments = list(dict.fromkeys(frame["instrument"]))
    markers = ["o", "s", "^", "D", "P", "X"]
    cluster_max = int(frame["cluster"].max())
    color_norm = BoundaryNorm(
        np.arange(0.5, cluster_max + 1.5), ncolors=plt.get_cmap("tab10").N
    )
    for index, instrument in enumerate(instruments):
        subset = frame[frame["instrument"] == instrument]
        axis.scatter(
            subset["dimension_1"],
            subset["dimension_2"],
            c=subset["cluster"],
            cmap="tab10",
            norm=color_norm,
            marker=markers[index % len(markers)],
            s=70,
            edgecolor="black",
            linewidth=0.5,
            label=instrument,
        )
        if subset["dimension_1_sd"].notna().all():
            axis.errorbar(
                subset["dimension_1"],
                subset["dimension_2"],
                xerr=subset["dimension_1_sd"],
                yerr=subset["dimension_2_sd"],
                fmt="none",
                ecolor="0.65",
                elinewidth=0.7,
                alpha=0.6,
                zorder=0,
            )
    for row in frame.itertuples():
        axis.annotate(
            row.item_id,
            (row.dimension_1, row.dimension_2),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    if result.metrics.get("embedding") == "pca":
        pc1 = 100 * float(result.metrics["pc1_explained_variance"])
        pc2 = 100 * float(result.metrics["pc2_explained_variance"])
        axis.set_xlabel(f"PC1 item loading ({pc1:.1f}% variance)")
        axis.set_ylabel(f"PC2 item loading ({pc2:.1f}% variance)")
    else:
        axis.set_xlabel("Empirical dimension 1")
        axis.set_ylabel("Empirical dimension 2")
    axis.set_title("BRIDGE-D empirical item map")
    axis.legend(title="Instrument")
    axis.text(
        0.01,
        0.01,
        "Coordinates reflect response similarity; axes have no assigned construct labels.",
        transform=axis.transAxes,
        fontsize=8,
        color="0.35",
    )
    figure.tight_layout()
    written = save_figure_pair(figure, path)
    plt.close(figure)
    return written


def _write_instrument_footprints(
    result: ConstructMapResult, path: Path
) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    frame = result.coordinates
    figure, axis = plt.subplots(figsize=(9, 7))
    colors = plt.get_cmap("tab10")
    for index, (instrument, subset) in enumerate(
        frame.groupby("instrument", sort=False)
    ):
        color = colors(index % 10)
        points = subset[["dimension_1", "dimension_2"]].to_numpy()
        axis.scatter(
            points[:, 0], points[:, 1], color=color, s=55, alpha=0.82,
            edgecolor="black", linewidth=0.4, label=instrument,
        )
        centroid = points.mean(axis=0)
        axis.scatter(
            *centroid, marker="X", color=color, s=160,
            edgecolor="white", linewidth=0.9, zorder=4,
        )
        axis.annotate(
            instrument, centroid, xytext=(6, 6), textcoords="offset points",
            fontsize=9, weight="bold",
        )
        if len(points) >= 3 and np.linalg.matrix_rank(points - centroid) >= 2:
            from scipy.spatial import ConvexHull

            hull = ConvexHull(points)
            polygon = points[hull.vertices]
            axis.fill(
                polygon[:, 0], polygon[:, 1], color=color, alpha=0.12,
                linewidth=0,
            )
            axis.plot(
                np.r_[polygon[:, 0], polygon[0, 0]],
                np.r_[polygon[:, 1], polygon[0, 1]],
                color=color, linewidth=1.0, alpha=0.65,
            )
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    axis.set_xlabel("Empirical dimension 1")
    axis.set_ylabel("Empirical dimension 2")
    axis.set_title("Projected instrument footprints")
    axis.legend(title="Instrument")
    axis.text(
        0.01, 0.01,
        "Hulls, centroids, and distances are descriptive in this fitted 2D projection.",
        transform=axis.transAxes, fontsize=8, color="0.35",
    )
    figure.tight_layout()
    written = save_figure_pair(figure, path)
    plt.close(figure)
    return written


def _write_tree(result: ConstructMapResult, path: Path) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 6))
    dendrogram(
        result.linkage_matrix,
        labels=result.coordinates["item"].tolist(),
        leaf_rotation=90,
        leaf_font_size=7,
        ax=axis,
    )
    axis.set_ylabel("Response-pattern distance")
    axis.set_title("Average-linkage item hierarchy")
    figure.tight_layout()
    written = save_figure_pair(figure, path)
    plt.close(figure)
    return written


def write_construct_map(result: ConstructMapResult, out_dir: str | Path) -> list[Path]:
    """Write reusable tables, figures, configuration, and a short report."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    tables = {
        "item_associations.csv": result.associations,
        "item_distances.csv": result.distances,
        "pairwise_n.csv": result.pairwise_n,
    }
    for name, frame in tables.items():
        path = out / name
        frame.rename_axis("item").to_csv(path)
        written.append(path)

    coordinate_path = out / "item_coordinates.csv"
    result.coordinates.to_csv(coordinate_path, index=False)
    written.append(coordinate_path)
    footprint_path = out / "instrument_footprints.csv"
    result.instrument_footprints.to_csv(footprint_path, index=False)
    written.append(footprint_path)
    distance_path = out / "instrument_distances.csv"
    result.instrument_distances.to_csv(distance_path, index=False)
    written.append(distance_path)
    if result.coassignment is not None:
        path = out / "bootstrap_coassignment.csv"
        result.coassignment.rename_axis("item").to_csv(path)
        written.append(path)

    config_path = out / "analysis_config.json"
    config_path.write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    written.append(config_path)

    map_path = out / "item_map.png"
    legacy_map_path = out / "construct_map.png"
    footprint_figure_path = out / "instrument_footprints.png"
    tree_path = out / "cluster_tree.png"
    map_paths = _write_plot(result, map_path)
    legacy_map_paths = (
        legacy_map_path,
        legacy_map_path.with_suffix(".svg"),
    )
    for source, destination in zip(map_paths, legacy_map_paths):
        shutil.copyfile(source, destination)
    footprint_figure_paths = _write_instrument_footprints(
        result, footprint_figure_path
    )
    tree_paths = _write_tree(result, tree_path)
    written.extend(
        [*map_paths, *legacy_map_paths, *footprint_figure_paths, *tree_paths]
    )

    metrics = result.metrics
    fit_lines = []
    if metrics.get("embedding") == "pca":
        fit_lines.extend(
            [
                f"- PC1 explained variance: {metrics['pc1_explained_variance']:.4f}",
                f"- PC2 explained variance: {metrics['pc2_explained_variance']:.4f}",
                f"- PC1 + PC2 explained variance: {metrics['pc12_explained_variance']:.4f}",
            ]
        )
    else:
        fit_lines.append(f"- Non-metric MDS stress: {metrics['stress']:.4f}")
    report = "\n".join(
        [
            "# BRIDGE-D empirical item map",
            "",
            f"- Subjects: {metrics['n_subjects']}",
            f"- Items: {metrics['n_items']}",
            f"- Method: {metrics['method']}",
            *fit_lines,
            f"- Clusters: {metrics['clusters']}",
            (
                f"- Silhouette: {metrics['silhouette']:.4f}"
                if metrics["silhouette"] is not None
                else "- Silhouette: not available (no non-singleton multi-cluster solution)"
            ),
            f"- Valid bootstrap fits: {metrics['bootstrap_valid']} / "
            f"{metrics['bootstrap_requested']}",
            f"- Instruments summarized: {len(result.instrument_footprints)}",
            "",
            "The coordinates describe item-response similarity in this sample. "
            "Dimension 1 and Dimension 2 do not have assigned psychological meanings.",
            "Instrument footprints are descriptive summaries of the fitted "
            "two-dimensional projection, not universal scale boundaries.",
            "",
        ]
    )
    report_path = out / "item_map_report.md"
    report_path.write_text(report, encoding="utf-8")
    written.append(report_path)
    legacy_report_path = out / "construct_map_report.md"
    shutil.copyfile(report_path, legacy_report_path)
    written.append(legacy_report_path)
    return written
