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

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import FrameBreak, NextPageTemplate, PageBreak, Paragraph, Table

from config import ReportConfig
from data.loader import load_data, _resolve_path
from analysis.summary import CreateCoverPageTable
from analysis.cutby import ConsolidatedCutBy
from viz.histograms import CreateFeatureHistograms
from report.builder import createMultiPage
from report.components import SectionMarker

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
    main_table, cover_chart, _table_df = CreateCoverPageTable(
        data,
        weighting=config.weight_col,
        features=config.feature_cols,
        grouping=config.grouping,
        sumcols=config.sum_cols,
        kpi=config.kpi,
        date_col=config.date_col,
        time_bin=config.time_bin,
        activity_col=config.activity_col,
    )

    logger.info("Building feature histogram grid")
    hist_image, _sns_obj = CreateFeatureHistograms(data, features=config.feature_cols)

    logger.info("Building cut-by panels for: %s", config.cut_by_cols)
    cutby_dict = ConsolidatedCutBy(
        data,
        sub_df_init=config.sub_df_cols,
        KPI=config.kpi,
        nbins=config.nbins,
        cut_by_cols=config.cut_by_cols,
        weighting=config.weight_col,
        sum_cols=config.sum_cols,
        grouping=config.grouping,
    )

    return {
        'main_table':  main_table,
        'hist_image':  hist_image,
        'cover_chart': cover_chart,
        'cutby_dict':  cutby_dict,
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

    elements: list = [cover, components['cover_chart']]

    cutby_dict = components['cutby_dict']

    # -- Commented out: original two-panel-per-page layout -----------------
    # for i, feature in enumerate(config.cut_by_cols):
    #     if i % 2 == 0:
    #         # First panel on a fresh CutBy page
    #         elements += [NextPageTemplate('CutByPage'), PageBreak()]
    #     else:
    #         # Second panel on the same page — drop into the bottom frame
    #         elements.append(FrameBreak())
    #     elements += [Paragraph(f'CutBy: {feature}'), cutby_dict[feature]]
    # ----------------------------------------------------------------------

    # Grid layout: all CutBy figures on one page in 3 columns.
    # FirstPage has a single 10" × 7.5" frame — large enough to hold 3 rows
    # of 3-column images at ~1.94" per row (5.82" total) without overflowing
    # to a third page.  CutByPage's two 3.5" frames cannot hold 3 rows each,
    # so FirstPage is the right template here.
    ncols = 3
    col_w = 9.9 * inch / ncols
    aspect = 3.5 / 6   # ConsolidatedCutBy figsize=(6, 3.5)

    cutby_images = []
    for f in config.cut_by_cols:
        if f in cutby_dict:
            img = cutby_dict[f]
            img.drawWidth  = col_w
            img.drawHeight = col_w * aspect
            cutby_images.append(img)

    # Pad last row so the Table is rectangular
    while len(cutby_images) % ncols:
        cutby_images.append('')

    rows = [cutby_images[i:i + ncols] for i in range(0, len(cutby_images), ncols)]
    grid = Table(rows, colWidths=[col_w] * ncols)
    grid.hAlign = 'LEFT'
    elements += [NextPageTemplate('FirstPage'), PageBreak(), grid]

    return elements


# ---------------------------------------------------------------------------
# Stage 3b — Multi-section assembly (split_by)
# ---------------------------------------------------------------------------

def _assemble_split(data: pd.DataFrame, config: ReportConfig) -> list:
    """Build one 2-page section per unique value of ``config.split_by``.

    Sections are concatenated into a single flowable list suitable for a single
    ``createMultiPage`` call.  Each section starts on a fresh FirstPage and is
    labelled with its split value.
    """
    split_values = sorted(data[config.split_by].dropna().unique())
    all_elements: list = []

    for i, val in enumerate(split_values):
        logger.info("Building section for %s='%s'", config.split_by, val)
        subset     = data[data[config.split_by] == val].copy()
        components = build_components(subset, config)
        section    = assemble_elements(components, config)

        # SectionMarker must be the first flowable AFTER the page break so
        # afterFlowable fires on the correct new page before showPage() snapshots it.
        label = f'{config.split_by.title()}: {val}'
        section = [SectionMarker(label)] + section

        if i > 0:
            section = [NextPageTemplate('FirstPage'), PageBreak()] + section

        all_elements.extend(section)

    return all_elements


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

    data = load_data(config)

    # Apply row_filters before any analysis (e.g. restrict to one client)
    for col, val in config.row_filters.items():
        data = data[data[col] == val].copy()
    if config.row_filters and data.empty:
        raise ValueError(
            f"No rows remain after applying row_filters: {config.row_filters}"
        )

    # Capture date strings from the full filtered dataset (pre-split)
    sd = str(data[config.date_col].min().date())
    ed = str(data[config.date_col].max().date())

    if config.split_by:
        elements = _assemble_split(data, config)
    else:
        components = build_components(data, config)
        elements   = assemble_elements(components, config)

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
