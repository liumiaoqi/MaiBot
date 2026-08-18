import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_dir = r'E:\Users\lmq\Documents\finance\data'
stocks = ['600519', '600900']
for code in stocks:
    ok = False
    for attempt in range(6):
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
            ok = True
            break
        except Exception as e:
            print(f'{code} attempt{attempt+1}: {str(e)[:60]}')
            time.sleep(5)
    if not ok:
        print(f'{code}: 全部失败')