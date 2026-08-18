import akshare as ak
import pandas as pd

# 上证指数日线(免费,前复权)
df = ak.stock_zh_index_daily(symbol='sh000001')
print('列:', list(df.columns))
print('行数:', len(df))
print('时间范围:', df['date'].iloc[0], '→', df['date'].iloc[-1])
print(df.tail(3))

# 取最近 10 年
df['date'] = pd.to_datetime(df['date'])
df10 = df[df['date'] >= '2015-01-01'].copy()
print('近10年行数:', len(df10))

# 存 CSV(纯基础列,MATLAB 好读)
out = df10[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
out.to_csv(r'E:\Users\lmq\Documents\finance\sh000001_daily.csv', index=False)
print('已保存: E:\\Users\\lmq\\Documents\\finance\\sh000001_daily.csv')
print(out.head(3))