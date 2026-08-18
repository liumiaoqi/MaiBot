import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 1) 东财行业板块列表
try:
    boards = ak.stock_board_industry_name_em()
    print(f'东财行业板块: {len(boards)} 个')
    print('列:', list(boards.columns))
    print(boards.head(3))
    # 试拉第一个板块成分
    first = boards.iloc[0]['板块名称'] if '板块名称' in boards.columns else boards.iloc[0][0]
    print(f'试拉板块: {first}')
    cons = ak.stock_board_industry_cons_em(symbol=first)
    print(f'成分股: {len(cons)} 只')
    print('列:', list(cons.columns))
    print(cons.head(3))
except Exception as e:
    print(f'东财失败: {str(e)[:120]}')