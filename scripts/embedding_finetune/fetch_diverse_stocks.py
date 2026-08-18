import akshare as ak
import pandas as pd
import os, time

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

out_dir = r'E:\Users\lmq\Documents\finance\data'

# 多样化股票池:代码 -> (名称, 质地档位)
# 绩优股(好): 茅台(白酒龙头)/长江电力(公用事业)/招商银行(银行)
# 一般股(中): 宝钢股份(钢铁周期)/中国中车(制造业)/上汽集团(汽车)
# 差/困境股(差): 华夏幸福(地产暴雷)/ST 类难拉——用海航科技/中远海控(航运周期)代替
stocks = [
    ('600519', '贵州茅台', '好-白酒龙头'),
    ('600900', '长江电力', '好-公用事业'),
    ('600036', '招商银行', '好-银行'),
    ('600019', '宝钢股份', '中-钢铁周期'),
    ('601766', '中国中车', '中-制造业'),
    ('600104', '上汽集团', '中-汽车'),
    ('600340', '华夏幸福', '差-地产暴雷'),
    ('601919', '中远海控', '差-航运周期'),
    ('600221', '海航控股', '差-航空困境'),
    ('601989', '中国重工', '中-船舶'),
    ('600028', '中国石化', '中-能源'),
    ('002594', '比亚迪', '好-新能源车'),
    ('300750', '宁德时代', '好-动力电池'),
    ('600276', '恒瑞医药', '好-医药'),
    ('601318', '中国平安', '中-保险'),
    ('600030', '中信证券', '中-券商'),
    ('600050', '中国联通', '中-电信'),
    ('601668', '中国建筑', '中-基建'),
    ('600887', '伊利股份', '好-消费'),
    ('000725', '京东方A', '中-面板周期'),
    ('600585', '海螺水泥', '中-建材周期'),
    ('600031', '三一重工', '中-机械'),
    ('601088', '中国神华', '好-煤炭能源'),
    ('600690', '海尔智家', '好-家电'),
    ('000001', '平安银行', '中-银行'),
    ('600606', '绿地控股', '差-地产'),
    ('600519_skip', '', ''),
];
stocks = [s for s in stocks if s[2]]

# 结果表
results = []

for code, name, grade in stocks:
    for attempt in range(4):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period='daily',
                                   start_date='20140101', end_date='20261231', adjust='hfq')
            df = df.rename(columns={'日期':'date','开盘':'open','最高':'high',
                                   '最低':'low','收盘':'close','成交量':'volume'})
            df['date'] = pd.to_datetime(df['date'])
            df = df[df['date'] >= '2015-01-01']
            out = df[['date','open','high','low','close','volume']].copy()
            fname = os.path.join(out_dir, code + '_daily.csv')
            out.to_csv(fname, index=False)
            # 计算 11 年总涨幅(后复权)
            total_ret = out['close'].iloc[-1] / out['close'].iloc[0] - 1
            results.append((code, name, grade, len(out), total_ret*100))
            print(f'{code} {name}[{grade}]: {len(out)}行 11年涨幅{total_ret*100:.0f}%')
            break
        except Exception as e:
            print(f'{code} attempt{attempt+1}: {str(e)[:60]}')
            time.sleep(4)

print('\n=== 汇总 ===')
for r in sorted(results, key=lambda x: x[4], reverse=True):
    print(f'{r[1]}[{r[2]}]: {r[4]:.0f}%')