import sys

sys.path.append('C:/Users/dstee/PycharmProjects/awesome_repo/tableone')
from tableone import TableOne, load_dataset
import pandas as pd

#data=load_dataset('toydata_v2.xlsx')

data = pd.read_excel('toydata_v2.xlsx')
data['adv_pct']*=100
data['avg_spread']*=100

#For Hypothesis testing
#data = data[(data['trader_id']=='A') | (data['trader_id']=='B')]


columns = ['ordre_len_seconds','adv_pct', 'liq_consumption', 'impact_cost_bps','market_cap','volatility_30d','avg_spread','arrival_mid_px_slp_bps']
groupby = ['trader_id']
weight = ['exec_val_usd']
sum_cols = ['order_qty','exec_qty','exec_val_usd']

#mytable = TableOne(data, columns=columns, groupby=groupby, pval=False, weights=weight, sum_cols=sum_cols, smd=True)
mytable = TableOne(data, columns=columns, pval=False, weights=weight, sum_cols=sum_cols)



print(mytable.tabulate(tablefmt = "fancy_grid"))
