"""Validate pre-specified content contrasts with the NSDUH adult MDE sample.

This is a construct-map validation analysis, not a nationally representative
survey estimate. The current construct-map implementation does not use the
NSDUH complex-survey weights or design variables.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bridged.construct_map import fit_construct_map, write_construct_map  # noqa: E402
from bridged.instrument import Instrument  # noqa: E402
from bridged.map_analysis import (  # noqa: E402
    compare_item_maps,
    validate_map_groups,
    write_group_validation,
    write_map_comparison,
)

HERE = Path(__file__).resolve().parent
DATASET = (
    ROOT.parents[1]
    / "公开数据集"
    / "nsduh_2021_2024_mde_social_function"
)
RAW_DATA = DATASET / "raw_tsv" / "NSDUH_2021_2024_Tab.txt"
PREPARED_DATA = DATASET / "analysis" / "nsduh_adult_mde_construct_map.csv"
PREPARATION_SUMMARY = DATASET / "analysis" / "preparation_summary.json"
OUTPUT = HERE / "output_pca"

SYMPTOM_SOURCES = {
    "AD_MDEA1": "mde_depressed",
    "AD_MDEA2": "mde_anhedonia",
    "AD_MDEA3": "mde_appetite",
    "AD_MDEA4": "mde_sleep",
    "AD_MDEA5": "mde_psychomotor",
    "AD_MDEA6": "mde_fatigue",
    "AD_MDEA7": "mde_worthlessness",
    "AD_MDEA8": "mde_concentration",
}
FUNCTION_SOURCES = {
    "ADPSHMGT": "sds_home",
    "ADPSWORK": "sds_work",
    "ADPSRELS": "sds_relationships",
    "ADPSSOC": "sds_social",
}
IDENTIFIERS = [
    "YEAR",
    "QUESTID2",
    "AMDEYR",
    "ANALWT2_C4",
    "VESTR_C",
    "VEREP",
]

EXPECTED_GROUPS = {
    "cognitive_affective": [
        "mde_depressed",
        "mde_anhedonia",
        "mde_worthlessness",
        "mde_concentration",
    ],
    "somatic": [
        "mde_appetite",
        "mde_sleep",
        "mde_psychomotor",
        "mde_fatigue",
    ],
    "non_interpersonal_function": ["sds_home", "sds_work"],
    "interpersonal_function": ["sds_relationships", "sds_social"],
}

SHORT_LABELS = {
    "mde_depressed": "depressed",
    "mde_anhedonia": "anhedonia",
    "mde_appetite": "appetite/weight",
    "mde_sleep": "sleep",
    "mde_psychomotor": "psychomotor",
    "mde_fatigue": "fatigue",
    "mde_worthlessness": "worthlessness",
    "mde_concentration": "concentration",
    "sds_home": "home",
    "sds_work": "work",
    "sds_relationships": "relationships",
    "sds_social": "social life",
}

LABEL_OFFSETS = {
    "mde_appetite": (6, 8),
    "mde_sleep": (6, -14),
    "sds_home": (8, -12),
    "sds_work": (8, 8),
    "sds_relationships": (8, 8),
    "sds_social": (-8, -16),
}

COLORS = {
    "cognitive_affective": "#4477AA",
    "somatic": "#EE7733",
    "non_interpersonal_function": "#228833",
    "interpersonal_function": "#CC3311",
}


def prepare_data(
    raw_data: Path = RAW_DATA,
    prepared_data: Path = PREPARED_DATA,
    preparation_summary: Path = PREPARATION_SUMMARY,
    *,
    force: bool = False,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Extract a complete-case adult past-year-MDE table from the large TSV."""
    if prepared_data.exists() and preparation_summary.exists() and not force:
        data = pd.read_csv(prepared_data, dtype={"QUESTID2": "string"})
        summary = json.loads(preparation_summary.read_text(encoding="utf-8"))
        return data, summary

    if not raw_data.exists():
        raise FileNotFoundError(
            f"NSDUH TSV not found: {raw_data}. Pass --raw-data PATH."
        )

    usecols = IDENTIFIERS + list(SYMPTOM_SOURCES) + list(FUNCTION_SOURCES)
    selected: list[pd.DataFrame] = []
    rows_read = 0
    adult_past_year_mde = 0
    symptom_complete = 0
    function_complete = 0

    for chunk in pd.read_csv(
        raw_data,
        sep="\t",
        usecols=usecols,
        dtype={"QUESTID2": "string"},
        chunksize=25_000,
        low_memory=False,
    ):
        rows_read += len(chunk)
        cleaned = chunk[IDENTIFIERS].copy()

        for source, target in SYMPTOM_SOURCES.items():
            raw = pd.to_numeric(chunk[source], errors="coerce")
            cleaned[target] = raw.map({1: 1.0, 2: 0.0})

        for source, target in FUNCTION_SOURCES.items():
            raw = pd.to_numeric(chunk[source], errors="coerce")
            cleaned[target] = raw.where(raw.between(0, 10))

        is_adult_mde = pd.to_numeric(cleaned["AMDEYR"], errors="coerce").eq(1)
        symptoms_ok = cleaned[list(SYMPTOM_SOURCES.values())].notna().all(axis=1)
        functions_ok = cleaned[list(FUNCTION_SOURCES.values())].notna().all(axis=1)
        adult_past_year_mde += int(is_adult_mde.sum())
        symptom_complete += int((is_adult_mde & symptoms_ok).sum())
        function_complete += int((is_adult_mde & functions_ok).sum())
        selected.append(cleaned.loc[is_adult_mde & symptoms_ok & functions_ok])

    data = pd.concat(selected, ignore_index=True)
    data["YEAR"] = pd.to_numeric(data["YEAR"], errors="raise").astype(int)
    for column in [*SYMPTOM_SOURCES.values(), *FUNCTION_SOURCES.values()]:
        data[column] = pd.to_numeric(data[column], errors="raise")

    prepared_data.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(prepared_data, index=False)
    summary: dict[str, object] = {
        "source": str(raw_data.resolve()),
        "rows_read": rows_read,
        "adult_past_year_mde": adult_past_year_mde,
        "adult_mde_complete_symptoms": symptom_complete,
        "adult_mde_complete_function_domains": function_complete,
        "analysis_complete_cases": len(data),
        "years": {
            str(int(year)): int(count)
            for year, count in data["YEAR"].value_counts().sort_index().items()
        },
        "symptom_recoding": "AD_MDEA1-8: 1 -> 1 (present), 2 -> 0 (absent); all other codes -> missing",
        "function_recoding": "ADPSHMGT/WORK/RELS/SOC: retain 0-10; all other codes -> missing",
        "selection": "AMDEYR=1 and complete on all 8 symptom indicators and all 4 SDS role domains",
        "survey_design_note": "Weights and design variables are retained but not used by this descriptive construct-map validation.",
    }
    preparation_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data, summary


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


