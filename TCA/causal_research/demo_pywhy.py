"""
PyWhy demo: config-selection causal analysis via DoWhy + EconML, driven by the
explicit DAG in causal_dag.py.

Pipeline (the DoWhy four-step workflow):
  1. MODEL    -- load our networkx DAG into dowhy.CausalModel (as GML).
  2. IDENTIFY -- let DoWhy derive the backdoor adjustment set from the graph.
  3. ESTIMATE -- fit EconML's DRLearner (doubly-robust, heterogeneous) for the
                 effect of config on implementation shortfall, using the
                 graph-identified adjustment set.
  4. REFUTE   -- run DoWhy-style robustness checks (placebo treatment, random
                 common cause, subset) that our hand-rolled demo could not.

This is the library-backed counterpart to demo_dr.py. Same data, same DAG, same
estimand (TOTAL effect of config, mediator excluded) -- but identification and
refutation now come from tested PyWhy machinery instead of hand code.

Treatment is multi-valued (3 configs). EconML's DRLearner handles this natively;
we treat 'balanced' (index 1) as the baseline category.
"""
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from synth_data import make_data, CONFIGS
from causal_dag import build_dag, to_dowhy_graph

from dowhy import CausalModel
from econml.dr import DRLearner
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier

# ─── data ────────────────────────────────────────────────────────────────────
df, A, A_idx, Y, Y_all = make_data()
context = ["size_pct_adv", "volatility", "arrival_spread_bps",
           "momentum", "imbalance", "time_of_day"]

data = df.copy()
data["config"] = A_idx
data["implementation_shortfall"] = Y.values

# ─── STEP 1 & 2: MODEL + IDENTIFY (DoWhy, graph-driven) ──────────────────────
print("=" * 74)
print("STEP 1-2: MODEL + IDENTIFY  (DoWhy reads our DAG)")
print("=" * 74)
gml = to_dowhy_graph(build_dag(), include_mediator=False)
model = CausalModel(data=data, treatment="config",
                    outcome="implementation_shortfall", graph=gml)
identified = model.identify_effect(proceed_when_unidentifiable=True)
backdoor = identified.get_backdoor_variables()
print(f"  Graph-identified backdoor adjustment set ({len(backdoor)}):")
for v in backdoor:
    print(f"    - {v}")
print("  Note: propagator features are NOT in the backdoor set -- they are")
print("  descendants of context (predictive, not confounders). They can still")
print("  be added as effect-modifiers to sharpen heterogeneity (done below).")

# ─── STEP 3: ESTIMATE (EconML DRLearner) ─────────────────────────────────────
print("\n" + "=" * 74)
print("STEP 3: ESTIMATE  (EconML doubly-robust learner)")
print("=" * 74)

# W = backdoor controls (confounders); X = effect modifiers (heterogeneity).
#
# WHERE DOES THE PROPAGATOR FORECAST GO?
# It must NOT go in W: in the DAG the forecast is a DESCENDANT of context (a
# deterministic function of size/vol), not an independent common cause of config
# and cost. Its parents (size, vol, ...) are already in W, so adding it as a
# control is redundant -- which is exactly why DoWhy excluded it from the
# backdoor set.
# It DOES belong in X (effect modifiers): the predicted impact is a low-variance
# scalar summary of order difficulty, and the config effect varies along it
# (aggressive is cheap when predicted impact is low, costly when high). Putting
# it in X lets the DR-learner express difficulty-driven heterogeneity directly
# instead of re-deriving that nonlinear combination from raw size/vol. This also
# makes the PyWhy demo consistent with demo_dr.py, which feeds the same forecast
# in via build_pretrade_features.
from dr_config_selection import PropagatorParams, build_pretrade_features

_p = PropagatorParams(G0=8e-4, beta=0.55, tau0=5.0)  # calibrated kernel (placeholder)
_pre = build_pretrade_features(df, _p)
prop_cols = ["pred_impact_twap", "pred_impact_dispersion"]  # forecast summaries

W = data[backdoor].to_numpy()
# X now = raw effect modifiers + propagator forecast features
X = np.column_stack([
    data[["size_pct_adv", "volatility"]].to_numpy(),
    _pre[prop_cols].to_numpy(),
])
X_cols = ["size_pct_adv", "volatility"] + prop_cols
T = data["config"].to_numpy()
Yv = data["implementation_shortfall"].to_numpy()
print(f"  effect-modifier set X = {X_cols}")
print(f"  (propagator forecast added as effect modifier, NOT as a backdoor control)")

