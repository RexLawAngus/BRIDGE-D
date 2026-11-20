# BRIDGE-D v0.3.1 release notes

Release date: 2026-11-21

## Fixed

- Construct-map fitting now copies correlation and distance arrays before
  in-place numerical operations. This restores compatibility with pandas 3,
  which exposes the underlying arrays as read-only.
- Non-metric MDS now supports both the established and revised scikit-learn
  parameter interfaces.
- Added a regression test that supplies a read-only correlation matrix.

## Maintenance

- Updated the GitHub Actions runtime actions to their Node 24 releases.
- Recorded the intended role of NSDUH and possible future clinical data in the
  first Behavioral Research Methods paper.

## Scope

This patch does not change the v0.3.0 construct-map method or the reported
Granwald and NSDUH validation results.
