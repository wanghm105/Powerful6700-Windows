import json
p = json.load(open('../refs/a7c2-fl23/src/camera_runtime/assets/patches.json'))
def walk(o, depth=0):
    if isinstance(o, dict):
        ks = list(o.keys())
        return
entries = p if isinstance(p, list) else p.get('patches') or p.get('entries')
print(type(p), len(entries) if entries is not None else None)
for e in entries:
    keys = sorted(e.keys())
    print('---', {k: (e[k] if not isinstance(e[k], (list, dict)) else type(e[k]).__name__) for k in keys})
    break
print()
for e in entries:
    blob = json.dumps(e, ensure_ascii=False)
    if '0x59892' in blob.lower() or '0x59893' in blob.lower():
        print(json.dumps(e, ensure_ascii=False, indent=1)[:1200])