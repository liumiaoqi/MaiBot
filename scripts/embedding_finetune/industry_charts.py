import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

DATA = r'E:\Users\lmq\Documents\finance\data'
stats = pd.read_csv(os.path.join(DATA, '_industry_rank.csv'), index_col=0)

# 图1:行业兴衰排行(平均涨幅,去掉次新股)
top = stats.drop(index='次新股', errors='ignore').sort_values('平均涨幅', ascending=True).tail(20)

fig, ax = plt.subplots(figsize=(12, 9))
colors = ['#c0392b' if v > 5 else ('#e67e22' if v > 2 else '#7f8c8d') for v in top['平均涨幅']]
ax.barh(top.index, top['平均涨幅']*100, color=colors)
ax.set_xlabel('平均涨幅 (%)')
ax.set_title('中国行业 30 年兴衰(1995-2026,平均涨幅)——红>500%, 橙>200%, 灰<200%', fontsize=13)
ax.axvline(0, color='black', linewidth=0.8)
for i, v in enumerate(top['平均涨幅']*100):
    ax.text(v + 15, i, f'{v:.0f}%', va='center', fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(DATA, '..', 'industry_30yr.png'), dpi=150)
print('已保存 industry_30yr.png')

# 图2:年代对比——各年代上市的股票,平均涨幅(看时代起点差异)
res = pd.read_csv(os.path.join(DATA, '_stock_industry_ret.csv'))
res['era'] = pd.cut(res['year'].astype(int), bins=[0,2000,2005,2010,2015,2020,2027],
                    labels=['1995-99','2000-04','2005-09','2010-14','2015-19','2020+'])
era_stats = res.groupby('era', observed=True)['ret'].agg(['mean','median','count'])
print(era_stats)

fig2, ax2 = plt.subplots(figsize=(10, 5))
era_stats['mean'].plot(kind='bar', ax=ax2, color='#2980b9')
ax2.set_title('不同年代上市的股票,上市至今平均涨幅——时代起点决定命运', fontsize=13)
ax2.set_ylabel('平均涨幅 (%)')
ax2.axhline(0, color='black', linewidth=0.8)
for i, v in enumerate(era_stats['mean']*100):
    ax2.text(i, v*100 + 50, f'{v*100:.0f}%', ha='center', fontsize=9)
plt.tight_layout()
plt.savefig(os.path.join(DATA, '..', 'era_start_comparison.png'), dpi=150)
print('已保存 era_start_comparison.png')