import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 新浪行业板块列表(之前成功过)
try:
    boards = ak.stock_sector_spot(indicator='新浪行业')
    print(f'新浪行业板块: {len(boards)} 个')
    # 试 stock_sector_detail 拉成分
    try:
        detail = ak.stock_sector_detail(sector='new_blhy')
        print(f'成分详情: {len(detail)} 只')
        print('列:', list(detail.columns))
        print(detail.head(3))
    except Exception as e2:
        print(f'stock_sector_detail 失败: {str(e2)[:100]}')
except Exception as e:
    print(f'新浪板块失败: {str(e)[:100]}')