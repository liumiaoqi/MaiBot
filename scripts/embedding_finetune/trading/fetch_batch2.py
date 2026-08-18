import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'

stocks = [
    ('sh600036', '招商银行'), ('sh600887', '伊利股份'), ('sh601398', '工商银行'),
    ('sh600050', '中国联通'), ('sh601668', '中国建筑'), ('sh600276', '恒瑞医药'),
    ('sz002415', '海康威视'), ('sh600031', '三一重工'), ('sh601899', '紫金矿业'),
    ('sz000858', '五粮液'),
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
            print(f'{name} attempt{attempt+1}: {str(e)[:50]}')
            time.sleep(3)