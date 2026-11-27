# BRIDGE-D v0.5.1

Release date: 2026-11-27.

Adds Anchor-Item Neighborhood Analysis as an independent post-fit module.
Existing scoring, map fitting, correlations, clustering, CLI commands and
default map figures retain their implementations.

## API

```python
from bridged.construct_map import collect_item_values, fit_construct_map
from bridged.anchor_analysis import (
    analyze_anchor_items, write_anchor_analysis, plot_anchor_neighborhood,
)

fitted = fit_construct_map(instruments, data, embedding="pca")
values, metadata = collect_item_values(instruments, data)
anchor = metadata.iloc[0]["item"]  # caller chooses stable instrument@version/item ID
result = analyze_anchor_items(
    fitted, values, [anchor], top_k=10, bootstrap=1000,
    permutations=9999, seed=0,
    # groups=table_with_item_group_and_optional_group_set,
    # positive_thresholds={anchor: minimum_scale_value},
)
write_anchor_analysis(result, "anchor_output")
plot_anchor_neighborhood(fitted, result, "anchor_output/highlight")
```

The response table must contain the scored item values used to fit the map.
Participant count and associations are checked against that map. Constant or
entirely missing items and insufficient pair counts raise explicit errors.
The default positivity threshold is zero; callers can supply per-anchor
thresholds for scales with nonzero minimum values. Nonzero rates and positive
rates are exported separately.

## CLI

```text
python -m bridged anchor-analysis --map-dir fitted_map --responses scored.csv --anchor scale@1.0/item --out anchor_output --plot
```

`--map-dir` uses the existing map export format (`item_coordinates.csv`,
`item_associations.csv`, `item_distances.csv`, `analysis_config.json`).
`--responses` contains scored responses with stable item IDs as column names.
Optional arguments: `--groups`, `--positive-thresholds` (JSON object),
`--top-k`, `--bootstrap`, `--permutations`, `--min-pairs`, `--seed`, `--plot`.
This command does not refit the supplied map.

## Outputs and interpretation

Four CSV tables and `anchor_analysis.json` provide distributions, full-space
nearest neighbors, cross-instrument anchor convergence, and post-fit group
proximity. The optional figure is a separate 300 dpi PNG/vector SVG pair.
The main package contains no dataset-specific analysis or anchor selection.
No dependency requirements were added.

Ranking uses full `1-r` distances. Projected two-dimensional Euclidean
distances are reported separately. Participant percentile bootstrap CIs use
finite pair resamples; Top-K stability uses complete anchor-row resamples.
Both valid-resample counts are exported. Zero requested resamples yield
undefined CIs/stability (JSON null), rather than artificial certainty.

Group centroids refer to the supplied 2D coordinates. Group tests exclude all
anchors from groups and label permutation pools, preserve group sizes, and
use the smaller-distance tail with a Monte Carlo plus-one correction.
Multiple label partitions use separate `group_set` values. Unlabeled items
stay outside that partition's pool. P values are unadjusted. Cross-scale
midrank distance percentiles are descriptive, not significance tests.

The independent application and its verified source columns are documented
in `validation/anchor_use_case/README.md`; its Chinese result summary and
separate dataset outputs provide the paper application values.

## Validation

Eight new tests cover single/cross-scale anchors, full-space ranking,
low-occurrence resamples, constant/mismatched inputs, label permutation,
perfectly correlated tied ordinal responses, missing pairs, and CLI/export/plot
round trips. The original test functions were retained. The full suite passes
40/40 executable tests; one pre-existing optional DOCX test is skipped in this
environment because python-docx is absent (baseline: 32/32, same skip).
The 27-condition simulation and R reference checks were not rerun.

The application used 1000 participant resamples and 9999 permutations per
label partition (seed 20261127), with all requested anchor-row resamples valid.
An independent enumeration of the NSDUH mean-distance null distribution gave
exact p values of .575758, .075758, .136364, and .995960 for cognitive/affective,
interpersonal function, non-interpersonal function, and somatic groups. The
exported Monte Carlo estimates were .5767, .0774, .1381, and .9960.

## Local release artifact and file manifest

Built with `python -m pip wheel --no-deps --no-build-isolation . --wheel-dir dist`:
`dist/bridge_d-0.5.1-py3-none-any.whl`. Its version metadata and included
anchor-module source were checked against this workspace. This is a local
release build; no remote registry or GitHub release was created.

Modified by this upgrade:

- `bridged/__init__.py`
- `bridged/cli.py`
- `pyproject.toml`
- `CITATION.cff`
- `tests/run_tests.py` (eight tests and one fixture added; existing tests retained)

Added by this upgrade:

- `bridged/anchor_analysis.py`
- `docs/release_v0.5.1.md`
- `validation/anchor_use_case/run_suicide_demo.py`
- `validation/anchor_use_case/README.md`
- `validation/anchor_use_case/RESULTS_ANCHOR_DEMO.zh-CN.md`
- `validation/anchor_use_case/outputs/Granwald/` and `outputs/NSDUH/`, each with
  `anchor_analysis.json`, four `anchor_*.csv` tables, `anchor_map.png`,
  `anchor_map.svg`, `item_coordinates.csv`, `item_associations.csv`,
  `item_distances.csv`, `analysis_config.json`, `content_groups.csv`, and
  `provenance.json`.

Pre-existing uncommitted changes in comparison, DOCX, translations, the PHQ-9
definition, and validation materials were retained. They are not changes made
by this upgrade.
