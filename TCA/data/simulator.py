"""
data/simulator.py — Synthetic trade-data generation.

Generates realistic trade-level TCA data conforming to the schema defined in
DataSchema.xlsx and writes it as Hive-partitioned Parquet files under::

    data/year=YYYY/month=MM/part-0000.parquet

Usage
-----
Run as a module (writes files to data/)::

    uv run python -m data.simulator

Or import programmatically::

    from data.simulator import generate_sample_data, write_parquet

    df = generate_sample_data()           # returns a pandas DataFrame
    write_parquet(df)                     # writes Hive-partitioned Parquet

Design notes
------------
- All columns are generated in a single vectorised NumPy pass — no Python
  loops over rows.  A short loop over trading days is used only where it is
  unavoidable (per-day ``order_id`` counters).
- Derived columns (``exec_qty``, ``exec_val_usd``, ``end_time``,
  ``min_since_open``, ``int_spread``, ``arrival_mid_px_slp_bps``) are
  computed from their upstream columns after all independent draws are made.
- Parquet files use an explicit PyArrow schema so every column has the
  exact type described in the data dictionary (``date32``, ``timestamp[us]``,
  ``int32``, ``float64``, ``string``).
- Business days are Monday–Friday; US market holidays are not excluded.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─── Parquet schema ───────────────────────────────────────────────────────────
# Column order matches DataSchema.xlsx.

_PARQUET_SCHEMA = pa.schema([
    pa.field('trade_date',             pa.date32()),
    pa.field('strategy',               pa.string()),
    pa.field('order_id',               pa.string()),
    pa.field('side_sign',              pa.int32()),
    pa.field('symbol',                 pa.string()),
    pa.field('limit_px',               pa.float64()),
    pa.field('client',                 pa.string()),
    pa.field('order_qty',              pa.int32()),
    pa.field('comp_pct',               pa.float64()),
    pa.field('exec_qty',               pa.int32()),
    pa.field('hist_spread',            pa.float64()),
    pa.field('arrival_price',          pa.float64()),
    pa.field('avg_price',              pa.float64()),
    pa.field('exec_val_usd',           pa.float64()),
    pa.field('trader_id',              pa.string()),
    pa.field('urgency',                pa.string()),
    pa.field('market_cap',             pa.float64()),
    pa.field('avg_spread',             pa.float64()),
    pa.field('volatility_30d',         pa.float64()),
    pa.field('start_time',             pa.timestamp('us')),
    pa.field('order_len_minutes',      pa.float64()),
    pa.field('end_time',               pa.timestamp('us')),
    pa.field('min_since_open',         pa.float64()),
    pa.field('int_spread',             pa.float64()),
    pa.field('sector',                 pa.string()),
    pa.field('adv_pct',                pa.float64()),
    pa.field('trade_rate',             pa.float64()),
    pa.field('impact_cost_bps',        pa.float64()),
    pa.field('arrival_mid_px_slp_bps', pa.float64()),
])

# ─── Reference data ───────────────────────────────────────────────────────────

# 60 symbols with permanent GICS sector mapping
_SYMBOLS: dict[str, str] = {
    # Information Technology (12)
    'AAPL':  'Information Technology',
    'MSFT':  'Information Technology',
    'NVDA':  'Information Technology',
    'INTC':  'Information Technology',
    'AMD':   'Information Technology',
    'ORCL':  'Information Technology',
    'CRM':   'Information Technology',
    'ADBE':  'Information Technology',
    'AVGO':  'Information Technology',
    'QCOM':  'Information Technology',
    'TXN':   'Information Technology',
    'NOW':   'Information Technology',
    # Communication Services (6)
    'GOOGL': 'Communication Services',
    'META':  'Communication Services',
    'NFLX':  'Communication Services',
    'DIS':   'Communication Services',
    'T':     'Communication Services',
    'VZ':    'Communication Services',
    # Consumer Discretionary (6)
    'AMZN':  'Consumer Discretionary',
    'TSLA':  'Consumer Discretionary',
    'MCD':   'Consumer Discretionary',
    'NKE':   'Consumer Discretionary',
    'HD':    'Consumer Discretionary',
    'BKNG':  'Consumer Discretionary',
    # Consumer Staples (6)
    'PG':    'Consumer Staples',
    'KO':    'Consumer Staples',
    'WMT':   'Consumer Staples',
    'CL':    'Consumer Staples',
    'PEP':   'Consumer Staples',
    'GIS':   'Consumer Staples',
    # Financials (7)
    'JPM':   'Financials',
    'BAC':   'Financials',
    'GS':    'Financials',
    'V':     'Financials',
    'MA':    'Financials',
    'MS':    'Financials',
    'BLK':   'Financials',
    # Health Care (7)
    'JNJ':   'Health Care',
    'PFE':   'Health Care',
    'UNH':   'Health Care',
    'ABBV':  'Health Care',
    'MRK':   'Health Care',
    'BMY':   'Health Care',
    'LLY':   'Health Care',
    # Energy (5)
    'XOM':   'Energy',
    'CVX':   'Energy',
    'COP':   'Energy',
    'SLB':   'Energy',
    'OXY':   'Energy',
    # Industrials (5)
    'CAT':   'Industrials',
    'GE':    'Industrials',
    'HON':   'Industrials',
    'RTX':   'Industrials',
    'UPS':   'Industrials',
    # Materials (3)
    'LIN':   'Materials',
    'APD':   'Materials',
    'NEM':   'Materials',
    # Utilities (3)
    'NEE':   'Utilities',
    'SO':    'Utilities',
    'DUK':   'Utilities',
    # Real Estate (3)
    'AMT':   'Real Estate',
    'PLD':   'Real Estate',
    'EQIX':  'Real Estate',
}

# 20 institutional clients
_CLIENTS: list[str] = [
    'Apex Capital Management',
    'Blue Ridge Partners',
    'Citadel Advisors',
    'Dune Capital',
    'Evergreen Asset Management',
    'Falcon Ridge Capital',
    'Granite Peak Investments',
    'Harbor View Capital',
    'Iron Bridge Partners',
    'Jasper Capital Group',
    'Keystone Investment Advisors',
    'Lighthouse Capital',
    'Meridian Asset Management',
    'Nordic Capital Partners',
    'Osprey Investment Group',
    'Pinnacle Capital Management',
    'Quorum Asset Partners',
    'Redwood Capital',
    'Summit Ridge Capital',
    'Torchlight Investments',
]

# Many-to-one: traders → clients.  Median traders-per-client = 1.
# Distribution: 13 clients × 1 trader, 5 clients × 2 traders, 2 clients × 3 traders
_TRADER_MAP: dict[str, list[str]] = {
    'Apex Capital Management':       ['Chen_A'],
    'Blue Ridge Partners':           ['Smith_B'],
    'Citadel Advisors':              ['Johnson_C', 'Williams_C'],
    'Dune Capital':                  ['Brown_D'],
    'Evergreen Asset Management':    ['Davis_E', 'Miller_E', 'Wilson_E'],
    'Falcon Ridge Capital':          ['Moore_F'],
    'Granite Peak Investments':      ['Taylor_G'],
    'Harbor View Capital':           ['Anderson_H', 'Thomas_H'],
    'Iron Bridge Partners':          ['Jackson_I'],
    'Jasper Capital Group':          ['White_J'],
    'Keystone Investment Advisors':  ['Harris_K'],
    'Lighthouse Capital':            ['Martin_L', 'Garcia_L'],
    'Meridian Asset Management':     ['Martinez_M'],
    'Nordic Capital Partners':       ['Robinson_N'],
    'Osprey Investment Group':       ['Clark_O'],
    'Pinnacle Capital Management':   ['Rodriguez_P', 'Lewis_P'],
    'Quorum Asset Partners':         ['Lee_Q'],
    'Redwood Capital':               ['Walker_R'],
    'Summit Ridge Capital':          ['Hall_S'],
    'Torchlight Investments':        ['Allen_T'],
}

_STRATEGIES   = ['VWAP', 'POV', 'TWAP', 'IS', 'LiqSeek']
_URGENCY_VALS = ['1', '2', '3', '4']

# Minutes from midnight for key market times
_OPEN_MIN  = 570   # 09:30
_CLOSE_MIN = 960   # 16:00
_NOON_MIN  = 720   # 12:00
_3H_MIN    = 180   # 3 hours in minutes


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _clip_normal(
    rng: np.random.Generator,
    mean: float,
    sd: float,
    lo: float,
    hi: float,
    size: int,
) -> np.ndarray:
    """Draw from Normal(mean, sd) then clip to [lo, hi]."""
    return np.clip(rng.normal(mean, sd, size), lo, hi)


def _daily_counts(
    rng: np.random.Generator,
    n_days: int,
    n_total: int,
) -> np.ndarray:
    """Return an array of per-day row counts summing exactly to n_total.

    Counts are drawn from a log-normal distribution to produce realistic
    volume variation (some busy days, some quiet days).
    """
    raw = rng.lognormal(np.log(n_total / n_days), 0.5, n_days)
    counts = np.round(raw / raw.sum() * n_total).astype(int)
    # Fix rounding error on the last element
    counts[-1] += n_total - counts.sum()
    return counts


# ─── Core generator ──────────────────────────────────────────────────────────

def generate_sample_data(
    start_date: str = '2025-09-01',
    end_date:   str = '2026-03-31',
    n_total:    int = 100_000,
    seed:       int = 42,
) -> pd.DataFrame:
    """Generate a synthetic trade-level TCA DataFrame.

    All columns conform to the types and constraints defined in
    DataSchema.xlsx.  Derived columns (``exec_qty``, ``exec_val_usd``,
    ``end_time``, ``min_since_open``, ``int_spread``,
    ``arrival_mid_px_slp_bps``) are computed from their upstream sources.

    Args:
        start_date: First trading date (inclusive).  Defaults to 2025-09-01.
        end_date:   Last trading date (inclusive).   Defaults to 2026-03-31.
        n_total:    Approximate total row count.    Defaults to 100,000.
        seed:       NumPy random seed for reproducibility.

    Returns:
        DataFrame with one row per simulated trade, sorted by trade_date.
    """
    rng = np.random.default_rng(seed)

    # ── Day assignments ──────────────────────────────────────────────────────
    biz_days  = pd.bdate_range(start_date, end_date)
    n_days    = len(biz_days)
    counts    = _daily_counts(rng, n_days, n_total)
    n         = int(counts.sum())
    day_idx   = np.repeat(np.arange(n_days), counts)   # which day each row belongs to

    logger.info(
        "Generating %d rows across %d trading days (%s – %s)",
        n, n_days, start_date, end_date,
    )

    # ── Categorical columns ──────────────────────────────────────────────────
    symbols       = list(_SYMBOLS.keys())
    sector_lookup = list(_SYMBOLS.values())
    sym_idx       = rng.integers(0, len(symbols), n)

    strategies    = rng.choice(_STRATEGIES, n)
    side_signs    = rng.choice([1, -1], n).astype(np.int32)
    syms          = np.array(symbols)[sym_idx]
    sectors       = np.array(sector_lookup)[sym_idx]

    clients_arr   = np.array(_CLIENTS)
    client_idx    = rng.integers(0, len(_CLIENTS), n)
    clients       = clients_arr[client_idx]

    # Trader: for each row pick a random trader from the client's pool
    trader_pools  = [_TRADER_MAP[c] for c in _CLIENTS]
    traders       = np.array([
        rng.choice(trader_pools[ci]) for ci in client_idx
    ])

    # ── Independent numeric columns ──────────────────────────────────────────

    # order_qty: Normal(30000, 15000) → [100, 100000]
    order_qty = np.round(
        _clip_normal(rng, 30_000, 15_000, 100, 100_000, n)
    ).astype(np.int32)

    # comp_pct: Normal(0.8, 0.3) → [0, 1]  (clip, per spec)
    comp_pct = _clip_normal(rng, 0.8, 0.3, 0.0, 1.0, n)

    # arrival_price: Normal(100, 50) → [1, 1000]
    arrival_price = _clip_normal(rng, 100, 50, 1, 1_000, n)

    # avg_price: Normal(100, 40) → [1, 1000]
    # then clipped to within 2 population SDs (±80) of each row's arrival_price
    avg_price = _clip_normal(rng, 100, 40, 1, 1_000, n)
    avg_price = np.clip(avg_price, arrival_price - 80, arrival_price + 80)
    avg_price = np.clip(avg_price, 1, 1_000)

    # limit_px: ~15% non-null; when set, within ±0.5% of arrival_price
    limit_mask  = rng.random(n) < 0.15
    limit_px    = np.where(
        limit_mask,
        arrival_price * (1.0 + rng.uniform(-0.005, 0.005, n)),
        np.nan,
    )

    # hist_spread: Normal(10, 5) → [0.5, 30]
    hist_spread = _clip_normal(rng, 10, 5, 0.5, 30, n)

    # avg_spread: Normal(9, 6) → [0.1, 20]
    avg_spread = _clip_normal(rng, 9, 6, 0.1, 20, n)

    # volatility_30d: Normal(38, 10) → [0.1, 65]
    volatility_30d = _clip_normal(rng, 38, 10, 0.1, 65, n)

    # market_cap: Normal(600, 200) → [1, 1000]
    market_cap = _clip_normal(rng, 600, 200, 1, 1_000, n)

    # adv_pct: Normal(4, 0.5) → [0.1, 10]
    adv_pct = _clip_normal(rng, 4, 0.5, 0.1, 10, n)

    # trade_rate: Normal(10, 3) → [0.1, 100]
    trade_rate = _clip_normal(rng, 10, 3, 0.1, 100, n)

    # impact_cost_bps: Normal(4, 10) → [1, 30]
    impact_cost_bps = _clip_normal(rng, 4, 10, 1, 30, n)

    # ── Time columns ─────────────────────────────────────────────────────────
    # start_time: Normal(12:00, 3h) → [09:30, 16:00]  in minutes from midnight
    start_min = _clip_normal(rng, _NOON_MIN, _3H_MIN, _OPEN_MIN, _CLOSE_MIN, n)

    # order_len_minutes: Normal(120, 100) → [0, minutes until market close]
    max_len        = _CLOSE_MIN - start_min            # per-row cap
    order_len_min  = np.clip(rng.normal(120, 100, n), 0, max_len)

    # Vectorised timestamp construction.
    # Use pandas Timedelta arithmetic so the result is independent of the
    # DatetimeIndex resolution (.asi8 changes meaning across pandas versions).
    base_dates = biz_days[day_idx]                                   # DatetimeIndex at midnight
    start_secs = np.round(start_min * 60).astype(np.int64)          # whole seconds from midnight
    end_secs   = np.round((start_min + order_len_min) * 60).astype(np.int64)
    start_time = base_dates + pd.to_timedelta(start_secs, unit='s')
    end_time   = base_dates + pd.to_timedelta(end_secs,   unit='s')

    # min_since_open: minutes between 09:30 and start_time (derived)
    min_since_open = start_min - _OPEN_MIN

    # ── Derived numeric columns ───────────────────────────────────────────────

    # exec_qty = round(order_qty × comp_pct), must be ≥ 0
    exec_qty     = np.maximum(np.round(order_qty * comp_pct).astype(np.int32), 0)

    # exec_val_usd = avg_price × exec_qty
    exec_val_usd = avg_price * exec_qty

    # int_spread: intraday spread ≈ avg_spread ± noise, bounded within
    # avg_spread ± 2 × population SD of avg_spread (SD=6 → bound=±12),
    # and clipped to schema range [0.1, 20]
    int_spread = avg_spread + rng.normal(0, avg_spread * 0.15, n)
    int_spread = np.clip(int_spread, avg_spread - 12, avg_spread + 12)
    int_spread = np.clip(int_spread, 0.1, 20)

    # arrival_mid_px_slp_bps = 10000 × side_sign × (avg_price − arrival_price) / arrival_price
    arrival_mid_px_slp_bps = (
        10_000 * side_signs * (avg_price - arrival_price) / arrival_price
    )

    # ── urgency: null for all strategies except LiqSeek ─────────────────────
    is_liqseek = strategies == 'LiqSeek'
    urgency    = np.where(
        is_liqseek,
        rng.choice(_URGENCY_VALS, n),
        None,
    )

    # ── order_id: 8-digit counter, unique per day, reset each day ────────────
    within_day_rank = np.empty(n, dtype=int)
    pos = 0
    for cnt in counts:
        within_day_rank[pos : pos + cnt] = np.arange(cnt)
        pos += cnt
    order_ids = np.array([f'{r + 1:08d}' for r in within_day_rank])

    # ── Assemble DataFrame ───────────────────────────────────────────────────
    trade_dates = biz_days[day_idx].normalize()   # midnight timestamps → date32 via PyArrow

    df = pd.DataFrame({
        'trade_date':             trade_dates,
        'strategy':               strategies,
        'order_id':               order_ids,
        'side_sign':              side_signs,
        'symbol':                 syms,
        'limit_px':               limit_px,
        'client':                 clients,
        'order_qty':              order_qty,
        'comp_pct':               comp_pct,
        'exec_qty':               exec_qty,
        'hist_spread':            hist_spread,
        'arrival_price':          arrival_price,
        'avg_price':              avg_price,
        'exec_val_usd':           exec_val_usd,
        'trader_id':              traders,
        'urgency':                urgency,
        'market_cap':             market_cap,
        'avg_spread':             avg_spread,
        'volatility_30d':         volatility_30d,
        'start_time':             start_time,
        'order_len_minutes':      order_len_min,
        'end_time':               end_time,
        'min_since_open':         min_since_open,
        'int_spread':             int_spread,
        'sector':                 sectors,
        'adv_pct':                adv_pct,
        'trade_rate':             trade_rate,
        'impact_cost_bps':        impact_cost_bps,
        'arrival_mid_px_slp_bps': arrival_mid_px_slp_bps,
    })

    logger.info("DataFrame assembled: %d rows × %d columns", len(df), len(df.columns))
    return df


# ─── Parquet writer ───────────────────────────────────────────────────────────

def write_parquet(
    df: pd.DataFrame,
    output_dir: Path | str | None = None,
) -> Path:
    """Write *df* as Hive-partitioned Parquet files under *output_dir*.

    Partition layout::

        <output_dir>/year=YYYY/month=MM/part-0000.parquet

    Month directories are zero-padded (``month=01`` … ``month=12``).
    The partition columns (year, month) are encoded in the directory path and
    are **not** included in the Parquet file itself.

    An explicit PyArrow schema is applied so every column has the exact type
    declared in DataSchema.xlsx.

    Args:
        df:         DataFrame produced by :func:`generate_sample_data`.
        output_dir: Root partition directory.
                    Defaults to ``<project_root>/data``.

    Returns:
        Absolute path to the root partition directory.
    """
    if output_dir is None:
        output_dir = _PROJECT_ROOT / 'data'
    output_dir = Path(output_dir).resolve()

    # Partition keys (excluded from Parquet schema)
    df = df.copy()
    df['_year']  = df['trade_date'].dt.year
    df['_month'] = df['trade_date'].dt.month

    total_rows = 0
    for (year, month), group in df.groupby(['_year', '_month']):
        partition_dir = output_dir / f'year={year}' / f'month={month:02d}'
        partition_dir.mkdir(parents=True, exist_ok=True)
        out_file = partition_dir / 'part-0000.parquet'

        group_data = group.drop(columns=['_year', '_month'])

        table = pa.Table.from_pandas(group_data, schema=_PARQUET_SCHEMA, preserve_index=False)
        pq.write_table(table, str(out_file), compression='snappy')

        total_rows += len(group)
        logger.info(
            "year=%d  month=%02d  rows=%6d  → %s",
            year, month, len(group), out_file,
        )

    logger.info("Done — %d rows written to %s", total_rows, output_dir)
    return output_dir


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(
        prog='python -m data.simulator',
        description='Generate synthetic TCA trade data as Hive-partitioned Parquet.',
    )
    parser.add_argument('--start',  default='2025-09-01', help='First trading date (YYYY-MM-DD)')
    parser.add_argument('--end',    default='2026-03-31', help='Last  trading date (YYYY-MM-DD)')
    parser.add_argument('--rows',   default=100_000, type=int, help='Approximate total row count')
    parser.add_argument('--seed',   default=42,      type=int, help='NumPy random seed')
    parser.add_argument('--output', default=None,             help='Root output directory')
    args = parser.parse_args()

    df  = generate_sample_data(args.start, args.end, args.rows, args.seed)
    out = write_parquet(df, args.output)

    print(f'\nGenerated {len(df):,} rows across {df["trade_date"].nunique()} trading days.')
    print(f'Date range : {df["trade_date"].min().date()} to {df["trade_date"].max().date()}')
    print(f'Output     : {out}')
    print(f'Partitions : {len(list(out.rglob("*.parquet")))} parquet files')
