import akshare as ak
import pandas as pd
import os, time, threading, queue

for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)

DATA = r'E:\Users\lmq\Documents\finance\data'
LIST = os.path.join(DATA, '_a_stock_list.csv')

stocks = pd.read_csv(LIST)
stocks['code'] = stocks['code'].astype(str).str.zfill(6)

def to_sina(code):
    if code.startswith(('6', '9')): return 'sh' + code
    if code.startswith(('0', '3')): return 'sz' + code
    return 'bj' + code

# 断点续传
todo = []
for _, row in stocks.iterrows():
    code = row['code']
    fpath = os.path.join(DATA, code + '_daily.csv')
    if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
        continue
    todo.append((code, str(row['name'])))

print('待拉取: %d 只(共 %d 只)' % (len(todo), len(stocks)))

q = queue.Queue()
for item in todo: q.put(item)
lock = threading.Lock()
failed = []
done = [0]
start_t = time.time()

def worker():
    while True:
        try:
            code, name = q.get_nowait()
        except queue.Empty:
            return
        sym = to_sina(code)
        ok = False
        for attempt in range(3):
            try:
                df = ak.stock_zh_a_daily(symbol=sym, start_date='19950101',
                                        end_date='20261231', adjust='hfq')
                df['date'] = pd.to_datetime(df['date'])
                out = df[['date','open','high','low','close','volume']].copy()
                out.to_csv(os.path.join(DATA, code + '_daily.csv'), index=False)
                ok = True
                break
            except Exception:
                time.sleep(2 + attempt * 3)
        with lock:
            done[0] += 1
            if not ok:
                failed.append(code)
            if done[0] % 50 == 0:
                el = time.time() - start_t
                rate = done[0] / el
                remain = (len(todo) - done[0]) / rate if rate > 0 else 0
                msg = '[%s] 完成 %d/%d, 剩余约 %d 分钟, 失败 %d' % (
                    time.strftime('%H:%M:%S'), done[0], len(todo), remain/60, len(failed))
                print(msg)
        q.task_done()

threads = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()

el = time.time() - start_t
print('完成! 共 %d 只, 耗时 %.1f 分钟' % (done[0], el/60))
print('失败 %d 只: %s' % (len(failed), failed[:30]))
with open(os.path.join(DATA, '_failed_list.txt'), 'w') as f:
    for c in failed: f.write(c + '\n')