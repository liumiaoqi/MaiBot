#!/usr/bin/env python3
"""收官图:AI交易 × 量子计算 噪声研究线(exp15-26)最终成果

左图:6 只代表股 × 5 配置(真·Qiskit 量子信道 vs det vs 满仓)
右图:每股票每信道的噪声收益(vs det)
数据来源:exp26 实测(6 只 × 5 seeds 大随机种子平均)
输出:E:/Users/lmq/Documents/finance/noise_final_qiskit.png
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# exp26 实测数据(6 只代表股 × 5 配置,5 seeds 大随机种子平均)
stocks = ['中国神华', '中远海控', '紫金矿业', '五粮液', '恒瑞医药', '招商银行']
det = [126.4, 201.3, 232.1, 37.9, 81.6, 109.7]
depolar = [183.5, 208.6, 199.2, 42.0, 69.2, 113.1]
ampdamp = [182.5, 262.3, 241.7, 50.2, 68.8, 105.1]
bitflip = [182.0, 242.6, 268.6, 56.9, 78.5, 111.8]
full = [377.0, 287.7, 372.5, 29.4, 57.8, 116.8]

fig, axes = plt.subplots(1, 2, figsize=(17, 7.5))
fig.suptitle('AI 交易 × 量子计算——噪声研究收官(exp15-26,真·Qiskit 量子信道)',
             fontsize=16, fontweight='bold')

# 左图:分组柱状图
ax = axes[0]
x = np.arange(len(stocks))
w = 0.15
colors = ['#bdc3c7', '#e74c3c', '#3498db', '#2ecc71', '#f39c12']
labels = ['确定性(det)', '退极化0.1', '振幅阻尼0.02', '比特翻转0.02', '满仓']
for i, (data, lab, col) in enumerate(zip([det, depolar, ampdamp, bitflip, full],
                                         labels, colors)):
    offset = (i - 2) * w
    bars = ax.bar(x + offset, data, w, label=lab, color=col, edgecolor='white')
    for b, v in zip(bars, data):
        ax.text(b.get_x() + b.get_width() / 2, v + 4, '%.0f' % v,
                ha='center', fontsize=8)
ax.set_xticks(x)
ax.set_xticklabels(stocks, fontsize=11)
ax.set_ylabel('测试段终值(初始100,2021-2026)')
ax.set_title('6 只代表股:量子信道噪声 vs 确定性 vs 满仓', fontsize=13)
ax.legend(fontsize=10, loc='upper left')
ax.grid(axis='y', alpha=0.3)
ax.set_ylim(0, 420)

# 右图:噪声收益(相对 det)
ax2 = axes[1]
gains = {
    '退极化0.1': [d - b for d, b in zip(depolar, det)],
    '振幅阻尼0.02': [d - b for d, b in zip(ampdamp, det)],
    '比特翻转0.02': [d - b for d, b in zip(bitflip, det)],
}
x2 = np.arange(len(stocks))
for i, (name, gs) in enumerate(gains.items()):
    ax2.bar(x2 + (i - 1) * 0.25, gs, 0.25, label=name,
            color=['#e74c3c', '#3498db', '#2ecc71'][i], edgecolor='white')
    for xi, v in zip(x2 + (i - 1) * 0.25, gs):
        ax2.text(xi, v + (2 if v >= 0 else -6), '%+.0f' % v,
                 ha='center', fontsize=8)
ax2.axhline(0, color='black', lw=1)
ax2.set_xticks(x2)
ax2.set_xticklabels(stocks, fontsize=11)
ax2.set_ylabel('噪声收益(vs 确定性,终值差)')
ax2.set_title('量子信道噪声收益——正=受益,负=受害', fontsize=13)
ax2.legend(fontsize=10)
ax2.grid(axis='y', alpha=0.3)

# 底部结论文字
conclusion = ('结论:比特翻转0.02平均收益+25.2(5/6跑赢)——真Qiskit量子信道>数学模拟>高斯(exp19-26)。'
              '五粮液37.9→56.9(满仓1.9倍) 中远海控201→262逼近满仓 神华三信道一致+56 紫金从受害转受益。'
              '随机性定论:10个大随机种子平均才可靠;大随机种子列表=实验规范(exp23-25)')
fig.text(0.5, 0.015, conclusion, ha='center', fontsize=11, color='#2c3e50',
         bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.9))

plt.tight_layout(rect=[0, 0.06, 1, 0.95])
out = 'E:/Users/lmq/Documents/finance/noise_final_qiskit.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print('saved:', out)
