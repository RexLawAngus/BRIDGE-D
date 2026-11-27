"""Post-fit neighborhoods for arbitrary user-selected item anchors.

Labels never enter map fitting. Full-space distance is 1 - Spearman r;
centroid distances refer explicitly to the supplied two-dimensional projection.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd


@dataclass
class AnchorAnalysisResult:
    distributions: pd.DataFrame
    neighbors: pd.DataFrame
    convergence: pd.DataFrame
    groups: pd.DataFrame
    settings: dict[str, Any]


def analyze_anchor_items(
    fitted_map: Any,
    item_values: pd.DataFrame,
    anchor_items: Sequence[str],
    *,
    groups: pd.DataFrame | None = None,
    positive_thresholds: dict[str, float] | None = None,
    top_k: int = 10,
    bootstrap: int = 1000,
    permutations: int = 9999,
    seed: int = 0,
    min_pairs: int = 10,
) -> AnchorAnalysisResult:
    """Analyze a fitted map using the same scored participants and item IDs.

    ``item_values`` is the scored table returned by collect_item_values, not
    raw response codes. Positivity means value > threshold (default zero).
    Groups contain item/group and optionally group_set for separate label
    partitions. Missing labels stay outside that partition's permutation pool.
    Bootstrap resamples participant rows, recomputes tied ranks, and reports
    percentile CIs and Top-K frequency conditional on a complete anchor row.
    Invalid resamples are counted, never replaced by zero correlations.
    """
    if isinstance(anchor_items, str):
        raise ValueError("anchor_items must be a sequence of stable item IDs")
    anchors = list(anchor_items)
    if not anchors or len(anchors) != len(set(anchors)):
        raise ValueError("provide at least one anchor, without duplicates")
    if top_k < 1 or bootstrap < 0 or permutations < 0 or min_pairs < 3:
        raise ValueError("invalid top_k, bootstrap, permutations, or min_pairs")
    coordinates = fitted_map.coordinates.set_index("item", verify_integrity=True)
    keys = coordinates.index.tolist()
    if not set(anchors).issubset(keys):
        raise ValueError("anchors must occur in the fitted map")
    if not set(keys).issubset(item_values.columns) or item_values.columns.duplicated().any():
        raise ValueError("scored responses must contain unique fitted item IDs")
    values = item_values[keys].astype(float)
    if fitted_map.metrics.get("n_subjects", len(values)) != len(values):
        raise ValueError("participant count does not match fitted map")
    if np.isinf(values.to_numpy()).any():
        raise ValueError("scored responses cannot contain infinities")
    if any(values[c].nunique() < 2 for c in keys):
        raise ValueError("constant or entirely missing items cannot define a neighborhood")
    observed = values.corr(method="spearman", min_periods=min_pairs)
    association = fitted_map.associations.loc[keys, keys]
    distance = fitted_map.distances.loc[keys, keys]
    distance_array = distance.to_numpy()
    if not np.isfinite(observed.to_numpy()).all():
        raise ValueError("insufficient paired observations")
    if not np.allclose(observed, association, atol=1e-10, rtol=1e-8):
        raise ValueError("responses do not match fitted map associations")
    if not np.allclose(distance, (1 - association).clip(0, 2), atol=1e-10):
        raise ValueError("fitted map must use 1 - Spearman r distances")
    xy = coordinates[["dimension_1", "dimension_2"]].to_numpy(float)
    if not np.isfinite(xy).all():
        raise ValueError("coordinates must be finite")
    thresholds = positive_thresholds or {}
    if set(thresholds) - set(anchors) or any(not np.isfinite(v) for v in thresholds.values()):
        raise ValueError("positive thresholds must be finite and refer to anchors")
    lookup = {key: i for i, key in enumerate(keys)}
    ai = [lookup[a] for a in anchors]
    k = min(top_k, len(keys) - 1)

    def order(row: np.ndarray, own: int) -> list[int]:
        return sorted((j for j in range(len(keys)) if j != own),
                      key=lambda j: (-row[j], keys[j]))[:k]

    rng_boot, rng_perm = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(2)]
    boot = np.full((bootstrap, len(anchors), len(keys)), np.nan)
    counts = np.zeros((len(anchors), len(keys)), dtype=int)
    valid = np.zeros(len(anchors), dtype=int)
    array = values.to_numpy()
    complete = not np.isnan(array).any()
    for b in range(bootstrap):
        sample = array[rng_boot.integers(0, len(values), len(values))]
        if complete:
            from scipy.stats import rankdata

            ranks = rankdata(sample, axis=0)
            ranks -= ranks.mean(axis=0)
            norms = np.linalg.norm(ranks, axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                corr = (ranks[:, ai].T @ ranks) / (norms[ai, None] * norms[None, :])
            corr = np.clip(corr, -1, 1)
        else:
            corr = pd.DataFrame(sample).corr(method="spearman", min_periods=min_pairs).to_numpy()[ai]
        boot[b] = corr
        for a, own in enumerate(ai):
            if np.isfinite(corr[a]).all():
                valid[a] += 1
                counts[a, order(corr[a], own)] += 1

    def pair(a: int, j: int) -> dict[str, Any]:
        own = ai[a]
        draws = boot[:, a, j]
        draws = draws[np.isfinite(draws)]
        low, high = np.quantile(draws, [.025, .975]) if len(draws) else (np.nan, np.nan)
        return dict(spearman_r=float(association.iloc[own, j]),
                    distance_1_minus_r=float(distance.iloc[own, j]),
                    distance_2d=float(np.linalg.norm(xy[own] - xy[j])),
                    pairwise_n=int(values.iloc[:, [own, j]].dropna().shape[0]),
                    r_ci_low=float(low), r_ci_high=float(high),
                    distance_ci_low=float(1 - high), distance_ci_high=float(1 - low),
                    bootstrap_pair_valid=int(len(draws)))

    distributions, neighbors, convergence, group_rows = [], [], [], []
    for a, anchor in enumerate(anchors):
        x = values[anchor].dropna()
        q = x.quantile([.25, .5, .75])
        threshold = thresholds.get(anchor, 0.0)
        distributions.append(dict(anchor=anchor, n_valid=len(x), n_missing=len(values)-len(x),
                                  nonzero_n=int(x.ne(0).sum()), nonzero_rate=float(x.ne(0).mean()),
                                  positive_threshold=threshold, positive_n=int(x.gt(threshold).sum()),
                                  positive_rate=float(x.gt(threshold).mean()), mean=float(x.mean()),
                                  sd=float(x.std(ddof=1)), median=float(q.loc[.5]),
                                  q1=float(q.loc[.25]), q3=float(q.loc[.75]), iqr=float(q.loc[.75]-q.loc[.25])))
        for rank, j in enumerate(order(association.iloc[ai[a]].to_numpy(), ai[a]), 1):
            neighbors.append(dict(anchor=anchor, rank=rank, neighbor=keys[j],
                                  **pair(a, j), bootstrap_top_k_count=int(counts[a, j]),
                                  bootstrap_anchor_valid=int(valid[a]),
                                  top_k_stability=float(counts[a, j]/valid[a]) if valid[a] else np.nan))

    cross = [distance.iloc[i, j] for i, j in itertools.combinations(range(len(keys)), 2)
             if coordinates.iloc[i]["instrument"] != coordinates.iloc[j]["instrument"]]
    cross = np.asarray(cross)
    for a, b in itertools.combinations(range(len(anchors)), 2):
        if coordinates.iloc[ai[a]]["instrument"] == coordinates.iloc[ai[b]]["instrument"]:
            continue
        d = float(distance.iloc[ai[a], ai[b]])
        tied = np.isclose(cross, d, atol=1e-12, rtol=0)
        percentile = 100 * (np.sum((cross < d) & ~tied) + .5 * tied.sum()) / len(cross)
        convergence.append(dict(anchor_a=anchors[a], anchor_b=anchors[b], **pair(a, ai[b]),
                                cross_scale_distance_percentile=float(percentile),
                                cross_scale_pair_count=len(cross)))

    if groups is not None:
        if not {"item", "group"}.issubset(groups):
            raise ValueError("groups require item and group columns")
        labels = groups.copy()
        if labels[["item", "group"]].isna().any().any():
            raise ValueError("group labels cannot be missing")
        if "group_set" not in labels:
            labels["group_set"] = "default"
        if labels["group_set"].isna().any() or labels.duplicated(["group_set", "item"]).any():
            raise ValueError("each item can have only one label per group_set")
        if not set(labels["item"]).issubset(keys):
            raise ValueError("group items must occur in fitted map")
        for family, table in labels.groupby("group_set", sort=True):
            group_names = sorted(table["group"].unique())
            table = table.loc[~table["item"].isin(anchors)]
            pool = [lookup[key] for key in table["item"]]
            label_array = table["group"].to_numpy()
            masks = [label_array == g for g in group_names]
            observations = {}
            exceed = {}
            for a, own in enumerate(ai):
                for g, mask in zip(group_names, masks):
                    indices = np.asarray(pool, dtype=int)[mask]
                    observations[a, g] = (float(distance_array[own, indices].mean()),
                                          float(np.linalg.norm(xy[own]-xy[indices].mean(axis=0)))) if len(indices) else (np.nan, np.nan)
                    exceed[a, g] = np.zeros(2, dtype=int)
            for _ in range(permutations):
                shuffled = rng_perm.permutation(label_array)
                for g in group_names:
                    indices = np.asarray(pool, dtype=int)[shuffled == g]
                    if not len(indices):
                        continue
                    centroid = xy[indices].mean(axis=0)
                    for a, own in enumerate(ai):
                        stat = np.array([distance_array[own, indices].mean(), np.linalg.norm(xy[own]-centroid)])
                        exceed[a, g] += stat <= np.asarray(observations[a, g]) + 1e-12
            for a, anchor in enumerate(anchors):
                for g, mask in zip(group_names, masks):
                    mean_d, centroid_d = observations[a, g]
                    p = (exceed[a, g] + 1) / (permutations + 1) if permutations and mask.any() else [np.nan, np.nan]
                    group_rows.append(dict(anchor=anchor, group_set=family, group=g, n_items=int(mask.sum()),
                                           mean_distance_1_minus_r=mean_d, centroid_distance_2d=centroid_d,
                                           p_mean_distance=float(p[0]), p_centroid_2d=float(p[1]),
                                           permutation_pool_n=len(pool)))
    return AnchorAnalysisResult(
        pd.DataFrame(distributions), pd.DataFrame(neighbors),
        pd.DataFrame(convergence, columns=["anchor_a", "anchor_b", "spearman_r", "distance_1_minus_r", "distance_2d", "pairwise_n", "r_ci_low", "r_ci_high", "distance_ci_low", "distance_ci_high", "bootstrap_pair_valid", "cross_scale_distance_percentile", "cross_scale_pair_count"]),
        pd.DataFrame(group_rows, columns=["anchor", "group_set", "group", "n_items", "mean_distance_1_minus_r", "centroid_distance_2d", "p_mean_distance", "p_centroid_2d", "permutation_pool_n"]),
        dict(top_k=k, bootstrap=bootstrap, permutations=permutations, seed=seed, min_pairs=min_pairs,
             n_participants=len(values), embedding=fitted_map.metrics.get("embedding", "unspecified"),
             ci_method="participant percentile bootstrap, finite pair draws", confidence_level=.95,
             stability_denominator="resamples with all anchor correlations finite",
             tie_rule="stable item ID ascending", centroid_space="supplied 2D projection",
             permutation_tail="smaller distance, unadjusted Monte Carlo (b+1)/(B+1)",
             permutation_anchor_rule="all anchors excluded from groups and permutation pools",
             percentile_rule="100 * (number smaller + half number tied) / all cross-scale pairs; descriptive, not a p value"))


def write_anchor_analysis(result: AnchorAnalysisResult, out_dir: str | Path) -> list[Path]:
    """Write strict JSON (undefined statistics are null) and four CSV tables."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"settings": result.settings}
    paths = []
    for name in ["distributions", "neighbors", "convergence", "groups"]:
        frame = getattr(result, name)
        path = out / f"anchor_{name}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
        payload[name] = json.loads(frame.to_json(orient="records", double_precision=15))
    path = out / "anchor_analysis.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return [*paths, path]


