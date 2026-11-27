"""Compare nominal 95% correlation intervals on the existing Level 2 grid.

Uses exactly the data seeds and scoring rules from run_grid.py. Bootstrap
resamples complete participant pairs and leaves the data-generation RNG alone.
Run with --out pointing to a new output directory to preserve earlier results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

import run_grid as grid


BOOTSTRAP_DRAWS = 1999
BOOTSTRAP_SEED = 20261126
MIN_VALID_FRACTION = 0.99


def bootstrap_interval(
    pairs: np.ndarray, rng: np.random.Generator, draws: int = BOOTSTRAP_DRAWS
) -> tuple[float, float, int]:
    """Percentile interval from complete pairs; count constant-sample failures."""
    n = len(pairs)
    if n < 5:
        return float('nan'), float('nan'), 0
    correlations = []
    for start in range(0, draws, 128):
        indices = rng.integers(0, n, size=(min(128, draws - start), n))
        samples = pairs[indices]
        centered = samples - samples.mean(axis=1, keepdims=True)
        numerator = (centered[:, :, 0] * centered[:, :, 1]).sum(axis=1)
        denominator = np.sqrt((centered[:, :, 0] ** 2).sum(axis=1)
                              * (centered[:, :, 1] ** 2).sum(axis=1))
        valid = denominator > 0
        correlations.extend((numerator[valid] / denominator[valid]).tolist())
    valid_count = len(correlations)
    if valid_count < int(np.ceil(MIN_VALID_FRACTION * draws)):
        return float('nan'), float('nan'), valid_count
    low, high = np.quantile(np.clip(correlations, -1, 1), [.025, .975], method='linear')
    return float(low), float(high), valid_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    sources = ['compare_intervals.py', 'run_grid.py', 'calibration.json', 'summary.csv']
    config = {
        'bootstrap_draws': BOOTSTRAP_DRAWS,
        'bootstrap_seed': BOOTSTRAP_SEED,
        'data_seed': grid.SEED,
        'replications_per_condition': grid.REPLICATIONS,
        'truth_n': grid.TRUTH_N,
        'min_valid_bootstrap_fraction': MIN_VALID_FRACTION,
        'method': 'paired complete-case percentile bootstrap, linear quantiles',
        'scoring': 'A >=7/9; B >=10/12; prorate; retain fractional totals',
        'source_sha256': {
            name: hashlib.sha256((here / name).read_bytes()).hexdigest()
            for name in sources
        },
    }
    (output / 'configuration.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    truth = {
        (rho, missing): grid.build_truth(rho, missing)['r']
        for rho in grid.LATENT_R_GRID for missing in grid.MISSING_GRID
    }
    records = []
    for n in grid.N_GRID:
        for rho in grid.LATENT_R_GRID:
            for missing_index, missing in enumerate(grid.MISSING_GRID):
                for repetition in range(grid.REPLICATIONS):
                    data_seed = grid.SEED + n * 10000 + int(rho * 1000) + repetition
                    a, b = grid.generate(n, rho, missing, np.random.default_rng(data_seed))
                    pairs = pd.concat([grid.prorate(a, 7), grid.prorate(b, 10)], axis=1).dropna().to_numpy()
                    n_effective = len(pairs)
                    estimate = float(np.corrcoef(pairs.T)[0, 1]) if n_effective >= 5 else float('nan')
                    tick = time.perf_counter()
                    fisher = grid.fisher_interval(estimate, n_effective)
                    fisher_seconds = time.perf_counter() - tick
                    seed = np.random.SeedSequence([BOOTSTRAP_SEED, n, int(rho * 1000), missing_index, repetition])
                    tick = time.perf_counter()
                    boot_low, boot_high, valid_draws = bootstrap_interval(pairs, np.random.default_rng(seed))
                    bootstrap_seconds = time.perf_counter() - tick
                    target = truth[(rho, missing)]
                    for method, bounds, elapsed in [
                        ('fisher', fisher, fisher_seconds),
                        ('paired_percentile', (boot_low, boot_high), bootstrap_seconds),
                    ]:
                        low, high = bounds
                        valid = bool(np.isfinite(low) and np.isfinite(high))
                        records.append({
                            'n': n, 'latent_r': rho, 'missing': missing, 'replication': repetition,
                            'method': method, 'n_eff': n_effective, 'r': estimate,
                            'true_r_mech': target, 'ci_low': low, 'ci_high': high,
                            'valid': valid, 'covered': bool(valid and low <= target <= high),
                            'width': high - low if valid else float('nan'),
                            'seconds': elapsed,
                            'valid_bootstrap_draws': valid_draws if method == 'paired_percentile' else None,
                        })
                print(f'Completed n={n}, latent_r={rho}, missing={missing}', flush=True)
    data = pd.DataFrame(records)
    data.to_csv(output / 'replications.csv', index=False)
    rows = []
    for condition, group in data.groupby(['n', 'latent_r', 'missing', 'method'], sort=True):
        n, rho, missing, method = condition
        probability = float(group.covered.mean())
        valid = group[group.valid]
        rows.append({
            'n': n, 'latent_r': rho, 'missing': missing, 'method': method,
            'attempted': len(group), 'valid': len(valid), 'failure_rate': 1 - len(valid) / len(group),
            'mean_r': group.r.mean(), 'true_r_mech': group.true_r_mech.iloc[0],
            'bias_mech': group.r.mean() - group.true_r_mech.iloc[0],
            'coverage_unconditional': probability,
            'coverage_conditional': valid.covered.mean(),
            'coverage_mcse': np.sqrt(probability * (1 - probability) / len(group)),
            'mean_width': valid.width.mean(), 'mean_seconds': group.seconds.mean(),
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(output / 'summary.csv', index=False)
    old = pd.read_csv(here / 'summary.csv')
    fisher = summary[summary.method.eq('fisher')].merge(old, on=['n', 'latent_r', 'missing'])
    checks = {
        'all_conditions_match_previous_mean_r': bool(np.allclose(fisher.mean_r_x, fisher.mean_r_y, atol=1e-12, rtol=0)),
        'all_conditions_match_previous_fisher_coverage': bool(np.allclose(fisher.coverage_unconditional, fisher.coverage_r, atol=1e-12, rtol=0)),
        'all_conditions_match_previous_true_r_mech': bool(np.allclose(fisher.true_r_mech_x, fisher.true_r_mech_y, atol=1e-12, rtol=0)),
    }
    base = summary[summary.method.eq('fisher')].set_index(['n', 'latent_r', 'missing'])
    candidate = summary[summary.method.eq('paired_percentile')].set_index(['n', 'latent_r', 'missing']).loc[base.index]
    baseline_error = float((base.coverage_unconditional - .95).abs().mean())
    bootstrap_error = float((candidate.coverage_unconditional - .95).abs().mean())
    width_ratio = float(candidate.mean_width.mean() / base.mean_width.mean())
    gates = {
        'all_cell_coverages_at_least_0_925': bool((candidate.coverage_unconditional >= .925).all()),
        'mean_absolute_coverage_error_improves_at_least_0_01': bool(baseline_error - bootstrap_error >= .01),
        'all_cell_failure_rates_at_most_0_01': bool((candidate.failure_rate <= .01).all()),
        'all_cell_coverage_drops_at_most_0_02': bool((candidate.coverage_unconditional >= base.coverage_unconditional - .02 - 1e-12).all()),
        'ratio_of_mean_widths_at_most_1_25': bool(width_ratio <= 1.25),
    }
    audit = {
        'reproduction_checks': checks, 'decision_gates': gates,
        'bootstrap_meets_replacement_gates': all(gates.values()),
        'mean_absolute_coverage_error_fisher': baseline_error,
        'mean_absolute_coverage_error_bootstrap': bootstrap_error,
        'ratio_of_mean_widths': width_ratio,
    }
    (output / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2), flush=True)
    if not all(checks.values()):
        raise RuntimeError('Fisher baseline failed to reproduce; inspect output before interpreting comparisons.')


if __name__ == '__main__':
    main()
