import pandas as pd
import numpy as np

DATA = r'E:\Users\lmq\Documents\finance\data'
df = pd.read_csv(DATA + '/601919_daily.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date')

# 看年度表现(识别周期)
df['year'] = df.index.year
yearly = df.groupby('year')['close'].agg(['first', 'last'])
yearly['ret'] = yearly['last'] / yearly['first'] - 1
print('中远海控 年度涨幅(看周期起伏):')
for y, row in yearly.iterrows():
    bar = '#' * max(0, int(row['ret'] * 20)) if row['ret'] > 0 else '.' * max(0, int(-row['ret'] * 20))
    print(f'{y}: {row["ret"]*100:+6.0f}%  {bar}')