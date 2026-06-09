import sys

sys.path.append('/TCA/tableone')
#from tableone import TableOne, load_dataset
import pandas as pd
from reportlabutils import *
from utils import *

#data=load_dataset('toydata_v2.xlsx')

data = pd.read_excel('toydata_v2.xlsx')
data['adv_pct']*=100
data['avg_spread']*=100

data[['order_qty','exec_qty','exec_val_usd']]/=1e6
data[['market_cap']]/=1e3
data.rename(columns={'ordre_len_seconds': 'Duration', 'liq_consumption': 'TradeRate', 'arrival_mid_px_slp_bps':'ArrSlipBps'}, inplace=True)

#datawin = CreateOutlierFrame(data,mode='win')
#For Hypothesis testing
#data = data[(data['trader_id']=='A') | (data['trader_id']=='B')]


columns = ['Duration','adv_pct', 'TradeRate', 'impact_cost_bps','market_cap','volatility_30d','avg_spread','ArrSlipBps']
grouping = None # ['trader_id]
weight = ['exec_val_usd']
sum_cols = ['order_qty','exec_qty','exec_val_usd']
sub_df_has = ['trade_date','exec_val_usd','ArrSlipBps']
KPI_ = 'ArrSlipBps'
cut_by_cols_ = ['Duration','adv_pct', 'TradeRate', 'impact_cost_bps','market_cap','volatility_30d','avg_spread']

MainTable,TableDF = CreateCoverPageTable(data, weighting=weight, features=columns,grouping=None,sumcols=sum_cols)
ReportLabHist, SNSObj = CreateFeatureHistograms(data,features=columns)
CutByDict = CreateCutBy(data,sub_df_init=sub_df_has,KPI=KPI_,TimeBin='Daily',nbins=5,cut_by_cols=cut_by_cols_,weighting=weight,sum_cols=sum_cols,grouping=None)

#TemporalDict = CreateFeatureTS(data,weighting=weight,dim='Daily',features=columns,sum_cols=sum_cols,grouping=None)
#logo = Image("snakehead.jpg")
#logo.drawHeight = 2 * inch
#logo.drawWidth = 2 * inch

tbl = Table([[MainTable,ReportLabHist]])

tbl.hAlign='LEFT'
tbl.setStyle([('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
                ('BOX', (0, 0), (-1, -1), 0.25, colors.white),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ])


elements = [tbl,NextPageTemplate('CutByPage'),PageBreak(),Paragraph('CutBy: Duration'),CutByDict['Duration'],
            FrameBreak(),Paragraph('CutBy: adv_pct'),CutByDict['adv_pct'], NextPageTemplate('CutByPage'),PageBreak(),
            Paragraph('CutBy: Trade_Rate'),CutByDict['TradeRate']]

#CutByDict['Duration'].drawHeight = 3.25 * inch
#CutByDict['Duration'].drawWidth = 2 * inch


#elements = [tbl,NextPageTemplate('CutByPage'),PageBreak(),Paragraph('This is some content for the PDF document Page 2.'),
#            FrameBreak(),Paragraph('This is EXTRA content for the PDF document Page 2.')]

MyDoc=MyDocTemplate('TestFile.pdf',pagesize=landscape(letter))

MyDoc.build(elements)

# # Convert the dataframe to a list of lists
# data = [list(df.columns)]
# for row in df.values:
#     data.append(list(row))
#
# # Create a PDF document
# #pdf = SimpleDocTemplate('table.pdf', pagesize=landscape(letter))
# canv = Canvas('ReportLabPractice/doc.pdf', pagesize=landscape(letter))
# width, height = canv._pagesize
#
# # Create a table from the data
# table = Table(data,splitByRow=False)
#
# table.setStyle(TableStyle([
#     ("VALIGN", (0,0), (0,0), "TOP"),
#     ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
#     ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
#     ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
#     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#     ('FONTSIZE', (0, 0), (-1, 0), 10),
#     ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
#     ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
#     ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
#     ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
#     ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
#     ('FONTSIZE', (0, 1), (-1, -1), 8),
#     ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
#     ('GRID', (0, 0), (-1, -1), 1, colors.black)
# ]))
#
# # Position the table at (x, y) = (1 inch, 1 inch)
# table.wrapOn(canv, width, height)
# table.drawOn(canv, 0.5 * inch, 4 * inch)
#
#
# # Define the header style
# header_style = ParagraphStyle(name='Header', fontSize=14, leading=16)
#
# # Define the header content
# header_content = 'This is the header'
# p = Paragraph(header_content,header_style)
# p.wrapOn(canv, width, height)
# p.drawOn(canv, 0.5 * inch, 8 * inch)
# canv.line(0.5*inch, 8*inch, 10.5*inch, 8*inch)
#
# # Add the table to the PDF document
# canv.save()
#pdf.build([table])


#print(mytable.tabulate(tablefmt = "fancy_grid"))
