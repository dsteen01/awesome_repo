from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# Define the header style
header_style = ParagraphStyle(name='Header', fontSize=14, leading=16)

# Define the header content
header_content = 'This is the header'

# Define the document template
doc = SimpleDocTemplate('example.pdf', pagesize=letter)

# Define the story
story = []

# Add the header to each page
def add_header(canvas, doc):
    canvas.saveState()
    header = Paragraph(header_content, header_style)
    w, h = header.wrap(doc.width, doc.topMargin)
    header.drawOn(canvas, doc.leftMargin, doc.height + doc.topMargin - h)
    canvas.restoreState()

# Define the table data
data = [['Name', 'Age', 'Gender'], ['Alice', '25', 'Female'], ['Bob', '30', 'Male'], ['Charlie', '35', 'Male']]

# Define the table style
table_style = TableStyle([('BACKGROUND', (0, 0), (-1, 0), '#CCCCCC'), ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 14), ('BOTTOMPADDING', (0, 0), (-1, 0), 12), ('BACKGROUND', (0, 1), (-1, -1), '#FFFFFF'), ('TEXTCOLOR', (0, 1), (-1, -1), '#000000'), ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 1), (-1, -1), 12), ('TOPPADDING', (0, 1), (-1, -1), 12), ('BOTTOMPADDING', (0, -1), (-1, -1), 12)])

# Create the table
table = Table(data)

# Apply the table style
table.setStyle(table_style)

# Define the table position
table_x = 1 * inch
table_y = 2 * inch

# Add the table to the story
story.append(Spacer(1, inch))
story.append(Paragraph('This is some content', ParagraphStyle(name='Normal')))
story.append(Spacer(1, inch))

# Build the document
doc.build(story, onFirstPage=add_header, onLaterPages=add_header)

# Get the page height and width
page_width, page_height = letter

# Get the table width and height
#table.wrapOn(doc, page_width, page_height)
table_width, table_height = table.wrap(0, 0)

# Create the canvas
canvas = doc.canv

# Draw the table at the specified position
table.drawOn(canvas, table_x, page_height - table_y - table_height)