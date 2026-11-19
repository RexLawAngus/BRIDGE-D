# BRIDGE-D

**Bridging Instruments for Depression — instrument-as-data scoring and comparison for co-administered scales.**

A new scale should not require new code. Write a TOML file describing items,
response options, scoring rules and cutoffs; `bridged` scores it and
compares it against any other instrument administered to the same people.

## Why

Scale development and cross-instrument comparison are routine in clinical and
health research, but the workflow is usually rebuilt from scratch: scoring in
Excel or R, agreement in another script, crosswalks in a third. The building
blocks exist (`psych`, `lavaan`, `equate`, `mirt`, `irr`), yet there is no
small, open, end-to-end workbench that treats an instrument as data.

`bridged` is that workbench. It does not replace the statistics packages;
it standardises the part everyone rewrites: the instrument definition, the
scoring rules, the missing-data policy, and the comparison report.

## Install

```bash
pip install -e .
```

Requires Python 3.11+ (uses stdlib `tomllib`), numpy and pandas.

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

The script exports `git archive HEAD` to
`F:\科研\5.抑郁量表基础设施\库\BRIDGE-D\v<version>-<date>`, writes a
`RELEASE.json` with the commit hash, and refuses to overwrite an existing
archive. Only committed files are exported, so `private/` and generated
artifacts never enter a release.

A post-commit hook does this automatically when `pyproject.toml`'s version
changes. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

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

## License

MIT for the code. Instrument definitions carry their own licenses; the
bundled PHQ-9 and HAMD-17 files contain only item labels, not copyrighted
anchor descriptions.
