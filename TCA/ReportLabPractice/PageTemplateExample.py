from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame, Paragraph, NextPageTemplate, PageBreak, Table, TableStyle, Image, FrameBreak
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors



#https://medium.com/@parveengoyal198/mastering-pdf-report-generation-with-reportlab-a-comprehensive-tutorial-part-2-c970ccd15fb6
#https://python.hotexamples.com/examples/reportlab.platypus/SimpleDocTemplate/addPageTemplates/python-simpledoctemplate-addpagetemplates-method-examples.html
#https://nicd.org.uk/knowledge-hub/creating-pdf-reports-with-reportlab-and-pandas

class MyDocTemplate(BaseDocTemplate):
    """Template class for PDF document"""

    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)

        # Define the page frames
        self.frame = Frame(
            inch, inch, self.pagesize[0] - inch * 2, self.pagesize[1] - inch * 2,
            leftPadding=0 * inch,
            bottomPadding=0 * inch,
            rightPadding= 0 * inch,
            topPadding=0 * inch,
            id='normal', showBoundary=1
        )

        self.CutByTopFrame = Frame(0.5*inch, 4.5*inch, width=10*inch, height=inch*3, showBoundary=1, id='Top')
        self.CutByBottomFrame = Frame(0.5*inch, 0.5*inch, width=10*inch, height=inch*3, showBoundary=1, id='Bottom')


        # Define the styles for header and footer
        self.styles = getSampleStyleSheet()
        self.header_style = self.styles['Heading1']
        self.footer_style = self.styles['Normal']

        # Define the header and footer frames
        self.header_frame = Frame(
            inch, self.pagesize[1] - 0.5 * inch, self.pagesize[0] - inch, 0.5 * inch, showBoundary=1,
            id='header'
        )
        self.footer_frame = Frame(
            inch, 0.25 * inch, self.pagesize[0] - inch, 0.5 * inch,
            id='footer'
        )

        # Define the PageTemplate
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
        self.header_style.alignment = 1  # center align the header text
        header_text = Paragraph('My Header Text', self.header_style)
        header_text.wrapOn(canvas, self.header_frame.width, self.header_frame.height)
        header_text.drawOn(canvas, self.header_frame.x1, self.header_frame.y1)

    def _footer(self, canvas, doc):
        # Draw the footer

        self.footer_style.alignment = 1  # center align the footer text
        footer_text = Paragraph("Page <seq id='PageNumber'/> of <seq id='TotalPages'/>", self.footer_style)
        footer_text.wrapOn(canvas, self.footer_frame.width, self.footer_frame.height)
        footer_text.drawOn(canvas, self.footer_frame.x1, self.footer_frame.y1)

# Create a new PDF document using the template
pdf_doc = MyDocTemplate('example_page_template_header_footer.pdf',pagesize=landscape(letter))

logo = Image("snakehead.jpg")
logo.drawHeight = 2 * inch
logo.drawWidth = 2 * inch

data = [['col_{}'.format(x) for x in range(1, 6)]]

table = Table(data)

tbl = Table([[table,logo]],colWidths=6*inch)

tbl.hAlign='LEFT'
tbl.setStyle([('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
                ('BOX', (0, 0), (-1, -1), 0.25, colors.white),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ])


elements = [tbl,NextPageTemplate('CutByPage'),PageBreak(),Paragraph('This is some content for the PDF document Page 2.'),
            FrameBreak(),Paragraph('This is EXTRA content for the PDF document Page 2.')]


# Add the content to the PDF document
#elements = [Paragraph('This is some content for the PDF document Page 1.'), PageBreak(),
#            Paragraph('This is some content for the PDF document Page 2.')]

pdf_doc.build(elements)