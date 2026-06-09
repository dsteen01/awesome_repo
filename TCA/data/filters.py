"""
data/filters.py — Row-level outlier handling.

Functions
---------
CreateOutlierFrame(df, mode, ...)
    Return a winsorized or trimmed copy of *df* based on size and cost
    thresholds.
"""

from __future__ import annotations

import pandas as pd
from scipy.stats.mstats import winsorize


def CreateOutlierFrame(
    df: pd.DataFrame,
    mode: str = 'win',
    SizeThresh: float = 0.025,
    CostThresh: float = 0.01,
    SizeCol: str = 'exec_val_usd',
    CostCol: str = 'ArrSlipBps',
) -> pd.DataFrame:
    """Return an outlier-treated copy of *df*.

    Two modes are supported:

    ``'win'`` (winsorize)
        Clip extreme values in-place on a copy — preserves row count.
        ``CostCol`` is winsorized symmetrically; ``SizeCol`` is capped only
        on the upper tail.

    ``'cut'`` (trim)
        Drop rows whose cost or size falls outside the specified quantile
        bounds — reduces row count.

    Args:
        df:          Source DataFrame.
        mode:        ``'win'`` or ``'cut'``.
        SizeThresh:  Upper quantile threshold applied to ``SizeCol``
                     (default 2.5 %).
        CostThresh:  Symmetric quantile threshold applied to ``CostCol``
                     (default 1 %).
        SizeCol:     Column name for trade size (default ``'exec_val_usd'``).
        CostCol:     Column name for execution cost (default ``'ArrSlipBps'``).

    Returns:
        A treated copy of *df* (never mutates the original).

    Raises:
        ValueError: If *mode* is not ``'win'`` or ``'cut'``.
    """
    df_out = df.copy()

    if mode == 'win':
        df_out[CostCol] = winsorize(df[CostCol], limits=[CostThresh, CostThresh])
        df_out[SizeCol] = winsorize(df[SizeCol], limits=[None, SizeThresh])
    elif mode == 'cut':
        cost_lo = df[CostCol].quantile(CostThresh)
        cost_hi = df[CostCol].quantile(1 - CostThresh)
        size_hi = df[SizeCol].quantile(1 - SizeThresh)
        df_out = df[
            (df[CostCol] > cost_lo) &
            (df[CostCol] < cost_hi) &
            (df[SizeCol] < size_hi)
        ].copy()
    else:
        raise ValueError(f"Unknown mode '{mode}'. Expected 'win' or 'cut'.")

    return df_out