def plot_anchor_neighborhood(fitted_map: Any, result: AnchorAnalysisResult, path: str | Path) -> tuple[Path, Path]:
    """Write an optional highlighted map without changing existing map plots."""
    import matplotlib.pyplot as plt
    from matplotlib.text import Text
    from .figure_output import save_figure_pair

    frame = fitted_map.coordinates.set_index("item")
    anchors = result.distributions["anchor"].tolist()
    nearby = set(result.neighbors["neighbor"]) - set(anchors)
    fig, (ax, key_ax) = plt.subplots(1, 2, figsize=(12, 7),
                                    gridspec_kw={"width_ratios": [3, 1.35]}, layout="constrained")
    key_ax.axis("off")
    ax.axhline(0, color="#d5dbe0", linewidth=.8, zorder=0)
    ax.axvline(0, color="#d5dbe0", linewidth=.8, zorder=0)
    for group, color, marker, label, size in [
        (set(frame.index)-nearby-set(anchors), "#aeb9c2", "o", "Other items", 40),
        (nearby, "#0072B2", "o", "Top-K neighbors", 65),
        (set(anchors), "#D55E00", "*", "Anchors", 230),
    ]:
        subset = frame.loc[sorted(group)]
        ax.scatter(subset.dimension_1, subset.dimension_2, c=color, marker=marker,
                   s=size, label=label, edgecolors="white", linewidths=.6, zorder=3)
    ax.margins(.15)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    occupied = []
    entries = [(key, f"A{i}") for i, key in enumerate(anchors, 1)]
    entries += [(key, str(i)) for i, key in enumerate(sorted(nearby), 1)]
    for number, (key, short) in enumerate(entries):
        row = frame.loc[key]
        annotation = ax.annotate(short, (row.dimension_1, row.dimension_2),
                                 xytext=(6, 6), textcoords="offset points", fontsize=8,
                                 color="#9c3c00" if key in anchors else "#17334a",
                                 arrowprops={"arrowstyle": "-", "color": "#8b99a4", "lw": .6})
        for radius in [9, 18, 28, 40, 55, 75]:
            found = False
            for angle in np.linspace(0, 2*np.pi, 12, endpoint=False):
                annotation.set_position((radius*np.cos(angle), radius*np.sin(angle)))
                # Only text bounds, excluding the leader line to the data point.
                box = Text.get_window_extent(annotation, renderer).expanded(1.25, 1.3)
                if not any(box.overlaps(previous) for previous in occupied):
                    found = True
                    break
            if found:
                break
        occupied.append(box)
        spacing = min(.048, .88 / max(1, len(entries)))
        key_ax.text(0, .94-number*spacing, f"{short}  {row.instrument}/{row.item_id}",
                    transform=key_ax.transAxes, fontsize=9,
                    color="#9c3c00" if key in anchors else "#17334a")
    key_ax.text(0, 1, "Item key", transform=key_ax.transAxes, fontsize=11, weight="bold")
    prefix = "PC" if result.settings["embedding"] == "pca" else "Dimension "
    ax.set(xlabel=f"{prefix}1", ylabel=f"{prefix}2", title="Anchor-item neighborhoods")
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    paths = save_figure_pair(fig, path)
    plt.close(fig)
    return paths
