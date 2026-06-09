"""
data/loader.py — Source-file ingestion for the TCA pipeline.

Functions
---------
load_data(config)
    Read the Excel source file, apply unit scaling, column renames, and date
    parsing, then validate that every column referenced by the config is
    present in the resulting DataFrame.

_resolve_path(p)
    Resolve a relative path against the project root so the pipeline works
    regardless of the process working directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config import ReportConfig

logger = logging.getLogger(__name__)

# Absolute path to the project root (TCA/), two levels above this file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(p: str | Path) -> Path:
    """Return an absolute Path, resolving relative paths against the project root.

    Args:
        p: A string or ``pathlib.Path``.  If already absolute it is returned
           unchanged; if relative it is joined to the TCA project root.

    Returns:
        Absolute ``Path``.
    """
    path = Path(p)
    return path if path.is_absolute() else _PROJECT_ROOT / path


def load_data(config: ReportConfig) -> pd.DataFrame:
    """Read the source file, apply unit scaling and column renames.

    Validates that every column referenced by *config* is present in the
    DataFrame after transforms, so callers get a clear error instead of a
    confusing KeyError deep inside the analysis layer.

    Args:
        config: Fully populated ``ReportConfig`` instance.

    Returns:
        Transformed DataFrame ready for analysis.

    Raises:
        FileNotFoundError: If ``config.input_file`` does not exist.
        ValueError: If any column named in the config is absent after
                    transforms.
    """
    path = _resolve_path(config.input_file)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    logger.info("Loading data from %s", path)
    data = pd.read_excel(path)

    # Unit scaling — applied before rename so keys match raw column names
    for col, factor in config.scale_multiply.items():
        data[col] *= factor
    for col, factor in config.scale_divide.items():
        data[col] /= factor

    data.rename(columns=config.rename_map, inplace=True)

    # Parse the date column to datetime so .min()/.max() return Timestamps.
    # Needed when dates are stored as integers (e.g. 20240101 → YYYYMMDD).
    date_col = config.date_col
    if not pd.api.types.is_datetime64_any_dtype(data[date_col]):
        fmt = config.date_format or None   # None = let pandas infer
        data[date_col] = pd.to_datetime(data[date_col], format=fmt)
        logger.info("Parsed '%s' to datetime (format=%r)", date_col, fmt)

    logger.info("Loaded %d rows across %d columns", len(data), len(data.columns))

    # Early validation — catch config typos before anything expensive runs
    required = (
        set(config.feature_cols)
        | {config.kpi}
        | set(config.weight_col)
        | set(config.sum_cols)
        | set(config.sub_df_cols)
        | {config.date_col}
    )
    if config.grouping:
        required.add(config.grouping)

    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(
            f"The following columns are referenced in ReportConfig but are "
            f"absent from the data after transforms: {missing}\n"
            f"Available columns: {sorted(data.columns.tolist())}"
        )

    return data
