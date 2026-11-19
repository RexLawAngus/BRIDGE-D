"""Markdown report generation (English default, Chinese opt-in)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .compare import (
    bland_altman,
    cohen_kappa,
    cronbach_alpha,
    descriptives,
    equipercentile,
    icc21,
)
from .i18n import strings
from .instrument import Instrument


def _md_table(frame: pd.DataFrame, floatfmt: str = ".2f") -> str:
    columns = [str(c) for c in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]
    for _, row in frame.iterrows():
        cells = []
        for value in row:
            if isinstance(value, float):
                cells.append("" if pd.isna(value) else format(value, floatfmt))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _corr(left: pd.Series, right: pd.Series, method: str) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 3:
        return float("nan")
    return float(pair.corr(method=method).iloc[0, 1])


def build_report(
    a: Instrument,
    b: Instrument,
    data: pd.DataFrame,
    n_boot: int = 0,
    lang: str = "en",
) -> str:
    t = strings(lang)
    h: dict[str, str] = t["headers"]  # type: ignore[assignment]

    scores_a = a.score(data)
    scores_b = b.score(data)
    total_a = scores_a[f"{a.id}_total"]
    total_b = scores_b[f"{b.id}_total"]
    pair = pd.concat([total_a, total_b], axis=1).dropna()
    n = len(pair)

    sections: list[str] = []
    sections.append(f"# {t['title'].format(a=a.name, b=b.name)}\n")  # type: ignore[index]
    sections.append(
        t["meta"].format(  # type: ignore[index]
            id=a.id,
            version=a.version,
            n=len(a.items),
            missing=a.missing_strategy,
            validation=a.validation,
            hash=a.definition_hash()[:12],
        )
        + "\n"
        + t["meta"].format(  # type: ignore[index]
            id=b.id,
            version=b.version,
            n=len(b.items),
            missing=b.missing_strategy,
            validation=b.validation,
            hash=b.definition_hash()[:12],
        )
        + "\n"
        + t["complete_pairs"].format(n=n)  # type: ignore[index]
        + "\n"
    )

    desc = descriptives({a.id: total_a, b.id: total_b})
    desc.columns = [h[c] for c in desc.columns]
    sections.append(f"## {t['descriptives']}\n\n{_md_table(desc)}\n")  # type: ignore[index]

    reliability = pd.DataFrame(
        [
            {h["scale"]: a.id, h["alpha"]: cronbach_alpha(a.item_values(data))},
            {h["scale"]: b.id, h["alpha"]: cronbach_alpha(b.item_values(data))},
        ]
    )
    sections.append(f"## {t['reliability']}\n\n{_md_table(reliability)}\n")  # type: ignore[index]

    association = pd.DataFrame(
        [
            {
                h["pair"]: f"{a.id} vs {b.id}",
                h["pearson"]: _corr(total_a, total_b, "pearson"),
                h["spearman"]: _corr(total_a, total_b, "spearman"),
            }
        ]
    )
    sections.append(f"## {t['association']}\n\n{_md_table(association)}\n")  # type: ignore[index]

    agreement = bland_altman(total_a, total_b)
    agreement["icc21"] = icc21(total_a, total_b)
    agreement_frame = pd.DataFrame([agreement])
    agreement_frame.columns = [
        h.get(c, c) for c in agreement_frame.columns
    ]
    sections.append(
        f"## {t['agreement']}\n\n"  # type: ignore[index]
        + _md_table(agreement_frame)
        + "\n\n"
        + str(t["agreement_note"])
        + "\n"
    )

    subscale_rows = []
    for name in a.subscales:
        series = scores_a[f"{a.id}_{name}"]
        subscale_rows.append(
            {
                h["subscale"]: f"{a.id}_{name}",
                h["pearson"]: _corr(series, total_b, "pearson"),
                h["spearman"]: _corr(series, total_b, "spearman"),
            }
        )
    for name in b.subscales:
        series = scores_b[f"{b.id}_{name}"]
        subscale_rows.append(
            {
                h["subscale"]: f"{b.id}_{name}",
                h["pearson"]: _corr(series, total_a, "pearson"),
                h["spearman"]: _corr(series, total_a, "spearman"),
            }
        )
    if subscale_rows:
        sections.append(
            f"## {t['subscale_corr']}\n\n{_md_table(pd.DataFrame(subscale_rows))}\n"  # type: ignore[index]
        )

    if a.cutoffs and b.cutoffs:
        order_a = [c["label"] for c in a.cutoffs]
        order_b = [c["label"] for c in b.cutoffs]
        class_a = pd.Categorical(a.classify(total_a), categories=order_a, ordered=True)
        class_b = pd.Categorical(b.classify(total_b), categories=order_b, ordered=True)
        class_a = pd.Series(class_a)
        class_b = pd.Series(class_b)
        kappa = cohen_kappa(class_a, class_b)
        table = (
            pd.crosstab(class_a, class_b, dropna=True)
            .rename_axis(index=a.id, columns=b.id)
            .reset_index()
        )
        sections.append(
            f"## {t['classification']}\n\n"  # type: ignore[index]
            + t["kappa"].format(  # type: ignore[index]
                kappa=kappa["kappa"], agreement=kappa["agreement"], n=kappa["n"]
            )
            + "\n\n"
            + _md_table(table)
            + "\n"
        )
    else:
        sections.append(
            f"## {t['classification']}\n\n{str(t['skipped_cutoffs'])}\n"  # type: ignore[index]
        )

    try:
        crosswalk = equipercentile(total_a, total_b, n_boot=n_boot)
        crosswalk = crosswalk.rename(
            columns={
                "score_a": h["score_a"],
                "percentile": h["percentile"],
                "linked_b": h["linked_b"],
                "ci_low": h["ci_low"],
                "ci_high": h["ci_high"],
            }
        )
        sections.append(
            f"## {t['crosswalk']}\n\n"  # type: ignore[index]
            + _md_table(crosswalk.head(20), floatfmt=".3f")
            + "\n"
        )
        if n < 100:
            sections.append(str(t["crosswalk_warning"]) + "\n")  # type: ignore[index]
    except ValueError as exc:
        sections.append(f"## {t['crosswalk']}\n\nSkipped: {exc}\n")  # type: ignore[index]

    sections.append(
        f"## {t['methods']}\n\n"  # type: ignore[index]
        + t["methods_text"].format(  # type: ignore[index]
            a=a.name, b=b.name, n_boot=n_boot, n=n
        )
        + "\n"
    )
    return "\n".join(sections)


def summarize(
    a: Instrument, b: Instrument, data: pd.DataFrame
) -> dict[str, Any]:
    total_a = a.score(data)[f"{a.id}_total"]
    total_b = b.score(data)[f"{b.id}_total"]
    pair = pd.concat([total_a, total_b], axis=1).dropna()
    return {
        "n": int(len(pair)),
        "pearson": _corr(total_a, total_b, "pearson"),
        "icc21": icc21(total_a, total_b),
        "bland_altman": bland_altman(total_a, total_b),
    }
