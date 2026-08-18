import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_path = r'E:\Users\lmq\Documents\finance\data\_industry_map.csv'

# 方案1:巨潮行业分类(一次拉全市场)
try:
    df = ak.stock_industry_category_cninfo(symbol='巨潮行业分类')
    print(f'巨潮行业分类: {len(df)} 只')
    print('列:', list(df.columns))
    print(df.head(8))
    df.to_csv(out_path, index=False)
    print('已保存 _industry_map.csv')
except Exception as e:
    print(f'巨潮失败: {str(e)[:100]}')
    # 方案2:东财行业板块成分(重试)
    try:
        boards = ak.stock_board_industry_name_em()
        print(f'东财行业板块: {len(boards)} 个')
        print(boards.head(3))
    except Exception as e2:
        print(f'东财板块也失败: {str(e2)[:80]}')