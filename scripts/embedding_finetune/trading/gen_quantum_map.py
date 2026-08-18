#!/usr/bin/env python3
"""量子实验全景收官图:exp15-34 二十连——概念到落地的完整地图"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(20, 12))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12)
ax.axis('off')

# 标题
ax.text(10, 11.6, '量子模拟 x MaiBot/AI 实验全景——exp15-34 二十连收官', ha='center', fontsize=20, fontweight='bold')
ax.text(10, 11.1, '2026-08-18 | 源头:量子线 x AI实验线交叉 | 三个域:AI交易 / MaiBot记忆(ZH铸魂) / 系统可靠性(ZG铸骨)', ha='center', fontsize=12, color='#555555')

def card(x, y, w, h, title, body, color='#ecf0f1', edge='#2c3e50', tsize=11, bsize=8.5):
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.12', facecolor=color, edgecolor=edge, linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h - 0.32, title, ha='center', va='center', fontsize=tsize, fontweight='bold')
    ax.text(x + 0.18, y + 0.18, body, ha='left', va='bottom', fontsize=bsize, color='#2c3e50')

# ===== 分区标题 =====
ax.text(3.3, 10.55, 'AI 交易线(股票)', ha='center', fontsize=14, fontweight='bold', color='#c0392b')
ax.text(10.0, 10.55, 'MaiBot 记忆与思考(ZH 铸魂)', ha='center', fontsize=14, fontweight='bold', color='#2980b9')
ax.text(16.7, 10.55, '系统可靠性(ZG 铸骨)', ha='center', fontsize=14, fontweight='bold', color='#27ae60')

# ===== 左列:AI 交易 =====
card(0.2, 8.6, 6.2, 1.7, 'exp19-21 量子信道噪声 vs 高斯', '16只样本:bitflip 噪声收益 +9.4 vs gauss +2.6(3.6倍)\nR-STDP脉冲网络匹配离散扰动(翻转>微扰)', '#fdebd0', '#c0392b')
card(0.2, 6.7, 6.2, 1.7, 'exp26 真·Qiskit 量子信道', '特征过真实量子电路(RY+信道+测量)\nbitflip +25.2(5/6跑赢) 五粮液37.9→56.9 翻盘', '#fdebd0', '#c0392b')
card(0.2, 4.8, 6.2, 1.7, 'exp22-25 方法论沉淀', '完整方法组合=110.9全样本最优\n种子相关性:连续小种子std低估30-40%\n大随机种子列表=实验规范', '#fdebd0', '#c0392b')
card(0.2, 2.9, 6.2, 1.7, 'exp34 QSNN 复振幅相位学习', '权重=旋转角(防饱和) 发放=sin^2(相位)\n平均132.9vs131.5 神华+106 五粮液满仓3倍', '#fdebd0', '#c0392b')
card(0.2, 1.0, 6.2, 1.7, 'exp27-28 检索多样性(桥)', '候选分数概率扰动:ampdamp 25.0 / qbit 7.99\n角色不成为复读机——MaiBot应用起点', '#fadbd8', '#c0392b')

# ===== 中列:MaiBot 记忆(ZH) =====
card(6.9, 8.6, 6.2, 1.7, 'exp29 量子两能级遗忘曲线', 'S短期快衰减+L长期慢衰减=Ebbinghaus形状\nMAE 0.177(现状2.4倍优) 间隔复习111%\n重要记忆靠初始巩固(学习深度)', '#d6eaf8', '#2980b9')
card(6.9, 6.7, 6.2, 1.7, 'exp30 纠缠熵去重(诚实否定)', '互信息准确率98%但仅+1%(vs Jaccard 97%)\n词袋级≈文本相似度——不替换现状', '#d6eaf8', '#2980b9')
card(6.9, 4.8, 6.2, 1.7, 'exp31 Grover 目标放大', '目标选择P~score^2(概率平方放大)\nk=2最优:4.4完成 vs 贪心3.8(+16%)\n次目标也推进(偶尔想起别的事)', '#d6eaf8', '#2980b9')
card(6.9, 2.9, 6.2, 1.7, 'exp32 量子退火欲望演化', '隧穿跳出局部最优:被冷落感知目标\n约束(合理切换频率)下 -8%饥饿\n揭示"切换频率"是欲望系统维度', '#d6eaf8', '#2980b9')
card(6.9, 1.0, 6.2, 1.7, '落地接口(编入ZH计划(17)-(23))', '检索扰动开关+偏好下沉agent配置\n遗忘引擎两能级化 / 目标选择概率放大\nvitality三件套:贪心+频率限制+隧穿', '#d6eaf8', '#2980b9')

# ===== 右列:系统可靠性(ZG) =====
card(13.6, 8.6, 6.2, 1.7, 'exp33 bitflip 混沌测试', 'sqlite位翻转注入:16bit是分水岭\n页头翻转>数据区(位置是胜负手)\n单bit 2.5%打不开=数据丢失风险', '#d5f5e3', '#27ae60')
card(13.6, 6.7, 6.2, 1.7, '落地:故障注入测试工具', '混沌测试用4-16bit敏感区间\n建议:文件头校验+定期自动备份\n消除2.5%单bit丢失风险', '#d5f5e3', '#27ae60')

# ===== 底部:核心认知 =====
box = FancyBboxPatch((1.0, 0.15), 18.0, 0.6, boxstyle='round,pad=0.1', facecolor='#fef9e7', edgecolor='#f39c12', linewidth=1.5)
ax.add_patch(box)
ax.text(10, 0.45, '核心认知:量子概念不是万能药——有的真金(遗忘/QSNN/噪声信道)有的镀金(纠缠熵) | 数据说话,诚实否定也是产出 | 受控的不确定=人味(⑥EFE同构) | 指标要带约束看 | 大随机种子=实验规范', ha='center', va='center', fontsize=11, color='#7d6608')

plt.tight_layout()
out = 'E:/Users/lmq/Documents/finance/quantum_experiment_map.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print('saved:', out)