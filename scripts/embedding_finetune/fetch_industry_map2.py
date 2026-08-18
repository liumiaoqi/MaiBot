import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_path = r'E:\Users\lmq\Documents\finance\data\_industry_map.csv'

# 方案1:东财全市场(重试3次)
ok = False
for attempt in range(3):
    try:
        df = ak.stock_zh_a_spot_em()
        cols = [c for c in ['代码','名称','所属行业'] if c in df.columns]
        if cols:
            df[cols].to_csv(out_path, index=False)
            print(f'东财成功: {len(df)} 只')
            ok = True
            break
    except Exception as e:
        print(f'东财 attempt{attempt+1}: {str(e)[:60]}')
        time.sleep(5)

if not ok:
    # 方案2:新浪行业板块(逐板块拉成分股,30+板块)
    try:
        boards = ak.stock_sector_spot(indicator='新浪行业')
        print(f'新浪行业板块: {len(boards)} 个')
        print(boards.head(3))
        # 逐板块拉成分——较慢,先看板块列表
        boards.to_csv(r'E:\Users\lmq\Documents\finance\data\_sector_list.csv', index=False)
        print('板块列表已保存(成分股拉取下一步)')
    except Exception as e2:
        print(f'新浪板块也失败: {str(e2)[:80]}')