#!/usr/bin/env python3
"""probe22_make_index.py -- 生成实验区总索引（math_probe/INDEX.md）。

覆盖：trading/ 的 exp*.py（自动抓编号/行数/首行摘要）+ math_probe 的探针清单（手写）。
重跑即可刷新（新加 exp 后跑一次）。
跑法: ../.venv/Scripts/python.exe probe22_make_index.py
"""
import glob
import os
import re

TRADING = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading'
MP = os.path.dirname(os.path.abspath(__file__))

PROBE_MAP = {
    'exp29': 'probe1', 'exp37': 'probe2/5', 'exp31': 'probe3', 'exp30': 'probe7',
    'exp41b': 'probe8/9', 'exp32': 'probe10', 'exp42': 'probe11/17/19',
    'exp34': 'probe15', 'exp36': 'probe14', 'exp44': 'probe20',
    'exp46': 'probe18', 'exp48': 'probe21', 'exp45': '补跑#1', 'exp47': '补跑#2',
    'exp49': '补跑#4', 'exp27': 'probe16', 'exp28': 'probe16',
}

BANDS = [
    (1, 14, 'A. 交易基础线', 'R-STDP 演进 / 特征 / 先验 / 参数寻优'),
    (15, 28, 'B. 噪声与量子信道线', '噪声注入 / 量子信道 / 种子 / 完整方法 / 检索扰动'),
    (29, 40, 'C. 记忆与量子结构线', '遗忘 / 去重 / Hopfield / 果蝇 VQC / 退火 / 故障注入 / QSNN'),
    (41, 50, 'D. 线虫与进化线', '真实连接组 / 进化家族 / 社会 / 生存'),
    (51, 99, 'E. 角色模拟线', '角色漂移 / GRN / Concordia / 协方差 —— ⚠️ 尚未被探针覆盖'),
]

PROBES = [
    ('probe1', 'exp29', '数学体检：策略无关性（31 天留存只依赖次数不依赖分布）'),
    ('probe2', 'exp37', '修正模型验证：间隔效应出现（补上 F12.6 量化对拍教训）'),
    ('probe3', 'exp31', '身份查明：「Grover 式放大」= softmax 温度采样'),
    ('probe4', 'salience', 'salience 加权 Hopfield SNR：低负载有害 / 高负载有益（交叉结构）'),
    ('probe5', 'exp37', '张量网络压缩：谱结构 + r 拐点（三方逐位对拍 max_diff=0）'),
    ('probe6', '秩扫描', '高秩对话下低秩压缩的三重退化'),
    ('probe7', 'exp30', '「纠缠熵」= 加权共现计数（三层鉴定 + 词袋边界）'),
    ('probe8', 'exp41b', '线虫自发吸引子：95% 的「收敛」不是不动点 + 子网全枚举'),
    ('probe9', 'exp41b', '±1 反对称引理与配对统计（含 probe8 结论自我修正）'),
    ('probe10', 'exp32', '量子退火欲望：假退火（常量 ΔE）/「冻结」不存在 / 空转是唯一的罪'),
    ('probe11', 'exp42', '线虫进化「撞墙者」：scal_back 钉死下界 / scal_fwd 贴上界（玩具判决 = 界外最优）'),
    ('probe12', '连接组', '场论第一枪：Ising 化 χ 峰 β_c≈0.5 + exp31 热力学（转变带 β≈2）'),
    ('probe13', '连接组', '复分析线：谱半径审计（0.85 = 2.4× 超临界）+ Lee-Yang 零点（嵌套设计）'),
    ('probe14', 'exp36', '对抗随机性审计：对手是 stub / 滑点反向 / 随机性只影响 0.15% 行为'),
    ('probe15', 'exp34', 'QSNN：量子测量被 softmax 换芯 / 50.6% 语义空白 / 梯度死区'),
    ('probe16', 'exp27/28', '检索多样性：公平对照下「量子信道更划算」反转 + gap 标度判据（σ 甜点带 2-4×）'),
    ('probe17', 'exp42-49', '进化家族体检：谱系三代 / 完成度 2/9（后修正为「无存档设计」）/ society 选择失效'),
    ('probe18', 'exp46', '资产失控追查：跨世界估值跳变（P(>40)=15%）× 截断棘轮'),
    ('probe19', 'exp42', '挪墙实验：方向信号在、n=1 证据不足（噪声 300% vs 效应 30%）'),
    ('probe20', 'exp44', 'society 负值化：修好「选择失效」、未修好「选择信号」'),
    ('probe21', 'exp48', '极限环定案：振荡是「繁殖过滤器」的投影（交易层平稳 41-66%）'),
]


