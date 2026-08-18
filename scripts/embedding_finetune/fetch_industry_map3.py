import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'

# 新浪行业板块列表
boards = pd.read_csv(os.path.join(DATA, '_sector_list.csv'))
print('板块数:', len(boards))

# 拉每个板块成分股,映射 股票代码->行业
mapping = {}
fail = []
for i, row in boards.iterrows():
    label = row['label']
    name = row['板块']
    for attempt in range(3):
        try:
            cons = ak.stock_sector_cons(symbol=label)  # 新浪行业成分
            codes = cons['代码'].astype(str).str.zfill(6) if '代码' in cons.columns else []
            for c in codes:
                mapping[c] = name
            print(f'[{i+1}/{len(boards)}] {name}: {len(codes)} 只')
            break
        except Exception as e:
            time.sleep(2 + attempt*3)
    else:
        fail.append(name)
        print(f'[{i+1}/{len(boards)}] {name}: 失败')

print(f'\n映射完成: {len(mapping)} 只, 失败板块 {len(fail)}: {fail}')
df = pd.DataFrame([{'code': k, 'industry': v} for k, v in mapping.items()])
df.to_csv(os.path.join(DATA, '_industry_map.csv'), index=False)
print('已保存 _industry_map.csv')