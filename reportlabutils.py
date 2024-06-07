from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame, Paragraph, NextPageTemplate, PageBreak, Table, TableStyle, Image, FrameBreak, Spacer
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
import io


#https://medium.com/@parveengoyal198/mastering-pdf-report-generation-with-reportlab-a-comprehensive-tutorial-part-2-c970ccd15fb6
#https://python.hotexamples.com/examples/reportlab.platypus/SimpleDocTemplate/addPageTemplates/python-simpledoctemplate-addpagetemplates-method-examples.html
#https://nicd.org.uk/knowledge-hub/creating-pdf-reports-with-reportlab-and-pandas

class MyDocTemplate(BaseDocTemplate):
    """Template class for PDF document"""
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)

        self.title = kwargs.get('title',None)
        self.start_date = kwargs.get('start',None)
        self.end_date = kwargs.get('end',None)

        # Define the page frames

        self.frame = Frame(0.5*inch, 0.5*inch, width=10*inch, height=inch*7.5,
            leftPadding=0 * inch,
            bottomPadding=0 * inch,
            rightPadding= 0 * inch,
            topPadding=0 * inch,
            id='normal', showBoundary=1
        )

        self.CutByTopFrame = Frame(0.5 * inch, 4.5 * inch, width=10 * inch, height=3.5 * inch, showBoundary=1, id='Top')
        self.CutByBottomFrame = Frame(0.5 * inch, 0.5 * inch, width=10 * inch, height=3.5 * inch, showBoundary=1, id='Bottom')

        # Define the styles for header and footer
        self.styles = getSampleStyleSheet()
        self.header_style = self.styles['Title']
        self.footer_style = self.styles['Normal']

        # Define the header and footer frames
        self.header_frame = Frame(
            0.5 * inch, self.pagesize[1] - 0.5 * inch, self.pagesize[0] - inch, 0.5 * inch, showBoundary=1,
            id='header'
        )
        self.footer_frame = Frame(
            0.5 * inch, 0.25 * inch, self.pagesize[0] - inch, 0.5 * inch,
            id='footer'
        )

        # Define the PageTemplates
        self.addPageTemplates([
            PageTemplate(
                id='FirstPage',
                frames=[self.frame, self.header_frame, self.footer_frame],
                onPage=self._header_footer,
                onPageEnd=self._footer
            ),
            PageTemplate(
                id='CutByPage',
                frames=[self.CutByTopFrame, self.CutByBottomFrame],
                onPage=self._header_footer,
                onPageEnd=self._footer
            )
        ])

    def _header_footer(self, canvas, doc):
        # Draw the header
        self.header_style.alignment = 0  # center align the header text
        header_text = Paragraph(self.title, self.header_style)
        header_text.wrapOn(canvas, self.header_frame.width, self.header_frame.height)
        header_text.drawOn(canvas, self.header_frame.x1, self.header_frame.y1)

    def _footer(self, canvas, doc):
        # Draw the footer
        self.footer_style.alignment = 0  # center align the footer text
        dates = "Date Range: %s - %s" % (self.start_date,self.end_date)
        footer_text= Paragraph(dates,self.footer_style)
        #page = "Page <seq id='PageNumber'/> of %s" % (len(self.pageTemplates))
        #footer_text = Paragraph("",self.footer_style)
        #footer_text = Paragraph("Page <seq id='PageNumber'/> of <seq id='TotalPages'/>", self.footer_style)
        footer_text.wrapOn(canvas, self.footer_frame.width, self.footer_frame.height)
        footer_text.drawOn(canvas, self.footer_frame.x1, self.footer_frame.y1)

########################################################################

def df2table(df):
    return Table(
      [[Paragraph(col) for col in df.columns]] + df.values.tolist(),
      colWidths=[1.5 * inch, 1.1 * inch],
      style=[
          ("VALIGN", (0, 0), (0, 0), "TOP"),
          ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
          ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
          ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
          ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
          ('FONTSIZE', (0, 0), (-1, 0), 10),
          ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
          ('BACKGROUND', (0, 1), (-1, -1), colors.transparent),
          ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
          ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
          ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
          ('FONTSIZE', (0, 1), (-1, -1), 8),
          ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
          ('GRID', (0, 0), (-1, -1), 1, colors.black)],
      hAlign = 'LEFT')

########################################################################
def fig2image(f):
    buf = io.BytesIO()
    f.savefig(buf, format='png', dpi=300)
    buf.seek(0)
    try:
        x, y = f.fig.get_size_inches()
    except:
        x, y = f.get_size_inches()
    return Image(buf, x * inch, y * inch)


########################################################################

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm


########################################################################
class PageNumCanvas(canvas.Canvas):
    """
    https://www.blog.pythonlibrary.org/2013/08/12/reportlab-how-to-add-page-numbers/
    http://code.activestate.com/recipes/546511-page-x-of-y-with-reportlab/
    http://code.activestate.com/recipes/576832/
    """

    # ----------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        """Constructor"""
        canvas.Canvas.__init__(self, *args, **kwargs)
        self.pages = []



    # ----------------------------------------------------------------------
    def showPage(self):
        """
        On a page break, add information to the list
        """
        self.pages.append(dict(self.__dict__))
        self._startPage()

    # ----------------------------------------------------------------------
    def save(self):
        """
        Add the page number to each page (page x of y)
        """
        page_count = len(self.pages)

        for page in self.pages:
            self.__dict__.update(page)
            self.draw_page_number(page_count)
            canvas.Canvas.showPage(self)

        canvas.Canvas.save(self)

    # ----------------------------------------------------------------------
    def draw_page_number(self, page_count):
        """
        Add the page number
        """
        page = "Page %s of %s" % (self._pageNumber, page_count)
        self.setFont("Helvetica", 9)
        #self.drawRightString(195 * mm, 272 * mm, page)
        self.drawRightString(272 * mm, 8 * mm, page)

# ----------------------------------------------------------------------
def createMultiPage(elements,report_name,sd,ed):
    """
    Create a multi-page document
    """
    doc = MyDocTemplate('TestFile.pdf', pagesize=landscape(letter),title=report_name,start=sd,end=ed)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY))

    doc.build(elements, canvasmaker=PageNumCanvas)


