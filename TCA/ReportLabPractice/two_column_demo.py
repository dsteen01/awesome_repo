# two_column_demo.py

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Frame, Image, Spacer



def frame_demo():
    my_canvas = Canvas("frame_demo.pdf",
                       pagesize=landscape(letter))

    img = Image("snakehead.jpg", 50, 50)

    styles = getSampleStyleSheet()
    normal = styles['Normal']
    heading = styles['Heading1']

    flowables = []
    flowables.append(img)
    flowables.append(Paragraph('Heading #1', heading))

    right_flowables = []
    right_flowables.append(Paragraph('Heading #2', heading))
    right_flowables.append(Paragraph('ipsum lorem', normal))

    bottom_frame = Frame(0.5*inch, 0.5*inch, width=10*inch, height=3.5*inch, showBoundary=1)
    top_frame = Frame(0.5*inch, 4.5*inch, width=10*inch, height=3.5*inch, showBoundary=1)

    bottom_frame.addFromList(flowables, my_canvas)
    top_frame.addFromList(right_flowables, my_canvas)

    my_canvas.save()

if __name__ == '__main__':
    frame_demo()