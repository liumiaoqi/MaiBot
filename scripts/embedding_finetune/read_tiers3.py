import pandas as pd

xl = pd.ExcelFile(r'E:\Users\lmq\Documents\finance\era_industry_tiers.xlsx')

for sheet in xl.sheet_names:
    df = xl.parse(sheet)
    print(f'===== {sheet} =====')
    for tier in ['好', '中', '差']:
        sub = df[df['tier'] == tier].sort_values('median', ascending=False)
        if len(sub):
            lines = [f'{row.industry}({row.median*100:.0f}%)' for _, row in sub.iterrows()]
            print(f'  [{tier} {len(sub)}个] ' + '、'.join(lines))
    print()