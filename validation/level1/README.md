# Level 1: numerical agreement with R

Checks that BRIDGE-D's core statistics match established R implementations on
one fixed dataset.

| Metric | BRIDGE-D | R reference |
|---|---|---|
| Cronbach's alpha | `cronbach_alpha` | `psych::alpha` |
| ICC(2,1) | `icc21` | `irr::icc(model="twoway", type="agreement", unit="single")` |
| Cohen's kappa | `cohen_kappa` | `irr::kappa2` |
| Equipercentile linking | `equipercentile` | `equate::equate(type="equipercentile")` |

## Run

From the repository root:

```bash
python validation/level1/make_fixture.py
Rscript validation/level1/reference.R
python validation/level1/run_level1.py
```

`reference.R` needs `psych`, `irr`, `equate` and `jsonlite`. The script adds
`../.rlib` to the library path, so a workspace-local install works without
touching the system R library:

```bash
Rscript -e "install.packages(c('psych','irr','equate'), lib='.rlib', repos='https://cloud.r-project.org')"
```

## Result

Last run (R 4.3.3, psych 2.6.9, irr 0.85, equate 2.0.9):

```
metric             python            R     abs diff  status
alpha_phq      0.84752790   0.84752790     4.26e-14  ok
alpha_ex       0.72502617   0.72502617     3.61e-14  ok
icc21          0.30195482   0.30195482     8.77e-15  ok
kappa          0.00662252   0.00662252     3.85e-16  ok

link_max       0.98333333     1.00e+00 ok
link_mean      0.27046239     5.00e-01 ok
percentile_max   0.00000000     1.00e-10 ok
```

Tolerances: alpha `1e-6`, ICC `1e-4`, kappa `1e-6`; linking max difference
`1.0` point, mean `0.5` point, percentile ranks `1e-10`.

The kappa value is close to zero because the two instruments use different
cutoff systems; it is a numerical check, not a substantive finding.

## Linking: what matches and what does not

Percentile ranks match exactly. Linked scores differ slightly because the two
implementations interpolate differently:

- BRIDGE-D maps each score to its mid-percentile and interpolates the target
  score at that percentile (`numpy.quantile`, linear).
- `equate` uses half-interval linear interpolation on the cumulative
  frequency table (Kolen & Brennan convention).

The largest difference in this fixture is `0.98` points on a `0-48` scale,
mean `0.27`. The check is therefore a tolerance check, not bitwise agreement.
If exact agreement is needed, the `equate` interpolation can be implemented as
an option later.

## Limits

- `fixture.csv` is synthetic (120 complete cases) and includes reverse-keyed
  items.
- Missing-data edge cases and boundary scores are not yet covered.
- This checks numbers, not interpretation.
