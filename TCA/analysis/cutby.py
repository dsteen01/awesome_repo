"""
analysis/cutby.py — CutBy sensitivity analysis panels.

Functions
---------
CreateCutBy(df, sub_df_init, KPI, TimeBin, nbins, cut_by_cols, ...)
    For every feature in *cut_by_cols* produce a three-panel Matplotlib
    figure (time-series, KPI scatter, histogram) and return a dict mapping
    feature name → ReportLab Image flowable.

ConsolidatedCutBy(df, sub_df_init, KPI, nbins, cut_by_cols, ...)
    Streamlined variant: one dual-axis figure per feature showing KPI mean
    (left y-axis) and weight percentage (right y-axis) across quantile bins.
    The temporal panel is omitted.
"""

from __future__ import annotations

# analysis/__init__.py already added the local tableone path to sys.path.
import analysis  # noqa: F401 — ensure __init__.py side-effects run

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from tableone import TableOne

from data.transforms import resolve_time_grouping
from report.components import fig2image


def CreateCutBy(
    df: pd.DataFrame,
    sub_df_init: list,
    KPI: str,
    TimeBin: str = 'Daily',
    nbins: int = 5,
    cut_by_cols: list | None = None,
    weighting: list | None = None,
    sum_cols: list | None = None,
    grouping: str | None = None,
) -> dict:
    """Run CutBy analysis and return one figure per feature.

    For each feature in *cut_by_cols* the function produces a 1 × 3 figure:

    * **Left panel** — feature mean ± SEM over time.
    * **Centre panel** — KPI vs. quantile bin of feature (mean ± SEM per bin).
    * **Right panel** — feature histogram.

    Args:
        df:          Transformed trade-level DataFrame.
        sub_df_init: Base columns always included in each feature sub-frame
                     (must contain the date column, weight column, and KPI).
        KPI:         Key-performance-indicator column name.
        TimeBin:     ``'Daily'`` or ``'Weekly'`` time granularity.
        nbins:       Number of quantile bins.
        cut_by_cols: Feature columns to analyse.  Defaults to ``[]``.
        weighting:   Weight column(s) for TableOne.  Defaults to ``[]``.
        sum_cols:    Columns for which TableOne computes sums.  Defaults to ``[]``.
        grouping:    Optional grouping column (currently unused in CutBy but
                     accepted for API symmetry).

    Returns:
        ``{feature_name: ReportLab Image flowable}`` dict.
    """
    if cut_by_cols is None:
        cut_by_cols = []
    if weighting is None:
        weighting = []
    if sum_cols is None:
        sum_cols = []

    # resolve_time_grouping always returns a *copy*, so the caller's df is
    # never mutated, and tmp_grouping is correct for both Daily and Weekly.
    df, tmp_grouping = resolve_time_grouping(df, TimeBin)

    all_cutbys: dict = {}

    for feature in cut_by_cols:
        # Explicit .copy() so the 'Bin' assignment below stays local.
        sub_df = df[sub_df_init + [feature]].copy()

        sub_df['Bin'] = pd.qcut(sub_df[feature], q=nbins, labels=False,duplicates='drop')

        # ── Temporal evolution of the feature ────────────────────────────────
        temporal_tbl = TableOne(sub_df, columns=[feature], pval=False,
                                weights=weighting, sum_cols=weighting,
                                groupby=tmp_grouping)
        feat_ts = temporal_tbl.cont_describe.loc[
            :, (['wt_mean', 'wt_err'], slice(None))
        ]
        feat_ts = feat_ts.T.sort_index(level=1, ascending=False)
        t_means  = feat_ts.loc['wt_mean'].reset_index().melt(id_vars=[feat_ts.loc['wt_mean'].index.name])
        t_sigmas = feat_ts.loc['wt_err'].reset_index().melt(id_vars=[feat_ts.loc['wt_err'].index.name])
        t_means.rename(columns={'value': 'mean'}, inplace=True)
        t_sigmas.rename(columns={'value': 'SEM'},  inplace=True)
        temp_melted = pd.merge(t_means, t_sigmas, on=[tmp_grouping, 'variable'])

        # ── KPI sensitivity to quantile bins of the feature ──────────────────
        notional_tbl = TableOne(sub_df, columns=[feature, KPI], pval=False,
                                weights=weighting, sum_cols=weighting, groupby='Bin')
        feat_cb = notional_tbl.cont_describe.loc[
            :, (['wt_mean', 'wt_err'], slice(None))
        ]
        feat_cb = feat_cb.T.sort_index(level=1, ascending=False)
        n_means  = feat_cb.loc['wt_mean']
        n_sigmas = feat_cb.loc['wt_err']
        n_sigmas.columns = [col + 'SEM' for col in n_sigmas.columns]
        notional_final = pd.concat([n_means, n_sigmas], axis=1)

        # ── 1 × 3 figure ─────────────────────────────────────────────────────
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(9.9, 3))

        ax1.errorbar(tmp_grouping, 'mean', yerr='SEM',
                     data=temp_melted, fmt='o', capsize=5)
        ax1.set_title(f'{feature} vs. Time')
        ax1.set_xlabel('Date')
        ax1.set_ylabel(feature)

        ax2.errorbar(feature, KPI, yerr=KPI + 'SEM',
                     data=notional_final, fmt='o', capsize=5)
        ax2.set_title(f'{feature} vs. {KPI}')
        ax2.set_xlabel(feature)
        ax2.set_ylabel(KPI)

        sns.histplot(data=sub_df, x=feature, ax=ax3)
        ax3.set_title(f'{feature} Histogram')

        plt.tight_layout(pad=2.0)
        all_cutbys[feature] = fig2image(fig)
        plt.close(fig)

    return all_cutbys


