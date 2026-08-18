import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_dir = r'E:\Users\lmq\Documents\finance\data'
stocks = ['sh600519', 'sh600900']
for code in stocks:
    try:
        # 新浪日线(不复权——后复权自己算:连乘当日涨跌幅)
        df = ak.stock_zh_a_daily(symbol=code, start_date='20140101', end_date='20261231', adjust='hfq')
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'] >= '2015-01-01']
        df = df.rename(columns={'volume':'volume'})
        out = df[['date','open','high','low','close','volume']].copy()
        fname = os.path.join(out_dir, code[2:] + '_daily.csv')
        out.to_csv(fname, index=False)
        print(f'{code}: OK {len(out)} 行 首日{out["close"].iloc[0]:.2f} 末日{out["close"].iloc[-1]:.2f}')
    except Exception as e:
        print(f'{code}: {type(e).__name__} {str(e)[:100]}')