"""
Rigorous parameter-recovery test for the hardened propagator calibration.

Generates fills from a KNOWN power-law kernel (in increment form, matching the
estimator's model), across multiple seeds and noise levels, and reports how
well each method recovers (G0, beta, tau0).
"""
import numpy as np
import pandas as pd
from propagator_calibration import calibrate_propagator, _power_law

TRUE = dict(G0=1.2e-3, beta=0.45, tau0=6.0)
MAX_LAG = 30

_taus = np.arange(1, MAX_LAG + 1, dtype=float)
_Gtrue = _power_law(_taus, TRUE["G0"], TRUE["beta"], TRUE["tau0"])
_g_true = np.empty_like(_Gtrue)
_g_true[0] = _Gtrue[0]; _g_true[1:] = np.diff(_Gtrue)


def simulate(seed, noise_sd, n_parents=400):
    rng = np.random.default_rng(seed)
    rows = []; ts = 0
    for pid in range(n_parents):
        side = rng.choice([1, -1])
        n_child = rng.integers(20, 60)
        adv = rng.uniform(1e6, 5e6)
        sizes = rng.gamma(2.0, 500, n_child)
        aggressor = np.where(rng.uniform(size=n_child) < 0.7, side, -side)
        flow = side * np.sqrt(sizes / adv)
        # one-step changes from the increment model
        dm = np.zeros(n_child)
        for i in range(n_child):
            kmax = min(i + 1, len(_g_true))
            dm[i] = (_g_true[:kmax] * flow[i::-1][:kmax]).sum()
        dm += rng.normal(0, noise_sd, n_child)
        mid = 1.0 + np.cumsum(dm)
        price = mid + aggressor * 1e-4
        for i in range(n_child):
            rows.append(dict(parent_id=pid, ts=ts, price=price[i], size=sizes[i],
                             side=side, aggressor=int(aggressor[i]),
                             mid=mid[i], adv=adv)); ts += 1
    return pd.DataFrame(rows)


def recovery_error(cal):
    return (abs(cal.G0 - TRUE["G0"]) / TRUE["G0"],
            abs(cal.beta - TRUE["beta"]),
            abs(cal.tau0 - TRUE["tau0"]))


print("=" * 78)
print(f"TRUE: G0={TRUE['G0']:.2e}  beta={TRUE['beta']}  tau0={TRUE['tau0']}")
print("=" * 78)

noise_levels = {"low (2e-5)": 2e-5, "med (1e-4)": 1e-4, "high (5e-4)": 5e-4}
methods = ["mle", "regularized"]
seeds = [1, 2, 3]

for nname, nsd in noise_levels.items():
    print(f"\n--- noise = {nname} ---")
    for method in methods:
        errs = []
        betas, tau0s, g0s, r2s = [], [], [], []
        for s in seeds:
            fills = simulate(s, nsd)
            cal = calibrate_propagator(fills, max_lag=MAX_LAG,
                                       sign_source="parent_intention",
                                       method=method)
            g0e, be, te = recovery_error(cal)
            errs.append((g0e, be, te))
            betas.append(cal.beta); tau0s.append(cal.tau0)
            g0s.append(cal.G0); r2s.append(cal.r2)
        errs = np.array(errs)
        print(f"  {method:12s}: "
              f"beta={np.mean(betas):.3f}±{np.std(betas):.3f}  "
              f"tau0={np.mean(tau0s):5.2f}±{np.std(tau0s):4.2f}  "
              f"G0={np.mean(g0s):.2e}  "
              f"| beta_err={errs[:,1].mean():.3f}  "
              f"G0_relerr={errs[:,0].mean():.2f}  "
              f"R2={np.mean(r2s):.3f}")

print("\n" + "=" * 78)
print("Recovery target: beta_err small, G0_relerr small. MLE should dominate.")
