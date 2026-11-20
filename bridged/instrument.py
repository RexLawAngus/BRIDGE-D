"""Instrument definitions and scoring.

An instrument is data, not code: a TOML file declares items, response
scales, scoring rules and cutoffs. Adding a new scale never requires
touching Python.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

__all__ = ["ResponseScale", "Item", "Instrument"]


@dataclass
class ResponseScale:
    name: str
    levels: list[float]
    labels: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.levels) < 2:
            raise ValueError(f"response scale {self.name!r} needs >= 2 levels")
        if sorted(self.levels) != self.levels:
            raise ValueError(f"response scale {self.name!r}: levels must be ascending")
        if self.labels and len(self.labels) != len(self.levels):
            raise ValueError(
                f"response scale {self.name!r}: labels/levels length mismatch"
            )


@dataclass
class Item:
    id: str
    response: str | None = None
    construct: str | None = None
    reverse: bool = False
    text: str | None = None
    column: str | None = None
    kind: str = "item"


class Instrument:
    """A declarative scale definition plus its scoring rules."""

    def __init__(
        self,
        id: str,
        name: str,
        version: str,
        items: list[Item],
        response_scales: dict[str, ResponseScale],
        total_items: list[str],
        subscales: dict[str, list[str]],
        cutoffs: list[dict[str, Any]],
        missing_min_answered: int,
        missing_strategy: str,
        meta: dict[str, Any] | None = None,
        total_column: str | None = None,
        subscale_columns: dict[str, str] | None = None,
        source: str | None = None,
        validation: str = "unverified",
    ) -> None:
        self.id = id
        self.name = name
        self.version = version
        self.items = items
        self.response_scales = response_scales
        self.total_items = total_items
        self.subscales = subscales
        self.cutoffs = sorted(cutoffs, key=lambda c: float(c["min"]))
        self.missing_min_answered = missing_min_answered
        self.missing_strategy = missing_strategy
        self.meta = meta or {}
        self.total_column = total_column
        self.subscale_columns = subscale_columns or {}
        self.source = source
        self.validation = validation
        self._by_id = {item.id: item for item in items}

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: str | Path) -> "Instrument":
        path = Path(path)
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        return cls.from_dict(raw, source=str(path))

    @classmethod
    def from_dict(cls, raw: dict[str, Any], source: str = "<dict>") -> "Instrument":
        try:
            response_scales = {
                name: ResponseScale(
                    name=name,
                    levels=[float(x) for x in spec["levels"]],
                    labels=list(spec.get("labels", [])),
                )
                for name, spec in raw.get("response_scales", {}).items()
            }
            items = [
                Item(
                    id=str(item["id"]),
                    response=item.get("response"),
                    construct=item.get("construct"),
                    reverse=bool(item.get("reverse", False)),
                    text=item.get("text"),
                    column=item.get("column"),
                    kind=str(item.get("kind", "column" if item.get("column") else "item")),
                )
                for item in raw.get("items", [])
            ]
            scoring = raw.get("scoring", {})
            total_spec = scoring.get("total", {"method": "sum", "items": "all"})
            total_column = total_spec.get("column")
            all_ids = [item.id for item in items]
            items_spec = total_spec.get("items", "all")
            if items_spec == "all":
                total_items = all_ids
            elif isinstance(items_spec, str):
                total_items = [items_spec]
            else:
                total_items = list(items_spec)
            subscales: dict[str, list[str]] = {}
            subscale_columns: dict[str, str] = {}
            for name, spec in scoring.get("subscales", {}).items():
                if "column" in spec:
                    subscale_columns[name] = str(spec["column"])
                    subscales[name] = []
                else:
                    subscales[name] = list(spec.get("items", []))
            instrument = cls(
                id=str(raw["id"]),
                name=str(raw.get("name", raw["id"])),
                version=str(raw.get("version", "0.0.0")),
                items=items,
                response_scales=response_scales,
                total_items=total_items,
                subscales=subscales,
                cutoffs=list(raw.get("cutoffs", [])),
                missing_min_answered=int(
                    scoring.get("missing_min_answered", len(all_ids))
                ),
                missing_strategy=str(scoring.get("missing_strategy", "prorate")),
                meta={
                    k: v
                    for k, v in raw.items()
                    if k
                    not in {
                        "id",
                        "name",
                        "version",
                        "items",
                        "response_scales",
                        "scoring",
                        "cutoffs",
                    }
                },
                total_column=total_column,
                subscale_columns=subscale_columns,
                source=raw.get("source"),
                validation=str(raw.get("validation", "unverified")),
            )
        except KeyError as exc:
            raise ValueError(f"{source}: missing required field {exc}") from exc
        instrument._source = source
        instrument.validate()
        return instrument

    # -------------------------------------------------------------- validate
    def validate(self) -> "Instrument":
        source = getattr(self, "_source", self.id)
        if not self.items and not self.total_column:
            raise ValueError(f"{source}: no items and no total column")
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"{source}: duplicate item ids {dupes}")
        for item in self.items:
            if item.kind == "column":
                if not item.column:
                    raise ValueError(f"{source}: column item {item.id!r} has no column")
                continue
            if item.response not in self.response_scales:
                raise ValueError(
                    f"{source}: item {item.id!r} uses unknown response scale "
                    f"{item.response!r}"
                )
        for group, members in {"total": self.total_items, **self.subscales}.items():
            unknown = [m for m in members if m not in self._by_id]
            if unknown:
                raise ValueError(f"{source}: {group} references unknown items {unknown}")
        if self.missing_strategy not in {"prorate", "zero", "listwise"}:
            raise ValueError(
                f"{source}: unknown missing_strategy {self.missing_strategy!r}"
            )
        if self.missing_min_answered < 1:
            raise ValueError(f"{source}: missing_min_answered must be >= 1")
        if self.validation not in {
            "unverified",
            "numerically-checked",
            "source-verified",
        }:
            raise ValueError(
                f"{source}: unknown validation status {self.validation!r}; "
                "use unverified, numerically-checked or source-verified"
            )
        return self

    def _canonical_definition(self) -> dict[str, Any]:
        """Scoring-relevant content, excluding provenance fields."""
        return {
            "id": self.id,
            "version": self.version,
            "items": [
                {
                    "id": item.id,
                    "response": item.response,
                    "construct": item.construct,
                    "reverse": item.reverse,
                    "text": item.text,
                    "column": item.column,
                    "kind": item.kind,
                }
                for item in self.items
            ],
            "response_scales": {
                name: {"levels": scale.levels, "labels": scale.labels}
                for name, scale in sorted(self.response_scales.items())
            },
            "total_items": self.total_items,
            "total_column": self.total_column,
            "subscales": dict(sorted(self.subscales.items())),
            "subscale_columns": dict(sorted(self.subscale_columns.items())),
            "cutoffs": self.cutoffs,
            "missing_min_answered": self.missing_min_answered,
            "missing_strategy": self.missing_strategy,
        }

    def definition_hash(self) -> str:
        """Stable SHA-256 of the scoring definition (not the file bytes)."""
        payload = json.dumps(
            self._canonical_definition(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def check_data(self, df: pd.DataFrame) -> None:
        missing: list[str] = []
        for item in self.items:
            name = item.column if item.kind == "column" else item.id
            if name and name not in df.columns:
                missing.append(name)
        for name in [self.total_column, *self.subscale_columns.values()]:
            if name and name not in df.columns:
                missing.append(name)
        if missing:
            raise ValueError(f"{self.id}: data is missing columns {sorted(set(missing))}")

    # ----------------------------------------------------------------- score
    def item_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a frame of scored item values with reverse-keying applied."""
        self.check_data(df)
        out: dict[str, pd.Series] = {}
        for item in self.items:
            if item.kind == "column":
                out[item.id] = pd.to_numeric(df[item.column], errors="coerce")
                continue
            scale = self.response_scales[item.response]  # type: ignore[index]
            values = pd.to_numeric(df[item.id], errors="coerce")
            invalid = values.notna() & ~values.isin(scale.levels)
            if invalid.any():
                bad = sorted(values[invalid].unique().tolist())
                raise ValueError(
                    f"{self.id}.{item.id}: values {bad} not in response scale "
                    f"{scale.name!r}"
                )
            if item.reverse:
                lo, hi = min(scale.levels), max(scale.levels)
                values = lo + hi - values
            out[item.id] = values
        return pd.DataFrame(out, index=df.index)

    def _aggregate(self, values: pd.DataFrame, members: list[str]) -> pd.Series:
        subset = values[members]
        answered = subset.notna().sum(axis=1)
        total = subset.sum(axis=1, skipna=True)
        if self.missing_strategy == "prorate":
            scored = total * len(members) / answered.replace(0, pd.NA)
        elif self.missing_strategy == "zero":
            scored = total
        else:  # listwise
            scored = total.where(answered == len(members))
        # A subscale cannot require more answered items than it contains.
        threshold = min(self.missing_min_answered, len(members))
        scored = scored.mask(answered < threshold)
        return scored.astype(float).rename(f"{self.id}_total")

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score a data frame; returns one column per total/subscale."""
        values = self.item_values(df)
        result = pd.DataFrame(index=df.index)
        if self.total_column:
            result[f"{self.id}_total"] = pd.to_numeric(
                df[self.total_column], errors="coerce"
            )
        else:
            result[f"{self.id}_total"] = self._aggregate(values, self.total_items)
        for name, members in self.subscales.items():
            key = f"{self.id}_{name}"
            if name in self.subscale_columns:
                result[key] = pd.to_numeric(
                    df[self.subscale_columns[name]], errors="coerce"
                )
            else:
                result[key] = self._aggregate(values, members)
        return result

    def classify(self, score: pd.Series) -> pd.Series:
        """Map a total score to the highest cutoff whose min is satisfied."""
        labels = pd.Series([None] * len(score), index=score.index, dtype=object)
        for cutoff in self.cutoffs:
            labels[score >= float(cutoff["min"])] = cutoff["label"]
        return labels

    # ------------------------------------------------------------------ info
    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "items": len(self.items),
            "subscales": list(self.subscales),
            "cutoffs": [c["label"] for c in self.cutoffs],
            "missing_strategy": self.missing_strategy,
            "missing_min_answered": self.missing_min_answered,
            "total_column": self.total_column,
            "subscale_columns": self.subscale_columns,
            "source": self.source,
            "validation": self.validation,
            "sha256": self.definition_hash(),
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Instrument({self.id!r}, items={len(self.items)})"
