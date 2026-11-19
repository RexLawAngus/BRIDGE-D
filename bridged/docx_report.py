"""Publication-style Chinese Word report with three-line tables."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from . import __version__
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

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
LATIN_FONT = "Times New Roman"


def _font(run, east_asia: str = BODY_FONT, size: float = 10.5, bold: bool = False) -> None:
    run.font.name = LATIN_FONT
    run.font.size = Pt(size)
    run.bold = bold
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    fonts.set(qn("w:eastAsia"), east_asia)


def _cell_border(cell, top: int | None = None, bottom: int | None = None) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge, size in (("top", top), ("bottom", bottom)):
        if size is None:
            continue
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")
        borders.append(element)


def _three_line(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "nil")
        borders.append(element)
    tbl_pr.append(borders)
    for cell in table.rows[0].cells:
        _cell_border(cell, top=12, bottom=8)
    for cell in table.rows[-1].cells:
        _cell_border(cell, bottom=12)


def _fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def _add_table(
    doc: Document,
    caption: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    note: str | None = None,
) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(caption)
    _font(run, HEAD_FONT, 10.5, bold=True)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(header))
        _font(run, BODY_FONT, 9, bold=True)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = ""
            run = cells[index].paragraphs[0].add_run(str(value))
            _font(run, BODY_FONT, 9)
            cells[index].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    _three_line(table)
    if note:
        note_paragraph = doc.add_paragraph()
        note_run = note_paragraph.add_run(note)
        _font(note_run, BODY_FONT, 8)


def build_docx(
    a: Instrument,
    b: Instrument,
    data: pd.DataFrame,
    n_boot: int = 0,
    lang: str = "zh",
    path: str | Path = "report.docx",
) -> Path:
    t = strings(lang)
    h = t["headers"]  # type: ignore[index]

    scores_a = a.score(data)
    scores_b = b.score(data)
    total_a = scores_a[f"{a.id}_total"]
    total_b = scores_b[f"{b.id}_total"]
    pair = pd.concat([total_a, total_b], axis=1).dropna()
    n = len(pair)

    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.5)
    normal = document.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(10.5)
    normal_rpr = normal.element.get_or_add_rPr()
    normal_fonts = normal_rpr.find(qn("w:rFonts"))
    if normal_fonts is None:
        normal_fonts = OxmlElement("w:rFonts")
        normal_rpr.append(normal_fonts)
    normal_fonts.set(qn("w:eastAsia"), BODY_FONT)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(str(t["title"]).format(a=a.name, b=b.name))  # type: ignore[index]
    _font(run, HEAD_FONT, 15, bold=True)

    intro = document.add_paragraph()
    intro.add_run(
        f"{a.name}（{a.id} v{a.version}，{len(a.items)} 个条目）与 "
        f"{b.name}（{b.id} v{b.version}，{len(b.items)} 个条目），"
        f"完整配对 n = {n}。"
    ).font.size = Pt(10.5)

    desc = descriptives({a.id: total_a, b.id: total_b})
    _add_table(
        document,
        "表 1  各量表描述统计",
        [h["scale"], h["n"], h["mean"], h["sd"], h["median"], h["min"], h["max"], h["missing"]],
        [
            [
                row["scale"],
                row["n"],
                _fmt(row["mean"]),
                _fmt(row["sd"]),
                _fmt(row["median"]),
                _fmt(row["min"]),
                _fmt(row["max"]),
                row["missing"],
            ]
            for _, row in desc.iterrows()
        ],
        "注：连续变量保留两位小数。",
    )

    _add_table(
        document,
        "表 2  内部一致性",
        [h["scale"], h["alpha"]],
        [
            [a.id, _fmt(cronbach_alpha(a.item_values(data)), 3)],
            [b.id, _fmt(cronbach_alpha(b.item_values(data)), 3)],
        ],
        "注：α 为 Cronbach's alpha，基于完整作答条目计算。",
    )

    _add_table(
        document,
        "表 3  两量表相关性",
        [h["pair"], h["pearson"], h["spearman"]],
        [
            [
                f"{a.id} vs {b.id}",
                _fmt(float(pair.corr().iloc[0, 1]), 3),
                _fmt(float(pair.corr(method="spearman").iloc[0, 1]), 3),
            ]
        ],
        "注：相关不等于一致，请结合表 4 解读。",
    )

    agreement = bland_altman(total_a, total_b)
    agreement["icc21"] = icc21(total_a, total_b)
    _add_table(
        document,
        "表 4  一致性分析",
        [h["n"], h["mean_diff"], h["sd_diff"], h["loa_lower"], h["loa_upper"], h["icc21"]],
        [
            [
                agreement["n"],
                _fmt(agreement["mean_diff"]),
                _fmt(agreement["sd_diff"]),
                _fmt(agreement["loa_lower"]),
                _fmt(agreement["loa_upper"]),
                _fmt(agreement["icc21"], 3),
            ]
        ],
        "注：ICC(2,1) 为双向随机效应、绝对一致性、单次测量；"
        "LoA 为 Bland-Altman 一致性界限。量程不同时 ICC 仅作描述性参考。",
    )

    subscale_rows = []
    for name in a.subscales:
        series = scores_a[f"{a.id}_{name}"]
        sub_pair = pd.concat([series, total_b], axis=1).dropna()
        subscale_rows.append(
            [
                f"{a.id}_{name}",
                _fmt(float(sub_pair.corr().iloc[0, 1]), 3),
                _fmt(float(sub_pair.corr(method="spearman").iloc[0, 1]), 3),
            ]
        )
    for name in b.subscales:
        series = scores_b[f"{b.id}_{name}"]
        sub_pair = pd.concat([series, total_a], axis=1).dropna()
        subscale_rows.append(
            [
                f"{b.id}_{name}",
                _fmt(float(sub_pair.corr().iloc[0, 1]), 3),
                _fmt(float(sub_pair.corr(method="spearman").iloc[0, 1]), 3),
            ]
        )
    if subscale_rows:
        _add_table(
            document,
            "表 5  维度分与另一量表总分的相关",
            [h["subscale"], h["pearson"], h["spearman"]],
            subscale_rows,
            "注：每一行是某量表的维度分与另一量表总分的相关。",
        )

    if a.cutoffs and b.cutoffs:
        class_a = pd.Categorical(a.classify(total_a), categories=[c["label"] for c in a.cutoffs], ordered=True)
        class_b = pd.Categorical(b.classify(total_b), categories=[c["label"] for c in b.cutoffs], ordered=True)
        class_a = pd.Series(class_a)
        class_b = pd.Series(class_b)
        kappa = cohen_kappa(class_a, class_b)
        cross = (
            pd.crosstab(class_a, class_b, dropna=True)
            .rename_axis(index=a.id, columns=b.id)
            .reset_index()
        )
        _add_table(
            document,
            "表 6  分类一致性",
            [a.id, *[str(c) for c in cross.columns[1:]]],
            cross.astype(object).values.tolist(),
            f"注：κ = {kappa['kappa']:.3f}，观察一致率 = {kappa['agreement']:.3f}。",
        )

    try:
        crosswalk = equipercentile(total_a, total_b, n_boot=n_boot)
        table = crosswalk.head(15)
        _add_table(
            document,
            "表 7  等百分位链接",
            [h["score_a"], h["percentile"], h["linked_b"], h["ci_low"], h["ci_high"]],
            [
                [
                    _fmt(row["score_a"], 2),
                    _fmt(row["percentile"], 3),
                    _fmt(row["linked_b"], 3),
                    _fmt(row.get("ci_low"), 3),
                    _fmt(row.get("ci_high"), 3),
                ]
                for _, row in table.iterrows()
            ],
            "注：仅展示前 15 个分数点；n < 100 时链接结果不稳定，应谨慎解读。",
        )
    except ValueError:
        pass

    heading = document.add_paragraph()
    run = heading.add_run("方法学段落")
    _font(run, HEAD_FONT, 12, bold=True)

    methods = str(t["methods_text"]).format(  # type: ignore[index]
        a=a.name, b=b.name, n_boot=n_boot, n=n
    )
    methods = methods.lstrip("> ").replace("\n> ", "\n")
    paragraph = document.add_paragraph(methods)
    paragraph.paragraph_format.first_line_indent = Pt(21)

    footer = document.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run(
        f"由 BRIDGE-D v{__version__} 生成 · https://github.com/RexLawAngus/BRIDGE-D"
    )
    _font(run, BODY_FONT, 8)

    destination = Path(path)
    document.save(destination)
    return destination
