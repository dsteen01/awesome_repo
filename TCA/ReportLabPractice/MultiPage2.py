from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm


########################################################################
class PageNumCanvas(canvas.Canvas):
    """
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
        self.drawRightString(195 * mm, 272 * mm, page)


# ----------------------------------------------------------------------
def createMultiPage():
    """
    Create a multi-page document
    """
    doc = SimpleDocTemplate("doc_page_num_v2.pdf", pagesize=letter,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Justify', alignment=TA_JUSTIFY))

    Story = []

    magName = "Pythonista"
    issueNum = 12
    subPrice = "99.00"
    limitedDate = "03/05/2010"
    freeGift = "tin foil hat"
    full_name = "Marvin Jones"
    address_parts = ["411 State St.", "Reno, NV 80158"]

    for page in range(5):
        # Create return address
        ptext = '<font size="12">%s</font>' % full_name
        Story.append(Paragraph(ptext, styles["Normal"]))
        for part in address_parts:
            ptext = '<font size="12">%s</font>' % part.strip()
            Story.append(Paragraph(ptext, styles["Normal"]))

        Story.append(Spacer(1, 12))
        ptext = '<font size="12">Dear %s:</font>' % full_name.split()[0].strip()
        Story.append(Paragraph(ptext, styles["Normal"]))
        Story.append(Spacer(1, 12))

        ptext = """<font size="12">We would like to welcome you to our subscriber base 
        for %s Magazine! You will receive %s issues at the excellent introductory 
        price of $%s. Please respond by %s to start receiving your subscription 
        and get the following free gift: %s.</font>"""
        ptext = ptext % (magName, issueNum, subPrice, limitedDate, freeGift)
        Story.append(Paragraph(ptext, styles["Justify"]))
        Story.append(Spacer(1, 12))

        ptext = '<font size="12">Thank you very much and we look forward to serving you.</font>'
        Story.append(Paragraph(ptext, styles["Justify"]))
        Story.append(Spacer(1, 12))
        ptext = '<font size="12">Sincerely,</font>'
        Story.append(Paragraph(ptext, styles["Normal"]))
        Story.append(Spacer(1, 48))
        ptext = '<font size="12">Ima Sucker</font>'
        Story.append(Paragraph(ptext, styles["Normal"]))
        Story.append(Spacer(1, 12))
        Story.append(PageBreak())

    doc.build(Story, canvasmaker=PageNumCanvas)


# ----------------------------------------------------------------------
if __name__ == "__main__":
    createMultiPage()