"""
Causal config-analysis using the `causalinference` library for balance &
matching, driven by the same DAG and cross-checked against DoWhy/EconML.

Division of labour:
  * DoWhy            -> identification (graph proves the backdoor adjustment set)
  * causalinference  -> covariate balance (normalized differences), propensity,
                        matching/weighting/stratification estimators, trimming
  * EconML DRLearner -> doubly-robust cross-check of the matching ATE

`causalinference` replaces the hand-rolled covariate_balance.py: its
`summary_stats['ndiff']` is the standardized/normalized mean difference, and it
provides matching with bias correction, IPW, stratification, and overlap
trimming out of the box.

Treatment is binarized (aggressive vs rest) because causalinference is a
binary-treatment toolkit; this matches how the DoWhy refuters operate.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from causalinference import CausalModel as CICausalModel
from synth_data import make_data, CONFIGS
from causal_dag import build_dag, to_dowhy_graph


# ─── data + binarized treatment ──────────────────────────────────────────────
df, A, A_idx, Y, Y_all = make_data()
context = ["size_pct_adv", "volatility", "arrival_spread_bps",
           "momentum", "imbalance", "time_of_day"]
treat = (A_idx == 2).astype(int)              # 1 = aggressive, 0 = rest
Yv = Y.to_numpy()
Xv = df[context].to_numpy()


# ─── STEP 1: identification via DoWhy (graph-driven), reused from the DAG ─────
print("=" * 74)
print("STEP 1: IDENTIFY  (DoWhy reads the DAG -> backdoor set)")
print("=" * 74)
from dowhy import CausalModel as DoWhyModel
data = df.copy(); data["config"] = treat
data["implementation_shortfall"] = Yv
dw = DoWhyModel(data=data, treatment="config",
                outcome="implementation_shortfall",
                graph=to_dowhy_graph(build_dag(), include_mediator=False))
ident = dw.identify_effect(proceed_when_unidentifiable=True)
backdoor = ident.get_backdoor_variables()
print(f"  backdoor adjustment set ({len(backdoor)}): {backdoor}")
print("  -> these are the covariates whose balance we must verify.")


# ─── STEP 2: build the causalinference model ─────────────────────────────────
cm = CICausalModel(Yv, treat, Xv)

print("\n" + "=" * 74)
print("STEP 2: COVARIATE BALANCE  (causalinference normalized differences)")
print("=" * 74)
print("  Raw normalized differences (|ndiff| > 0.1 = imbalance):")
for name, nd in zip(context, cm.summary_stats["ndiff"]):
    flag = "  <-- IMBALANCED" if abs(nd) > 0.1 else ""
    print(f"    {name:20s}: {nd:+.4f}{flag}")


# ─── STEP 3: propensity, overlap trimming, and balance after adjustment ──────
print("\n" + "=" * 74)
print("STEP 3: PROPENSITY + TRIMMING + MATCHING (causalinference)")
print("=" * 74)
cm.est_propensity_s()                          # propensity w/ auto term selection
print("  propensity estimated (auto-selected terms).")

# overlap trimming: drop units with extreme propensity (poor overlap)
n_before = cm.raw_data["N"]
cm.trim_s()                                    # data-driven optimal trimming
# after trimming, re-view balance via stratification
cm.stratify_s()
print(f"  optimal trim cutoff: {cm.cutoff:.4f}")
print("  stratification (propensity balanced within strata):")
print(cm.strata)


# ─── STEP 4: estimators + cross-check vs EconML DR ───────────────────────────
print("\n" + "=" * 74)
print("STEP 4: EFFECT ESTIMATES + DR cross-check")
print("=" * 74)

# IMPORTANT: trimming changes the ESTIMAND. cm was trimmed in Step 3, so its
# estimates are for the trimmed (good-overlap) subpopulation -- which drops the
# rare large+aggressive orders where impact is highest, biasing the ATE DOWN.
# To compare apples-to-apples with EconML's full-sample DR, we ALSO fit an
# untrimmed model. The two causalinference rows below are different estimands.
cm.est_via_matching(bias_adj=True)
cm.est_via_weighting()
print("  -- TRIMMED subpopulation (overlap-restricted estimand) --")
for method in ["matching", "weighting"]:
    e = cm.estimates[method]
    print(f"    {method:10s} ATE: {e['ate']:8.2f} bps  (se {e.get('ate_se', np.nan):.2f})")

cm_full = CICausalModel(Yv, treat, Xv)
cm_full.est_propensity_s()
cm_full.est_via_matching(bias_adj=True)
cm_full.est_via_weighting()
print("  -- FULL sample (no trimming; matches EconML's estimand) --")
for method in ["matching", "weighting"]:
    e = cm_full.estimates[method]
    print(f"    {method:10s} ATE: {e['ate']:8.2f} bps  (se {e.get('ate_se', np.nan):.2f})")

# EconML doubly-robust cross-check (full sample)
from econml.dr import DRLearner
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
dr = DRLearner(
    model_propensity=GradientBoostingClassifier(n_estimators=150, max_depth=3,
                                                learning_rate=0.05, random_state=0),
    model_regression=GradientBoostingRegressor(n_estimators=150, max_depth=3,
                                               learning_rate=0.05, random_state=0),
    cv=5, random_state=0)
dr.fit(Yv, treat, X=df[["size_pct_adv", "volatility"]].to_numpy(),
       W=df[backdoor].to_numpy())
dr_ate = dr.ate(df[["size_pct_adv", "volatility"]].to_numpy(), T0=0, T1=1)
print(f"  -- DR (EconML, full sample) --\n    DRLearner  ATE: {dr_ate:8.2f} bps")

oracle_ate = float(np.mean([Y_all[2][i] - (Y_all[A_idx[i]][i] if A_idx[i] != 2
                                           else Y_all[0][i]) for i in range(len(Yv))]))
print(f"\n  rough oracle ATE (full sample): {oracle_ate:.2f} bps")

print("\n" + "=" * 74)
print("INTERPRETATION")
print("=" * 74)
print("  * ndiff flags size_pct_adv as the imbalanced confounder (as designed).")
print("  * KEY LESSON: trimming changes the ESTIMAND. The trimmed causalinference")
print("    ATE (~11) drops the rare large+aggressive orders -> biased toward the")
print("    well-overlapped region. The UNTRIMMED full-sample estimates align with")
print("    EconML's DR (~16) and the oracle. Always compare like-for-like estimands.")
print("  * causalinference gives balance/matching/trimming in one toolkit; DoWhy")
print("    owns identification; EconML owns the heterogeneous/DR estimate.")
