from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, NextPageTemplate, PageBreak
from reportlab.pdfgen.canvas import Canvas


#https://medium.com/@parveengoyal198/mastering-pdf-report-generation-with-reportlab-a-comprehensive-tutorial-part-2-c970ccd15fb6

class MyDocTemplate(BaseDocTemplate):
    """Template class for PDF document"""

    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)

        # Define the page frames
        self.frame = Frame(
            inch, inch, self.pagesize[0] - inch * 2, self.pagesize[1] - inch * 2,
            id='normal'
        )

        # Define the styles for header and footer
        self.styles = getSampleStyleSheet()
        self.header_style = self.styles['Heading1']
        self.footer_style = self.styles['Normal']

        # Define the header and footer frames
        self.header_frame = Frame(
            inch, self.pagesize[1] - 0.5 * inch, self.pagesize[0] - inch, 0.5 * inch,
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
        footer_text = Paragraph("Page<seq id='PageNumber'/> of <seq id='TotalPages'/>", self.footer_style)
        footer_text.wrapOn(canvas, self.footer_frame.width, self.footer_frame.height)
        footer_text.drawOn(canvas, self.footer_frame.x1, self.footer_frame.y1)


# Create a new PDF document using the template
pdf_doc = MyDocTemplate('example_page_template_header_footer.pdf')

# Add the content to the PDF document
elements = [Paragraph('This is some content for the PDF document.'), PageBreak(),
            Paragraph('This is some content for the PDF document Page 2.')]

pdf_doc=MyDocTemplate('MultipageTest.pdf')
pdf_doc.build(elements)