#!/usr/bin/env python3
"""量子前沿调研收官图:WB 8 方向调研 + exp35-37 实验验证"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(20, 12.5))
ax.set_xlim(0, 20)
ax.set_ylim(0, 12.5)
ax.axis('off')

ax.text(10, 12.15, '量子前沿调研 → 实验验证收官(WB 8 方向 + exp35-37)', ha='center', fontsize=20, fontweight='bold')
ax.text(10, 11.7, '2026-08-18 | 调研:quantum_frontier_survey_0818.md | 验证:exp35 Hopfield / exp36 QRNG / exp37 张量网络', ha='center', fontsize=12, color='#555555')

def card(x, y, w, h, title, body, color='#ecf0f1', edge='#2c3e50', tsize=11, bsize=8.5):
    box = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.12', facecolor=color, edgecolor=edge, linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h - 0.3, title, ha='center', va='center', fontsize=tsize, fontweight='bold')
    ax.text(x + 0.18, y + 0.18, body, ha='left', va='bottom', fontsize=bsize, color='#2c3e50')

# ===== 左栏:WB 调研 8 方向 =====
ax.text(4.2, 11.15, 'WB 调研:8 方向评估(2023-2026 前沿)', ha='center', fontsize=13, fontweight='bold', color='#7d3c98')
card(0.3, 9.6, 7.8, 1.3, '5. 张量网络压缩 LLM(可落地:高)', 'CompactifAI 95% / KARIPAP 93% 内存减 2-3% 损失\n"量子启发"纯经典可实现——工程距离最近', '#e8daef', '#7d3c98')
card(0.3, 8.2, 7.8, 1.3, '3. 量子 Hopfield 联想记忆(中)', '2025 实验 7 倍容量已证实(非炒作)\nA_memorix 直接相关,与 exp29 同物理家族', '#e8daef', '#7d3c98')
card(0.3, 6.8, 7.8, 1.3, '8. QRNG 量子随机性(中)', '内禀随机性=定律保证(非炒作)\nexp23-24 种子相关性发现延伸', '#e8daef', '#7d3c98')
card(0.3, 5.4, 7.8, 1.3, '7. QAOA/退火(中) | 6. QRL(低-中)', 'exp32 已有能量景观基础 / exp31 已做在前列', '#e8daef', '#7d3c98')
card(0.3, 4.0, 7.8, 1.3, '1. QML / 2. QNLP / 4. 量子Transformer(低)', '经典更快更省 / 架构不匹配(⑯已证)\n诚实标注:概念炒作,无直接关联', '#fadbd8', '#c0392b')
card(0.3, 2.3, 7.8, 1.4, '诚实标注(报告第十节)', '已证实:张量网络/Hopfield容量/QRNG定律\n炒作:QML普遍宣称/量子Transformer商业化\n无关联:QNLP/量子核检索(明说)', '#fef9e7', '#f39c12')

# ===== 右栏:3 候选实验验证 =====
ax.text(14.2, 11.15, '3 候选实验验证(exp35-37 全部可复现)', ha='center', fontsize=13, fontweight='bold', color='#1a5276')
card(10.4, 9.6, 7.6, 1.5, 'exp35 量子 Hopfield 记忆(候选2)', 'salience 加权=势阱深浅(exp29 c0 概念)\n容量 ~10条→~20-30条(+50-100%)\n错误纠正:翻转30%恢复0.26(经典0.00)\n诚实否定:不替代相似度检索(现状已最优)', '#d6eaf8', '#2980b9')
card(10.4, 7.7, 7.6, 1.6, 'exp36 内禀随机性对抗(候选3)', '变量隔离三版迭代(设计难度教训)\n"对抗伤害"未复现:滑点与学习纠缠\n内禀 vs 伪随机非对抗统计等效(第3次确认)\n结论:QRNG 价值在安全域,不在交易域', '#d6eaf8', '#2980b9')
card(10.4, 5.4, 7.6, 2.0, 'exp37 张量网络压缩会话(候选1)★★★', '同压缩率下:老话题检索 截断0% vs 张量网络92-100%\n参数量仅 9.4%(r=6)几乎无损(100%/100%/92%)\n会话嵌入天然低秩(8话题=8主方向)——纠缠有界实证\n截断丢全局结构;张量网络保留结构丢细节\n记忆/检索场景:结构 > 细节', '#d6eaf8', '#2980b9')

# ===== 底部:最终建议 =====
card(1.0, 1.0, 18.0, 1.0, '最终建议(待用户/CA 拍板)', '① exp37 张量网络压缩=首选立项(SSD 派发,会话压缩升级,与 dsh compaction 对标) ② exp35 Hopfield=记忆扩容/纠错储备 ③ exp36 QRNG=安全域知识沉淀 ④ 明确不做:真量子硬件(不符合全 API 路线)', '#d5f5e3', '#27ae60', 12, 9.5)

plt.tight_layout()
out = 'E:/Users/lmq/Documents/finance/quantum_frontier_final.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print('saved:', out)