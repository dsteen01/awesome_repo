"""
report/components.py — Low-level ReportLab building blocks.

Functions
---------
df2table(df)
    Convert a pandas DataFrame into a styled ReportLab Table flowable.

fig2image(f)
    Render a Matplotlib Figure (or FacetGrid) to a ReportLab Image flowable
    without writing any temporary files to disk.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, Image, Paragraph, Table


class SectionMarker(Flowable):
    """Zero-height marker that carries a section label to MyDocTemplate.

    Placing this as the first flowable in a section causes ``afterFlowable``
    on ``MyDocTemplate`` to update the canvas's ``current_section``, which
    ``PageNumCanvas`` then stamps in the top-right corner of every page via
    its deferred-draw mechanism.
    """

    def __init__(self, section: str):
        super().__init__()
        self.section = section
        self.width   = 0
        self.height  = 0

    def draw(self):
        pass


def df2table(df) -> Table:
    """Convert *df* into a styled ReportLab ``Table`` flowable.

    The first row is treated as a header (grey background, bold Helvetica).
    Subsequent rows use plain Helvetica at 8 pt.

    Args:
        df: pandas DataFrame whose ``.columns`` and ``.values`` are used.

    Returns:
        Left-aligned ``Table`` flowable ready for ``doc.build()``.
    """
    return Table(
        [[Paragraph(col) for col in df.columns]] + df.values.tolist(),
        colWidths=[1.5 * inch, 1.1 * inch],
        style=[
            ('VALIGN',        (0, 0), (0,  0),  'TOP'),
            ('BACKGROUND',    (0, 0), (-1, 0),   colors.grey),
            ('TEXTCOLOR',     (0, 0), (-1, 0),   colors.whitesmoke),
            ('ALIGN',         (0, 0), (-1, 0),   'LEFT'),
            ('FONTNAME',      (0, 0), (-1, 0),   'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0),   10),
            ('BOTTOMPADDING', (0, 0), (-1, 0),   4),
            ('BACKGROUND',    (0, 1), (-1, -1),  colors.transparent),
            ('TEXTCOLOR',     (0, 1), (-1, -1),  colors.black),
            ('ALIGN',         (0, 1), (-1, -1),  'LEFT'),
            ('FONTNAME',      (0, 1), (-1, -1),  'Helvetica'),
            ('FONTSIZE',      (0, 1), (-1, -1),  8),
            ('BOTTOMPADDING', (0, 1), (-1, -1),  2),
            ('GRID',          (0, 0), (-1, -1),  1, colors.black),
        ],
        hAlign='LEFT',
    )


def fig2image(f) -> Image:
    """Render Matplotlib figure *f* to a ReportLab ``Image`` flowable.

    Works with both plain ``Figure`` objects and seaborn ``FacetGrid``
    instances (which expose ``.fig``).

    Args:
        f: Matplotlib ``Figure`` or seaborn ``FacetGrid``.

    Returns:
        ``Image`` flowable sized to match the figure's declared size in inches.
    """
    buf = io.BytesIO()
    f.savefig(buf, format='png', dpi=300)
    buf.seek(0)
    try:
        x, y = f.fig.get_size_inches()   # FacetGrid
    except AttributeError:
        x, y = f.get_size_inches()        # plain Figure
    return Image(buf, x * inch, y * inch)
