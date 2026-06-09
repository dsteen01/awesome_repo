"""
ReportConfig — single source of truth for every report parameter.

To run a different client or scenario, instantiate ReportConfig with
different values rather than editing the runner script:

    from config import ReportConfig

    xyz_cfg = ReportConfig(client_name='ClientName: XYZ', ...)
    abc_cfg = ReportConfig(client_name='ClientName: ABC',
                           input_file='abc_data.xlsx',
                           output_file='abc_report.pdf',
                           grouping='trader_id')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReportConfig:
    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    input_file: str = 'toydata_v2.xlsx'
    output_file: str = 'TestFile.pdf'
    client_name: str = 'ClientName: XYZ'

    # ------------------------------------------------------------------
    # Column definitions
    # All names refer to columns *after* rename_map has been applied.
    # ------------------------------------------------------------------

    #: Full set of numeric features used in TableOne and histograms.
    feature_cols: list = field(default_factory=lambda: [
        'Duration',
        'adv_pct',
        'TradeRate',
        'impact_cost_bps',
        'market_cap',
        'volatility_30d',
        'avg_spread',
        'ArrSlipBps',
    ])

    #: The key performance indicator — also included in feature_cols.
    kpi: str = 'ArrSlipBps'

    #: Column(s) used as analytic weights in TableOne.
    weight_col: list = field(default_factory=lambda: ['exec_val_usd'])

    #: Columns for which TableOne computes sums rather than means.
    sum_cols: list = field(default_factory=lambda: [
        'order_qty',
        'exec_qty',
        'exec_val_usd',
    ])

    #: Base columns always included in each CutBy sub-DataFrame.
    #: Must contain the date column, the weight column, and the KPI.
    sub_df_cols: list = field(default_factory=lambda: [
        'trade_date',
        'exec_val_usd',
        'ArrSlipBps',
    ])

    #: Optional column to group all analyses by (e.g. 'trader_id').
    #: Set to None for an ungrouped report.
    grouping: Optional[str] = None

    #: Name of the date column in the *transformed* DataFrame.
    #: Used to derive the report date range shown in the footer.
    date_col: str = 'trade_date'

    #: strptime format string used to parse the date column at load time.
    #: Set to '%Y%m%d' when dates are stored as integers (e.g. 20240101).
    #: Set to '' to let pandas infer the format (works for ISO strings and
    #: proper Excel date cells).
    date_format: str = '%Y%m%d'

    # ------------------------------------------------------------------
    # Analysis parameters
    # ------------------------------------------------------------------

    #: Time granularity for temporal charts. 'Daily' or 'Weekly'.
    time_bin: str = 'Daily'

    #: Number of quantile bins used in CutBy analysis.
    nbins: int = 5

    # ------------------------------------------------------------------
    # Raw-data transformations (applied once at load time)
    # ------------------------------------------------------------------

    #: Columns to multiply by a scalar (e.g. fraction → percentage).
    scale_multiply: dict = field(default_factory=lambda: {
        'adv_pct':    100,
        'avg_spread': 100,
    })

    #: Columns to divide by a scalar (e.g. units → millions / thousands).
    scale_divide: dict = field(default_factory=lambda: {
        'order_qty':     1e6,
        'exec_qty':      1e6,
        'exec_val_usd':  1e6,
        'market_cap':    1e3,
    })

    #: Raw column names → display names applied before any analysis runs.
    rename_map: dict = field(default_factory=lambda: {
        'ordre_len_seconds':       'Duration',
        'liq_consumption':         'TradeRate',
        'arrival_mid_px_slp_bps':  'ArrSlipBps',
    })

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    #: Email addresses that receive the finished report.
    #: Leave empty for ad-hoc / on-demand runs where no email is sent.
    recipients: list = field(default_factory=list)

    #: Cron expression controlling when the scheduler runs this report
    #: automatically, e.g. ``'0 17 * * fri'`` (every Friday at 5 pm).
    #: Leave empty to treat this config as ad-hoc / Streamlit-only.
    schedule: str = ''

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def cut_by_cols(self) -> list:
        """All feature columns except the KPI.

        Derived automatically so feature_cols and cut_by_cols can never
        fall out of sync.
        """
        return [c for c in self.feature_cols if c != self.kpi]
