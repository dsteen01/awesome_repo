from reportlab.lib.pagesizes import letter
from reportlab.platypus import Frame, PageTemplate, Table, TableStyle, BaseDocTemplate
from reportlab.lib.units import cm
from reportlab.lib import colors

def create_pdf():
    # Create a frame
    CatBox_frame = Frame(
        x1=14.00 * cm,
        y1=1.5 * cm,
        height=9.60 * cm,
        width=5.90 * cm,
        showBoundary=1,
        id='CatBox_frame'
    )

    # Create a table (adjust data as needed)
    CatBox = Table(
        [['', '', '', 'A'],
         ['', '', '', 'B'],
         ['', '', '', 'C'],
         ['AA', 'BB', 'CC', '']],
        1.2 * cm,
        1.2 * cm,
        vAlign='BOTTOM'  # Align the table to the bottom of the frame
    )

    # Style the table (customize as needed)
    CatBox.setStyle(TableStyle([
        ('SIZE', (0, 0), (-1, -1), 7),
        ('SIZE', (0, 0), (0, 0), 5.5),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),  # Align vertically to the bottom
    ]))

    # Build the story
    story = [CatBox]

    # Create a page template
    frontpage = PageTemplate(id='FrontPage', frames=[CatBox_frame])

    # Create the document
    doc = BaseDocTemplate("BottomAlignTable.pdf", pagesize=letter)
    doc.addPageTemplates(frontpage)
    doc.build(story)

if __name__ == "__main__":
    create_pdf()