def exact_group_separation(
    coordinates: pd.DataFrame,
    first_group: list[str],
    second_group: list[str],
) -> dict[str, object]:
    """Compare a pre-specified two-group contrast with every same-size split."""
    item_ids = first_group + second_group
    indexed = coordinates.set_index("item_id").loc[item_ids]
    points = indexed[["dimension_1", "dimension_2"]].to_numpy()
    pc2 = indexed["dimension_2"].to_numpy()
    first_size = len(first_group)
    observed_mask = np.array([item in first_group for item in item_ids])

    def stats(mask: np.ndarray) -> tuple[float, float]:
        distance_2d = float(
            np.linalg.norm(points[mask].mean(axis=0) - points[~mask].mean(axis=0))
        )
        pc2_difference = float(abs(pc2[mask].mean() - pc2[~mask].mean()))
        return distance_2d, pc2_difference

    observed_2d, observed_pc2 = stats(observed_mask)
    null_2d: list[float] = []
    null_pc2: list[float] = []
    for indices in itertools.combinations(range(len(item_ids)), first_size):
        mask = np.zeros(len(item_ids), dtype=bool)
        mask[list(indices)] = True
        distance_2d, pc2_difference = stats(mask)
        null_2d.append(distance_2d)
        null_pc2.append(pc2_difference)

    tolerance = 1e-12
    p_2d = sum(value >= observed_2d - tolerance for value in null_2d) / len(null_2d)
    p_pc2 = sum(value >= observed_pc2 - tolerance for value in null_pc2) / len(null_pc2)
    return {
        "groups": [first_group, second_group],
        "centroid_distance_pc1_pc2": observed_2d,
        "exact_permutation_p_pc1_pc2": p_2d,
        "absolute_pc2_mean_difference": observed_pc2,
        "exact_permutation_p_pc2": p_pc2,
        "partitions_evaluated": len(null_2d),
    }


