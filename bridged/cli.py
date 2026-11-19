"""Command line interface: validate, score, compare, template, import-items."""

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
        print(f"wrote {args.out} ({len(scores)} rows)")
        return 0

    if args.command == "compare":
        a, b = _load_pair(args.a, args.b)
        data = pd.read_csv(args.data)
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

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
