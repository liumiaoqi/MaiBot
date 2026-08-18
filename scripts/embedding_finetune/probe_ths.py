import akshare as ak
import pandas as pd
import os

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_path = r'E:\Users\lmq\Documents\finance\data\_industry_map.csv'

# 同花顺行业列表
try:
    boards = ak.stock_board_industry_name_ths()
    print(f'同花顺行业: {len(boards)} 个')
    print('列:', list(boards.columns))
    print(boards.head(5))
except Exception as e:
    print(f'同花顺失败: {str(e)[:100]}')

# 巨潮参数探测
try:
    import inspect
    sig = inspect.signature(ak.stock_industry_category_cninfo)
    print(f'\n巨潮函数签名: {sig}')
except Exception as e:
    print(f'签名探测失败: {e}')