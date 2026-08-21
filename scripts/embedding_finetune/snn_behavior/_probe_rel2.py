
import json, urllib.request, os, sys, traceback
print('start', flush=True)
def cypher(q, token):
    url = 'https://neuprint.janelia.org/api/custom/custom'
    body = json.dumps({'cypher': q, 'dataset': 'hemibrain:v1.2.1'}).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())
try:
    token = os.environ['NEUPRINT_TOKEN']
    print('token len:', len(token), flush=True)
    r = cypher('MATCH ()-[s]->() RETURN type(s) AS rel LIMIT 10', token)
    print('关系类型:', r, flush=True)
except Exception as e:
    traceback.print_exc()
    print('FAIL:', e, flush=True)