def ConsolidatedCutBy(
    df: pd.DataFrame,
    sub_df_init: list,
    KPI: str,
    nbins: int = 5,
    cut_by_cols: list | None = None,
    weighting: list | None = None,
    sum_cols: list | None = None,
    grouping: str | None = None,
) -> dict:
    """Run CutBy analysis and return one consolidated dual-axis figure per feature.

    For each feature in *cut_by_cols* produces a single figure combining the
    KPI sensitivity panel with a weight-distribution overlay:

    * **Left y-axis** — KPI weighted mean ± SEM per quantile bin of the feature.
    * **Right y-axis** — percentage of total notional weight in each bin (bars).

    The temporal (time-series) panel from :func:`CreateCutBy` is omitted.

    Args:
        df:          Transformed trade-level DataFrame.
        sub_df_init: Base columns always included in each feature sub-frame.
        KPI:         Key-performance-indicator column name.
        nbins:       Number of quantile bins.
        cut_by_cols: Feature columns to analyse.  Defaults to ``[]``.
        weighting:   Weight column(s) for TableOne.  Defaults to ``[]``.
        sum_cols:    Columns for which TableOne computes sums.  Defaults to ``[]``.
        grouping:    Optional grouping column (accepted for API symmetry).

    Returns:
        ``{feature_name: ReportLab Image flowable}`` dict.
    """
    if cut_by_cols is None:
        cut_by_cols = []
    if weighting is None:
        weighting = []
    if sum_cols is None:
        sum_cols = []

    weight_col = weighting[0] if weighting else None
    all_cutbys: dict = {}

    for feature in cut_by_cols:
        sub_df = df[sub_df_init + [feature]].copy()
        sub_df['Bin'] = pd.qcut(sub_df[feature], q=nbins, labels=False, duplicates='drop')

        # ── KPI sensitivity to quantile bins of the feature ──────────────────
        notional_tbl = TableOne(sub_df, columns=[feature, KPI], pval=False,
                                weights=weighting, sum_cols=weighting, groupby='Bin')
        feat_cb = notional_tbl.cont_describe.loc[
            :, (['wt_mean', 'wt_err'], slice(None))
        ]
        feat_cb = feat_cb.T.sort_index(level=1, ascending=True)
        n_means  = feat_cb.loc['wt_mean']
        n_sigmas = feat_cb.loc['wt_err']
        n_sigmas.columns = [col + 'SEM' for col in n_sigmas.columns]
        notional_final = pd.concat([n_means, n_sigmas], axis=1)

        # ── Weight percentage per bin ─────────────────────────────────────────
        if weight_col and weight_col in sub_df.columns:
            bin_weights = sub_df.groupby('Bin')[weight_col].sum()
        else:
            bin_weights = sub_df.groupby('Bin').size()
        weight_pct = (100 * bin_weights / bin_weights.sum()).reindex(
            notional_final.index, fill_value=0
        )

        # ── Bin range labels (min – max of feature values per bin) ───────────
        bin_ranges = sub_df.groupby('Bin')[feature].agg(['min', 'max'])
        bin_ranges = bin_ranges.reindex(notional_final.index)
        tick_labels = [
            f"{row['min']:.1f}–{row['max']:.1f}"
            for _, row in bin_ranges.iterrows()
        ]

        # ── Dual-axis figure ──────────────────────────────────────────────────
        fig, ax_kpi = plt.subplots(figsize=(6, 3.5))
        ax_wt = ax_kpi.twinx()

        bins = notional_final.index.tolist()

        ax_wt.bar(bins, weight_pct, alpha=0.3, color='tab:orange', label='Weight %')
        ax_wt.set_ylabel('Weight (%)')

        ax_kpi.errorbar(bins, notional_final[KPI], yerr=notional_final[KPI + 'SEM'],
                        fmt='o', capsize=5, color='tab:blue', label=KPI, zorder=3)
        ax_kpi.set_xticks(bins)
        ax_kpi.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=7)
        ax_kpi.set_ylabel(KPI)
        ax_kpi.set_xlabel(feature)
        ax_kpi.set_title(f'{feature} vs. {KPI}')

        plt.tight_layout(pad=2.0)
        all_cutbys[feature] = fig2image(fig)
        plt.close(fig)

    return all_cutbys
