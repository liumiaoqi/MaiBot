import pandas as pd
import os

DATA = r'E:\Users\lmq\Documents\finance\data'

# 行业映射
ind = pd.read_csv(os.path.join(DATA, '_industry_map.csv'))
print(f'行业映射: {len(ind)} 只')

# 遍历每只股票的 CSV,算上市至今涨幅 + 上市年份
rows = []
for _, r in ind.iterrows():
    code = str(r['code']).zfill(6)
    industry = r['industry']
    fpath = os.path.join(DATA, code + '_daily.csv')
    if not os.path.exists(fpath):
        continue
    try:
        df = pd.read_csv(fpath)
        if len(df) < 50:  # 过滤上市太短的
            continue
        first_close = df['close'].iloc[0]
        last_close = df['close'].iloc[-1]
        if first_close <= 0:
            continue
        total_ret = last_close / first_close - 1
        year = str(df['date'].iloc[0])[:4]
        rows.append({'code': code, 'industry': industry, 'ret': total_ret, 'year': year, 'name': str(r.get('name', ''))})
    except Exception:
        continue

res = pd.DataFrame(rows)
print(f'有效样本: {len(res)} 只')

# 按行业统计
stats = res.groupby('industry').agg(
    平均涨幅=('ret', 'mean'),
    中位涨幅=('ret', 'median'),
    股票数=('ret', 'count'),
    最早上市=('year', 'min'),
).sort_values('平均涨幅', ascending=False)

print('\n=== 行业 30 年兴衰排行(平均涨幅) ===')
pd.set_option('display.float_format', lambda x: f'{x*100:.0f}%')
print(stats.head(25))
print('\n=== 最差行业 ===')
print(stats.tail(10))

# 保存结果
stats.to_csv(os.path.join(DATA, '_industry_rank.csv'))
res.to_csv(os.path.join(DATA, '_stock_industry_ret.csv'), index=False)
print('\n已保存 _industry_rank.csv + _stock_industry_ret.csv')