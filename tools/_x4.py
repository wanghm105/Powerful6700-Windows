import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()

# 1) gamma ramp signature: v0=0, v1~, v2~2*v1, v3~3*v1
hits = []
n = len(cp)
for p in range(0, n-64, 4):
    v = struct.unpack_from('<4I', cp, p)
    if v[0] != 0: continue
    a = v[1]
    if not (400 <= a <= 1600): continue
    if abs(v[2] - 2*a) <= 80 and abs(v[3] - 3*a) <= 120:
        hits.append((p, v))
print('ramp hits:', len(hits))
for p, v in hits[:20]:
    print(' ', hex(p), v)

# 2) matrix-record signature: runs of 12-byte groups of small int16
def good_group(p):
    s = struct.unpack_from('<6h', cp, p)
    return all(abs(x) <= 1300 for x in s) and (s[0] + s[1]) > 0 and (s[2] + s[3]) > 0
runs = []
p = 0
while p < n - 12*8:
    if good_group(p):
        q = p
        cnt = 0
        while q < n - 12 and good_group(q):
            cnt += 1; q += 12
        if cnt >= 8:
            runs.append((p, cnt))
        p = q
    else:
        p += 2
print('matrix-like runs:', len(runs))
for p, c in sorted(runs, key=lambda t: -t[1])[:15]:
    print(' ', hex(p), 'groups', c)
