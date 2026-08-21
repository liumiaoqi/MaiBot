
import json, urllib.request, os, sys

def cypher(q, token):
    url = 'https://neuprint.janelia.org/api/custom/custom'
    body = json.dumps({'cypher': q, 'dataset': 'hemibrain:v1.2.1'}).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

token = os.environ['NEUPRINT_TOKEN']
# 1. 关系类型
try:
    r = cypher('MATCH ()-[s]->() RETURN type(s) AS rel, count(*) AS n LIMIT 10', token)
    print('关系类型:', r.get('data'))
except Exception as e:
    print('关系类型查询失败:', e)
# 2. 用拉到的第一个神经元查连接
try:
    d = json.load(open(r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\flywire_data\mb_neurons.json', encoding='utf-8'))
    bid = d[0][0]
    print('测试神经元 bodyId:', bid)
    r = cypher('MATCH (a:Neuron)-[s]->(b:Neuron) WHERE a.bodyId = %d RETURN a.bodyId, b.bodyId, s.weight, type(s) LIMIT 5' % bid, token)
    print('连接:', r.get('data'))
except Exception as e:
    print('连接查询失败:', e)
