"""
Shared synthetic execution dataset (identical DGP to demo_dr.py) so the
hand-rolled DR-learner demo and the PyWhy demo operate on the same data.

Ground truth:
  * 3 configs: passive / balanced / aggressive
  * Order difficulty (size, vol) confounds BOTH config choice and cost.
  * Heterogeneous true effect: aggressive cheap for small orders, costly for
    large; passive the reverse.
"""
import numpy as np
import pandas as pd

CONFIGS = ["passive", "balanced", "aggressive"]


def make_data(n=6000, seed=42):
    rng = np.random.default_rng(seed)

    size_pct_adv = np.exp(rng.normal(-3.0, 1.0, n)).clip(1e-4, 0.5)
    volatility   = np.exp(rng.normal(-4.5, 0.4, n)).clip(1e-3, 0.1)
    spread       = (rng.gamma(2.0, 1.5, n)).clip(0.3, 30)
    momentum     = rng.normal(0, 1, n)
    imbalance    = rng.normal(0, 1, n)
    tod          = rng.uniform(0, 1, n)

    df = pd.DataFrame(dict(
        size_pct_adv=size_pct_adv, volatility=volatility,
        arrival_spread_bps=spread, momentum=momentum,
        imbalance=imbalance, time_of_day=tod,
        horizon_steps=np.full(n, 10)))

    # confounded assignment (good overlap)
    big = (size_pct_adv > 0.05).astype(float)
    logit = np.column_stack([
        -0.4 + 1.2 * big,
         0.3 + 0.0 * big,
         0.5 - 1.2 * big,
    ]) + rng.normal(0, 0.8, (n, 3))
    probs = np.exp(logit) / np.exp(logit).sum(1, keepdims=True)
    A_idx = np.array([rng.choice(3, p=probs[i]) for i in range(n)])
    A = pd.Series([CONFIGS[i] for i in A_idx], name="config")

    base_impact = 60.0 * np.sqrt(size_pct_adv) * (volatility / 0.01)
    half_spread = 0.5 * spread

    def cost_for(cidx):
        c = np.empty(n)
        for i in range(n):
            s = size_pct_adv[i]
            if cidx[i] == 0:      # passive
                im, extra = 0.6, 1.2 * half_spread[i] + 1.5
            elif cidx[i] == 1:    # balanced
                im, extra = 0.85, 0.6 * half_spread[i] + 0.5
            else:                 # aggressive
                im, extra = 1.0 + 6.0 * s, 0.2 * half_spread[i]
            c[i] = im * base_impact[i] + extra
        return c

    Y_all = {ci: cost_for(np.full(n, ci)) for ci in range(3)}
    Y = pd.Series(np.array([Y_all[A_idx[i]][i] for i in range(n)])
                  + rng.normal(0, 1.0, n), name="implementation_shortfall")

    return df, A, A_idx, Y, Y_all
