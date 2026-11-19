# Level 2: recovery and interval coverage

Checks how the comparison statistics behave when the truth is known, across
sample sizes, latent correlations and missingness mechanisms.

## Design

- **Calibration.** Item thresholds come from the public NHANES 2017-2018
  PHQ-9 data (`DPQ_J.XPT`, 5,533 respondents). Only aggregate parameters are
  stored here; the raw file stays in the public dataset folder.
- **Instrument A.** 9 items, NHANES thresholds, loadings 0.70, prorate with at
  least 7 answered.
- **Instrument B.** 12 items, same threshold family, loadings 0.70, prorate
  with at least 10 answered.
- **Grid.** `n ∈ {42, 100, 200}` × `latent_r ∈ {0.2, 0.4, 0.6}` ×
  `missing ∈ {none, mcar20, mnar20}`, 200 replications each.
- **Truth.** For every `(latent_r, missing)` condition, a 100,000-subject
  sample is generated *under the same mechanism*. This matters: missingness
  changes the large-sample limit, so coverage is evaluated against the
  mechanism-specific truth, not against the no-missing correlation.

## Metrics

- `bias_r`: mean estimate minus the no-missing truth (total bias).
- `bias_mech`: mean estimate minus the mechanism-specific truth (estimation
  bias after the missingness-induced shift).
- `rmse_r`: root mean squared error against the no-missing truth.
- `coverage_r`: share of 95% Fisher intervals containing the mechanism-specific
  truth.
- `mean_ci_width`: average interval width.
- `crosswalk_rmse`: error of the estimated equipercentile link over the
  5th–95th percentile range of A.

## Selected results

| n | latent_r | missing | mean_r | true_r | true_r_mech | bias_mech | coverage | CI width | link RMSE |
|---|---|---|---|---|---|---|---|---|---|
| 42 | 0.6 | none | 0.420 | 0.453 | 0.453 | -0.032 | 0.835 | 0.491 | 3.43 |
| 42 | 0.6 | mcar20 | 0.374 | 0.453 | 0.445 | -0.071 | 0.875 | 0.801 | 4.28 |
| 42 | 0.6 | mnar20 | 0.389 | 0.453 | 0.422 | -0.033 | 0.855 | 0.510 | 3.31 |
| 42 | 0.4 | none | 0.276 | 0.281 | 0.281 | -0.005 | 0.895 | 0.547 | 3.43 |
| 200 | 0.6 | none | 0.441 | 0.453 | 0.453 | -0.012 | 0.855 | 0.223 | 2.25 |
| 200 | 0.4 | mnar20 | 0.270 | 0.281 | 0.269 | +0.001 | 0.910 | 0.258 | 2.31 |

The full table is in `summary.csv`; per-replication results are in
`results.csv` (regenerated, not committed).

## What the numbers say

1. **Bias is small.** Against the mechanism-specific truth, most cells are
   within `±0.03`; the largest is `-0.071` under MCAR at `n = 42`,
   `latent_r = 0.6`. The estimator converges to the right value for the
   condition being simulated.
2. **Coverage is below nominal.** At `n = 42` and `latent_r = 0.6`, the 95%
   interval contains the truth only 83–88% of the time. At `n = 200` it is
   still 85–92%. Fisher intervals on ordinal totals are too optimistic,
   especially for high correlations; this is a limitation to report, and a
   candidate for a bootstrap or BCa interval later.
3. **CI width shrinks as expected.** From about `0.55` at `n = 42` to `0.22`
   at `n = 200` for a true correlation near `0.45`.
4. **Crosswalk error is large at small n.** The equipercentile link is off by
   2–4 points on a 0–36 scale even in the central range; `n = 200` is the
   minimum at which the error approaches 2 points. Tails are worse and are not
   summarised here.
5. **MCAR 20% is a stress test, not a realistic scenario.** Independent 20%
   missingness per item plus the minimum-answered rules keeps only about 40%
   of subjects. In NHANES, the any-missing rate is 0.4%; realistic
   missingness needs a lower-rate condition.

## Reproduce

```bash
python validation/level2/calibrate_from_nhanes.py   # needs DPQ_J.XPT
python validation/level2/run_grid.py
```

## Limits

- One-factor generative model; no method factor, no MAR condition yet.
- NHANES calibration ignores survey weights and uses unweighted item
  distributions.
- Instrument B is hypothetical; only its thresholds are calibrated.
- Equipercentile linking uses BRIDGE-D's quantile interpolation, not the
  `equate` half-interval convention (see Level 1).
