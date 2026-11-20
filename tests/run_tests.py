"""Dependency-free test suite: python tests/run_tests.py"""

from __future__ import annotations

import sys
from unittest import SkipTest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridged.compare import (  # noqa: E402
    bland_altman,
    cohen_kappa,
    cronbach_alpha,
    equipercentile,
    icc21,
)
from bridged.instrument import Instrument  # noqa: E402
from bridged.report import build_report  # noqa: E402
from bridged.simulate import (  # noqa: E402
    InstrumentSpec,
    SimConfig,
    run_simulation,
)


def _map_instruments() -> tuple[Instrument, Instrument]:
    def build(instrument_id: str, prefix: str) -> Instrument:
        return Instrument.from_dict(
            {
                "id": instrument_id,
                "version": "1.0.0",
                "response_scales": {"s": {"levels": [0, 1, 2, 3]}},
                "items": [
                    {"id": f"{prefix}{index}", "response": "s"}
                    for index in range(1, 4)
                ],
                "scoring": {"total": {"method": "sum", "items": "all"}},
            }
        )

    return build("a", "a"), build("b", "b")


def _map_data(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(91)
    first = rng.normal(size=n)
    second = rng.normal(size=n)

    def ordinal(latent: np.ndarray, noise: float) -> np.ndarray:
        observed = latent + rng.normal(scale=noise, size=n)
        return np.digitize(observed, [-0.7, 0.0, 0.7])

    return pd.DataFrame(
        {
            "a1": ordinal(first, 0.35),
            "a2": ordinal(first, 0.40),
            "a3": ordinal(first, 0.45),
            "b1": ordinal(second, 0.35),
            "b2": ordinal(second, 0.40),
            "b3": ordinal(second, 0.45),
        }
    )


def test_construct_map_recovers_item_neighborhoods() -> None:
    from bridged.construct_map import fit_construct_map

    instruments = _map_instruments()
    result = fit_construct_map(instruments, _map_data(), clusters=2, seed=4)
    assert result.metrics["n_items"] == 6
    assert result.metrics["clusters"] == 2
    associations = result.associations
    within = associations.loc["a@1.0.0/a1", "a@1.0.0/a2"]
    between = associations.loc["a@1.0.0/a1", "b@1.0.0/b1"]
    assert within > between + 0.5
    labels = result.coordinates.set_index("item")["cluster"]
    assert labels["a@1.0.0/a1"] == labels["a@1.0.0/a2"]
    assert labels["b@1.0.0/b1"] == labels["b@1.0.0/b2"]
    assert labels["a@1.0.0/a1"] != labels["b@1.0.0/b1"]


def test_construct_map_bootstrap_records_uncertainty() -> None:
    from bridged.construct_map import fit_construct_map

    result = fit_construct_map(
        _map_instruments(), _map_data(), clusters=2, bootstrap=5, seed=7
    )
    assert result.metrics["bootstrap_valid"] == 5
    assert result.coassignment is not None
    assert result.coordinates["dimension_1_sd"].notna().all()
    assert result.coordinates["cluster_stability"].between(0, 1).all()


def test_construct_map_pca_reports_explained_variance() -> None:
    import json

    from bridged.construct_map import fit_construct_map

    result = fit_construct_map(
        _map_instruments(), _map_data(), clusters=2, bootstrap=3, seed=7,
        embedding="pca",
    )
    assert result.metrics["embedding"] == "pca"
    assert 0 < result.metrics["pc1_explained_variance"] < 1
    assert 0 < result.metrics["pc2_explained_variance"] < 1
    assert result.metrics["pc12_explained_variance"] <= 1
    assert result.metrics["bootstrap_valid"] == 3
    assert "stress" not in result.metrics
    json.dumps(result.metrics, allow_nan=False)
    assert np.isfinite(result.coordinates[["dimension_1", "dimension_2"]]).all().all()


def test_construct_map_rejects_unknown_embedding() -> None:
    from bridged.construct_map import fit_construct_map

    try:
        fit_construct_map(_map_instruments(), _map_data(), embedding="umap")
    except ValueError as exc:
        assert "embedding" in str(exc)
    else:
        raise AssertionError("unknown embedding should fail")


def test_construct_map_auto_cluster_does_not_promote_a_singleton() -> None:
    from bridged.construct_map import _cluster

    distance = pd.DataFrame(
        [
            [0.0, 0.1, 0.1, 1.0],
            [0.1, 0.0, 0.1, 1.0],
            [0.1, 0.1, 0.0, 1.0],
            [1.0, 1.0, 1.0, 0.0],
        ]
    )
    _, labels, cluster_count, silhouette = _cluster(distance)
    assert cluster_count == 1
    assert set(labels) == {1}
    assert np.isnan(silhouette)


def test_phq9_scoring() -> None:
    instrument = Instrument.load(ROOT / "instruments" / "phq9.toml")
    data = pd.DataFrame({f"phq{i}": [1] for i in range(1, 10)})
    scores = instrument.score(data)
    assert scores["phq9_total"].iloc[0] == 9
    assert scores["phq9_cognitive_affective"].iloc[0] == 5
    assert scores["phq9_somatic"].iloc[0] == 4


def test_phq9_prorates_one_missing_item() -> None:
    instrument = Instrument.load(ROOT / "instruments" / "phq9.toml")
    row = {f"phq{i}": 1 for i in range(1, 9)}
    row["phq9"] = np.nan
    scores = instrument.score(pd.DataFrame([row]))
    # 8 answered, 1 missing -> 8 * 9 / 8
    assert abs(scores["phq9_total"].iloc[0] - 9.0) < 1e-9


def test_phq9_prorated_total_uses_half_up_rounding() -> None:
    instrument = Instrument.load(ROOT / "instruments" / "phq9.toml")
    row = {f"phq{i}": np.nan for i in range(1, 10)}
    row.update({"phq1": 1, "phq2": 1, "phq3": 1, "phq4": 1, "phq5": 1, "phq6": 1, "phq7": 0})
    scores = instrument.score(pd.DataFrame([row]))
    # 6 * 9 / 7 = 7.714..., and the PHQ-9 rule rounds to a whole score.
    assert scores["phq9_total"].iloc[0] == 8.0


def test_hamd_item_16_and_17_match_standard_order() -> None:
    instrument = Instrument.load(ROOT / "instruments" / "hamd17.toml")
    by_id = {item.id: item for item in instrument.items}
    assert by_id["h16"].text == "Loss of weight"
    assert by_id["h16"].construct == "weight_loss"
    assert by_id["h17"].text == "Loss of insight"
    assert by_id["h17"].construct == "insight"


def test_reverse_keying() -> None:
    instrument = Instrument.load(ROOT / "instruments" / "example_new.toml")
    row = {f"ex{i}": 4 for i in range(1, 13)}
    values = instrument.item_values(pd.DataFrame([row]))
    assert values["ex5"].iloc[0] == 0  # 0-4 scale, reversed
    assert values["ex1"].iloc[0] == 4


def test_validation_rejects_unknown_response_scale() -> None:
    raw = {
        "id": "bad",
        "items": [{"id": "q1", "response": "does_not_exist"}],
        "response_scales": {"ok": {"levels": [0, 1]}},
        "scoring": {},
    }
    try:
        Instrument.from_dict(raw)
    except ValueError as exc:
        assert "unknown response scale" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cronbach_alpha_of_parallel_items_is_one() -> None:
    rng = np.random.default_rng(0)
    base = rng.normal(size=200)
    items = pd.DataFrame({f"i{k}": base for k in range(4)})
    assert abs(cronbach_alpha(items) - 1.0) < 1e-9


def test_icc_of_identical_series_is_one() -> None:
    rng = np.random.default_rng(1)
    series = pd.Series(rng.normal(size=100))
    assert abs(icc21(series, series) - 1.0) < 1e-9


def test_kappa_of_identical_labels_is_one() -> None:
    labels = pd.Series(["a", "b", "c", "a", "b", "c"])
    result = cohen_kappa(labels, labels)
    assert abs(result["kappa"] - 1.0) < 1e-9


def test_equipercentile_is_monotone() -> None:
    rng = np.random.default_rng(2)
    a = pd.Series(rng.integers(0, 20, 300))
    b = pd.Series(np.clip(a + rng.normal(0, 2, 300), 0, 20))
    table = equipercentile(a, b)
    linked = table["linked_b"].to_numpy()
    assert np.all(np.diff(linked) >= -1e-9)


def test_bland_altman_of_identical_series_is_zero() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = bland_altman(series, series)
    assert result["mean_diff"] == 0
    assert result["loa_lower"] == 0
    assert result["loa_upper"] == 0


def test_column_mode_reads_scores_from_export() -> None:
    instrument = Instrument.from_dict(
        {
            "id": "exported",
            "items": [{"id": "total", "kind": "column", "column": "total_score"}],
            "scoring": {"total": {"column": "total_score"}},
        }
    )
    data = pd.DataFrame({"total_score": [1.5, 2.5, 3.5]})
    assert instrument.score(data)["exported_total"].tolist() == [1.5, 2.5, 3.5]


def test_chinese_report_renders() -> None:
    rng = np.random.default_rng(0)
    data = pd.DataFrame(
        {
            **{f"phq{i}": rng.integers(0, 4, 40) for i in range(1, 10)},
            **{f"ex{i}": rng.integers(0, 5, 40) for i in range(1, 13)},
        }
    )
    a = Instrument.load(ROOT / "instruments" / "phq9.toml")
    b = Instrument.load(ROOT / "instruments" / "example_new.toml")
    report = build_report(a, b, data, lang="zh")
    assert "描述统计" in report
    assert "方法学段落" in report


def test_docx_report_writes_tables() -> None:
    try:
        from docx import Document
    except ModuleNotFoundError as exc:
        raise SkipTest("python-docx optional dependency is not installed") from exc

    from bridged.docx_report import build_docx

    rng = np.random.default_rng(1)
    data = pd.DataFrame(
        {
            **{f"phq{i}": rng.integers(0, 4, 60) for i in range(1, 10)},
            **{f"ex{i}": rng.integers(0, 5, 60) for i in range(1, 13)},
        }
    )
    a = Instrument.load(ROOT / "instruments" / "phq9.toml")
    b = Instrument.load(ROOT / "instruments" / "example_new.toml")
    out = _tmpdir("docx") / "report.docx"
    build_docx(a, b, data, n_boot=0, lang="zh", path=out)
    assert out.exists()
    assert out.stat().st_size > 5000
    document = Document(out)
    assert len(document.tables) >= 4


def _sim_config() -> SimConfig:
    return SimConfig(
        n=500,
        seed=7,
        replications=1,
        a=InstrumentSpec("a", 6, [0.7] * 6, 5),
        b=InstrumentSpec("b", 9, [0.65] * 9, 4),
        latent_r=0.5,
    )


def _tmpdir(name: str) -> Path:
    path = ROOT / "tests" / "_tmp" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_simulation_recovers_correlation() -> None:
    config = _sim_config()
    summary = run_simulation(config, _tmpdir("recover"), n=5000, replications=1)
    assert abs(summary["sample_r"] - summary["true_r"]) < 0.08


def test_simulation_writes_recovery_outputs() -> None:
    config = _sim_config()
    out = _tmpdir("recovery")
    summary = run_simulation(config, out, n=300, replications=3)
    assert (out / "data.csv").exists()
    assert (out / "truth.json").exists()
    assert (out / "recovery.csv").exists()
    assert 0.0 <= summary["ci_coverage"] <= 1.0
    assert summary["replications"] == 3


def _minimal_raw(validation: str = "unverified") -> dict:
    return {
        "id": "mini",
        "version": "1.0.0",
        "validation": validation,
        "items": [{"id": "q1", "response": "s"}],
        "response_scales": {"s": {"levels": [0, 1]}},
        "scoring": {"total": {"method": "sum", "items": "all"}},
    }


def test_definition_hash_is_stable() -> None:
    first = Instrument.from_dict(_minimal_raw()).definition_hash()
    second = Instrument.from_dict(_minimal_raw()).definition_hash()
    assert first == second


def test_definition_hash_changes_with_reverse_keying() -> None:
    raw = _minimal_raw()
    first = Instrument.from_dict(raw).definition_hash()
    raw["items"][0]["reverse"] = True
    second = Instrument.from_dict(raw).definition_hash()
    assert first != second


def test_unknown_validation_status_is_rejected() -> None:
    try:
        Instrument.from_dict(_minimal_raw("bogus"))
    except ValueError as exc:
        assert "unknown validation status" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_report_records_definition_hash() -> None:
    rng = np.random.default_rng(3)
    data = pd.DataFrame(
        {
            **{f"phq{i}": rng.integers(0, 4, 60) for i in range(1, 10)},
            **{f"ex{i}": rng.integers(0, 5, 60) for i in range(1, 13)},
        }
    )
    a = Instrument.load(ROOT / "instruments" / "phq9.toml")
    b = Instrument.load(ROOT / "instruments" / "example_new.toml")
    report = build_report(a, b, data, lang="en")
    assert "sha256=" in report
    assert a.definition_hash()[:12] in report
    assert a.validation in report


def test_package_version_matches_pyproject() -> None:
    import tomllib

    from bridged import __version__

    with (ROOT / "pyproject.toml").open("rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]
    assert __version__ == declared


def test_single_item_total_spec_is_not_split_into_characters() -> None:
    raw = {
        "id": "single",
        "version": "1.0.0",
        "items": [{"id": "q1", "response": "s"}],
        "response_scales": {"s": {"levels": [0, 1]}},
        "scoring": {"total": {"method": "sum", "items": "q1"}},
    }
    assert Instrument.from_dict(raw).total_items == ["q1"]


def test_simulation_missingness_reduces_effective_n() -> None:
    config = SimConfig(
        n=100,
        seed=2,
        replications=2,
        a=InstrumentSpec("a", 6, [0.7] * 6, 5, missing_rate=0.3),
        b=InstrumentSpec("b", 9, [0.65] * 9, 4, missing_rate=0.3),
    )
    summary = run_simulation(config, _tmpdir("missing_sim"), n=100, replications=2)
    assert summary["mean_n_eff"] < 100


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    skipped = 0
    for test in tests:
        try:
            test()
        except SkipTest as exc:
            skipped += 1
            print(f"skip {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    executed = len(tests) - skipped
    print(f"\n{executed - failures}/{executed} passed, {skipped} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
