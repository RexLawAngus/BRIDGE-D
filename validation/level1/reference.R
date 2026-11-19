# Level 1 references computed with established R packages.
# Run from the repository root:
#   Rscript validation/level1/reference.R
#
# Outputs validation/level1/r_results.json.

.libPaths(c("../.rlib", .libPaths()))
suppressPackageStartupMessages({
  library(psych)
  library(irr)
  library(equate)
  library(jsonlite)
})

data <- read.csv("validation/level1/fixture.csv")

phq_items <- data[paste0("phq", 1:9)]
ex_items <- data[paste0("ex", 1:12)]

phq_total <- rowSums(phq_items)
ex_total <- rowSums(ex_items)

alpha_phq <- psych::alpha(phq_items, check.keys = FALSE, warnings = FALSE)$total$raw_alpha
alpha_ex <- psych::alpha(ex_items, check.keys = FALSE, warnings = FALSE)$total$raw_alpha

icc_value <- irr::icc(
  data.frame(phq = phq_total, ex = ex_total),
  model = "twoway", type = "agreement", unit = "single"
)$value

classify <- function(score, cutoffs, labels) {
  out <- rep(labels[1], length(score))
  for (i in seq_along(cutoffs)) {
    out[score >= cutoffs[i]] <- labels[i]
  }
  out
}

phq_labels <- classify(phq_total, c(0, 5, 10, 15, 20),
                       c("minimal", "mild", "moderate", "moderately_severe", "severe"))
ex_labels <- classify(ex_total, c(0, 12, 24, 36),
                      c("low", "moderate", "high", "very_high"))

kappa_value <- irr::kappa2(data.frame(phq = phq_labels, ex = ex_labels))$value

fx <- freqtab(phq_total, scales = 0:max(phq_total))
fy <- freqtab(ex_total, scales = 0:max(ex_total))
eq <- equate(fx, fy, type = "equipercentile")

result <- list(
  alpha_phq = alpha_phq,
  alpha_ex = alpha_ex,
  icc21 = icc_value,
  kappa = kappa_value,
  n = nrow(data),
  link_x = as.numeric(eq$concordance$scale),
  link_y = as.numeric(eq$concordance$yx),
  percentile = as.numeric(px(fx))
)
write_json(result, "validation/level1/r_results.json", auto_unbox = TRUE, digits = 12, pretty = TRUE)
cat("wrote validation/level1/r_results.json\n")
