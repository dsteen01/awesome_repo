import sys
import numpy as np
import pandas as pd
from scipy.stats.mstats import winsorize
from tableone import TableOne, load_dataset
sys.path.append('C:/Users/dstee/PycharmProjects/awesome_repo/tableone')
from reportlabutils import *
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def CreateOutlierFrame(df,mode='win',SizeThresh=.025,CostThresh=0.01,SizeCol='exec_val_usd',CostCol='ArrSlipBps'):
    df_win = df.copy()

    if mode=='win':
        df_win[CostCol]= winsorize(df[CostCol], limits=[CostThresh, CostThresh])
        df_win[SizeCol]= winsorize(df[SizeCol], limits=[None, SizeThresh])
    elif mode == 'cut':
        CostLimitLower = df[CostCol].quantile(CostThresh)
        CostLimitUpper = df[CostCol].quantile(1-CostThresh)
        SizeLimitUpper = df[SizeCol].quantile(1-SizeThresh)
        df_win = df[(df[CostCol]>CostLimitLower) & (df[CostCol]<CostLimitUpper) & (df[SizeCol]<SizeLimitUpper)]
    else:
        print("Select 'win' or 'cut' mode")

    return df_win

def CreateCoverPageTable(data, weighting, features=[],grouping=None,sumcols=[]):

    datawin = CreateOutlierFrame(data,mode='win')

    # mytable = TableOne(data, columns=columns, groupby=groupby, pval=False, weights=weight, sum_cols=sum_cols, smd=True)
    RawTable = TableOne(data, columns=features, pval=False, weights=weighting, sum_cols=sumcols, groupby=grouping)
    WinTable = TableOne(datawin, columns=features, pval=False, weights=weighting, sum_cols=sumcols, groupby=grouping)

    df_raw = RawTable.tableone
    df_win = WinTable.tableone
    if grouping:
        df_raw.columns = df_raw.columns.droplevel(0)
        df_win.columns = df_win.columns.droplevel(0)

    df_raw = df_raw.reset_index()
    df_raw = df_raw.drop('level_1', axis=1)
    df_raw = df_raw.rename(columns={'level_0': 'Metric'})

    df_win = df_win.reset_index()
    df_win = df_win.drop('level_1', axis=1)
    df_win = df_win.rename(columns={'level_0': 'Metric'})

    if grouping is None:
        df_raw = df_raw.merge(df_win['Overall'], left_index=True, right_index=True)
        df_raw.rename(columns={'Overall_x': 'Raw', 'Overall_y': 'Winsorized'}, inplace=True)

    tbl = df2table(df_raw.drop('Missing',axis=1))

    tbl.hAlign = 'LEFT'
    tbl.setStyle([('INNERGRID', (0, 0), (-1, -1), 0.25, colors.white),
                  ('BOX', (0, 0), (-1, -1), 0.25, colors.white),
                  ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                  ])

    return tbl,df_raw

def CreateFeatureHistograms(df,features=[]):
    g = sns.FacetGrid(df[features].melt(), col='variable', col_wrap=3, sharex=False, sharey=False, height=1.0, aspect=2.0)
    g.map(sns.histplot, 'value')

    # Set the title and axis labels for each subplot
#    for ax in g.axes.flat:
#        ax.set(xlabel='Value', ylabel='Frequency')

    g.set_titles('{col_name}')

    # Adjust the spacing between subplots
    g.fig.tight_layout()

    g.fig.savefig('facetgrid.png')

    return fig2image(g), g

