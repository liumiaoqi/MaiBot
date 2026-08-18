#!/usr/bin/env python3
"""拉取果蝇蘑菇体(蘑菇体)连接组子图——NeuPrint REST API(hemibrain 数据集)

用法(用户本地跑):
  $env:NEUPRINT_TOKEN = "你的token"
  uv run python fetch_flywire_mb.py
或: uv run python fetch_flywire_mb.py "你的token"

产出(放 scripts/embedding_finetune/snn_behavior/flywire_data/):
  mb_neurons.json    蘑菇体相关神经元(类型/状态/体ID)
  mb_connections.csv 连接(源->目标, 突触权重)——带权重邻接矩阵
  统计打印:神经元数/连接数/数据量

数据量预估:蘑菇体子图 ~2000 神经元 + ~5万条连接 ≈ 5-15 MB(JSON/CSV)
运行时长:几十次 API 请求,网络稳定时 2-10 分钟;超时自动重试 3 次
"""

import json
import os
import sys
import time
import csv
import urllib.request
import urllib.error

BASE = 'https://neuprint.janelia.org'
DATASET = 'hemibrain:v1.2.1'
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flywire_data')

# 蘑菇体相关神经元类型(嗅觉学习回路:肯扬细胞/蘑菇体输出/多巴胺/嗅觉投射)
MB_TYPES = ['MBON', 'KC', 'DAN', 'MBIN', 'PN', 'APL', 'MB']


def get_token():
    if len(sys.argv) > 1:
        return sys.argv[1]
    t = os.environ.get('NEUPRINT_TOKEN', '')
    if t:
        return t
    print('错误:未提供 token。用法:')
    print('  $env:NEUPRINT_TOKEN = "你的token"; uv run python fetch_flywire_mb.py')
    print('或: uv run python fetch_flywire_mb.py "你的token"')
    sys.exit(1)


def api_get(path, token, retries=3):
    url = BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'Authorization': 'Bearer ' + token,
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError('token 无效或过期(401)')
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                raise


def api_post_cypher(cypher, token, retries=3):
    """POST /api/custom/custom——NeuPrint 的图查询入口(neuprint-python 同款)。"""
    url = BASE + '/api/custom/custom'
    body = json.dumps({'cypher': cypher, 'dataset': DATASET}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError('token 无效或过期(401)')
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
            else:
                raise


def main():
    token = get_token()
    os.makedirs(OUT_DIR, exist_ok=True)
    print('=== 果蝇蘑菇体连接组拉取(hemibrain) ===')
    print('1/4 验证 token + 查数据集...')
    try:
        datasets = api_get('/api/datasets', token)
        print('   数据集可用 ✓')
    except Exception as e:
        print('   datasets 端点: %s(继续尝试 cypher)' % e)

    print('2/4 查询蘑菇体相关神经元...')
    type_filter = ' OR '.join('n.type CONTAINS "%s"' % t for t in MB_TYPES)
    cypher_neurons = (
        'MATCH (n:Neuron) WHERE %s '
        'RETURN n.bodyId AS bodyId, n.type AS type, n.status AS status '
        'LIMIT 5000' % type_filter
    )
    try:
        res = api_post_cypher(cypher_neurons, token)
        rows = res.get('data', [])
        print('   命中神经元: %d 个' % len(rows))
        if not rows:
            print('   无结果——尝试去掉 LIMIT 或换类型名')
            return
        with open(os.path.join(OUT_DIR, 'mb_neurons.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('   查询失败: %s' % e)
        print('   (token 若有效,可能是网络/限流——稍后重试)')
        return

    print('3/4 查询神经元间连接(突触权重)——分步简单查询(大 OR 表达式会 400)...')
    # 核心路径:KC(肯扬细胞) → MBON(蘑菇体输出)——学习回路主干
    conn_queries = [
        ('KC->MBON', 'MATCH (a:Neuron)-[s:ConnectsTo]->(b:Neuron) '
                     'WHERE a.type CONTAINS "KC" AND b.type CONTAINS "MBON" '
                     'RETURN a.bodyId AS src, b.bodyId AS dst, s.weight AS weight LIMIT 100000'),
        ('PN->KC', 'MATCH (a:Neuron)-[s:ConnectsTo]->(b:Neuron) '
                   'WHERE a.type CONTAINS "PN" AND b.type CONTAINS "KC" '
                   'RETURN a.bodyId AS src, b.bodyId AS dst, s.weight AS weight LIMIT 100000'),
        ('KC->DAN', 'MATCH (a:Neuron)-[s:ConnectsTo]->(b:Neuron) '
                    'WHERE a.type CONTAINS "KC" AND b.type CONTAINS "DAN" '
                    'RETURN a.bodyId AS src, b.bodyId AS dst, s.weight AS weight LIMIT 100000'),
        ('MBON->ALL', 'MATCH (a:Neuron)-[s:ConnectsTo]->(b:Neuron) '
                      'WHERE a.type CONTAINS "MBON" '
                      'RETURN a.bodyId AS src, b.bodyId AS dst, s.weight AS weight LIMIT 100000'),
    ]
    all_conns = []
    with open(os.path.join(OUT_DIR, 'mb_connections.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['src', 'dst', 'weight'])
        for label, cypher_conns in conn_queries:
            try:
                res = api_post_cypher(cypher_conns, token)
                conns = res.get('data', [])
                print('   %s: %d 条' % (label, len(conns)))
                for c in conns:
                    w.writerow([c[0], c[1], c[2]])
                all_conns.extend(conns)
            except Exception as ex:
                print('   %s 失败: %s' % (label, ex))
    print('   连接总数: %d 条' % len(all_conns))

    print('4/4 统计 + 数据量...')
    n_neurons = len(rows)
    n_conns = len(all_conns if 'all_conns' in dir() else [])
    total_bytes = 0
    for fname in os.listdir(OUT_DIR):
        total_bytes += os.path.getsize(os.path.join(OUT_DIR, fname))
    print()
    print('=== 完成 ===')
    print('神经元: %d | 连接: %d' % (n_neurons, n_conns))
    print('数据量: %.1f MB(文件在 %s)' % (total_bytes / 1048576, OUT_DIR))
    print('下一步: exp40 用 mb_connections.csv 构建真实连接矩阵喂 VQC')


if __name__ == '__main__':
    main()
