"""Command line interface for scoring, comparison, simulation, and item maps."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from .instrument import Instrument
from .report import build_report
from .simulate import load_config, run_simulation

TEMPLATE = """\
# bridged instrument definition
# Fill in the fields below, then run:
#   bridged validate this_file.toml
#
# Two ways to score an instrument:
#   1. item-based  (each item has a response scale, we sum them)
#   2. column-based (your export already contains scores; point at the column)
# Delete whichever block you do not need.

id = "my_scale"                 # short, unique, lowercase
name = "My New Instrument"
version = "0.1.0"
language = "en"
rater = "self"                  # self | clinician | parent | observer
recall = "past 2 weeks"
license = "CC-BY-4.0"
citation = "Author A, Author B. Journal. Year;volume:pages."

# ---------------------------------------------------------------- item-based
[response_scales.five_point]
levels = [0, 1, 2, 3, 4]
labels = ["Never", "Rarely", "Sometimes", "Often", "Always"]

[[items]]
id = "q1"
text = "Item text"
construct = "depressed_mood"
response = "five_point"
reverse = false

[[items]]
id = "q2"
text = "Reverse-keyed item"
construct = "energy"
response = "five_point"
reverse = true

[scoring]
missing_min_answered = 1        # minimum answered items for a valid score
missing_strategy = "prorate"    # prorate | zero | listwise

[scoring.total]
method = "sum"
items = "all"

[scoring.subscales.cognitive]
items = ["q1"]

# -------------------------------------------------------------- column-based
# If your export already has a total score, uncomment and delete the item block:
#
# [scoring.total]
# method = "column"
# column = "total_score"
#
# [[items]]
# id = "total_score"
# kind = "column"
# column = "total_score"

