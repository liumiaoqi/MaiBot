import pandas as pd
import os

DATA = r'E:\Users\lmq\Documents\finance\data'

ind = pd.read_csv(os.path.join(DATA, '_industry_map.csv'))
ind['code'] = ind['code'].astype(str).str.zfill(6)
print('行业映射:', len(ind), '只')

eras = [('1995-2005', '1995-01-01', '2005-12-31'),
        ('2005-2015', '2006-01-01', '2015-12-31'),
        ('2015-2026', '2016-01-01', '2026-12-31')]

stock_data = {}
for _, r in ind.iterrows():
    code = r['code']
    fpath = os.path.join(DATA, code + '_daily.csv')
    if not os.path.exists(fpath):
        continue
    try:
        df = pd.read_csv(fpath)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        stock_data[code] = df['close']
    except Exception:
        continue
print('有效股票:', len(stock_data), '只')

results = {}
for era_name, start, end in eras:
    era_rows = []
    for code, close in stock_data.items():
        seg = close[(close.index >= start) & (close.index <= end)]
        if len(seg) < 100:
            continue
        ret = seg.iloc[-1] / seg.iloc[0] - 1
        match = ind[ind['code'] == code]['industry'].values
        if len(match) == 0:
            continue
        era_rows.append({'code': code, 'industry': match[0], 'ret': ret})
    era_df = pd.DataFrame(era_rows)
    ind_stats = era_df.groupby('industry')['ret'].agg(['median', 'count']).sort_values('median', ascending=False)
    ind_stats = ind_stats[ind_stats['count'] >= 3]
    n = len(ind_stats)
    ind_stats['tier'] = '差'
    if n >= 3:
        ind_stats.iloc[:max(1, n//3), -1] = '好'
        ind_stats.iloc[max(1, n//3):max(1, 2*n//3), -1] = '中'
    results[era_name] = ind_stats
    print('\n===', era_name, '行业分档(', n, '个行业) ===')
    print(ind_stats[['median', 'count', 'tier']].to_string())

with pd.ExcelWriter(os.path.join(DATA, '..', 'era_industry_tiers.xlsx')) as writer:
    for era_name, stats in results.items():
        stats.to_excel(writer, sheet_name=era_name)
print('\n已保存 era_industry_tiers.xlsx')