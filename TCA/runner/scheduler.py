"""
runner/scheduler.py — Full-automation report runner.

Discovers every ReportConfig in the configs/ directory, registers a cron
job for each one that has a non-empty ``schedule`` field, then blocks until
stopped.  On each trigger it runs the report pipeline and emails the PDF to
``config.recipients``.

Usage
-----
Run directly::

    python -m runner.scheduler

Or as a script::

    python runner/scheduler.py

To keep it running as a service, wrap it with a process manager such as
Windows Task Scheduler, systemd, or supervisord.

Adding a new report
-------------------
Create a new file in configs/ that exposes a module-level ``config``
variable that is a ReportConfig instance with a non-empty ``schedule``::

    # configs/my_new_report.py
    from config import ReportConfig
    config = ReportConfig(
        client_name='My Report',
        schedule='0 8 * * mon',   # every Monday at 8 AM
        recipients=['alice@firm.com'],
        ...
    )

The scheduler picks it up automatically on next restart — no code changes
needed here.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Allow imports from the project root regardless of how the script is invoked
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import ReportConfig
from delivery import send_report
from pipeline import ReportResult, run_report

logger = logging.getLogger(__name__)

# Directory that the scheduler scans for ReportConfig definitions
_CONFIGS_DIR = _PROJECT_ROOT / 'configs'

# Default timezone for all cron triggers
_DEFAULT_TZ = 'America/New_York'


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------

def discover_configs(configs_dir: Path = _CONFIGS_DIR) -> list[ReportConfig]:
    """Scan *configs_dir* and return every ReportConfig found.

    A file is considered a config source if:
    - it ends in ``.py`` and does not start with ``_``
    - it exposes a module-level attribute named ``config`` that is a
      ``ReportConfig`` instance

    Files that do not match are silently skipped so that ``__init__.py``
    and utility helpers can coexist in the same directory.

    Args:
        configs_dir: Directory to scan.  Defaults to ``<project_root>/configs``.

    Returns:
        List of discovered ReportConfig instances (including those with no
        schedule — callers decide whether to register them).
    """
    if not configs_dir.is_dir():
        logger.warning("configs/ directory not found at %s — no reports loaded.", configs_dir)
        return []

    found: list[ReportConfig] = []

    for py_file in sorted(configs_dir.glob('*.py')):
        if py_file.name.startswith('_'):
            continue

        spec   = importlib.util.spec_from_file_location(py_file.stem, py_file)
        module = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("Failed to import config file '%s' — skipping.", py_file.name)
            continue

        cfg = getattr(module, 'config', None)
        if isinstance(cfg, ReportConfig):
            found.append(cfg)
            logger.debug("Discovered config '%s' from %s", cfg.client_name, py_file.name)
        else:
            logger.warning(
                "'%s' has no top-level 'config = ReportConfig(...)' — skipping.",
                py_file.name,
            )

    logger.info("Discovered %d config(s) in %s", len(found), configs_dir)
    return found


# ---------------------------------------------------------------------------
# Job function
# ---------------------------------------------------------------------------

def _run_and_deliver(cfg: ReportConfig) -> None:
    """Execute one scheduled report run.

    Called by APScheduler on each trigger.  Any exception is caught and
    logged so a single failure does not cancel future scheduled runs.

    Args:
        cfg: The ReportConfig for this job.
    """
    logger.info("--- Scheduled run starting: '%s' ---", cfg.client_name)

    try:
        result: ReportResult = run_report(cfg)
    except Exception:
        logger.exception(
            "Pipeline failed for '%s' — PDF not produced.", cfg.client_name
        )
        return  # Do not attempt delivery if the report itself failed

    if cfg.recipients:
        try:
            send_report(
                result.pdf_path,
                cfg,
                sd=result.start_date,
                ed=result.end_date,
            )
        except Exception:
            logger.exception(
                "Delivery failed for '%s' (PDF is at %s).",
                cfg.client_name,
                result.pdf_path,
            )
    else:
        logger.info(
            "No recipients configured for '%s' — PDF saved to %s.",
            cfg.client_name,
            result.pdf_path,
        )

    logger.info("--- Scheduled run complete: '%s' ---", cfg.client_name)


# ---------------------------------------------------------------------------
# Scheduler construction
# ---------------------------------------------------------------------------

def build_scheduler(
    configs:  list[ReportConfig],
    timezone: str = _DEFAULT_TZ,
) -> BlockingScheduler:
    """Create a BlockingScheduler with one job per scheduled config.

    Configs with an empty ``schedule`` field are skipped — they are intended
    for ad-hoc use via the Streamlit UI or MyReportV2.py.

    Args:
        configs:  List of ReportConfig instances (from discover_configs()).
        timezone: IANA timezone string applied to every cron trigger.

    Returns:
        A configured (but not yet started) BlockingScheduler.
    """
    scheduler = BlockingScheduler(timezone=timezone)
    registered = 0

    for cfg in configs:
        if not cfg.schedule:
            logger.info(
                "Skipping '%s' — schedule is empty (ad-hoc only).",
                cfg.client_name,
            )
            continue

        try:
            trigger = CronTrigger.from_crontab(cfg.schedule, timezone=timezone)
        except ValueError:
            logger.error(
                "Invalid cron expression '%s' for '%s' — skipping.",
                cfg.schedule,
                cfg.client_name,
            )
            continue

        scheduler.add_job(
            _run_and_deliver,
            trigger,
            args=[cfg],
            name=cfg.client_name,
            # Replace any existing job with the same name on restart
            id=cfg.client_name,
            replace_existing=True,
            # If a trigger fires while the previous run is still active,
            # queue the missed execution rather than skipping it
            misfire_grace_time=300,  # seconds
            coalesce=True,           # merge multiple missed firings into one
        )

        logger.info(
            "Registered '%s'  schedule='%s'  recipients=%s",
            cfg.client_name,
            cfg.schedule,
            cfg.recipients or ['(none — PDF only)'],
        )
        registered += 1

    if registered == 0:
        logger.warning(
            "No scheduled reports registered. "
            "Add a non-empty schedule= field to at least one config in configs/."
        )

    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Discover configs, build the scheduler, and run until interrupted."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
    )

    logger.info("TCA Report Scheduler starting up")
    logger.info("Config directory : %s", _CONFIGS_DIR)
    logger.info("Timezone         : %s", _DEFAULT_TZ)

    configs   = discover_configs()
    scheduler = build_scheduler(configs)

    logger.info("Press Ctrl+C to stop the scheduler.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received — shutting down.")
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


if __name__ == '__main__':
    main()
