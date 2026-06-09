"""
Synthetic demo: can the DR-learner recover a KNOWN heterogeneous config effect
from CONFOUNDED observational data?

Ground truth we bake in:
  * 3 configs: passive / balanced / aggressive
  * Order difficulty (size, vol) drives BOTH config choice (confounding) AND cost.
  * The TRUE config effect is heterogeneous:
       - aggressive is cheaper for SMALL/urgent orders
       - passive   is cheaper for LARGE orders (impact-dominated)
  * Traders confound: they already tend to pick aggressive for small orders,
    so a naive cost-by-config comparison is biased.
"""
import numpy as np
import pandas as pd
from dr_config_selection import (
    PropagatorParams, build_pretrade_features, DRConfigLearner
)

rng = np.random.default_rng(42)
N = 6000
CONFIGS = ["passive", "balanced", "aggressive"]

# ---- 1. order context -------------------------------------------------------
size_pct_adv = np.exp(rng.normal(-3.0, 1.0, N)).clip(1e-4, 0.5)   # mostly small
volatility   = np.exp(rng.normal(-4.5, 0.4, N)).clip(1e-3, 0.1)   # daily vol
spread       = (rng.gamma(2.0, 1.5, N)).clip(0.3, 30)             # bps
momentum     = rng.normal(0, 1, N)
imbalance    = rng.normal(0, 1, N)
tod          = rng.uniform(0, 1, N)
horizon      = np.full(N, 10)

df = pd.DataFrame(dict(
    size_pct_adv=size_pct_adv, volatility=volatility,
    arrival_spread_bps=spread, momentum=momentum,
    imbalance=imbalance, time_of_day=tod, horizon_steps=horizon))

# ---- 2. CONFOUNDED config assignment (logging policy) -----------------------
# Traders lean aggressive for small orders, passive for large ones -- BUT we
# keep partial overlap (softer tilt + more noise) so every config is observed
# across the size range. Without this, effects are unidentified where a config
# is never tried (positivity violation). Mimics a desk running some interleaving.
big = (size_pct_adv > 0.05).astype(float)
logit = np.column_stack([
    -0.4 + 1.2 * big,                 # passive: mildly favored for big orders
     0.3 + 0.0 * big,                 # balanced: baseline
     0.5 - 1.2 * big,                 # aggressive: mildly favored for small
])
logit += rng.normal(0, 0.8, logit.shape)   # more noise -> better overlap
probs = np.exp(logit) / np.exp(logit).sum(1, keepdims=True)
A_idx = np.array([rng.choice(3, p=probs[i]) for i in range(N)])
A = pd.Series([CONFIGS[i] for i in A_idx])

# ---- 3. TRUE cost model (implementation shortfall, bps) ---------------------
# Base difficulty: square-root impact in size, scaled by vol; plus half-spread.
base_impact = 60.0 * np.sqrt(size_pct_adv) * (volatility / 0.01)   # ~realistic bps
half_spread = 0.5 * spread

# Heterogeneous config multipliers on the IMPACT component:
#   aggressive: low impact-mult for small (fast, cheap) but BAD for large
#   passive:    high spread/adverse-sel for small, but LOW impact for large
def cost_for(config_idx):
    c = np.empty(N)
    for i in range(N):
        s = size_pct_adv[i]
        if config_idx[i] == 0:        # passive
            impact_mult = 0.6                          # low impact
            extra = 1.2 * half_spread[i] + 1.5         # pays spread + adverse sel
        elif config_idx[i] == 1:      # balanced
            impact_mult = 0.85
            extra = 0.6 * half_spread[i] + 0.5
        else:                          # aggressive
            impact_mult = 1.0 + 6.0 * s                # cheap small, costly large
            extra = 0.2 * half_spread[i]
        c[i] = impact_mult * base_impact[i] + extra
    return c

Y_true_all = {ci: cost_for(np.full(N, ci)) for ci in range(3)}
# realized outcome = cost under the config actually taken + noise
Y = pd.Series(np.array([Y_true_all[A_idx[i]][i] for i in range(N)])
              + rng.normal(0, 1.0, N))

# ---- 4. build features & fit DR-learner -------------------------------------
p = PropagatorParams(G0=8e-4, beta=0.55, tau0=5.0)
X = build_pretrade_features(df, p)

learner = DRConfigLearner(configs=CONFIGS, n_folds=5, random_state=0)
learner.fit(X, A, Y, baseline="balanced")

# ---- 5. OVERLAP DIAGNOSTIC (run this BEFORE trusting any effect) ------------
# Positivity check: is every config observed across the size range? Effects are
# only identified where propensities are bounded away from 0.
print("=" * 70)
print("OVERLAP DIAGNOSTIC: config share by size tercile")
print("=" * 70)
size_bucket = pd.qcut(size_pct_adv, 3, labels=["small", "mid", "large"])
share = pd.crosstab(size_bucket, A, normalize="index").round(3)
print(share.to_string())
min_share = pd.crosstab(size_bucket, A, normalize="index").min().min()
print(f"\n  Min config share in any bucket: {min_share:.3f}  "
      f"({'OK overlap' if min_share > 0.05 else 'POOR overlap -- effects unreliable'})")

# ---- 5b. evaluate recovery of the TRUE effect -------------------------------
eff = learner.effect(X)                          # estimated cost vs balanced
true_eff = pd.DataFrame({
    "passive":    Y_true_all[0] - Y_true_all[1],
    "balanced":   np.zeros(N),
    "aggressive": Y_true_all[2] - Y_true_all[1],
})

print("=" * 70)
print("RECOVERY OF HETEROGENEOUS CONFIG EFFECT (cost vs 'balanced', bps)")
print("=" * 70)
for c in ["passive", "aggressive"]:
    corr = np.corrcoef(eff[c], true_eff[c])[0, 1]
    mae = np.abs(eff[c] - true_eff[c]).mean()
    print(f"  {c:11s}: corr(est,true)={corr:5.3f}   MAE={mae:5.2f} bps")

# ---- 6. policy value vs naive / logged --------------------------------------
rec = learner.recommend(X)
res = learner.evaluate_policy(X, A, Y, rec)

# oracle: pick the truly-cheapest config per order
oracle_idx = np.argmin(np.column_stack([Y_true_all[i] for i in range(3)]), axis=1)
oracle_cost = np.array([Y_true_all[oracle_idx[i]][i] for i in range(N)]).mean()

print("\n" + "=" * 70)
print("POLICY EVALUATION (mean implementation shortfall, bps -- lower better)")
print("=" * 70)
print(f"  Logged (status quo)      : {res['naive_logged_bps']:6.2f}")
print(f"  DR-learner policy (OPE)  : {res['dr_value_bps']:6.2f}  "
      f"95% CI [{res['ci95_bps'][0]:.2f}, {res['ci95_bps'][1]:.2f}]")
print(f"  Oracle (true best/order) : {oracle_cost:6.2f}")
print(f"\n  Recommendation mix: "
      f"{rec.value_counts(normalize=True).round(3).to_dict()}")

# show the heterogeneity was learned: aggressive recommended for small orders?
small = size_pct_adv < 0.01
large = size_pct_adv > 0.05
print(f"\n  Among SMALL orders -> % recommended aggressive: "
      f"{(rec[small] == 'aggressive').mean():.1%}")
print(f"  Among LARGE orders -> % recommended passive   : "
      f"{(rec[large] == 'passive').mean():.1%}")
