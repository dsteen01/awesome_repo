"""
data/transforms.py — Column-level data transformations shared across
                     analysis and visualisation modules.

Functions
---------
resolve_time_grouping(df, time_bin, date_col)
    Map a time-bin label ('Daily' / 'Weekly') to a concrete grouping column,
    returning a safe copy of the DataFrame.
"""

from __future__ import annotations

import pandas as pd


def resolve_time_grouping(
    df: pd.DataFrame,
    time_bin: str,
    date_col: str = 'trade_date',
) -> tuple[pd.DataFrame, str]:
    """Return a ``(df_copy, grouping_col)`` pair for the requested granularity.

    Always returns a *copy* of *df* so callers never accidentally mutate the
    original DataFrame, and always produces the correct grouping column name
    regardless of which ``time_bin`` is selected.

    Args:
        df:       Source DataFrame.
        time_bin: ``'Daily'`` or ``'Weekly'``.
        date_col: Name of the date column in *df*
                  (default ``'trade_date'``).

    Returns:
        Tuple of ``(DataFrame copy, grouping column name)``.

    Raises:
        ValueError: If *time_bin* is not ``'Daily'`` or ``'Weekly'``.
    """
    df = df.copy()
    if time_bin == 'Daily':
        return df, date_col
    elif time_bin == 'Weekly':
        df[date_col] = pd.to_datetime(df[date_col])
        df['WeekEnding'] = df[date_col] + pd.to_timedelta(
            (4 - df[date_col].dt.weekday).astype(int), unit='d'
        )
        return df, 'WeekEnding'
    else:
        raise ValueError(
            f"Unknown time_bin value '{time_bin}'. Expected 'Daily' or 'Weekly'."
        )
