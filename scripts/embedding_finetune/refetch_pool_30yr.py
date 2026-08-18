import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'

# 选定股票池(固定不可换):新浪代码 -> 名称
stocks = [
    ('sh600519', '贵州茅台'),
    ('sh600900', '长江电力'),
    ('sh601919', '中远海控'),
    ('sh600340', '华夏幸福'),
    ('sz000001', '平安银行'),
    ('sh601857', '中国石油'),
    ('sh600028', '中国石化'),
    ('sh000300', '沪深300指数'),
]

for sym, name in stocks:
    code = sym[2:]
    fpath = os.path.join(DATA, code + '_daily.csv')
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=sym, start_date='19950101', end_date='20261231', adjust='hfq')
            df['date'] = pd.to_datetime(df['date'])
            out = df[['date','open','high','low','close','volume']].copy()
            out.to_csv(fpath, index=False)
            print(f'{name}({code}): {len(out)} 行, 起点 {str(out["date"].iloc[0])[:10]}')
            break
        except Exception as e:
            print(f'{name} attempt{attempt+1}: {str(e)[:60]}')
            time.sleep(3)