import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'

# 沪深300指数(新浪指数接口)
try:
    df = ak.stock_zh_index_daily(symbol='sh000300')
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] >= '1995-01-01']
    out = df[['date','open','high','low','close','volume']].copy()
    out.to_csv(os.path.join(DATA, '000300_daily.csv'), index=False)
    print(f'沪深300: {len(out)} 行, 起点 {str(out["date"].iloc[0])[:10]}')
except Exception as e:
    print(f'失败: {str(e)[:100]}')