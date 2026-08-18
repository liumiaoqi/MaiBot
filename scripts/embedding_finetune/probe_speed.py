import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

# 测速样本:不同板块的 5 只,拉 30 年(1996-2026)
samples = ['sh600000', 'sz000002', 'sh601398', 'sz000858', 'sh600050']
t0 = time.time()
sizes = []
for sym in samples:
    try:
        t1 = time.time()
        df = ak.stock_zh_a_daily(symbol=sym, start_date='19950101', end_date='20261231', adjust='hfq')
        dt = time.time() - t1
        sizes.append(len(df))
        print(f'{sym}: {len(df)} 行, {dt:.1f}s')
    except Exception as e:
        print(f'{sym}: 失败 {str(e)[:60]}')
total = time.time() - t0
print(f'\n5 只共耗时 {total:.1f}s, 平均 {total/5:.1f}s/只')
if sizes:
    avg_rows = sum(sizes)/len(sizes)
    print(f'平均 {avg_rows:.0f} 行/只(30年)')
    # 估算全量
    est_time = 5545 * total / 5
    print(f'5545 只估算: {est_time/3600:.1f} 小时(串行), 并行x4: {est_time/4/3600:.1f} 小时')
    est_mb = 5545 * avg_rows * 45 / 1e6  # 每行约 45 字节
    print(f'5545 只估算空间: {est_mb:.0f} MB (30年日线)')