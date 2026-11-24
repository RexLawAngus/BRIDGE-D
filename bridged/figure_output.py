"""Shared publication-figure output settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

FIGURE_DPI = 300


def save_figure_pair(
    figure: Any,
    path: str | Path,
    *,
    dpi: int = FIGURE_DPI,
) -> tuple[Path, Path]:
    """Save one figure as a high-resolution PNG and a matching vector SVG.

    SVG coordinates and text remain vector-based. The dpi setting applies to
    the PNG and to any rasterized artists embedded in the SVG.
    """
    requested = Path(path)
    png_path = requested.with_suffix(".png")
    svg_path = requested.with_suffix(".svg")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=dpi)
    figure.savefig(svg_path, format="svg", dpi=dpi)
    return png_path, svg_path
