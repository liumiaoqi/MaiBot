import akshare as ak
import pandas as pd
import os

out_dir = r'E:\Users\lmq\Documents\finance\data'
os.makedirs(out_dir, exist_ok=True)

# 标的清单:名称 -> (类型, 代码)
targets = [
    ('sh000300', 'index'),    # 沪深300 指数
    ('sz399006', 'index'),    # 创业板指
    ('600519', 'stock'),      # 贵州茅台
    ('600036', 'stock'),      # 招商银行
    ('600900', 'stock'),      # 长江电力(防御股,波动小)
]

for code, kind in targets:
    try:
        if kind == 'index':
            df = ak.stock_zh_index_daily(symbol=code)
        else:
            df = ak.stock_zh_a_hist(symbol=code, period='daily',
                                   start_date='20140101', end_date='20261231', adjust='qfq')
            # 归一列名与指数一致
            df = df.rename(columns={'日期':'date','开盘':'open','最高':'high',
                                   '最低':'low','收盘':'close','成交量':'volume'})
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'] >= '2015-01-01']
        out = df[['date','open','high','low','close','volume']].copy()
        fname = os.path.join(out_dir, code + '_daily.csv')
        out.to_csv(fname, index=False)
        print(f'{code}: {len(out)} 行 {out["date"].iloc[0].date()} → {out["date"].iloc[-1].date()} 收盘{out["close"].iloc[-1]:.2f}')
    except Exception as e:
        print(f'{code}: 失败 {e}')