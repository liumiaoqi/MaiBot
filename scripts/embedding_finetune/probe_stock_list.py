import akshare as ak
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 1) 获取 A 股全部股票清单
print('=== 拉取 A 股股票清单 ===')
t0 = time.time()
try:
    df = ak.stock_info_a_code_name()
    print(f'A 股清单: {len(df)} 只 ({time.time()-t0:.1f}s)')
    print(df.head(5))
    # 保存清单
    df.to_csv(r'E:\\Users\\lmq\\Documents\\finance\\data\\_a_stock_list.csv', index=False)
except Exception as e:
    print(f'清单拉取失败: {e}')
    # 备选接口
    try:
        df = ak.stock_zh_a_spot_em()
        print(f'备选: {len(df)} 只')
        df[['代码','名称']].to_csv(r'E:\\Users\\lmq\\Documents\\finance\\data\\_a_stock_list.csv', index=False)
    except Exception as e2:
        print(f'备选也失败: {e2}')