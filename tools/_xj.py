import json
from pathlib import Path
p = json.loads(Path('../refs/a7c2-fl23/src/camera_runtime/assets/patches.json').read_text(encoding='utf-8'))
print('chips', len(p), 'keys', list(p[0]))
w = p[0]['writes'][0]
print('write keys', list(w))
for k, v in w.items():
    print('  ', k, '=', repr(v)[:160])
