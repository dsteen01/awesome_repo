"""
Doubly-Robust learner for execution algo-config selection.
================================================================

Estimates the heterogeneous causal effect of execution algorithm CONFIGURATION
on implementation shortfall (IS), using ONLY pre-trade features -- including
a propagator-derived impact forecast computed at arrival.

Design principles (see accompanying discussion):
  * The propagator enters ONLY as a pre-trade covariate (a forecast), never as
    a function of realized fills. This keeps it a legitimate confounder-adjuster
    rather than a post-treatment MEDIATOR.
  * Cross-fitting (a.k.a. double machine learning, Chernozhukov et al. 2018):
    nuisance models (outcome mu, propensity e) are fit on held-out folds so that
    the pseudo-outcome is orthogonalized and not biased by overfitting.
  * Doubly robust: the effect estimate is consistent if EITHER the outcome model
    OR the propensity model is correctly specified.

Outcome convention: IS is a COST in basis points (lower is better). The policy
therefore picks the config with the *minimum* predicted cost.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.base import clone


# ────────────────────────────────────────────────────────────────────────────
# 1. PROPAGATOR PRE-TRADE FEATURE BUILDER
#    Computes predicted impact (bps) at ARRIVAL under the calibrated kernel,
#    for a reference schedule. Uses only size/ADV/vol/horizon -- NO realized fills.
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class PropagatorParams:
    """Calibrated kernel G(tau) = G0 / (1 + tau/tau0)^beta (from your ITCH/Binance fit)."""
    G0: float = 8.0e-4     # impact scale
    beta: float = 0.55     # decay exponent (no-arb: 0<beta<1)
    tau0: float = 5.0      # crossover lag in (schedule) steps


def predicted_impact_bps(size_pct_adv: np.ndarray,
                         volatility: np.ndarray,
                         horizon_steps: int,
                         schedule: str,
                         p: PropagatorParams) -> np.ndarray:
    """
    Forecast impact cost (bps) for a *reference* execution schedule under the
    propagator kernel. This is a PRE-TRADE prediction: it answers "if we ran a
    TWAP/front-loaded/POV schedule of this size, what impact would the kernel
    imply?" -- a structured, low-variance summary of order difficulty.

    The cost functional for a deterministic schedule {x_s} is
        C = sum_{s<=t} G(t-s) * w_s * w_t,   w_s = sign * sqrt(v_s / V)
    Here we evaluate it for a unit parent order split according to `schedule`,
    then scale by size and volatility to get bps.
    """
    n = max(int(horizon_steps), 1)
    steps = np.arange(n)

    # Reference participation weights over the horizon (sum to 1)
    if schedule == "twap":
        w = np.ones(n) / n
    elif schedule == "front":          # front-loaded: linearly decreasing
        raw = np.linspace(n, 1, n); w = raw / raw.sum()
    elif schedule == "back":           # back-loaded: linearly increasing
        raw = np.linspace(1, n, n); w = raw / raw.sum()
    elif schedule == "pov":            # proxy: U-shaped (heavier at open/close)
        raw = (steps - (n - 1) / 2) ** 2 + n; w = raw / raw.sum()
    else:
        raise ValueError(f"unknown schedule {schedule!r}")

    # Propagator double-sum on the *shape* (size-independent kernel interaction)
    # tau = |t - s|, kernel decays with lag
    tt, ss = np.meshgrid(steps, steps, indexing="ij")
    tau = np.abs(tt - ss)
    G = p.G0 / (1.0 + tau / p.tau0) ** p.beta
    shape_cost = float(w @ G @ w)          # scalar: kernel-weighted schedule cost

    # Scale: impact ~ shape_cost * sqrt(participation) * vol, expressed in bps.
    # sqrt-law in size enters via sqrt(size_pct_adv); vol scales the price moves.
    impact = shape_cost * np.sqrt(np.clip(size_pct_adv, 0, None)) * volatility
    return impact * 1e4   # to bps


def build_pretrade_features(df: pd.DataFrame, p: PropagatorParams) -> pd.DataFrame:
    """
    Assemble phi(x): raw arrival-time context + propagator forecasts.
    Expected raw columns in df:
        size_pct_adv, volatility, arrival_spread_bps, momentum,
        imbalance, time_of_day, horizon_steps  (+ any categoricals already encoded)
    """
    feat = pd.DataFrame(index=df.index)

    # Raw confounders (drive both config choice AND cost)
    for col in ["size_pct_adv", "volatility", "arrival_spread_bps",
                "momentum", "imbalance", "time_of_day"]:
        if col in df:
            feat[col] = df[col].astype(float)

    # Propagator-derived forecasts under several reference schedules.
    # These linearize the hardest (size x liquidity) part of the cost surface,
    # letting the estimator spend capacity on the CONFIG effect instead.
    hs = int(df["horizon_steps"].median()) if "horizon_steps" in df else 10
    for sched in ["twap", "front", "back", "pov"]:
        feat[f"pred_impact_{sched}"] = predicted_impact_bps(
            df["size_pct_adv"].to_numpy(),
            df["volatility"].to_numpy(),
            hs, sched, p,
        )
    # The *spread* across schedules is itself informative: how much does
    # loading choice matter for this order? (large for big/illiquid orders)
    sched_cols = [f"pred_impact_{s}" for s in ["twap", "front", "back", "pov"]]
    feat["pred_impact_dispersion"] = feat[sched_cols].std(axis=1)

    return feat


# ────────────────────────────────────────────────────────────────────────────
# 2. CROSS-FITTED DOUBLY-ROBUST LEARNER  (multi-arm, one-vs-rest pseudo-outcome)
# ────────────────────────────────────────────────────────────────────────────
@dataclass
class DRConfigLearner:
    configs: list                       # e.g. ["passive", "balanced", "aggressive"]
    n_folds: int = 5
    propensity_clip: float = 0.02       # trim to enforce overlap/positivity
    outcome_model: object = None
    propensity_model: object = None
    random_state: int = 0

    # filled after fit
    tau_models_: dict = field(default_factory=dict)   # config -> effect model vs baseline
    baseline_: str = None
    _oof_mu: dict = field(default_factory=dict)
    _oof_e: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.outcome_model is None:
            self.outcome_model = GradientBoostingRegressor(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, random_state=self.random_state)
        if self.propensity_model is None:
            self.propensity_model = GradientBoostingClassifier(
                n_estimators=200, max_depth=3, learning_rate=0.05,
                subsample=0.8, random_state=self.random_state)

    # ---- nuisance estimation with cross-fitting ----------------------------
    def _cross_fit_nuisances(self, X, A, Y):
        """
        Produce out-of-fold predictions for:
          mu_a(x) = E[Y | X=x, A=a]   (one outcome model per config, OOF)
          e_a(x)  = P(A=a | X=x)      (multiclass propensity, OOF)
        OOF prediction is what makes the later pseudo-outcome orthogonal.
        """
        n = len(Y)
        idx_config = {c: i for i, c in enumerate(self.configs)}
        A_idx = A.map(idx_config).to_numpy()

        skf = StratifiedKFold(n_splits=self.n_folds, shuffle=True,
                              random_state=self.random_state)

        # propensity: one multiclass model, OOF probabilities
        e_oof = np.zeros((n, len(self.configs)))
        for tr, te in skf.split(X, A_idx):
            clf = clone(self.propensity_model)
            clf.fit(X.iloc[tr], A_idx[tr])
            # align predicted columns to self.configs order
            proba = np.zeros((len(te), len(self.configs)))
            for j, cls in enumerate(clf.classes_):
                proba[:, cls] = clf.predict_proba(X.iloc[te])[:, j]
            e_oof[te] = proba
        e_oof = np.clip(e_oof, self.propensity_clip, 1 - self.propensity_clip)

        # outcome: per-config model, OOF predictions for ALL rows
        # (we need mu_a(x) for every x and every a, regardless of realized A)
        mu_oof = {c: np.zeros(n) for c in self.configs}
        for c in self.configs:
            ci = idx_config[c]
            mask = A_idx == ci
            # Fit on rows that took config c; predict OOF for all rows.
            # Use KFold over the c-subset for the fitted part, and a global
            # model for rows outside c (predicted by models trained on c-folds).
            sub_idx = np.where(mask)[0]
            if len(sub_idx) < self.n_folds * 5:
                # too few samples: fall back to a single model on all c-rows
                m = clone(self.outcome_model).fit(X.iloc[sub_idx], Y.iloc[sub_idx])
                mu_oof[c][:] = m.predict(X)
                continue
            # cross-fit within the c-subset for unbiased mu on c-rows...
            skf_c = KFold_indices(len(sub_idx), self.n_folds, self.random_state)
            for tr_s, te_s in skf_c:
                m = clone(self.outcome_model).fit(
                    X.iloc[sub_idx[tr_s]], Y.iloc[sub_idx[tr_s]])
                mu_oof[c][sub_idx[te_s]] = m.predict(X.iloc[sub_idx[te_s]])
            # ...and a full model trained on all c-rows to score the non-c rows
            m_full = clone(self.outcome_model).fit(X.iloc[sub_idx], Y.iloc[sub_idx])
            non_c = np.where(~mask)[0]
            mu_oof[c][non_c] = m_full.predict(X.iloc[non_c])

        self._oof_mu = mu_oof
        self._oof_e = {c: e_oof[:, idx_config[c]] for c in self.configs}
        return mu_oof, e_oof, A_idx

    # ---- doubly-robust pseudo-outcome & effect models ----------------------
    def fit(self, X: pd.DataFrame, A: pd.Series, Y: pd.Series, baseline: str = None):
        """
        X : pre-trade features phi(x)  (DataFrame)
        A : realized config per order  (Series of strings in self.configs)
        Y : realized implementation shortfall in bps (Series, COST)
        """
        self.baseline_ = baseline or self.configs[0]
        mu_oof, e_oof, A_idx = self._cross_fit_nuisances(X, A, Y)
        idx_config = {c: i for i, c in enumerate(self.configs)}

        base = self.baseline_
        for c in self.configs:
            if c == base:
                continue
            # DR pseudo-outcome for the contrast (c vs baseline), per order i:
            #   psi = [mu_c - mu_base]
            #         + 1{A=c}/e_c   * (Y - mu_c)
            #         - 1{A=base}/e_base * (Y - mu_base)
            mu_c, mu_b = mu_oof[c], mu_oof[base]
            e_c, e_b = self._oof_e[c], self._oof_e[base]
            ind_c = (A_idx == idx_config[c]).astype(float)
            ind_b = (A_idx == idx_config[base]).astype(float)

            psi = (mu_c - mu_b
                   + ind_c / e_c * (Y.to_numpy() - mu_c)
                   - ind_b / e_b * (Y.to_numpy() - mu_b))

            # Regress pseudo-outcome on features -> heterogeneous effect tau_c(x)
            tau_model = clone(self.outcome_model)
            tau_model.fit(X, psi)
            self.tau_models_[c] = tau_model
        return self

    # ---- effects, policy, and OPE ------------------------------------------
    def effect(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return tau_c(x) = cost(c) - cost(baseline) for each non-baseline config."""
        out = pd.DataFrame(index=X.index)
        out[self.baseline_] = 0.0
        for c, m in self.tau_models_.items():
            out[c] = m.predict(X)
        return out[self.configs]

    def recommend(self, X: pd.DataFrame) -> pd.Series:
        """Policy pi(x): pick the MIN-cost config (effects are cost vs baseline)."""
        eff = self.effect(X)
        return eff.idxmin(axis=1)

    def evaluate_policy(self, X, A, Y, policy: pd.Series = None) -> dict:
        """
        Doubly-robust off-policy value of `policy` (default: this learner's own).
        Returns estimated mean IS (bps) under the policy + bootstrap 95% CI.
        Lower is better.
        """
        if policy is None:
            policy = self.recommend(X)
        idx_config = {c: i for i, c in enumerate(self.configs)}
        A_idx = A.map(idx_config).to_numpy()
        pol_idx = policy.map(idx_config).to_numpy()

        # DR value:  V = mu_{pi(x)}(x) + 1{A=pi(x)}/e_{pi(x)} (Y - mu_{pi(x)})
        n = len(Y)
        mu_pi = np.array([self._oof_mu[policy.iloc[i]][i] for i in range(n)])
        e_pi = np.array([self._oof_e[policy.iloc[i]][i] for i in range(n)])
        ind = (A_idx == pol_idx).astype(float)
        scores = mu_pi + ind / e_pi * (Y.to_numpy() - mu_pi)

        rng = np.random.default_rng(self.random_state)
        boot = [scores[rng.integers(0, n, n)].mean() for _ in range(1000)]
        return {
            "dr_value_bps": float(scores.mean()),
            "ci95_bps": (float(np.percentile(boot, 2.5)),
                         float(np.percentile(boot, 97.5))),
            "naive_logged_bps": float(Y.mean()),
        }


def KFold_indices(n, k, seed):
    """Simple KFold returning (train_idx, test_idx) over range(n)."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    folds = np.array_split(perm, k)
    for i in range(k):
        te = folds[i]
        tr = np.concatenate([folds[j] for j in range(k) if j != i])
        yield tr, te
