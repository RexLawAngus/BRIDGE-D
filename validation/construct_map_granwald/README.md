# Granwald PCA construct-map validation

This validation uses the public Granwald dataset containing co-administered
PHQ-9, CES-D, and Zung SDS item responses.

Run from the development project root:

```powershell
python validation\construct_map_granwald\run_pca.py `
  --data "path\to\extracted_data_networkPriors.csv"
```

The script excludes records with more than two failed attention checks, fits a
Spearman-correlation PCA item map to the full sample, repeats the fit in the two
original samples, and writes bootstrap uncertainty and split-sample
reproducibility results to `output_pca/`.

All generated figures are written as both 300 dpi PNG files and vector SVG
files.

Under v0.4.1 the same run also writes projected instrument footprints,
separate post-fit somatic-versus-non-somatic and
interpersonal-versus-non-interpersonal label tests, and a Procrustes-aligned
comparison of the two original samples. The paper-facing interpretation is in
[`../paper_v0.4.1/RESULTS.zh-CN.md`](../paper_v0.4.1/RESULTS.zh-CN.md).

PCA component signs are arbitrary, so the split-sample coordinate table aligns
each axis sign to the full-sample solution. Reported split loading correlations
use the absolute correlation. Automatic clustering rejects solutions that only
create singleton clusters; such items remain visible as coordinate outliers.

PCA supplies the two displayed coordinates. Average-linkage clustering still
uses the complete Spearman correlation distance, so the two-dimensional
projection does not determine cluster membership.

## Residual PCA experiment

`run_residual_pca.py` removes the general first component and the later
component most strongly associated with reverse keying. It then displays the
next two components and tests whether pre-registered somatic and interpersonal
content tags occupy distinct regions. The tags color the finished map but do
not determine its coordinates.

```powershell
python validation\construct_map_granwald\run_residual_pca.py `
  --data "path\to\extracted_data_networkPriors.csv"
```

This is an exploratory deflation diagnostic, not a fitted bifactor or ESEM
model. The semantic tags contain no item wording and remain local validation
metadata rather than instrument scoring definitions.
