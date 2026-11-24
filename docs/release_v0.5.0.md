# BRIDGE-D v0.5.0

Released: 2026-11-24

Version 0.5.0 adds publication-ready figure export across the BRIDGE-D
measurement-space workflow.

## Changes

- Every generated figure is now written as a 300 dpi PNG and a vector SVG.
- Item maps, instrument footprints, cluster trees, post-fit group validation,
  and cross-sample map comparison use one shared figure-output path.
- Granwald and NSDUH validation figures use the same output settings.
- Tests check the shared 300 dpi setting and the presence of SVG outputs.

This release changes figure output only. It does not change scoring,
association estimates, dimensional coordinates, clustering, permutation
tests, or cross-sample alignment calculations.
