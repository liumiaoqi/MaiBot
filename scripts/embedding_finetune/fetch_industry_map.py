import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 全市场实时行情(含行业字段)——一次拉取
try:
    df = ak.stock_zh_a_spot_em()
    print(f'全市场: {len(df)} 只')
    print('列:', list(df.columns)[:20])
    # 提取 代码/名称/行业
    cols = [c for c in ['代码','名称','所属行业'] if c in df.columns]
    if cols:
        out = df[cols].copy()
        out.to_csv(r'E:\\Users\\lmq\\Documents\\finance\\data\\_industry_map.csv', index=False)
        print(f'行业映射已保存: {len(out)} 只')
        print(out.head(10))
    else:
        print('未找到行业列,列:', list(df.columns))
except Exception as e:
    print(f'失败: {str(e)[:100]}')