def split_axis_reproducibility(reference, early, late) -> dict[str, float]:
    output: dict[str, float] = {}
    ref = reference.coordinates.set_index("item_id")
    for label, result in [("2021_2022", early), ("2023_2024", late)]:
        candidate = result.coordinates.set_index("item_id").loc[ref.index]
        for dimension in ["dimension_1", "dimension_2"]:
            correlation = float(np.corrcoef(ref[dimension], candidate[dimension])[0, 1])
            output[f"{label}_{dimension}_absolute_correlation"] = abs(correlation)
    return output


def cluster_agreement(
    coordinates: pd.DataFrame, first_group: list[str], second_group: list[str]
) -> float | None:
    indexed = coordinates.set_index("item_id").loc[first_group + second_group]
    if indexed["cluster"].nunique() < 2:
        return None
    expected = [0] * len(first_group) + [1] * len(second_group)
    return float(adjusted_rand_score(expected, indexed["cluster"]))


def category_for(item_id: str) -> str:
    for category, members in EXPECTED_GROUPS.items():
        if item_id in members:
            return category
    raise KeyError(item_id)


def add_hypothesis_labels(result, output_path: Path) -> None:
    frame = result.coordinates.copy()
    frame["expected_category"] = frame["item_id"].map(category_for)
    frame["short_label"] = frame["item_id"].map(SHORT_LABELS)
    frame.to_csv(output_path, index=False)


def postfit_groups_for(label: str) -> pd.DataFrame:
    categories: list[str]
    if label == "symptoms":
        categories = ["cognitive_affective", "somatic"]
    elif label == "functions":
        categories = ["non_interpersonal_function", "interpersonal_function"]
    else:
        categories = list(EXPECTED_GROUPS)
    rows = [
        {
            "instrument": (
                "nsduh_mde8" if item_id.startswith("mde_") else "nsduh_sds4"
            ),
            "item_id": item_id,
            "group": category,
        }
        for category in categories
        for item_id in EXPECTED_GROUPS[category]
    ]
    return pd.DataFrame(rows)


def plot_panel(axis, result, title: str) -> None:
    frame = result.coordinates.copy()
    frame["expected_category"] = frame["item_id"].map(category_for)
    for category, subset in frame.groupby("expected_category", sort=False):
        axis.scatter(
            subset["dimension_1"],
            subset["dimension_2"],
            color=COLORS[category],
            s=64,
            edgecolor="black",
            linewidth=0.5,
            label=category.replace("_", " "),
            zorder=2,
        )
        if subset["dimension_1_sd"].notna().all():
            axis.errorbar(
                subset["dimension_1"],
                subset["dimension_2"],
                xerr=subset["dimension_1_sd"],
                yerr=subset["dimension_2_sd"],
                fmt="none",
                ecolor=COLORS[category],
                alpha=0.28,
                linewidth=0.7,
                zorder=1,
            )
        centroid = subset[["dimension_1", "dimension_2"]].mean().to_numpy()
        axis.scatter(
            centroid[0],
            centroid[1],
            marker="X",
            s=115,
            color=COLORS[category],
            edgecolor="white",
            linewidth=1.0,
            zorder=3,
        )
    for row in frame.itertuples():
        offset = LABEL_OFFSETS.get(row.item_id, (4, 4))
        axis.annotate(
            SHORT_LABELS[row.item_id],
            (row.dimension_1, row.dimension_2),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
            ha="right" if offset[0] < 0 else "left",
        )
    axis.axhline(0, color="0.85", linewidth=0.8)
    axis.axvline(0, color="0.85", linewidth=0.8)
    axis.set_title(title)
    axis.set_xlabel(
        f"PC1 loading ({100 * result.metrics['pc1_explained_variance']:.1f}%)"
    )
    axis.set_ylabel(
        f"PC2 loading ({100 * result.metrics['pc2_explained_variance']:.1f}%)"
    )
    axis.legend(fontsize=7, loc="best")


