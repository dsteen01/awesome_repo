"""
analysis/summary.py — TableOne-based cover-page summary table.

Functions
---------
CreateCoverPageTable(data, weighting, features, grouping, sumcols, kpi, ...)
    Build side-by-side Raw / Winsorized TableOne summaries and a 1×3
    overview chart (notional over time, KPI over time, KPI histogram).
    Returns a 3-tuple: (ReportLab Table flowable, chart Image, summary DataFrame).
"""

from __future__ import annotations

# analysis/__init__.py already added the local tableone path to sys.path.
import analysis  # noqa: F401 — ensure __init__.py side-effects run

import re

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from reportlab.lib import colors
from tableone import TableOne

from data.filters import CreateOutlierFrame
from data.transforms import resolve_time_grouping
from report.components import df2table, fig2image


def CreateCoverPageTable(
    data: pd.DataFrame,
    weighting: list,
    features: list | None = None,
    grouping: str | None = None,
    sumcols: list | None = None,
    kpi: str = '',
    date_col: str = 'trade_date',
    time_bin: str = 'Daily',
    activity_col: str | None = None,
):
    """Build a side-by-side Raw / Winsorized summary table and 1×3 overview chart.

    Args:
        data:         Transformed trade-level DataFrame.
        weighting:    Column name(s) used as analytic weights (e.g. exec value).
        features:     Numeric feature columns to include.  Defaults to ``[]``.
        grouping:     Optional column to split the table by (e.g. ``'trader_id'``).
        sumcols:      Columns for which TableOne computes sums rather than means.
                      Defaults to ``[]``.
        kpi:          KPI column name — drives the centre and right chart panels.
                      The centre panel shows the KPI weighted mean over time,
                      weighted by ``weighting[0]``.
        date_col:     Date column used for time-series grouping.
        time_bin:     ``'Daily'``, ``'Weekly'``, or ``'Monthly'`` granularity.
        activity_col: Column to sum for the left activity panel.  Defaults to
                      ``weighting[0]`` (executed notional).  Pass ``'exec_qty'``
                      to show share volume instead.

    Returns:
        3-tuple of ``(ReportLab Table flowable, chart Image flowable, summary DataFrame)``.
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

    # ── Format sumcols: round to nearest integer, comma-separate thousands ────
    if sumcols:
        val_cols = [c for c in df_raw.columns if c not in ('Metric', 'Missing')]

        def _fmt_int_comma(val):
            s = str(val).strip()
            if not s or s in ('-', 'nan', 'NaN'):
                return val
            m = re.search(r'-?\d+\.?\d*', s.replace(',', ''))
            if m:
                try:
                    return f'{round(float(m.group())):,}'
                except (ValueError, OverflowError):
                    return val
            return val

        for col_name in sumcols:
            mask = df_raw['Metric'].str.strip() == col_name
            if mask.any():
                for vc in val_cols:
                    df_raw.loc[mask, vc] = df_raw.loc[mask, vc].map(_fmt_int_comma)

    tbl = df2table(df_raw.drop('Missing', axis=1))
    tbl.hAlign = 'LEFT'
    tbl.setStyle([
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
        ('BOX',       (0, 0), (-1, -1), 0.25, colors.white),
        ('VALIGN',    (0, 0), ( 0,  0), 'MIDDLE'),
    ])

    # ── Alternating row colors (white / light grey, skipping the header) ──────
    _light_grey = colors.HexColor('#f0f0f0')
    alt_styles = [
        ('BACKGROUND', (0, row), (-1, row), colors.white if row % 2 == 1 else _light_grey)
        for row in range(1, len(df_raw) + 1)
    ]
    tbl.setStyle(alt_styles)

    # ── 1×3 cover chart ───────────────────────────────────────────────────────
    df_ts, grouping_col = resolve_time_grouping(data, time_bin, date_col)
    notional_col  = weighting[0] if weighting else None
    _activity_col = activity_col if activity_col else notional_col

    activity_ts = df_ts.groupby(grouping_col)[_activity_col].sum() if _activity_col else None

    if kpi and notional_col:
        def _wt_stats(g):
            w, x = g[notional_col], g[kpi]
            w_sum = w.sum()
            if w_sum == 0:
                return pd.Series({'mean': float('nan'), 'sem': float('nan')})
            mean = (x * w).sum() / w_sum
            sem  = ((w * (x - mean) ** 2).sum() / w_sum / max(len(g), 1)) ** 0.5
            return pd.Series({'mean': mean, 'sem': sem})
        kpi_stats = df_ts.groupby(grouping_col)[[kpi, notional_col]].apply(_wt_stats)
        kpi_ts  = kpi_stats['mean']
        kpi_sem = kpi_stats['sem']
    else:
        kpi_ts  = None
        kpi_sem = None

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(9.9, 3))

    if activity_ts is not None:
        if len(activity_ts.index) > 1:
            idx_days = pd.to_datetime(pd.Series(activity_ts.index)).diff().dt.days.dropna()
            bar_width = pd.Timedelta(days=float(idx_days.median() * 0.85))
        else:
            bar_width = pd.Timedelta(days=1)
        ax1.bar(activity_ts.index, activity_ts.values, width=bar_width, color='tab:blue', alpha=0.7)
        ax1.set_title(f'{_activity_col} over Time')
        ax1.set_xlabel('Date')
        ax1.set_ylabel(_activity_col)
        ax1.tick_params(axis='x', rotation=45)

    if kpi_ts is not None:
        ax2.errorbar(kpi_ts.index, kpi_ts.values, yerr=kpi_sem.values,
                     fmt='o', capsize=5, color='tab:orange')
        ax2.set_title(f'{kpi} over Time')
        ax2.set_xlabel('Date')
        ax2.set_ylabel(kpi)
        ax2.tick_params(axis='x', rotation=45)

    if kpi:
        sns.histplot(data=data, x=kpi, ax=ax3, color='tab:green')
        ax3.set_title(f'{kpi} Distribution')

    plt.tight_layout(pad=2.0)
    cover_chart = fig2image(fig)
    plt.close(fig)

    return tbl, cover_chart, df_raw