# -------------------------------------------------------------------- cutoffs
# Severity bands, ascending. Optional; without cutoffs, classification is skipped.
#
# [[cutoffs]]
# label = "mild"
# min = 5
#
# [[cutoffs]]
# label = "moderate"
# min = 10
"""


def _load_pair(a_path: str, b_path: str) -> tuple[Instrument, Instrument]:
    return Instrument.load(a_path), Instrument.load(b_path)


def _parse_levels(spec: str) -> list[float]:
    spec = str(spec).strip()
    if not spec:
        return [0.0, 1.0, 2.0, 3.0, 4.0]
    if "," in spec:
        return [float(x) for x in spec.split(",")]
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", spec)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        return [float(x) for x in range(int(low), int(high) + 1)]
    raise ValueError(f"cannot parse levels {spec!r}; use '0-4' or '0,1,2,3'")


def _toml_escape(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def import_items(items_path: str, out_path: str, instrument_id: str, name: str) -> None:
    path = Path(items_path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        frame = pd.read_csv(path)
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    if "id" not in frame.columns:
        raise ValueError("item sheet needs an 'id' column")
    frame = frame.fillna("")

    response_scales: dict[str, list[float]] = {}
    lines: list[str] = [
        f"id = {_toml_escape(instrument_id)}",
        f"name = {_toml_escape(name)}",
        'version = "0.1.0"',
        "",
    ]
    subscales: dict[str, list[str]] = {}
    for _, row in frame.iterrows():
        item_id = str(row["id"]).strip()
        if not item_id:
            continue
        response = str(row.get("response", "") or "default").strip()
        levels = _parse_levels(row.get("levels", ""))
        response_scales.setdefault(response, levels)
        lines.extend(
            [
                "[[items]]",
                f"id = {_toml_escape(item_id)}",
                f"response = {_toml_escape(response)}",
            ]
        )
        if row.get("text"):
            lines.append(f"text = {_toml_escape(row['text'])}")
        if row.get("construct"):
            lines.append(f"construct = {_toml_escape(row['construct'])}")
        if str(row.get("reverse", "")).strip().lower() in {"1", "true", "yes"}:
            lines.append("reverse = true")
        subscale = str(row.get("subscale", "") or "").strip()
        if subscale:
            subscales.setdefault(subscale, []).append(item_id)
        lines.append("")

    scale_lines = []
    for response, levels in response_scales.items():
        scale_lines.extend(
            [
                f"[response_scales.{response}]",
                "levels = [" + ", ".join(str(x) for x in levels) + "]",
                "",
            ]
        )
    lines = lines[:4] + scale_lines + lines[4:]

    lines.extend(
        [
            "[scoring]",
            f"missing_min_answered = {max(1, len(frame) // 2)}",
            'missing_strategy = "prorate"',
            "",
            "[scoring.total]",
            'method = "sum"',
            'items = "all"',
        ]
    )
    for subscale, members in subscales.items():
        lines.extend(
            [
                "",
                f"[scoring.subscales.{subscale}]",
                "items = [" + ", ".join(_toml_escape(m) for m in members) + "]",
            ]
        )
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(frame)} rows)")


def _add_item_map_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--instrument", action="append", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-pairs", type=int, default=10)
    parser.add_argument("--clusters", type=int, default=None)
    parser.add_argument("--bootstrap", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--embedding",
        choices=["mds", "pca"],
        default="mds",
        help="two-dimensional item mapping method (default: mds)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bridge-d",
        description="Score instruments and compare co-administered scales.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="check an instrument definition")
    p_validate.add_argument("instrument")

    p_score = sub.add_parser("score", help="score one instrument against a CSV")
    p_score.add_argument("--instrument", required=True)
    p_score.add_argument("--data", required=True)
    p_score.add_argument("--out", required=True)

    p_compare = sub.add_parser("compare", help="compare two co-administered scales")
    p_compare.add_argument("--a", required=True)
    p_compare.add_argument("--b", required=True)
    p_compare.add_argument("--data", required=True)
    p_compare.add_argument("--out", required=True)
    p_compare.add_argument("--bootstrap", type=int, default=0)
    p_compare.add_argument(
        "--lang", default="en", choices=["en", "zh"], help="report language"
    )
    p_compare.add_argument(
        "--format",
        default="md",
        choices=["md", "docx"],
        help="markdown report or publication-style Word document",
    )

    p_template = sub.add_parser("template", help="write a fillable instrument template")
    p_template.add_argument("--out", required=True)

    p_import = sub.add_parser(
        "import-items", help="build an instrument from a CSV/XLSX item sheet"
    )
    p_import.add_argument("--items", required=True)
    p_import.add_argument("--out", required=True)
    p_import.add_argument("--id", required=True)
    p_import.add_argument("--name", default="")
    p_import.add_argument("--lang", default="en", choices=["en", "zh"])

    p_sim = sub.add_parser(
        "simulate", help="generate known-truth data and check recovery"
    )
    p_sim.add_argument("--config", required=True)
    p_sim.add_argument("--out", required=True)
    p_sim.add_argument("--n", type=int, default=None)
    p_sim.add_argument("--replications", type=int, default=None)

    p_item_map = sub.add_parser(
        "item-map",
        help="derive an empirical item map and instrument footprints",
    )
    _add_item_map_arguments(p_item_map)

    p_map = sub.add_parser(
        "construct-map",
        help="legacy alias for item-map",
    )
    _add_item_map_arguments(p_map)

    p_map_validate = sub.add_parser(
        "map-validate",
        help="compare fitted item coordinates with pre-specified groups",
    )
    p_map_validate.add_argument("--coordinates", required=True)
    p_map_validate.add_argument("--groups", required=True)
    p_map_validate.add_argument("--out", required=True)
    p_map_validate.add_argument("--permutations", type=int, default=9999)
    p_map_validate.add_argument("--seed", type=int, default=0)

    p_map_compare = sub.add_parser(
        "map-compare",
        help="align and compare two independently fitted item maps",
    )
    p_map_compare.add_argument("--reference", required=True)
    p_map_compare.add_argument("--candidate", required=True)
    p_map_compare.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "validate":
        instrument = Instrument.load(args.instrument)
        for key, value in instrument.describe().items():
            print(f"{key}: {value}")
        print("OK")
        return 0

    if args.command == "score":
        instrument = Instrument.load(args.instrument)
        data = pd.read_csv(args.data)
        scores = instrument.score(data)
        scores.to_csv(args.out, index=False)
        print(
            f"wrote {args.out} ({len(scores)} rows) "
            f"[{instrument.id}@{instrument.version} "
            f"sha256:{instrument.definition_hash()[:12]}]"
        )
        return 0

    if args.command == "compare":
        a, b = _load_pair(args.a, args.b)
        data = pd.read_csv(args.data)
        if args.format == "docx":
            try:
                from .docx_report import build_docx
            except ImportError:
                print("docx output needs python-docx: pip install 'bridge-d[docx]'")
                return 1
            build_docx(
                a,
                b,
                data,
                n_boot=args.bootstrap,
                lang=args.lang,
                path=args.out,
            )
        else:
            report = build_report(a, b, data, n_boot=args.bootstrap, lang=args.lang)
            Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")
        return 0

    if args.command == "template":
        Path(args.out).write_text(TEMPLATE, encoding="utf-8")
        print(f"wrote {args.out}")
        return 0

    if args.command == "import-items":
        import_items(args.items, args.out, args.id, args.name or args.id)
        return 0

    if args.command == "simulate":
        config = load_config(args.config)
        summary = run_simulation(
            config, args.out, n=args.n, replications=args.replications
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command in {"item-map", "construct-map"}:
        try:
            from .construct_map import fit_construct_map, write_construct_map
        except ImportError as exc:
            print("item-map needs: pip install 'bridge-d[map]'", file=sys.stderr)
            print(f"missing dependency: {exc}", file=sys.stderr)
            return 1
        instruments = [Instrument.load(path) for path in args.instrument]
        data = pd.read_csv(args.data)
        result = fit_construct_map(
            instruments,
            data,
            min_pairs=args.min_pairs,
            clusters=args.clusters,
            bootstrap=args.bootstrap,
            seed=args.seed,
            embedding=args.embedding,
        )
        written = write_construct_map(result, args.out)
        print(
            f"wrote {len(written)} item-map files to {args.out} "
            f"({result.metrics['n_items']} items, "
            f"{result.metrics['n_subjects']} subjects)"
        )
        return 0

    if args.command == "map-validate":
        try:
            from .map_analysis import validate_map_groups, write_group_validation
        except ImportError as exc:
            print("map-validate needs: pip install 'bridge-d[map]'", file=sys.stderr)
            print(f"missing dependency: {exc}", file=sys.stderr)
            return 1
        coordinates = pd.read_csv(args.coordinates)
        groups = pd.read_csv(args.groups)
        result = validate_map_groups(
            coordinates,
            groups,
            permutations=args.permutations,
            seed=args.seed,
        )
        written = write_group_validation(result, args.out)
        print(
            f"wrote {len(written)} validation files to {args.out} "
            f"({result.metrics['n_labeled_items']} labeled items, "
            f"{result.metrics['n_groups']} groups)"
        )
        return 0

    if args.command == "map-compare":
        try:
            from .map_analysis import compare_item_maps, write_map_comparison
        except ImportError as exc:
            print("map-compare needs: pip install 'bridge-d[map]'", file=sys.stderr)
            print(f"missing dependency: {exc}", file=sys.stderr)
            return 1
        reference = pd.read_csv(args.reference)
        candidate = pd.read_csv(args.candidate)
        result = compare_item_maps(reference, candidate)
        written = write_map_comparison(result, args.out)
        print(
            f"wrote {len(written)} comparison files to {args.out} "
            f"({result.metrics['n_common_items']} common items)"
        )
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
