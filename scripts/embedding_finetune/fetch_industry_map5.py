import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_path = r'E:\Users\lmq\Documents\finance\data\_industry_map.csv'

# 巨潮行业分类(正确参数:巨潮行业分类标准)
try:
    df = ak.stock_industry_category_cninfo(symbol='巨潮行业分类标准')
    print(f'巨潮行业分类: {len(df)} 只')
    print('列:', list(df.columns))
    print(df.head(8))
    df.to_csv(out_path, index=False)
    print('已保存 _industry_map.csv')
except Exception as e:
    print(f'巨潮失败: {str(e)[:150]}')