import pandas as pd

xl = pd.ExcelFile(r'E:\Users\lmq\Documents\finance\era_industry_tiers.xlsx')
print('工作表:', xl.sheet_names)

for sheet in xl.sheet_names:
    df = xl.parse(sheet)
    print(f'\n===== {sheet} =====')
    # 分开打印好/中/差
    for tier in ['好', '中', '差']:
        sub = df[df['tier'] == tier].sort_values('median', ascending=False)
        if len(sub):
            names = '、'.join(sub.index.astype(str).tolist())
            print(f'  [{tier}] {names}')