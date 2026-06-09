"""
viz/histograms.py — Feature-distribution histogram grid.

Functions
---------
CreateFeatureHistograms(df, features)
    Render a seaborn FacetGrid of histograms (one per feature) and return
    a ReportLab Image flowable alongside the raw FacetGrid object.
"""

from __future__ import annotations

import pandas as pd
import seaborn as sns

from report.components import fig2image


def CreateFeatureHistograms(
    df: pd.DataFrame,
    features: list | None = None,
):
    """Produce a FacetGrid histogram for each feature in *features*.

    The grid is arranged in rows of three columns and uses independent x / y
    axes so that features with very different scales remain readable.

    Args:
        df:       Transformed trade-level DataFrame.
        features: Columns to plot.  Defaults to ``[]``.

    Returns:
        Tuple of ``(ReportLab Image flowable, seaborn FacetGrid)``.
    """
    if features is None:
        features = []

    g = sns.FacetGrid(
        df[features].melt(),
        col='variable',
        col_wrap=3,
        sharex=False,
        sharey=False,
        height=1.0,
        aspect=2.0,
    )
    g.map(sns.histplot, 'value')
    g.set_titles('{col_name}')
    g.fig.tight_layout()

    return fig2image(g), g
