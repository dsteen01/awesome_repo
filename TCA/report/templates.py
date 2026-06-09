"""
report/templates.py — ReportLab document-level classes.

Classes
-------
MyDocTemplate
    BaseDocTemplate subclass with a FirstPage and CutByPage template,
    plus header/footer callbacks that stamp the client name and date range.

PageNumCanvas
    Canvas subclass that defers page numbers until save-time so that the
    ``Page X of Y`` string can be rendered correctly on every page.
"""

from __future__ import annotations

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
)


class MyDocTemplate(BaseDocTemplate):
    """ReportLab document template with a header, footer, and two page layouts.

    Page templates
    --------------
    FirstPage
        Single full-width frame for the cover-page content, plus header and
        footer frames.
    CutByPage
        Two vertically stacked frames (top / bottom) for CutBy panels.
    """

    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)

        self.title      = kwargs.get('title', None)
        self.start_date = kwargs.get('start', None)
        self.end_date   = kwargs.get('end',   None)

        # ── Frames ────────────────────────────────────────────────────────────
        self.frame = Frame(
            0.5 * inch, 0.5 * inch,
            width=10 * inch, height=7.5 * inch,
            leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0,
            id='normal', showBoundary=1,
        )
        self.CutByTopFrame = Frame(
            0.5 * inch, 4.5 * inch,
            width=10 * inch, height=3.5 * inch,
            showBoundary=1, id='Top',
        )
        self.CutByBottomFrame = Frame(
            0.5 * inch, 0.5 * inch,
            width=10 * inch, height=3.5 * inch,
            showBoundary=1, id='Bottom',
        )

        # ── Header / footer frames ────────────────────────────────────────────
        styles = getSampleStyleSheet()
        self.header_style = styles['Title']
        self.footer_style = styles['Normal']

        self.header_frame = Frame(
            0.5 * inch, self.pagesize[1] - 0.5 * inch,
            self.pagesize[0] - inch, 0.5 * inch,
            showBoundary=1, id='header',
        )
        self.footer_frame = Frame(
            0.5 * inch, 0.25 * inch,
            self.pagesize[0] - inch, 0.5 * inch,
            id='footer',
        )

        self.addPageTemplates([
            PageTemplate(
                id='FirstPage',
                frames=[self.frame, self.header_frame, self.footer_frame],
                onPage=self._header_footer,
                onPageEnd=self._footer,
            ),
            PageTemplate(
                id='CutByPage',
                frames=[self.CutByTopFrame, self.CutByBottomFrame],
                onPage=self._header_footer,
                onPageEnd=self._footer,
            ),
        ])

    def _header_footer(self, canvas, doc) -> None:
        self.header_style.alignment = 0
        header = Paragraph(self.title or '', self.header_style)
        header.wrapOn(canvas, self.header_frame.width, self.header_frame.height)
        header.drawOn(canvas, self.header_frame.x1, self.header_frame.y1)

    def _footer(self, canvas, doc) -> None:
        self.footer_style.alignment = 0
        dates  = f"Date Range: {self.start_date} - {self.end_date}"
        footer = Paragraph(dates, self.footer_style)
        footer.wrapOn(canvas, self.footer_frame.width, self.footer_frame.height)
        footer.drawOn(canvas, self.footer_frame.x1, self.footer_frame.y1)


class PageNumCanvas(canvas.Canvas):
    """Canvas subclass that renders ``Page X of Y`` on every page.

    ReportLab's two-pass strategy: pages are collected during ``showPage``
    and the total count is only known at ``save`` time.

    References
    ----------
    https://www.blog.pythonlibrary.org/2013/08/12/reportlab-how-to-add-page-numbers/
    http://code.activestate.com/recipes/546511-page-x-of-y-with-reportlab/
    """

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self.pages: list[dict] = []

    def showPage(self) -> None:
        self.pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            self._draw_page_number(page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_page_number(self, page_count: int) -> None:
        label = f"Page {self._pageNumber} of {page_count}"
        self.setFont("Helvetica", 9)
        self.drawRightString(272 * mm, 8 * mm, label)
