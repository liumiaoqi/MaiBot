import pandas as pd

xl = pd.ExcelFile(r'E:\Users\lmq\Documents\finance\era_industry_tiers.xlsx')
for sheet in xl.sheet_names:
    df = xl.parse(sheet)
    print(sheet, '列:', list(df.columns), '前2行:');
    print(df.head(2).to_string())
    print()