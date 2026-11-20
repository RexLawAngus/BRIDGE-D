"""Explore content structure after removing general and wording components."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.construct_map import (  # noqa: E402
    _align_to_reference,
    _orient_axes,
    collect_item_values,
    spearman_associations,
)
from bridged.instrument import Instrument  # noqa: E402
from validation.construct_map_granwald.run_pca import (  # noqa: E402
    DEFAULT_DATA_PATH,
    prepare_data,
)

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output_residual_pca"
SEED = 20261120


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    return parser.parse_args(argv)


def reverse_mask(instruments: list[Instrument], columns: pd.Index) -> np.ndarray:
    reverse = {
        f"{instrument.id}@{instrument.version}/{item.id}": bool(item.reverse)
        for instrument in instruments
        for item in instrument.items
        if item.kind != "column"
    }
    return np.array([reverse[column] for column in columns], dtype=float)


def decompose(
    associations: pd.DataFrame, keyed_reverse: np.ndarray
) -> tuple[np.ndarray, dict[str, object]]:
    values = associations.to_numpy(copy=True)
    values = (values + values.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(values)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    loadings = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))

    method_candidates = range(1, min(7, len(eigenvalues)))
    reverse_correlations = {
        component: float(np.corrcoef(loadings[:, component], keyed_reverse)[0, 1])
        for component in method_candidates
    }
    method_component = max(
        reverse_correlations, key=lambda component: abs(reverse_correlations[component])
    )
    selected = [
        component
        for component in range(1, len(eigenvalues))
        if component != method_component
    ][:2]
    coordinates = _orient_axes(loadings[:, selected])
    explained = np.clip(eigenvalues, 0.0, None) / np.clip(
        eigenvalues, 0.0, None
    ).sum()
    metrics: dict[str, object] = {
        "general_component": 1,
        "general_explained_variance": float(explained[0]),
        "wording_component": int(method_component + 1),
        "wording_explained_variance": float(explained[method_component]),
        "wording_reverse_key_correlation": float(
            reverse_correlations[method_component]
        ),
        "displayed_components": [int(component + 1) for component in selected],
        "displayed_explained_variance": [
            float(explained[component]) for component in selected
        ],
        "candidate_reverse_key_correlations": {
            f"pc{component + 1}": correlation
            for component, correlation in reverse_correlations.items()
        },
    }
    return coordinates, metrics


def fit_map(
    data: pd.DataFrame,
    instruments: list[Instrument],
    *,
    bootstrap: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    values, metadata = collect_item_values(instruments, data)
    associations, _ = spearman_associations(values)
    keyed_reverse = reverse_mask(instruments, associations.columns)
    reference, metrics = decompose(associations, keyed_reverse)

    maps: list[np.ndarray] = []
    bootstrap_wording_components: Counter[int] = Counter()
    bootstrap_displayed_components: Counter[tuple[int, ...]] = Counter()
    rng = np.random.default_rng(SEED)
    for _ in range(bootstrap):
        row_index = rng.integers(0, len(values), len(values))
        sample = values.iloc[row_index].reset_index(drop=True)
        try:
            sample_associations, _ = spearman_associations(sample)
            sample_coordinates, sample_metrics = decompose(
                sample_associations, keyed_reverse
            )
            maps.append(_align_to_reference(sample_coordinates, reference))
            bootstrap_wording_components[int(sample_metrics["wording_component"])] += 1
            bootstrap_displayed_components[
                tuple(sample_metrics["displayed_components"])
            ] += 1
        except (ValueError, FloatingPointError):
            continue

    result = metadata.copy()
    result["residual_dimension_1"] = reference[:, 0]
    result["residual_dimension_2"] = reference[:, 1]
    result["residual_dimension_1_sd"] = np.nan
    result["residual_dimension_2_sd"] = np.nan
    if maps:
        stacked = np.stack(maps)
        ddof = 1 if len(maps) > 1 else 0
        result["residual_dimension_1_sd"] = stacked[:, :, 0].std(axis=0, ddof=ddof)
        result["residual_dimension_2_sd"] = stacked[:, :, 1].std(axis=0, ddof=ddof)
    metrics.update(
        {
            "n_subjects": int(len(data)),
            "n_items": int(len(result)),
            "bootstrap_requested": int(bootstrap),
            "bootstrap_valid": int(len(maps)),
            "bootstrap_wording_component_counts": {
                f"pc{component}": count
                for component, count in sorted(bootstrap_wording_components.items())
            },
            "bootstrap_displayed_component_counts": {
                "+".join(f"pc{component}" for component in components): count
                for components, count in sorted(bootstrap_displayed_components.items())
            },
        }
    )
    return result, metrics


def separation_statistics(
    coordinates: np.ndarray,
    labels: np.ndarray,
    *,
    permutations: int = 10000,
) -> dict[str, object]:
    labels = labels.astype(bool)
    vector = coordinates[labels].mean(axis=0) - coordinates[~labels].mean(axis=0)
    observed = float(np.linalg.norm(vector))
    rng = np.random.default_rng(SEED)
    null = np.empty(permutations)
    for index in range(permutations):
        shuffled = rng.permutation(labels)
        difference = (
            coordinates[shuffled].mean(axis=0)
            - coordinates[~shuffled].mean(axis=0)
        )
        null[index] = np.linalg.norm(difference)
    return {
        "tagged_items": int(labels.sum()),
        "centroid_difference": [float(value) for value in vector],
        "centroid_distance": observed,
        "permutation_p": float((1 + np.sum(null >= observed)) / (permutations + 1)),
        "dimension_1_correlation": float(np.corrcoef(coordinates[:, 0], labels)[0, 1]),
        "dimension_2_correlation": float(np.corrcoef(coordinates[:, 1], labels)[0, 1]),
    }


def controlled_item_regression(frame: pd.DataFrame, outcome: str) -> dict[str, object]:
    """Describe tag associations after accounting for instrument and keying."""
    instrument = pd.get_dummies(frame["instrument"], dtype=float)
    design = pd.DataFrame(
        {
            "intercept": 1.0,
            "reverse_keyed": frame["reverse_keyed"].astype(float),
            "instrument_phq9": instrument.get("phq9", 0.0),
            "instrument_sds20": instrument.get("sds20", 0.0),
            "somatic": frame["somatic"].astype(float),
            "interpersonal": frame["interpersonal"].astype(float),
        }
    )
    x = design.to_numpy()
    y = frame[outcome].to_numpy()
    beta, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ beta
    degrees_of_freedom = len(y) - x.shape[1]
    residual_variance = float(residual @ residual / degrees_of_freedom)
    covariance = residual_variance * np.linalg.inv(x.T @ x)
    standard_errors = np.sqrt(np.diag(covariance))
    t_values = beta / standard_errors
    p_values = 2 * student_t.sf(np.abs(t_values), degrees_of_freedom)
    return {
        name: {
            "coefficient": float(beta[index]),
            "standard_error": float(standard_errors[index]),
            "p_value": float(p_values[index]),
        }
        for index, name in enumerate(design.columns)
    }


def plot_map(frame: pd.DataFrame, metrics: dict[str, object], path: Path) -> None:
    styles = {
        "other": ("0.65", "o"),
        "somatic": ("#d95f02", "^"),
        "interpersonal": ("#7570b3", "s"),
    }
    figure, axis = plt.subplots(figsize=(10, 8))
    for category, (color, marker) in styles.items():
        subset = frame[frame["content_tag"] == category]
        axis.scatter(
            subset["residual_dimension_1"],
            subset["residual_dimension_2"],
            color=color,
            marker=marker,
            s=75,
            edgecolor="black",
            linewidth=0.5,
            label=category,
            zorder=2,
        )
        axis.errorbar(
            subset["residual_dimension_1"],
            subset["residual_dimension_2"],
            xerr=subset["residual_dimension_1_sd"],
            yerr=subset["residual_dimension_2_sd"],
            fmt="none",
            ecolor="0.75",
            elinewidth=0.7,
            alpha=0.7,
            zorder=1,
        )
    for row in frame.itertuples():
        axis.annotate(
            f"{row.instrument}:{row.item_id}",
            (row.residual_dimension_1, row.residual_dimension_2),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
        )
    components = metrics["displayed_components"]
    variances = metrics["displayed_explained_variance"]
    axis.set_xlabel(
        f"Residual PC{components[0]} loading ({100 * variances[0]:.1f}% original variance)"
    )
    axis.set_ylabel(
        f"Residual PC{components[1]} loading ({100 * variances[1]:.1f}% original variance)"
    )
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    axis.set_title("Residual item map after removing general and wording components")
    axis.legend(title="Content tag (not used to fit PCA)")
    axis.text(
        0.01,
        0.01,
        "Colors test content enrichment; they did not determine the PCA coordinates.",
        transform=axis.transAxes,
        fontsize=8,
        color="0.35",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def plot_pc3_groups(frame: pd.DataFrame, path: Path) -> None:
    order = ["other", "somatic", "interpersonal"]
    colors = ["0.65", "#d95f02", "#7570b3"]
    rng = np.random.default_rng(SEED)
    figure, axis = plt.subplots(figsize=(7, 5))
    for index, (category, color) in enumerate(zip(order, colors)):
        values = frame.loc[
            frame["content_tag"] == category, "residual_dimension_1"
        ].to_numpy()
        jitter = rng.uniform(-0.09, 0.09, size=len(values))
        axis.scatter(
            np.full(len(values), index) + jitter,
            values,
            color=color,
            edgecolor="black",
            linewidth=0.4,
            s=55,
            alpha=0.85,
        )
        axis.hlines(
            values.mean(), index - 0.22, index + 0.22, color="black", linewidth=2.2
        )
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.set_xticks(range(len(order)), order)
    axis.set_ylabel("Residual PC3 item loading")
    axis.set_title("Residual PC3 by content tag")
    axis.text(
        0.01,
        0.01,
        "Horizontal bars show group means; each point is one item.",
        transform=axis.transAxes,
        fontsize=8,
        color="0.35",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


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
    full, metrics = fit_map(data, instruments, bootstrap=200)
    tags = pd.read_csv(HERE / "semantic_tags.csv")
    frame = full.merge(tags, on=["instrument", "item_id"], validate="one_to_one")
    keyed_reverse = reverse_mask(
        instruments,
        pd.Index(frame["item"].tolist()),
    )
    frame["reverse_keyed"] = keyed_reverse.astype(bool)
    frame["content_tag"] = np.select(
        [frame["somatic"].eq(1), frame["interpersonal"].eq(1)],
        ["somatic", "interpersonal"],
        default="other",
    )
    coordinates = frame[["residual_dimension_1", "residual_dimension_2"]].to_numpy()
    metrics["somatic_separation"] = separation_statistics(
        coordinates, frame["somatic"].to_numpy()
    )
    metrics["interpersonal_separation"] = separation_statistics(
        coordinates, frame["interpersonal"].to_numpy()
    )
    metrics["controlled_item_regression"] = {
        "note": (
            "Exploratory item-level OLS; accounts for reverse keying and instrument "
            "membership but does not model dependence among item loadings."
        ),
        "residual_dimension_1": controlled_item_regression(
            frame, "residual_dimension_1"
        ),
        "residual_dimension_2": controlled_item_regression(
            frame, "residual_dimension_2"
        ),
    }

    sample_1 = data[data["sample"] == "sample_1"].reset_index(drop=True)
    sample_2 = data[data["sample"] == "sample_2"].reset_index(drop=True)
    first, first_metrics = fit_map(sample_1, instruments, bootstrap=0)
    second, second_metrics = fit_map(sample_2, instruments, bootstrap=0)
    first_aligned = _align_to_reference(
        first[["residual_dimension_1", "residual_dimension_2"]].to_numpy(),
        coordinates,
    )
    second_aligned = _align_to_reference(
        second[["residual_dimension_1", "residual_dimension_2"]].to_numpy(),
        coordinates,
    )
    metrics["split_sample"] = {
        "sample_1_n": int(len(sample_1)),
        "sample_2_n": int(len(sample_2)),
        "dimension_1_correlation": float(
            np.corrcoef(first_aligned[:, 0], second_aligned[:, 0])[0, 1]
        ),
        "dimension_2_correlation": float(
            np.corrcoef(first_aligned[:, 1], second_aligned[:, 1])[0, 1]
        ),
        "sample_1_components": first_metrics["displayed_components"],
        "sample_2_components": second_metrics["displayed_components"],
        "sample_1_wording_component": first_metrics["wording_component"],
        "sample_2_wording_component": second_metrics["wording_component"],
    }

    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "residual_item_coordinates.csv", index=False)
    (output / "residual_pca_summary.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    plot_map(frame, metrics, output / "residual_construct_map.png")
    plot_pc3_groups(frame, output / "residual_pc3_by_content.png")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
