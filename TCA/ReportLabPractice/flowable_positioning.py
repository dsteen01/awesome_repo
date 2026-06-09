from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph,SimpleDocTemplate


def my_canvas(canvas, doc):
    frame = Frame(inch, inch, 6*inch, 9*inch, showBoundary=1)
    text = "This is a paragraph."
    p = Paragraph(text, style=None)
    p.wrapOn(canvas, 6*inch, 9*inch)
    p.drawOn(canvas, frame._x1, frame._y1 - p.height)

doc = SimpleDocTemplate("example.pdf", pagesize=letter)
doc.build([Paragraph("Hello, world!")], onFirstPage=my_canvas)