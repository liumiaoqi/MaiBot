import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 同花顺成分股接口探测
try:
    cons = ak.stock_board_industry_cons_ths(symbol='半导体')
    print(f'同花顺半导体成分: {len(cons)} 只')
    print('列:', list(cons.columns))
    print(cons.head(5))
except Exception as e:
    print(f'失败: {str(e)[:150]}')