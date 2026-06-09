"""
pipeline.py — Shared report-generation core.

The pipeline is intentionally split into four explicit stages so that
callers (the scheduler, the Streamlit UI, or a test) can invoke only the
stages they need, inspect intermediate results, or substitute a stage for
testing purposes.

    Stage 1  load_data()          read + validate + transform raw data
    Stage 2  build_components()   run all analysis, return ReportLab objects
    Stage 3  assemble_elements()  order flowables for the PDF layout
    Stage 4  run_report()         orchestrate all stages, write PDF, return Path

Neither scheduling nor email delivery belongs here — callers handle that.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

from reportlab.lib import colors
from reportlab.platypus import FrameBreak, NextPageTemplate, PageBreak, Paragraph, Table

from config import ReportConfig
from data.loader import load_data, _resolve_path
from analysis.summary import CreateCoverPageTable
from analysis.cutby import CreateCutBy
from viz.histograms import CreateFeatureHistograms
from report.builder import createMultiPage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class ReportResult(NamedTuple):
    """Return value of run_report().

    Using a NamedTuple means callers can either unpack it::

        pdf_path, sd, ed = run_report(cfg)

    or access fields by name::

        result = run_report(cfg)
        send_report(result.pdf_path, cfg, sd=result.start_date, ed=result.end_date)
    """
    pdf_path:   Path
    start_date: str   # 'YYYY-MM-DD'
    end_date:   str   # 'YYYY-MM-DD'


# ---------------------------------------------------------------------------
# Stage 2 — Analyse
# ---------------------------------------------------------------------------

def build_components(data, config: ReportConfig) -> dict:
    """Run all analysis steps and return a dict of ReportLab-ready objects.

    Each value in the returned dict is a fully rendered ReportLab flowable
    (Table or Image) that can be placed directly into the elements list.

    Args:
        data:   Transformed DataFrame produced by load_data().
        config: Report configuration.

    Returns:
        Dict with keys:
            ``main_table`` — TableOne summary as a ReportLab Table
            ``hist_image`` — Feature histogram grid as a ReportLab Image
            ``cutby_dict`` — {feature: ReportLab Image} for every cut-by column
    """
    logger.info("Building cover-page summary table")
    main_table, _table_df = CreateCoverPageTable(
        data,
        weighting=config.weight_col,
        features=config.feature_cols,
        grouping=config.grouping,
        sumcols=config.sum_cols,
    )

    logger.info("Building feature histogram grid")
    hist_image, _sns_obj = CreateFeatureHistograms(data, features=config.feature_cols)

    logger.info("Building cut-by panels for: %s", config.cut_by_cols)
    cutby_dict = CreateCutBy(
        data,
        sub_df_init=config.sub_df_cols,
        KPI=config.kpi,
        TimeBin=config.time_bin,
        nbins=config.nbins,
        cut_by_cols=config.cut_by_cols,
        weighting=config.weight_col,
        sum_cols=config.sum_cols,
        grouping=config.grouping,
    )

    return {
        'main_table': main_table,
        'hist_image': hist_image,
        'cutby_dict': cutby_dict,
    }


# ---------------------------------------------------------------------------
# Stage 3 — Assemble ReportLab flowables
# ---------------------------------------------------------------------------

def assemble_elements(components: dict, config: ReportConfig) -> list:
    """Order analysis components into a ReportLab flowables list.

    Page layout
    -----------
    Page 1   Cover — summary table (left) + histogram grid (right)
    Page 2+  Two CutBy panels per page, using the CutByPage template's
             top frame (first panel) and bottom frame (second panel).
             A PageBreak opens each new pair; a FrameBreak separates the
             two panels that share a page.

    Args:
        components: Output of build_components().
        config:     Report configuration.

    Returns:
        Ordered list of ReportLab flowables ready for ``doc.build()``.
    """
    cover = Table([[components['main_table'], components['hist_image']]])
    cover.hAlign = 'LEFT'
    cover.setStyle([
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
        ('BOX',       (0, 0), (-1, -1), 0.25, colors.white),
        ('VALIGN',    (0, 0), ( 0,  0), 'MIDDLE'),
    ])

    elements: list = [cover]

    cutby_dict = components['cutby_dict']
    for i, feature in enumerate(config.cut_by_cols):
        if i % 2 == 0:
            # First panel on a fresh CutBy page
            elements += [NextPageTemplate('CutByPage'), PageBreak()]
        else:
            # Second panel on the same page — drop into the bottom frame
            elements.append(FrameBreak())
        elements += [Paragraph(f'CutBy: {feature}'), cutby_dict[feature]]

    return elements


# ---------------------------------------------------------------------------
# Stage 4 — Public entry point
# ---------------------------------------------------------------------------

def run_report(config: ReportConfig) -> ReportResult:
    """Run the full report pipeline end-to-end.

    This is the single function both the automation runner and the
    Streamlit UI call.  It owns no scheduling or delivery logic.

    Args:
        config: Fully populated ReportConfig instance.

    Returns:
        ReportResult(pdf_path, start_date, end_date) — the scheduler and
        Streamlit UI use start_date/end_date to populate email subjects and
        UI labels without having to re-read the source data.

    Example::

        from config import ReportConfig
        from pipeline import run_report

        result = run_report(ReportConfig(client_name='XYZ', output_file='xyz.pdf'))
        print(f"Report written to {result.pdf_path}")
    """
    logger.info("=== Starting report: %s ===", config.client_name)

    data       = load_data(config)
    components = build_components(data, config)
    elements   = assemble_elements(components, config)

    # Capture date strings once — used in both the PDF footer and the email
    sd = str(data[config.date_col].min().date())
    ed = str(data[config.date_col].max().date())

    output_path = _resolve_path(config.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    createMultiPage(
        elements,
        report_name=config.client_name,
        sd=sd,
        ed=ed,
        output_file=str(output_path),
    )

    logger.info("=== Report written to %s ===", output_path)
    return ReportResult(pdf_path=output_path, start_date=sd, end_date=ed)
