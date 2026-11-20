# BRIDGE-D

[English](README.md) | [简体中文](README.zh-CN.md)

**Bridging Instruments for Depression — instrument-as-data scoring, comparison,
and empirical item mapping for co-administered scales.**

A new scale should not require new code. Write a TOML file describing items,
response options, scoring rules and cutoffs; `bridged` scores it and
compares it against any other instrument administered to the same people, and
can map item-response similarities across instruments.

## Why

Scale development and cross-instrument comparison are routine in clinical and
health research, but the workflow is usually rebuilt from scratch: scoring in
Excel or R, agreement in another script, crosswalks in a third. The building
blocks exist (`psych`, `lavaan`, `equate`, `mirt`, `irr`), yet there is no
small, open, end-to-end workbench that treats an instrument as data.

`bridged` is that workbench. It does not replace the statistics packages;
it standardises the part everyone rewrites: the instrument definition, the
scoring rules, the missing-data policy, and the comparison report.

## Positioning

BRIDGE-D aims to become a shared, versioned definition layer for
psychological instruments — a way for a scale to be described, validated,
executed, compared and reused by machines and by different research teams.

That is a direction, not a claim about the current release. The path has
three stages:

| Stage | What it means | Status |
|---|---|---|
| **Now** | A local instrument-as-data toolkit: define a scale in TOML, score it, compare it with a co-administered instrument, and derive exploratory item maps. | Available |
| **Next** | Stable identifiers (`id@version`), content hashes, validation status, and a registry that can verify definitions across projects. | Planned |
| **Long term** | A shared definition layer that different researchers and studies can cite, check and reuse. | Direction |

The point is not saving a few minutes on one analysis. It is that two
researchers who both say "PHQ-9" can mean the same executable definition,
with the same scoring rules, the same missing-data policy and a checkable
provenance.

BRIDGE-D is not a replacement for `psych`, `lavaan` or `equate`, not a
clinical diagnostic device, and not a registry yet.

## Install

Requires Python 3.11+ (uses stdlib `tomllib`), numpy and pandas. Construct maps
use the optional `map` dependencies.

```bash
pip install -e .
bridged --help

# Include PCA/MDS construct maps and figures
pip install -e ".[map]"
```

If `bridged` is not on your PATH (common on Windows), use the module entry
point instead:

```bash
python -m bridged --help
```

You can also skip installation entirely and run from the repository root:

```bash
pip install numpy pandas
python -m bridged --help
```

## Quickstart

```bash
python examples/make_demo_data.py

bridged validate instruments/phq9.toml

bridged score \
  --instrument instruments/phq9.toml \
  --data examples/demo_cohort.csv \
  --out scores.csv

bridged compare \
  --a instruments/phq9.toml \
  --b instruments/example_new.toml \
  --data examples/demo_cohort.csv \
  --out report.md \
  --bootstrap 500

# Chinese report (English is the default)
bridged compare ... --lang zh

# Publication-style Word report with three-line tables
pip install -e ".[docx]"
bridged compare ... --lang zh --format docx --out report.docx
```

