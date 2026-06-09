import sys

sys.path.append('C:/Users/dstee/PycharmProjects/awesome_repo/tableone')
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

tbl = Table([[MainTable,ReportLabHist]])

elements = [tbl,NextPageTemplate('CutByPage'),PageBreak(),Paragraph('CutBy: Duration'),CutByDict['Duration'],
            FrameBreak(),Paragraph('CutBy: adv_pct'),CutByDict['adv_pct'], NextPageTemplate('CutByPage'),PageBreak(),
            Paragraph('CutBy: Trade_Rate'),CutByDict['TradeRate']]

createMultiPage(elements,report_name='ClientName: XYZ',sd=data.trade_date.min(),ed=data.trade_date.max())

#MyDoc=MyDocTemplate('TestFile.pdf',pagesize=landscape(letter))

#MyDoc.build(elements)