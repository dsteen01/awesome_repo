"""
Synthetic validation of propagator calibration.

Generates parent orders whose child fills move a mid-price according to a KNOWN
propagator kernel, then checks that calibrate_propagator() recovers (G0,beta,tau0).
"""
import numpy as np
import pandas as pd
from propagator_calibration import calibrate_propagator, _power_law

rng = np.random.default_rng(7)

# ---- TRUE kernel we will try to recover ------------------------------------
# The estimator fits the INCREMENT model: dm_i = sum_k g_k * f_{i-k} + noise,
# with cumulative kernel G(tau) = sum_{k<tau} g_k. To make this a true round
# trip, we GENERATE data from exactly that model. We choose increments g_k that
# integrate to a power-law cumulative kernel G(tau)=G0/(1+tau/tau0)^... no:
# a decaying transient kernel has g_k = G(k+1)-G(k) <0 after the first step.
# Simplest faithful choice: define g_k directly as a decaying sequence so the
# CUMULATIVE response rises then flattens (permanent component) -- but for a
# transient propagator we want G(tau) itself to DECAY. We therefore define the
# kernel increments as the analytic derivative of the power law.
TRUE = dict(G0=1.2e-3, beta=0.45, tau0=6.0)

def true_kernel(tau):
    return _power_law(np.asarray(tau, float), TRUE["G0"], TRUE["beta"], TRUE["tau0"])

# increments g_k such that cumsum(g)[tau-1] == G(tau): g_0=G(1), g_k=G(k+1)-G(k)
_taus = np.arange(1, 31)
_Gtrue = true_kernel(_taus)
_g_true = np.empty_like(_Gtrue)
_g_true[0] = _Gtrue[0]
_g_true[1:] = np.diff(_Gtrue)

# ---- simulate parent orders + child fills ----------------------------------
n_parents = 400
max_lag = 30
rows = []
ts_global = 0

for pid in range(n_parents):
    side = rng.choice([1, -1])                       # parent buy or sell
    n_child = rng.integers(20, 60)                   # child fills in this parent
    adv = rng.uniform(1e6, 5e6)
    # child sizes: a metaorder sliced up; mild autocorrelation in sign of aggressor
    sizes = rng.gamma(2.0, 500, n_child)
    # aggressor mostly aligned with parent side but ~30% passive
    aggressor = np.where(rng.uniform(size=n_child) < 0.7, side, -side)

    # signed volume-weighted flow uses PARENT INTENTION sign
    flow = side * np.sqrt(sizes / adv)

    # build the mid path from the INCREMENT model the estimator assumes.
    # Work in RETURN units (base=1) so recovered G0 matches TRUE G0 directly.
    base = 1.0
    dm = np.zeros(n_child)
    for i in range(n_child):
        kmax = min(i + 1, len(_g_true))
        dm[i] = (_g_true[:kmax] * flow[i::-1][:kmax]).sum()
    dm += rng.normal(0, 2e-5, n_child)             # martingale noise (return units)
    mid = base + np.cumsum(dm)
    m0 = base

    # execution price ~ mid + half-spread depending on aggressor (not used in calib)
    price = mid + aggressor * m0 * 1e-4

    for i in range(n_child):
        rows.append(dict(parent_id=pid, ts=ts_global, price=price[i],
                         size=sizes[i], side=side, aggressor=int(aggressor[i]),
                         mid=mid[i], adv=adv))
        ts_global += 1

fills = pd.DataFrame(rows)
print(f"Simulated {len(fills):,} fills across {n_parents} parents")
print(f"TRUE kernel: G0={TRUE['G0']:.3e}, beta={TRUE['beta']}, tau0={TRUE['tau0']}\n")

# ---- calibrate (parent-intention sign, all fills) --------------------------
# Note: the mid path was built with mid in PRICE units and flow scaled by m0,
# so the recovered G0 is in (price-fraction) units consistent with that build.
cal = calibrate_propagator(fills, max_lag=max_lag,
                           sign_source="parent_intention",
                           within_parent=True)
print(cal.summary())

print("\nRecovery check (fitted vs true at sample lags):")
for tau in [1, 3, 6, 12, 24]:
    print(f"  tau={tau:2d}:  fitted G={cal.predict_kernel(tau):.3e}   "
          f"true*m0-scale G={true_kernel(tau):.3e}")

# beta and tau0 are scale-free shape params -> should recover regardless of m0 scaling
print("\nShape-parameter recovery (scale-invariant):")
print(f"  beta : fitted {cal.beta:.3f}  vs true {TRUE['beta']:.3f}  "
      f"(err {abs(cal.beta-TRUE['beta']):.3f})")
print(f"  tau0 : fitted {cal.tau0:.3f}  vs true {TRUE['tau0']:.3f}  "
      f"(err {abs(cal.tau0-TRUE['tau0']):.3f})")

# ---- compare sign conventions ----------------------------------------------
cal_aggr = calibrate_propagator(fills, max_lag=max_lag,
                                sign_source="aggressor", within_parent=True)
print("\nSign-convention comparison (beta):")
print(f"  parent_intention -> beta={cal.beta:.3f}, R2={cal.r2:.3f}")
print(f"  aggressor        -> beta={cal_aggr.beta:.3f}, R2={cal_aggr.r2:.3f}")