def CreateCutBy(df,sub_df_init,KPI,TimeBin='Daily',nbins=5,cut_by_cols=[],weighting=[],sum_cols=[],grouping=[]):

    if TimeBin=='Daily':
        tmp_grouping='trade_date'
    elif TimeBin == 'Weekly':
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
        df['WeekEnding'] = df['trade_date']+ pd.to_timedelta((4 - df['trade_date'].dt.weekday).astype(int), unit='d')
        tmp_grouping='WeekEnding'

    AllCutBys = dict()

    for feature in cut_by_cols:
        sub_df = df[sub_df_init + [feature]]
        sub_df['Bin'] = pd.qcut(sub_df[feature],q=nbins,labels=False)

        #Cutby Evolution over time

        TemporalTable = TableOne(sub_df, columns=[feature], pval=False, weights=weighting, sum_cols=weighting, groupby=tmp_grouping)
        FeatureTS = TemporalTable.cont_describe.loc[:, (['wt_mean', 'wt_err'], slice(None))]
        FeatureTS = FeatureTS.T.sort_index(level=1, ascending=False)
        TempMeans = FeatureTS.loc['wt_mean']
        TempSigmas = FeatureTS.loc['wt_err']
        TempMeans = TempMeans.reset_index().melt(id_vars=[TempMeans.index.name])
        TempSigmas = TempSigmas.reset_index().melt(id_vars=[TempSigmas.index.name])
        TempMeans.rename(columns={'value': 'mean'}, inplace=True)
        TempSigmas.rename(columns={'value': 'SEM'}, inplace=True)
        TempMelted = pd.merge(TempMeans, TempSigmas, on=['trade_date', 'variable'])

        #KPI Sensitivity to each cutby
        NotionalTable = TableOne(sub_df, columns=[feature,KPI], pval=False, weights=weighting, sum_cols=weighting, groupby='Bin')
        FeatureCutBy = NotionalTable.cont_describe.loc[:, (['wt_mean', 'wt_err'], slice(None))]
        FeatureCutBy = FeatureCutBy.T.sort_index(level=1, ascending=False)
        NotionalMeans = FeatureCutBy.loc['wt_mean']
        NotionalSigmas = FeatureCutBy.loc['wt_err']
        NotionalSigmas.columns = [col + 'SEM' for col in NotionalSigmas.columns]
        NotionalFinal = pd.concat([NotionalMeans, NotionalSigmas], axis=1)

        #Cutby Histogram
        #sns.histplot(data=df, x="sepal_length")

        #Create 1x3 subplot for each feature
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(9.9,3))
        ax1.errorbar('trade_date','mean',yerr='SEM',data=TempMelted,fmt='o', capsize=5)
        ax1.set_title("{} vs. Time".format(feature))
        ax1.set_xlabel('Date')
        ax1.set_ylabel('{}'.format(feature))
        ax2.errorbar(feature,KPI, yerr= KPI + 'SEM', data=NotionalFinal,fmt='o', capsize=5)
        ax2.set_title("{} vs. {}".format(feature,KPI))
        ax2.set_xlabel('{}'.format(feature))
        ax2.set_ylabel('{}'.format(KPI))
        sns.histplot(data=sub_df, x=feature, ax=ax3)
        ax3.set_title("{} Histogram".format(feature))
        plt.tight_layout(pad=2.0)

        #Add to Dict
        AllCutBys[feature]=fig2image(fig)

    return AllCutBys



def CreateFeatureTS(df,dim='Daily',features=[],weighting=[],sum_cols=[],grouping=[]):
    #https: // stackoverflow.com / questions / 45875143 / making - seaborn - barplot - by - group -with-asymmetrical - custom - error - bars
    #https://stackoverflow.com/questions/24878095/plotting-errors-bars-from-dataframe-using-seaborn-facetgrid

    if dim=='Daily':
        grouping='trade_date'
    elif dim == 'Weekly':
        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
        df['WeekEnding'] = df['trade_date']+ pd.to_timedelta((4 - df['trade_date'].dt.weekday).astype(int), unit='d')
        grouping='WeekEnding'

    DateTable = TableOne(df, columns=features, pval=False, weights=weighting, sum_cols=sum_cols,groupby=grouping)
    FeatureTS = DateTable.cont_describe.loc[:, (['wt_mean', 'wt_err'], slice(None))]
    FeatureTS = FeatureTS.T.sort_index(level=1, ascending=False)

    means = FeatureTS.loc['wt_mean']
    sigma = FeatureTS.loc['wt_err']

    means = means.reset_index().melt(id_vars=[means.index.name])
    sigma = sigma.reset_index().melt(id_vars=[sigma.index.name])

    means.rename(columns={'value':'mean'},inplace=True)
    sigma.rename(columns={'value':'SEM'},inplace=True)

    MeltedDF = pd.merge(means,sigma,on=['trade_date','variable'])


    g = sns.FacetGrid(MeltedDF, col='variable', sharex=False, sharey=False)
    g.map(plt.errorbar,'trade_date','mean','SEM', marker="o")
    #g.map(sns.scatterplot, 'trade_date','mean')

    # Adjust the spacing between subplots
    g.fig.tight_layout()
    g.set_xticklabels(rotation=45)

    g.fig.savefig('facetgrid.png')

    g.axes[0].savefig('facetgrid_tmp.png')


