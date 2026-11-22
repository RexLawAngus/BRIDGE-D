# BRIDGE-D v0.4.0

Released: 2026-11-22

Version 0.4.0 turns the exploratory item map into a reproducible measurement-space workflow. It does not add patient subtyping or clinical diagnosis.

## Added

- `item-map`: the primary name for empirical item mapping; `construct-map` remains a compatible alias.
- Projected instrument footprints: centroids, within-instrument radii, convex-hull area, and pairwise instrument distances.
- `map-validate`: post-fit comparison of pre-specified item groups. Labels never enter map estimation.
- `map-compare`: cross-sample Procrustes alignment with coordinate RMSE, aligned-axis correlations, normalized residual, and pairwise-distance correlation.
- Figures and machine-readable tables for the new analyses.
- Granwald and NSDUH validation scripts now call the public v0.4.0 analysis functions.

## Interpretation boundary

The map is sample-dependent. Footprints describe the fitted two-dimensional projection, not universal construct boundaries. Permutation tests evaluate whether pre-specified labels are unusually separated on that projection; they do not make the exploratory coordinates a confirmatory measurement model. Cross-sample alignment measures reproducibility after resolving arbitrary translation, scale, rotation, and reflection.

Patient clustering, LCA, factor-mixture models, LLM conversation mapping, and clinical decision support remain outside this release.
