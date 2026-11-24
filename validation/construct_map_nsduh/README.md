# NSDUH PCA content-separation validation

Data source: [SAMHSA NSDUH 2021-2024 public-use files](https://www.samhsa.gov/data/data-we-collect/nsduh-national-survey-drug-use-and-health/datafiles/2021-2024).

This analysis checks whether an unsupervised PCA item-loading map recovers two
content contrasts that were specified before fitting the model:

- cognitive-affective versus somatic depression indicators;
- non-interpersonal role function versus interpersonal role function.

The input sample contains adults with past-year major depressive episode
(`AMDEYR=1`) who have complete data on eight derived MDE symptom indicators and
four original 0-10 Sheehan Disability Scale role-domain responses.

## Run

Pass the extracted combined NSDUH tab-delimited file explicitly:

```powershell
python run_pca.py `
  --raw-data "path\to\NSDUH_2021_2024_Tab.txt" `
  --prepared-data "path\to\analysis\nsduh_adult_mde_construct_map.csv"
```

The first run extracts a compact analysis table from the 1.6 GB NSDUH TSV. It
writes the prepared table and an auditable selection summary to the dataset's
`analysis` directory. Later runs reuse that table.

Outputs are written to `output_pca`. The three-panel
`hypothesis_validation` visual is written as a 300 dpi PNG and a vector SVG.
`validation_summary.json` contains exact label-permutation checks, split-year
loading reproducibility, PCA variance, clustering diagnostics, and sample
counts.

See `RESULTS.md` for the compact English result summary and
`RESULTS.zh-CN.md` for the Chinese summary.

## Interpretation boundary

PCA receives no content labels. The script applies the labels after fitting and
tests the separation of their loading centroids. The four-domain function test
has only six possible two-versus-two label assignments, so its exact permutation
p-value is coarse. Treat its distance and split-year stability as descriptive
evidence.

The current construct-map implementation does not use `ANALWT2_C4`, `VESTR_C`,
or `VEREP`. These results describe the complete-case analytic sample and do not
estimate a nationally representative population structure.
