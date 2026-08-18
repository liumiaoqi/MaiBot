import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 巨潮行业变化/市盈率接口(可能含股票-行业)
try:
    df = ak.stock_industry_change_cninfo(symbol='巨潮行业分类标准')
    print(f'行业变化: {len(df)} 行')
    print('列:', list(df.columns))
    print(df.head(5))
except Exception as e:
    print(f'行业变化失败: {str(e)[:100]}')

try:
    df2 = ak.stock_industry_pe_ratio_cninfo(symbol='巨潮行业分类标准')
    print(f'\n行业PE: {len(df2)} 行')
    print('列:', list(df2.columns))
    print(df2.head(5))
except Exception as e2:
    print(f'行业PE失败: {str(e2)[:100]}')