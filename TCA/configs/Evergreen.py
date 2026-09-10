"""
configs/Evergreen.py — Report definition for Evergreen Asset Management.

The scheduler discovers this file automatically.  To add a new report,
copy this file, rename it, and update the fields below.
"""

from config import ReportConfig

config = ReportConfig(
    client_name='ClientName: Evergreen',
    output_file='reports/Evergreen.pdf',

    row_filters={'client': 'Evergreen Asset Management'},
    split_by='strategy',

    # Delivery
    recipients=[],              # e.g. ['trader@firm.com', 'pm@firm.com']

    # Schedule: every Friday at 5:00 PM Eastern
    # Cron format: minute  hour  day  month  day_of_week
    schedule='0 17 * * fri',

    # All other fields inherit ReportConfig defaults — override as needed:
    # grouping='trader_id',
    time_bin='Monthly',
    # nbins=5,
    activity_col='exec_qty',
)
