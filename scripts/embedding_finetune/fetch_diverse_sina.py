import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_dir = r'E:\Users\lmq\Documents\finance\data'

# 新浪代码格式:sh600519 / sz000001
stocks = [
    ('sh600519', '贵州茅台', '好'),
    ('sh600900', '长江电力', '好'),
    ('sh600036', '招商银行', '好'),
    ('sh600019', '宝钢股份', '中'),
    ('sh601766', '中国中车', '中'),
    ('sh600104', '上汽集团', '中'),
    ('sh600340', '华夏幸福', '差'),
    ('sh601919', '中远海控', '差'),
    ('sh600221', '海航控股', '差'),
    ('sz002594', '比亚迪', '好'),
    ('sz300750', '宁德时代', '好'),
    ('sh600276', '恒瑞医药', '好'),
    ('sh601318', '中国平安', '中'),
    ('sh600030', '中信证券', '中'),
    ('sh600050', '中国联通', '中'),
    ('sh601668', '中国建筑', '中'),
    ('sh600887', '伊利股份', '好'),
    ('sz000725', '京东方A', '中'),
    ('sh600585', '海螺水泥', '中'),
    ('sh600031', '三一重工', '中'),
    ('sh601088', '中国神华', '好'),
    ('sh600690', '海尔智家', '好'),
    ('sz000001', '平安银行', '中'),
    ('sh600606', '绿地控股', '差'),
];

results = []
for sym, name, grade in stocks:
    code = sym[2:]
    fname = os.path.join(out_dir, code + '_daily.csv')
    if os.path.exists(fname) and os.path.getsize(fname) > 10000:
        print(f'{name}: 已有,跳过')
        continue
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=sym, start_date='20140101', end_date='20261231', adjust='hfq')
            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] >= '2015-01-01']
            out = df[['date','open','high','low','close','volume']].copy()
            out.to_csv(fname, index=False)
            total_ret = out['close'].iloc[-1] / out['close'].iloc[0] - 1
            results.append((name, grade, total_ret*100))
            print(f'{name}[{grade}]: {len(out)}行 11年{total_ret*100:.0f}%')
            break
        except Exception as e:
            print(f'{name} attempt{attempt+1}: {str(e)[:50]}')
            time.sleep(3)

print('\n=== 汇总(按涨幅) ===')
for r in sorted(results, key=lambda x: x[2], reverse=True):
    print(f'{r[0]}[{r[1]}]: {r[2]:.0f}%')