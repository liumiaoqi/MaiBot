import akshare as ak
import pandas as pd
import os, time

# 关掉 requests 代理(akshare 内部可能读环境代理)
for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_dir = r'E:\Users\lmq\Documents\finance\data'
stocks = ['600519', '600036', '600900']
for code in stocks:
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period='daily',
                                   start_date='20140101', end_date='20261231', adjust='hfq')
            df = df.rename(columns={'日期':'date','开盘':'open','最高':'high',
                                   '最低':'low','收盘':'close','成交量':'volume'})
            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] >= '2015-01-01']
            out = df[['date','open','high','low','close','volume']].copy()
            fname = os.path.join(out_dir, code + '_daily.csv')
            out.to_csv(fname, index=False)
            print(f'{code}: OK {len(out)} 行 首日{out["close"].iloc[0]:.2f} 末日{out["close"].iloc[-1]:.2f}')
            break
        except Exception as e:
            print(f'{code} attempt{attempt+1}: {type(e).__name__} {str(e)[:80]}')
            time.sleep(3)