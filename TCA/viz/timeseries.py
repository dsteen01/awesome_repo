"""
viz/timeseries.py — Feature time-series visualisation.

Functions
---------
CreateFeatureTS(df, dim, features, weighting, sum_cols)
    Plot weighted mean ± SEM for every feature over time (Daily or Weekly)
    using a seaborn FacetGrid of error-bar charts.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure TCA/tableone/ is at sys.path[0] so "import tableone" resolves to
# TCA/tableone/tableone/ (the actual package) not TCA/tableone/__init__.py.
_TABLEONE_PATH = str(Path(__file__).resolve().parent.parent / 'tableone')
if sys.path[0] != _TABLEONE_PATH:
    sys.path.insert(0, _TABLEONE_PATH)

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from tableone import TableOne

from data.transforms import resolve_time_grouping
from report.components import fig2image


def CreateFeatureTS(
    df: pd.DataFrame,
    dim: str = 'Daily',
    features: list | None = None,
    weighting: list | None = None,
    sum_cols: list | None = None,
):
    """Plot a weighted mean ± SEM time series for every feature.

    Args:
        df:        Transformed trade-level DataFrame.
        dim:       ``'Daily'`` or ``'Weekly'`` time granularity.
        features:  Columns to plot.  Defaults to ``[]``.
        weighting: Weight column(s) for TableOne.  Defaults to ``[]``.
        sum_cols:  Columns for which TableOne computes sums.  Defaults to ``[]``.

    Returns:
        Seaborn ``FacetGrid`` (caller can render or save as required).

    References
    ----------
    https://stackoverflow.com/questions/45875143
    https://stackoverflow.com/questions/24878095
    """
    if features is None:
        features = []
    if weighting is None:
        weighting = []
    if sum_cols is None:
        sum_cols = []

    df, tmp_grouping = resolve_time_grouping(df, dim)

    date_tbl = TableOne(df, columns=features, pval=False,
                        weights=weighting, sum_cols=sum_cols,
                        groupby=tmp_grouping)
    feat_ts = date_tbl.cont_describe.loc[
        :, (['wt_mean', 'wt_err'], slice(None))
    ]
    feat_ts = feat_ts.T.sort_index(level=1, ascending=False)

    means = feat_ts.loc['wt_mean'].reset_index().melt(id_vars=[feat_ts.loc['wt_mean'].index.name])
    sigma = feat_ts.loc['wt_err'].reset_index().melt(id_vars=[feat_ts.loc['wt_err'].index.name])
    means.rename(columns={'value': 'mean'}, inplace=True)
    sigma.rename(columns={'value': 'SEM'},  inplace=True)

    melted = pd.merge(means, sigma, on=[tmp_grouping, 'variable'])

    g = sns.FacetGrid(melted, col='variable', sharex=False, sharey=False)
    g.map(plt.errorbar, tmp_grouping, 'mean', 'SEM', marker='o')
    g.fig.tight_layout()
    g.set_xticklabels(rotation=45)

    return g
