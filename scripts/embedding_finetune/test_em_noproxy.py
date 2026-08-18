import akshare as ak
import os
# 清空所有代理变量
for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy','NO_PROXY','no_proxy']:
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'

# 测试东财行业板块
try:
    boards = ak.stock_board_industry_name_em()
    print(f'东财行业板块 OK: {len(boards)} 个')
except Exception as e:
    print(f'东财失败: {str(e)[:120]}')