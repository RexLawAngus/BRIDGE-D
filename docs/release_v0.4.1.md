# BRIDGE-D v0.4.1

Released: 2026-11-22

Version 0.4.1 corrects the Granwald content-label validation introduced in v0.4.0.

The Granwald tag table contains two independent binary annotations:

- somatic versus non-somatic;
- interpersonal versus non-interpersonal.

The v0.4.0 aggregation script mistakenly compared somatic-tagged items directly with interpersonal-tagged items. That comparison merged two conceptual dimensions and excluded items carrying neither tag. Version 0.4.1 runs the two planned contrasts separately across all 49 items and writes separate output directories and summary records.

The corrected raw-map results support somatic versus non-somatic separation but not interpersonal versus non-interpersonal separation. No coordinate estimation, scoring, PCA, clustering, footprint, or cross-sample alignment code changed in this patch.
