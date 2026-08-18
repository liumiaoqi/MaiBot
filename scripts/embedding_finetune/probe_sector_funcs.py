import akshare as ak
# 列出所有 sector/行业相关函数
funcs = [f for f in dir(ak) if 'sector' in f.lower() or 'industry' in f.lower() or '板块' in f]
print('板块/行业相关函数:');
for f in funcs: print(' ', f)