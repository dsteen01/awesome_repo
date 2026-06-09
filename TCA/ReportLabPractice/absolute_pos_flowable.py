# absolute_pos_flowable.py

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet


def mixed():
    my_canvas = canvas.Canvas("mixed_flowables.pdf", pagesize=letter)
    styles = getSampleStyleSheet()
    width, height = letter

    text = "Hello, I'm a Paragraph"
    para = Paragraph(text, style=styles["Normal"])
    para.wrapOn(my_canvas, width, height)
    para.drawOn(my_canvas, 200, 600)

    my_canvas.drawImage("snakehead.jpg",width/2,height/2, width=50,height=50)

    my_canvas.save()

if __name__ == '__main__':
    mixed()