The report contains descriptives, internal consistency, association,
ICC(2,1) and Bland-Altman agreement, subscale correlations, classification
agreement (Cohen's kappa), an equipercentile crosswalk with bootstrap
intervals, and a draft methods paragraph.

## Adding an instrument

### Item-based

Create `instruments/my_scale.toml`:

```toml
id = "my_scale"
name = "My New Instrument"
version = "0.1.0"
rater = "self"
recall = "past 2 weeks"
license = "CC-BY-4.0"

[response_scales.five_point]
levels = [0, 1, 2, 3, 4]
labels = ["Never", "Rarely", "Sometimes", "Often", "Always"]

[[items]]
id = "q1"
construct = "depressed_mood"
response = "five_point"

[[items]]
id = "q2"
construct = "anhedonia"
response = "five_point"
reverse = true

[scoring]
missing_min_answered = 1
missing_strategy = "prorate"

[scoring.total]
method = "sum"
items = "all"

[scoring.subscales.cognitive]
items = ["q1", "q2"]

[[cutoffs]]
label = "moderate"
min = 5
```

Every definition should also declare its provenance and validation status:

```toml
id = "my_scale"
version = "1.0.0"
source = "Author et al. 2024"
validation = "unverified"   # unverified | numerically-checked | source-verified
```

`bridged validate` prints the definition hash (`sha256`), and every report
records `id@version` plus the first 12 hex characters. Changing an item,
response scale, scoring rule, cutoff or missing-data rule changes the hash;
editing comments or whitespace does not. `source` and `validation` describe
provenance and are not part of the hash.

### Column-based

If your export already contains scores, point at the column instead of summing
items. This is how instruments with bespoke scoring engines (games, tasks,
vendor exports) plug in without reimplementing anything:

```toml
[scoring.total]
method = "column"
column = "total_score"

[scoring.subscales.mood]
column = "mood_score"

[[items]]
id = "total_score"
kind = "column"
column = "total_score"
```

## Templates and item sheets

```bash
# downloadable fillable template
bridged template --out instruments/my_scale.toml

# build an instrument from a CSV/XLSX item sheet
# columns: id, text, construct, response, levels, reverse, subscale
bridged import-items \
  --items items.xlsx \
  --out instruments/my_scale.toml \
  --id my_scale --name "My New Instrument"
```

Any instrument file can live anywhere; pass its path to `--instrument` / `--a`
/ `--b`. There is no central registry to update.

## Private instruments

Instruments that must not be released (unpublished scales, patent-pending
methods, licensed content) belong in `private/`, which is git-ignored:

```
private/
  my_scale.toml
  my_scale_cohort.csv
  my_scale_adapter.py
```

`private/` is excluded from the published package. Run the guard before any
release:

```bash
python scripts/check_public.py
```

It reads forbidden terms from `private/forbidden.txt` (one per line) and fails
if any appear outside `private/`.

## Empirical construct map

The optional construct-map module places co-administered items in a continuous
two-dimensional space based on similarity in their response patterns. It uses
pairwise Spearman correlations, non-metric multidimensional scaling, and
average-linkage hierarchical clustering. Bootstrap resampling estimates
coordinate and cluster stability.

```bash
pip install -e ".[map]"

bridged construct-map \
  --instrument instruments/phq9.toml \
  --instrument instruments/example_new.toml \
  --data examples/demo_cohort.csv \
  --out map_output \
  --embedding pca \
  --bootstrap 200
```

`--embedding pca` calibrates item coordinates from the first two loadings of
the Spearman item-correlation matrix and reports explained variance. The
default `--embedding mds` retains non-metric MDS. Hierarchical clustering uses
the full correlation distance under either embedding, so the two-dimensional
projection does not determine cluster membership.

The output includes association and distance matrices, item coordinates,
cluster assignments, bootstrap co-assignment probabilities, a map, a
dendrogram, and a method report. Coordinates reflect empirical response
similarity in the analyzed sample. The two axes have no automatic
psychological labels and are not estimates of a universal symptom space.

Reproducible validation examples are in
[`validation/construct_map_granwald`](validation/construct_map_granwald) and
[`validation/construct_map_nsduh`](validation/construct_map_nsduh). Pass only
the instruments needed for a local map when a global two-dimensional map
compresses a narrower content contrast.

## Simulation

`simulate` generates data with a known truth: you choose the correlation
between the two instruments' latents, the item loadings, the response format
and the sample size; the tool writes the dataset, the population values, and
(optionally) a recovery study across replications.

```bash
bridged simulate --config examples/sim.toml --out sim/

# recovery / precision study at a given n
bridged simulate \
  --config examples/sim.toml \
  --out sim_n200 --n 200 --replications 300
```

Outputs:

- `data.csv`: one synthetic cohort with both instruments' items
- `truth.json`: population correlation, ICC and crosswalk
- `recovery.csv` + `summary.json` (when `replications > 1`): bias, CI coverage,
  mean CI width, crosswalk RMSE across replications

Config:

```toml
n = 200
seed = 42
replications = 300

[model]
latent_r = 0.5        # correlation between the two instruments' latents

[instrument_a]
id = "a"
items = 6
levels = 5
loadings = [0.75, 0.55, 0.80, 0.65, 0.70, 0.45]

[instrument_b]
id = "b"
items = 9
levels = 4
loading = 0.65
```

`latent_r` is the correlation between the underlying traits; the observed
total-score correlation is lower because of measurement error. That gap is
the point: it lets you see how much attenuation your design can tolerate.

Synthetic data is for software validation and sample-size planning. It is not
evidence about a real instrument.

## Release and archiving

Every version bump gets an immutable snapshot before anything else:

1. Bump `version` in `pyproject.toml`.
2. Run `python tests/run_tests.py` and `python scripts/check_public.py`.
3. Commit the bump.
4. Run `python scripts/archive_version.py`.

The script exports `git archive HEAD` to `releases/v<version>-<date>`, writes
a `RELEASE.json` with the commit hash, and refuses to overwrite an existing
archive. Only committed files are exported, so `private/` and generated
artifacts never enter a release.

To archive somewhere else (for example an external drive), pass `--base` or
put the path in a git-ignored `.archive-dir` file:

```bash
python scripts/archive_version.py --base "D:/archives/BRIDGE-D"
```

A post-commit hook does this automatically when `pyproject.toml`'s version
changes. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

## Validation

Level 1 checks the core statistics against R (`psych`, `irr`) on a fixed
dataset:

```bash
python validation/level1/make_fixture.py
Rscript validation/level1/reference.R
python validation/level1/run_level1.py
```

See [`validation/level1/README.md`](validation/level1/README.md) for the
tolerances and the latest results. Simulation-based checks (Level 2) live in
`bridged simulate`. The statistical review packet for the paper is in
[`docs/statistical_review_packet.md`](docs/statistical_review_packet.md). The
end-to-end application pipeline (NHANES plus a synthetic companion) is in
[`validation/application/`](validation/application/README.md).

## Tests

```bash
python tests/run_tests.py
```

## Scope and limits

- Linking is equipercentile only. IRT co-calibration is planned, not built.
- Bland-Altman on raw scores assumes a shared metric; with different ranges it
  is descriptive, not an agreement claim.
- Cutoffs are whatever the instrument file declares. Verify them against the
  source publication before publishing results.
- The demo instrument `example_new.toml` is synthetic and must be replaced.
- Construct-map coordinates depend on the analyzed sample, missingness, and
  response distributions. Clusters and distances are exploratory results, not
  clinical subtypes or validated latent-trait coordinates.

## License

MIT for the code. Instrument definitions carry their own licenses; the
bundled PHQ-9 and HAMD-17 files contain only item labels, not copyrighted
anchor descriptions.
