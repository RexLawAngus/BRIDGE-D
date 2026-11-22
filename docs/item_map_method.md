# Empirical item-map method

## Estimation

BRIDGE-D reads executable instrument definitions, scores item responses, and estimates pairwise Spearman correlations from co-administered data. It converts correlations to distances with `1 - r`. The user can map items with the first two PCA loadings of the correlation matrix or with two-dimensional non-metric MDS. Average-linkage clustering uses the full distance matrix, not the displayed two-dimensional coordinates.

Bootstrap samples are drawn at the participant level. Each replicate is refitted and Procrustes-aligned to the original map before coordinate standard deviations are calculated. Cluster co-assignment probabilities describe how often two items remain together across valid replicates.

## Instrument footprints

For every instrument, BRIDGE-D reports its projected centroid, mean radius, root-mean-square radius, maximum radius, and convex-hull area. Between instruments it reports centroid distance, mean and minimum cross-item distance, and a symmetric nearest-neighbor distance. These summaries answer how two scales cover the fitted display. They depend on the sample and the two-dimensional projection.

## Post-fit label validation

`map-validate` joins pre-specified labels only after coordinates have been estimated. The global statistic is the proportion of total coordinate sum of squares lying between labeled groups. Its reference distribution comes from label permutations. Pairwise tests use the distance between two group centroids and enumerate all same-size partitions when feasible; otherwise they use Monte Carlo permutations with a plus-one correction.

This separation test is not a confirmatory factor analysis. A small p value says that the chosen labels are unusually separated on the fitted map under label exchangeability. It does not prove that the axes have those psychological meanings.

## Cross-sample comparison

`map-compare` matches stable item identifiers, then aligns the candidate map to the reference by translation, isotropic scaling, and orthogonal Procrustes rotation or reflection. It reports aligned-axis correlations, coordinate RMSE, normalized residual sum of squares, and the correlation between all pairwise item distances. The pairwise-distance correlation is invariant to axis sign and rotation and is therefore the least display-dependent summary.
