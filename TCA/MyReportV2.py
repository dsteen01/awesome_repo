"""
MyReportV2.py — Ad-hoc report runner (command-line entry point).

For the full automation runner (scheduled + email) see runner/scheduler.py.
For the interactive UI see frontend/app.py.

To generate a different report, swap in a different ReportConfig:

    cfg = ReportConfig(
        client_name='ClientName: ABC',
        input_file='abc_data.xlsx',
        output_file='abc_report.pdf',
        grouping='trader_id',
    )
"""

import logging
from config import ReportConfig
from pipeline import run_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt='%H:%M:%S',
)

cfg    = ReportConfig()
result = run_report(cfg)
print(f"\nDone. Report saved to: {result.pdf_path.resolve()}")
