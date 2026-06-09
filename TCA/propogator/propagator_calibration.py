"""
Propagator market-impact model calibration from historical order/execution data.
================================================================================

Calibrates the transient-impact propagator kernel

        G(tau) = G0 / (1 + tau/tau0)^beta

from desk execution data: a stream of (signed, volume-weighted) child fills and
the contemporaneous mid-price path. This is the "raw material" the config-
selection layer (dr_config_selection.py) ultimately sits on top of.

MODEL (Bouchaud et al. 2004; Gatheral 2010)
-------------------------------------------
The mid-price is modeled as a sum of decaying impact contributions from past
signed order flow plus a martingale noise term:

        m_t = m_0 + sum_{s < t} G(t - s) * f_s  + noise_t

where f_s = epsilon_s * sqrt(v_s / V_s) is the signed, volume-weighted flow of
fill s (epsilon = +1 buyer-initiated, -1 seller-initiated; V_s a volume
normalizer such as trailing ADV).

CALIBRATION (two stages)
------------------------
Stage A -- nonparametric response: estimate the kernel coefficients G(tau) at
   each lag by regressing forward mid-price changes on signed flow, using the
   single-impact (response-function) estimator. Robust, assumption-light.
Stage B -- parametric fit: fit the power-law form to the Stage-A coefficients by
   weighted nonlinear least squares, returning (G0, beta, tau0) with the
   no-arbitrage constraint 0 < beta < 1 (Gatheral).

The two-stage approach is deliberate: Stage A is transparent and lets you SEE
the empirical kernel shape (and whether a power law is even appropriate) before
committing to the parametric form in Stage B.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.optimize import curve_fit
from scipy.stats import t as student_t


# ────────────────────────────────────────────────────────────────────────────
# Input data contract
# ────────────────────────────────────────────────────────────────────────────
# Expected columns in the fills DataFrame (one row per child fill):
#   parent_id      : identifier grouping child fills into a parent order
#   ts             : timestamp (datetime or monotonically increasing int)
#   price          : execution price of the fill
#   size           : fill size (shares/contracts/base units)
#   side           : +1 if the PARENT is a buy, -1 if sell  (intention sign)
#   aggressor      : +1 if this fill took liquidity (crossed), -1 if passive
#   mid            : prevailing mid-price at the time of the fill
#   adv            : trailing average daily volume for the symbol (normalizer)
#
# The mid-price PATH (for forward returns) can be supplied either as the `mid`
# column sampled at fill times (simplest), or as a separate higher-resolution
# series. Here we use fill-time mids for a self-contained implementation.


@dataclass
class CalibratedPropagator:
    G0: float
    beta: float
    tau0: float
    # diagnostics
    lags: np.ndarray
    empirical_kernel: np.ndarray
    fitted_kernel: np.ndarray
    r2: float
    param_se: dict          # standard errors on (G0, beta, tau0)
    n_fills: int
    n_parents: int
    flow_sign_convention: str = "parent_intention"

    def predict_kernel(self, tau):
        tau = np.asarray(tau, dtype=float)
        return self.G0 / (1.0 + tau / self.tau0) ** self.beta

    def summary(self) -> str:
        se = self.param_se
        return (
            "Calibrated propagator  G(tau) = G0 / (1 + tau/tau0)^beta\n"
            f"  G0   = {self.G0:.3e}  (SE {se['G0']:.2e})\n"
            f"  beta = {self.beta:.4f}    (SE {se['beta']:.4f})"
            f"   {'[no-arb OK: 0<beta<1]' if 0 < self.beta < 1 else '[WARN: outside (0,1)]'}\n"
            f"  tau0 = {self.tau0:.3f}    (SE {se['tau0']:.3f})\n"
            f"  kernel fit R^2 = {self.r2:.3f}\n"
            f"  calibrated on {self.n_fills:,} fills across {self.n_parents:,} parent orders"
        )


# ────────────────────────────────────────────────────────────────────────────
# Signed, volume-weighted flow
# ────────────────────────────────────────────────────────────────────────────
def compute_signed_flow(fills: pd.DataFrame,
                        sign_source: str = "parent_intention",
                        aggressive_only: bool = False) -> pd.DataFrame:
    """
    Build f_s = epsilon_s * sqrt(v_s / V_s).

    sign_source:
      'parent_intention' -> epsilon = side (the parent's buy/sell intent).
            Correct choice for IMPACT OF YOUR METAORDER: a passive buy fill is
            still part of buying pressure. (See discussion: intention vs aggressor.)
      'aggressor'        -> epsilon = aggressor (who took liquidity).
            Matches the public-data / Lee-Ready convention; treats passive fills
            as opposite-signed. Use to compare with literature calibrated on tape.

    aggressive_only: if True, drop passive fills entirely (calibrate the impact
            of liquidity-taking only). Useful to separate the impact channel from
            the spread/adverse-selection channel.
    """
    df = fills.copy()
    if aggressive_only:
        df = df[df["aggressor"] == 1].copy()

    if sign_source == "parent_intention":
        eps = df["side"].to_numpy(dtype=float)
    elif sign_source == "aggressor":
        eps = df["aggressor"].to_numpy(dtype=float)
    else:
        raise ValueError(f"unknown sign_source {sign_source!r}")

    vol_norm = np.sqrt(np.clip(df["size"].to_numpy() / df["adv"].to_numpy(), 0, None))
    df["flow"] = eps * vol_norm
    return df


# ────────────────────────────────────────────────────────────────────────────
# Stage A -- nonparametric kernel via the response-function estimator
# ────────────────────────────────────────────────────────────────────────────
def estimate_empirical_kernel(fills: pd.DataFrame,
                              max_lag: int = 30,
                              within_parent: bool = True) -> tuple:
    """
    Estimate the propagator kernel G(tau) for tau = 1..max_lag.

    IMPORTANT -- why this is a multivariate regression, not a per-lag slope:
        The single-trade response function R(tau) = E[(m_{i+tau}-m_i) * f_i]
        EQUALS the kernel G(tau) only when order flow is uncorrelated. Real
        metaorder flow is strongly sign-autocorrelated (Lillo-Farmer long
        memory), and WITHIN a parent order it is almost perfectly persistent.
        A per-lag slope then captures the CUMULATIVE impact of all interleaving
        same-sign fills, producing a spuriously INCREASING "kernel". (This is
        the meta-order / deconvolution problem.)

    Correct estimator: model the one-step mid change as a linear function of the
    history of signed flow,
            dm_i = m_{i+1} - m_i = sum_{k=0..max_lag-1} g_k * f_{i-k} + eps
    and recover the kernel increments g_k by OLS on the design matrix of lagged
    flows. The cumulative kernel is G(tau) = sum_{k<tau} g_k (the impact still
    "on the books" tau steps after a unit flow). This deconvolves the flow
    autocorrelation out of the response.

    within_parent: build lagged-flow rows only from fills within the same parent
        (no bleed across unrelated orders).
    """
    flow = fills["flow"].to_numpy()
    mid = fills["mid"].to_numpy()
    pid = fills["parent_id"].to_numpy()
    n = len(flow)

    # Backward difference: dm[i] = mid[i] - mid[i-1] = dm_DGP[i] (matches design matrix).
    # Forward difference (mid[i+1]-mid[i]) gives dm_DGP[i+1], which depends on flow[i+1]
    # -- one step ahead of the design matrix -- causing a systematic lag misalignment.
    dm = np.empty(n); dm[0] = np.nan; dm[1:] = mid[1:] - mid[:-1]

    # Design matrix X[i, k] = f_{i-k}, valid only when i-k is in the same parent
    X = np.zeros((n, max_lag))
    valid = np.ones(n, dtype=bool)
    valid[0] = False                       # no previous mid for first fill
    # Exclude the first fill of each parent: its backward dm spans two independent
    # mid paths (both starting at base), producing a large spurious price jump.
    valid[1:] &= (pid[1:] == pid[:-1])
    for k in range(max_lag):
        if k == 0:
            X[:, 0] = flow
        else:
            X[k:, k] = flow[:-k]
            X[:k, k] = 0.0
            if within_parent:
                same = np.zeros(n, dtype=bool)
                same[k:] = pid[k:] == pid[:-k]
                X[~same, k] = 0.0          # zero out cross-parent contributions

    # require at least the first lag in-parent to be meaningful
    rows = valid & np.isfinite(dm)
    Xr, yr = X[rows], dm[rows]

    # OLS for the increment coefficients g_k  (mean-center y; flows ~ mean 0)
    yc = yr - yr.mean()
    # normal equations with tiny ridge for numerical stability
    XtX = Xr.T @ Xr + 1e-10 * np.eye(max_lag)
    g = np.linalg.solve(XtX, Xr.T @ yc)

    # cumulative kernel G(tau) = sum_{k < tau} g_k
    G_cum = np.cumsum(g)

    lags = np.arange(1, max_lag + 1)
    nobs = np.full(max_lag, rows.sum(), dtype=int)
    return lags, G_cum, nobs


# ────────────────────────────────────────────────────────────────────────────
# Stage B -- parametric power-law fit with no-arbitrage constraint
# ────────────────────────────────────────────────────────────────────────────
def _power_law(tau, G0, beta, tau0):
    return G0 / (1.0 + tau / tau0) ** beta


def fit_power_law(lags: np.ndarray,
                  coefs: np.ndarray,
                  nobs: np.ndarray = None) -> tuple:
    """
    Weighted NLS fit of G(tau)=G0/(1+tau/tau0)^beta to the empirical coefficients.
    Weights by sqrt(nobs) (more-observed lags trusted more). Enforces 0<beta<1
    and positive G0, tau0 via bounds (Gatheral no-dynamic-arbitrage).
    Returns (params dict, standard-error dict, fitted curve, r2).
    """
    mask = np.isfinite(coefs)
    x, y = lags[mask].astype(float), coefs[mask]
    w = np.sqrt(nobs[mask]) if nobs is not None else np.ones_like(y)
    sigma = 1.0 / np.clip(w, 1e-6, None)     # curve_fit uses sigma (inverse weight)

    p0 = [max(y[0], 1e-6), 0.5, 5.0]
    bounds = ([1e-10, 1e-3, 1e-2], [np.inf, 0.999, 1e3])
    popt, pcov = curve_fit(_power_law, x, y, p0=p0, sigma=sigma,
                           absolute_sigma=False, bounds=bounds, maxfev=20000)

    fitted = _power_law(lags.astype(float), *popt)
    # R^2 on the observed lags
    resid = y - _power_law(x, *popt)
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    se = np.sqrt(np.diag(pcov)) if np.all(np.isfinite(pcov)) else np.full(3, np.nan)
    params = {"G0": popt[0], "beta": popt[1], "tau0": popt[2]}
    param_se = {"G0": se[0], "beta": se[1], "tau0": se[2]}
    return params, param_se, fitted, r2


# ────────────────────────────────────────────────────────────────────────────
# Top-level driver
# ────────────────────────────────────────────────────────────────────────────
def calibrate_propagator(fills: pd.DataFrame,
                         max_lag: int = 30,
                         sign_source: str = "parent_intention",
                         aggressive_only: bool = False,
                         within_parent: bool = True) -> CalibratedPropagator:
    """
    End-to-end calibration. See module docstring for the data contract.
    """
    required = {"parent_id", "ts", "price", "size", "side",
                "aggressor", "mid", "adv"}
    missing = required - set(fills.columns)
    if missing:
        raise ValueError(f"fills is missing required columns: {sorted(missing)}")

    # sort by parent then time so lags are within-order and chronological
    fills = fills.sort_values(["parent_id", "ts"]).reset_index(drop=True)

    flow_df = compute_signed_flow(fills, sign_source=sign_source,
                                  aggressive_only=aggressive_only)
    lags, coefs, nobs = estimate_empirical_kernel(
        flow_df, max_lag=max_lag, within_parent=within_parent)
    params, param_se, fitted, r2 = fit_power_law(lags, coefs, nobs)

    return CalibratedPropagator(
        G0=params["G0"], beta=params["beta"], tau0=params["tau0"],
        lags=lags, empirical_kernel=coefs, fitted_kernel=fitted, r2=r2,
        param_se=param_se,
        n_fills=len(flow_df), n_parents=int(flow_df["parent_id"].nunique()),
        flow_sign_convention=sign_source,
    )


# ────────────────────────────────────────────────────────────────────────────
# Bridge to the config-selection layer
# ────────────────────────────────────────────────────────────────────────────
def to_propagator_params(cal: CalibratedPropagator):
    """
    Convert a CalibratedPropagator into the PropagatorParams used by
    dr_config_selection.build_pretrade_features(). Keeps the two modules
    decoupled (no hard import dependency).
    """
    from dr_config_selection import PropagatorParams
    return PropagatorParams(G0=cal.G0, beta=cal.beta, tau0=cal.tau0)
