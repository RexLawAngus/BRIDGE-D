# BRIDGE-D v0.3.0 release notes

Release date: 2026-11-20

## Added

- `bridged construct-map` for empirical item maps from co-administered ordinal
  responses.
- Spearman item associations, PCA-loading or non-metric-MDS coordinates, and
  average-linkage hierarchical clustering.
- Subject-level bootstrap uncertainty for coordinates and co-assignment
  stability for clusters.
- CSV matrices, item coordinates, PNG map and dendrogram, JSON analysis
  configuration, and a Markdown method report.
- Granwald PHQ-9/CES-D/SDS and NSDUH adult-MDE validation workflows.

## Corrected

- PHQ-9 prorated totals now use half-up whole-score rounding as declared in the
  instrument definition.
- HAMD-17 items 16 and 17 now follow the standard order: weight loss, then loss
  of insight.

## Validation summary

The Granwald analysis used 524 records and 49 co-administered items. Correlation
and distance matrices correlated 0.842 across the two source samples; PC1 and
PC2 loading correlations were 0.905 and 0.890. Automatic clustering returned
one cluster because no non-singleton multi-cluster solution met the stability
guard.

The NSDUH analysis used 19,832 complete adult past-year-MDE records. PCA showed
a stable somatic versus cognitive-affective symptom contrast. A four-domain
SDS submap separated home/work from relationships/social life, with perfect
agreement between the two-cluster solution and the pre-specified grouping.
Only four function domains were available, so that result remains descriptive.

## Interpretation boundary

Construct maps describe response-pattern similarity in the analyzed sample.
PCA and MDS axes have no automatic psychological names. Clusters do not define
clinical subtypes, and the current implementation does not handle complex
survey weights.
