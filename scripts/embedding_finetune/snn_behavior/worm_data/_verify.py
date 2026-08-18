
import json
import numpy as np

d = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
Gs = np.load(d + '\\Gs.npy')
Gg = np.load(d + '\\Gg.npy')
print('Gs(化学突触) shape:', Gs.shape, '| 非零边:', int((Gs > 0).sum()), '| 总权重:', int(Gs.sum()))
print('Gg(电突触)   shape:', Gg.shape, '| 非零边:', int((Gg > 0).sum()), '| 总权重:', int(Gg.sum()))
chem = json.load(open(d + '\\chem.json', encoding='utf-8'))
print('chem.json 类型:', type(chem))
if isinstance(chem, dict):
    keys = list(chem.keys())[:5]
    print('keys:', keys)
    for k in keys:
        v = chem[k]
        if isinstance(v, list) and v and isinstance(v[0], str) and len(v) > 250:
            print('  ', k, '长度:', len(v), '示例:', v[:3])
elif isinstance(chem, list):
    print('list 长度:', len(chem), '| 第一条:', str(chem[0])[:200])
