"""
Covariate balance diagnostics for propensity-score adjustment.
==============================================================

PyWhy/DoWhy provides propensity-score matching and weighting ESTIMATORS, but no
built-in balance table. Balance -- whether the treated and control groups have
similar covariate distributions AFTER adjustment -- is the key diagnostic for
whether the adjustment actually removed confounding. A doubly-robust or IPW
estimate is only trustworthy if balance is achieved.

This module computes the standardized mean difference (SMD) per covariate:

    SMD = (mean_treated - mean_control) / sqrt((var_treated + var_control)/2)

reported BEFORE adjustment (raw) and AFTER (via nearest-neighbour PS matching
and via IPW weighting). The usual rule of thumb: |SMD| < 0.1 indicates good
balance; 0.1-0.25 marginal; > 0.25 poor.

Treatment must be BINARY for a clean two-group balance comparison. For our
multi-config setting we binarize one-config-vs-rest (e.g. aggressive vs not),
which is also how the DoWhy refuters in demo_pywhy.py operate.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


def _smd(treated_vals: np.ndarray, control_vals: np.ndarray,
         w_t: np.ndarray = None, w_c: np.ndarray = None) -> float:
    """Standardized mean difference, optionally weighted."""
    if w_t is None:
        mt, vt = treated_vals.mean(), treated_vals.var()
        mc, vc = control_vals.mean(), control_vals.var()
    else:
        mt = np.average(treated_vals, weights=w_t)
        mc = np.average(control_vals, weights=w_c)
        vt = np.average((treated_vals - mt) ** 2, weights=w_t)
        vc = np.average((control_vals - mc) ** 2, weights=w_c)
    pooled = np.sqrt((vt + vc) / 2.0)
    return (mt - mc) / pooled if pooled > 0 else 0.0


def estimate_propensity(X: pd.DataFrame, treat: np.ndarray, model=None) -> np.ndarray:
    """
    Binary propensity P(treat=1 | X).

    model=None -> logistic regression (fast, but LINEAR; will MISSPECIFY
        threshold/non-linear assignment, which the balance table will then
        reveal as failure to balance after IPW).
    Pass a flexible classifier (e.g. GradientBoostingClassifier) to capture
        non-linear assignment and achieve IPW balance.
    """
    if model is None:
        Xs = (X - X.mean()) / X.std(ddof=0)
        lr = LogisticRegression(max_iter=2000, C=1e6)
        lr.fit(Xs, treat)
        return lr.predict_proba(Xs)[:, 1]
    from sklearn.base import clone
    m = clone(model).fit(X, treat)
    return m.predict_proba(X)[:, 1]


def nn_match(ps: np.ndarray, treat: np.ndarray, caliper: float = None):
    """
    1:1 nearest-neighbour matching on the propensity score (with optional
    caliper). Returns indices of matched treated and matched control rows.
    Simple greedy matching without replacement.
    """
    t_idx = np.where(treat == 1)[0]
    c_idx = np.where(treat == 0)[0]
    c_ps = ps[c_idx]
    used = np.zeros(len(c_idx), dtype=bool)

    matched_t, matched_c = [], []
    # default caliper: 0.2 * sd(logit(ps)) (Austin's rule of thumb)
    if caliper is None:
        logit = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / np.clip(1 - ps, 1e-6, 1))
        caliper = 0.2 * logit.std()

    for ti in t_idx:
        d = np.abs(c_ps - ps[ti])
        d[used] = np.inf
        j = np.argmin(d)
        if d[j] <= caliper:
            matched_t.append(ti)
            matched_c.append(c_idx[j])
            used[j] = True
    return np.array(matched_t), np.array(matched_c)


def ipw_weights(ps: np.ndarray, treat: np.ndarray, stabilized: bool = True):
    """ATE inverse-propensity weights (optionally stabilized)."""
    ps = np.clip(ps, 1e-3, 1 - 1e-3)
    w = np.where(treat == 1, 1.0 / ps, 1.0 / (1.0 - ps))
    if stabilized:
        p_treat = treat.mean()
        w = np.where(treat == 1, p_treat * w, (1 - p_treat) * w)
    return w


def balance_table(X: pd.DataFrame, treat: np.ndarray,
                  ps: np.ndarray = None, caliper: float = None,
                  propensity_model=None) -> pd.DataFrame:
    """
    Build a covariate-balance table: |SMD| before adjustment, after NN matching,
    and after IPW weighting, for every column of X.

    propensity_model: optional sklearn classifier for the propensity score. If
        None and ps is None, uses logistic regression (linear -- may misspecify).
    """
    if ps is None:
        ps = estimate_propensity(X, treat, model=propensity_model)

    cols = list(X.columns)
    t_mask = treat == 1
    c_mask = treat == 0

    # before
    before = {col: abs(_smd(X[col].to_numpy()[t_mask],
                            X[col].to_numpy()[c_mask])) for col in cols}

    # after matching
    mt, mc = nn_match(ps, treat, caliper)
    if len(mt) > 0:
        after_match = {col: abs(_smd(X[col].to_numpy()[mt],
                                     X[col].to_numpy()[mc])) for col in cols}
    else:
        after_match = {col: np.nan for col in cols}

    # after IPW
    w = ipw_weights(ps, treat)
    after_ipw = {}
    for col in cols:
        v = X[col].to_numpy()
        after_ipw[col] = abs(_smd(v[t_mask], v[c_mask],
                                  w_t=w[t_mask], w_c=w[c_mask]))

    tbl = pd.DataFrame({
        "smd_before": before,
        "smd_after_match": after_match,
        "smd_after_ipw": after_ipw,
    })
    tbl["matched_pairs"] = len(mt)
    return tbl.round(4)


def balance_summary(tbl: pd.DataFrame, threshold: float = 0.1) -> dict:
    """Summarize a balance table against the |SMD|<threshold rule of thumb."""
    def frac_ok(col):
        v = tbl[col].dropna()
        return float((v < threshold).mean()) if len(v) else np.nan
    return {
        "threshold": threshold,
        "max_smd_before": float(tbl["smd_before"].max()),
        "max_smd_after_match": float(tbl["smd_after_match"].max()),
        "max_smd_after_ipw": float(tbl["smd_after_ipw"].max()),
        "frac_balanced_before": frac_ok("smd_before"),
        "frac_balanced_after_match": frac_ok("smd_after_match"),
        "frac_balanced_after_ipw": frac_ok("smd_after_ipw"),
    }
