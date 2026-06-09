"""
configs/xyz_strategy.py — Report definition for the XYZ strategy.

The scheduler discovers this file automatically.  To add a new report,
copy this file, rename it, and update the fields below.
"""

from config import ReportConfig

config = ReportConfig(
    client_name='ClientName: XYZ',
    input_file='toydata_v2.xlsx',
    output_file='reports/xyz_strategy.pdf',

    # Delivery
    recipients=[],              # e.g. ['trader@firm.com', 'pm@firm.com']

    # Schedule: every Friday at 5:00 PM Eastern
    # Cron format: minute  hour  day  month  day_of_week
    schedule='0 17 * * fri',

    # All other fields inherit ReportConfig defaults — override as needed:
    # grouping='trader_id',
    # time_bin='Weekly',
    # nbins=5,
)
