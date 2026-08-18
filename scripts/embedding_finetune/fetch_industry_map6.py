import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'

# 板块列表(之前存的)
boards = pd.read_csv(os.path.join(DATA, '_sector_list.csv'))
print('板块数:', len(boards))

# 逐板块拉成分
mapping = {}
fail = []
for i, row in boards.iterrows():
    label = row['label']
    name = row['板块']
    for attempt in range(3):
        try:
            detail = ak.stock_sector_detail(sector=label)
            codes = detail['code'].astype(str).str.zfill(6)
            for c in codes:
                mapping[c] = name
            print(f'[{i+1}/{len(boards)}] {name}: {len(codes)} 只')
            break
        except Exception as e:
            time.sleep(2 + attempt*3)
    else:
        fail.append(name)
        print(f'[{i+1}/{len(boards)}] {name}: 失败')

print(f'\n完成: {len(mapping)} 只股票映射, 失败板块 {len(fail)}: {fail}')
df = pd.DataFrame([{'code': k, 'industry': v} for k, v in mapping.items()])
df.to_csv(os.path.join(DATA, '_industry_map.csv'), index=False)
print('已保存 _industry_map.csv')
# 统计行业分布
print('\n行业分布:');
print(df['industry'].value_counts().head(15))