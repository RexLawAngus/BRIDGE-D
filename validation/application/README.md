# Application pipeline: NHANES plus a synthetic companion

Runs the full path from raw data to report before a controlled-access cohort
arrives.

- **Stage 1** uses the public NHANES 2017-2018 PHQ-9 file. It checks scoring,
  internal consistency and the distribution on real data.
- **Stage 2** adds a synthetic 12-item companion so the comparison, linking and
  report path runs on a co-administered-like table.

The companion is synthetic. This is a pipeline test, not empirical evidence.

## Run

```bash
python validation/application/prepare_nhanes.py
python validation/application/run_pipeline.py
```

`prepare_nhanes.py` reads `DPQ_J.XPT` from the public dataset folder and writes
`data/nhanes_phq9.csv`. `run_pipeline.py` writes:

- `output/nhanes_phq9_scores.csv`
- `output/cohort_with_companion.csv`
- `output/application_report.md`
- `output/application_report.docx`

`data/` and `output/` are git-ignored. The raw XPT is not copied into the
repository.

## Swapping in the real cohort

`run_pipeline.py` reads one CSV with columns `phq1` to `phq9`. When CAN-BIND or
another approved cohort arrives, write a loader that exports the same columns,
then replace the `pd.read_csv(DATA)` line. The scoring, comparison and report
code stays unchanged.
