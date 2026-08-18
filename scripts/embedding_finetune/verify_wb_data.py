import pandas as pd

DATA = r'E:\Users\lmq\Documents\finance\data'
df = pd.read_csv(DATA + '/sh000001_daily.csv')
df['date'] = pd.to_datetime(df['date'])

# 验证关键点位:2007 顶 6124 / 2015 顶 5178 / 2024-10 顶 / 最新
checks = [
    ('2007-10-16 6124点', '2007-10-01', '2007-11-01'),
    ('2015-06 5178点', '2015-06-01', '2015-07-01'),
    ('2024-10-08 3674点', '2024-10-01', '2024-10-15'),
    ('2025-11 十年新高', '2025-11-01', '2025-12-01'),
    ('2026-05 4258点', '2026-05-01', '2026-06-01'),
    ('最新 2026-08-17', '2026-08-10', '2026-08-17'),
]
for label, s, e in checks:
    sub = df[(df['date'] >= s) & (df['date'] <= e)]
    if len(sub):
        peak = sub.loc[sub['close'].idxmax()]
        print(f'{label}: 区间高点 {peak["close"]:.0f} @ {peak["date"].date()}')
    else:
        print(f'{label}: 无数据')

# 全历史高点
peak_all = df.loc[df['close'].idxmax()]
print(f'\n30年最高: {peak_all["close"]:.0f} @ {peak_all["date"].date()}')