def write_validation_figure(symptoms, functions, combined, output: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    plot_panel(axes[0], symptoms, "Eight MDE symptom indicators")
    plot_panel(axes[1], functions, "Four SDS role domains")
    plot_panel(axes[2], combined, "Combined symptom-function map")
    figure.suptitle(
        "NSDUH PCA construct-map validation: pre-specified content groups",
        fontsize=14,
    )
    figure.tight_layout()
    figure.savefig(output / "hypothesis_validation.png", dpi=200)
    plt.close(figure)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-data", type=Path, default=RAW_DATA)
    parser.add_argument("--prepared-data", type=Path, default=PREPARED_DATA)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument(
        "--force-prepare",
        action="store_true",
        help="rebuild the compact analysis table from the raw TSV",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raw_data = args.raw_data.resolve()
    prepared_data = args.prepared_data.resolve()
    preparation_summary = prepared_data.with_name("preparation_summary.json")
    output = args.out.resolve()
    data, preparation = prepare_data(
        raw_data,
        prepared_data,
        preparation_summary,
        force=args.force_prepare,
    )
    symptom_instrument = Instrument.load(HERE / "instruments" / "nsduh_mde8.toml")
    function_instrument = Instrument.load(HERE / "instruments" / "nsduh_sds4.toml")

    early_data = data[data["YEAR"].isin([2021, 2022])].reset_index(drop=True)
    late_data = data[data["YEAR"].isin([2023, 2024])].reset_index(drop=True)

    analyses = {
        "symptoms": [symptom_instrument],
        "functions": [function_instrument],
        "combined": [symptom_instrument, function_instrument],
    }
    full_results = {}
    split_results = {}
    for label, instruments in analyses.items():
        full_results[label] = fit_one(
            label, data, instruments, bootstrap=200, output=output
        )
        split_results[label] = {
            "early": fit_one(
                f"{label}_2021_2022",
                early_data,
                instruments,
                bootstrap=0,
                output=output,
            ),
            "late": fit_one(
                f"{label}_2023_2024",
                late_data,
                instruments,
                bootstrap=0,
                output=output,
            ),
        }
        add_hypothesis_labels(
            full_results[label], output / label / "hypothesis_item_coordinates.csv"
        )

    symptom_groups = [
        EXPECTED_GROUPS["cognitive_affective"],
        EXPECTED_GROUPS["somatic"],
    ]
    function_groups = [
        EXPECTED_GROUPS["non_interpersonal_function"],
        EXPECTED_GROUPS["interpersonal_function"],
    ]

    summary = {
        "purpose": "Unsupervised PCA loading-map check against pre-specified content labels",
        "interpretation_limit": "The labels are used only after fitting PCA. Results describe this complete-case adult MDE sample and are not survey-weighted population estimates.",
        "preparation": preparation,
        "n_analysis": len(data),
        "n_2021_2022": len(early_data),
        "n_2023_2024": len(late_data),
        "analyses": {},
    }
    for label, result in full_results.items():
        postfit_validation = validate_map_groups(
            result.coordinates,
            postfit_groups_for(label),
            permutations=9999,
            seed=20261120,
        )
        write_group_validation(
            postfit_validation,
            output / label / "postfit_group_validation",
        )
        cross_sample = compare_item_maps(
            split_results[label]["early"].coordinates,
            split_results[label]["late"].coordinates,
        )
        write_map_comparison(
            cross_sample,
            output / label / "cross_sample_comparison",
        )
        label_summary: dict[str, object] = {
            "pca_metrics": result.metrics,
            "split_year_reproducibility": split_axis_reproducibility(
                result,
                split_results[label]["early"],
                split_results[label]["late"],
            ),
            "v0_4_postfit_group_validation": {
                "metrics": postfit_validation.metrics,
                "pairwise_tests": postfit_validation.pairwise_tests.to_dict(
                    orient="records"
                ),
            },
            "v0_4_cross_sample_comparison": cross_sample.metrics,
        }
        if label in {"symptoms", "combined"}:
            label_summary["somatic_vs_cognitive_affective"] = exact_group_separation(
                result.coordinates, *symptom_groups
            )
            label_summary["somatic_vs_cognitive_affective_cluster_ari"] = cluster_agreement(
                result.coordinates, *symptom_groups
            )
        if label in {"functions", "combined"}:
            label_summary["interpersonal_vs_non_interpersonal_function"] = (
                exact_group_separation(result.coordinates, *function_groups)
            )
            label_summary["interpersonal_vs_non_interpersonal_cluster_ari"] = (
                cluster_agreement(result.coordinates, *function_groups)
            )
        summary["analyses"][label] = label_summary

    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    write_validation_figure(
        full_results["symptoms"],
        full_results["functions"],
        full_results["combined"],
        output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
