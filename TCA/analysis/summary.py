"""
analysis/summary.py — TableOne-based cover-page summary table.

Functions
---------
CreateCoverPageTable(data, weighting, features, grouping, sumcols)
    Build side-by-side Raw / Winsorized TableOne summaries and return a
    styled ReportLab Table flowable plus the underlying DataFrame.
"""

from __future__ import annotations

# analysis/__init__.py already added the local tableone path to sys.path.
import analysis  # noqa: F401 — ensure __init__.py side-effects run

import pandas as pd
from reportlab.lib import colors
from tableone import TableOne

from data.filters import CreateOutlierFrame
from report.components import df2table


def CreateCoverPageTable(
    data: pd.DataFrame,
    weighting: list,
    features: list | None = None,
    grouping: str | None = None,
    sumcols: list | None = None,
):
    """Build a side-by-side Raw / Winsorized summary table for the cover page.

    Args:
        data:      Transformed trade-level DataFrame.
        weighting: Column name(s) used as analytic weights (e.g. exec value).
        features:  Numeric feature columns to include.  Defaults to ``[]``.
        grouping:  Optional column to split the table by (e.g. ``'trader_id'``).
        sumcols:   Columns for which TableOne computes sums rather than means.
                   Defaults to ``[]``.

    Returns:
        Tuple of ``(ReportLab Table flowable, summary DataFrame)``.
    """
    if features is None:
        features = []
    if sumcols is None:
        sumcols = []

    data_win = CreateOutlierFrame(data, mode='win')

    raw_t = TableOne(data,     columns=features, pval=False,
                     weights=weighting, sum_cols=sumcols, groupby=grouping)
    win_t = TableOne(data_win, columns=features, pval=False,
                     weights=weighting, sum_cols=sumcols, groupby=grouping)

    df_raw = raw_t.tableone
    df_win = win_t.tableone

    if grouping:
        df_raw.columns = df_raw.columns.droplevel(0)
        df_win.columns = df_win.columns.droplevel(0)

    df_raw = df_raw.reset_index().drop('level_1', axis=1).rename(columns={'level_0': 'Metric'})
    df_win = df_win.reset_index().drop('level_1', axis=1).rename(columns={'level_0': 'Metric'})

    if grouping is None:
        df_raw = df_raw.merge(df_win['Overall'], left_index=True, right_index=True)
        df_raw.rename(columns={'Overall_x': 'Raw', 'Overall_y': 'Winsorized'}, inplace=True)

    tbl = df2table(df_raw.drop('Missing', axis=1))
    tbl.hAlign = 'LEFT'
    tbl.setStyle([
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
        ('BOX',       (0, 0), (-1, -1), 0.25, colors.white),
        ('VALIGN',    (0, 0), ( 0,  0), 'MIDDLE'),
    ])

    return tbl, df_raw