dr = DRLearner(
    model_propensity=GradientBoostingClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8,
        random_state=0),
    model_regression=GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8,
        random_state=0),
    model_final=GradientBoostingRegressor(
        n_estimators=100, max_depth=3, learning_rate=0.05, random_state=0),
    multitask_model_final=False,
    cv=5, random_state=0,
)
# DRLearner uses the lowest treatment index (0 = passive) as the baseline.
dr.fit(Yv, T, X=X, W=W)

# Effects vs baseline (passive=0). T=1 balanced, T=2 aggressive.
eff_bal = dr.effect(X, T0=0, T1=1)  # balanced - passive
eff_agg = dr.effect(X, T0=0, T1=2)  # aggressive - passive
ate_bal = dr.ate(X, T0=0, T1=1)
ate_agg = dr.ate(X, T0=0, T1=2)
print(f"  ATE balanced  vs passive : {ate_bal:8.2f} bps")
print(f"  ATE aggressive vs passive: {ate_agg:8.2f} bps")

# Recover heterogeneity: aggressive should be RELATIVELY cheaper for small orders
small = data["size_pct_adv"].to_numpy() < 0.01
large = data["size_pct_adv"].to_numpy() > 0.05
print(f"\n  aggressive-vs-passive effect (cost bps; negative = aggressive cheaper):")
print(f"    among SMALL orders: mean {eff_agg[small].mean():8.2f}")
print(f"    among LARGE orders: mean {eff_agg[large].mean():8.2f}")
print("    (expect SMALL << LARGE: aggressive favored for small orders)")

# Compare against the TRUE effect baked into the DGP
true_agg = Y_all[2] - Y_all[0]  # aggressive - passive, truth
corr = np.corrcoef(eff_agg, true_agg)[0, 1]
print(f"\n  corr(estimated, true) aggressive-vs-passive effect: {corr:.3f}")

# ─── STEP 4: REFUTE (DoWhy robustness checks) ────────────────────────────────
# DoWhy's refuters need an estimate object; we run them on a binarized version
# (aggressive vs not) so DoWhy's built-in backdoor.linear/propensity estimators
# apply cleanly. The refuters perturb the data and check the estimate is stable.
print("\n" + "=" * 74)
print("STEP 4: REFUTE  (DoWhy robustness checks, binarized aggressive-vs-rest)")
print("=" * 74)

data_bin = data.copy()
data_bin["config"] = (data["config"] == 2).astype(int)  # 1 = aggressive
gml_bin = to_dowhy_graph(build_dag(), include_mediator=False)
model_bin = CausalModel(data=data_bin, treatment="config",
                        outcome="implementation_shortfall", graph=gml_bin)
ident_bin = model_bin.identify_effect(proceed_when_unidentifiable=True)
est_bin = model_bin.estimate_effect(
    ident_bin, method_name="backdoor.propensity_score_weighting",
    target_units="ate")
print(f"  Baseline estimate (aggressive vs rest): {est_bin.value:.2f} bps")

refuters = [
    ("Placebo treatment (should -> ~0)",
     dict(method_name="placebo_treatment_refuter",
          placebo_type="permute", num_simulations=20)),
    ("Random common cause (should be stable)",
     dict(method_name="random_common_cause", num_simulations=20)),
    ("Data subset (should be stable)",
     dict(method_name="data_subset_refuter",
          subset_fraction=0.8, num_simulations=20)),
]
for label, kwargs in refuters:
    try:
        r = model_bin.refute_estimate(ident_bin, est_bin, **kwargs)
        print(f"\n  {label}")
        print(f"    new effect : {r.new_effect:.2f}"
              if np.isscalar(r.new_effect) else f"    new effect : {r.new_effect}")
        if r.refutation_result is not None:
            pv = r.refutation_result.get('p_value')
            print(f"    p-value    : {pv}")
    except Exception as e:
        print(f"\n  {label}\n    (refuter error: {e})")

print("\n" + "=" * 74)
print("INTERPRETATION")
print("=" * 74)
print("  * Placebo: scrambling the treatment should collapse the effect to ~0.")
print("    A near-zero placebo effect supports that we measured signal, not noise.")
print("  * Random common cause: adding a noise confounder shouldn't move the")
print("    estimate if the adjustment set already captures confounding.")
print("  * Subset: estimate should be stable on random 80% subsamples.")
print("  These are the checks the hand-rolled demo could not provide.")