def expkey(fn):
    m = re.match(r'(exp\d+[a-z]*\d*)', fn)
    return m.group(1) if m else fn[:-3]


def first_doc(f):
    t = open(f, encoding='utf-8', errors='replace').read()
    m = re.search(r'"""(.*?)"""', t, re.S)
    if not m:
        return '(no docstring)'
    return m.group(1).strip().split('\n')[0][:78]


def main():
    files = sorted(glob.glob(os.path.join(TRADING, 'exp*.py')),
                   key=lambda f: (int(re.match(r'exp(\d+)', os.path.basename(f)).group(1)),
                                  os.path.basename(f)))
    out = []
    out.append('# 实验区索引 —— trading/ × math_probe/')
    out.append('')
    out.append('> 2026-10-08 立（`probe22_make_index.py` 生成 + 手写分组）。')
    out.append('> **入口**：`trading/` 是实验本体（%d 个 exp）；`math_probe/` 是审计探针与档案（21 探针）。' % len(files))
    out.append('> 探针结论详情 → `math_probe/NOTES.md`；审计方法论 → `math_probe/AUDIT-CHECKLIST.md`。')
    out.append('')

    for lo, hi, band, note in BANDS:
        grp = [f for f in files
               if lo <= int(re.match(r'exp(\d+)', os.path.basename(f)).group(1)) <= hi]
        if not grp:
            continue
        out.append('## %s（exp%d–%d）  ' % (band, lo if hi < 99 else 51, hi if hi < 99 else 60))
        out.append('*%s*' % note)
        out.append('')
        out.append('| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |')
        out.append('|---|---|---|---|---|')
        for f in grp:
            fn = os.path.basename(f)
            k = expkey(fn)
            lines = open(f, encoding='utf-8', errors='replace').read().count('\n')
            probe = PROBE_MAP.get(k, '')
            out.append('| %s | `%s` | %d | %s | %s |' % (k, fn, lines, first_doc(f), probe))
        out.append('')

    out.append('## 二、探针清单（math_probe/，21 个）')
    out.append('')
    out.append('| # | 对象 | 一句话结论 |')
    out.append('|---|---|---|')
    for name, obj, concl in PROBES:
        out.append('| %s | %s | %s |' % (name, obj, concl))
    out.append('')
    out.append('## 三、覆盖缺口（2026-10-08 状态）')
    out.append('')
    out.append('- **角色模拟线（exp51–60c）尚未被探针覆盖**——该线含漂移/GRN/Concordia 等 12+ 实验；')
    out.append('- 探针主要在 B/C/D 三线（噪声 / 记忆 / 进化），A 线（交易基础）仅 exp29/31/37 被审过；')
    out.append('- 补跑六连（exp45/47/44/46/48/49）已全部完成，输出留档于 `py_exp*_output.txt`。')
    out.append('')

    dst = os.path.join(MP, 'INDEX.md')
    with open(dst, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))
    print('written:', dst, '| exp files:', len(files))
    # 简报
    for lo, hi, band, _ in BANDS:
        grp = [f for f in files
               if lo <= int(re.match(r'exp(\d+)', os.path.basename(f)).group(1)) <= hi]
        print('  %-22s %d files' % (band, len(grp)))


if __name__ == '__main__':
    main()
