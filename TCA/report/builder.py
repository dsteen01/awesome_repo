"""
report/builder.py — High-level PDF assembly entry point.

Functions
---------
createMultiPage(elements, report_name, sd, ed, output_file)
    Instantiate MyDocTemplate, wire up PageNumCanvas, and call doc.build().
"""

from __future__ import annotations

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from report.templates import MyDocTemplate, PageNumCanvas


def createMultiPage(
    elements: list,
    report_name: str,
    sd: str,
    ed: str,
    output_file: str = 'TestFile.pdf',
) -> None:
    """Build a multi-page landscape PDF from a ReportLab flowable list.

    Args:
        elements:    Ordered list of ReportLab flowables.
        report_name: Client / report title shown in the page header.
        sd:          Report start date string shown in the footer.
        ed:          Report end date string shown in the footer.
        output_file: Destination path for the PDF (default ``'TestFile.pdf'``).
    """
    doc = MyDocTemplate(
        output_file,
        pagesize=landscape(letter),
        title=report_name,
        start=sd,
        end=ed,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY))

    doc.build(elements, canvasmaker=PageNumCanvas)
