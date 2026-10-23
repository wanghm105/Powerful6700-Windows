import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
n = len(cp)

def chroma_ok(p):
    if cp[p+48:p+64] != b'\x00'*16: return False
    vals = struct.unpack_from('<24h', cp, p)
    if all(v == 0 for v in vals): return False
    return all(abs(v) <= 4096 for v in vals)

runs = []
p = 0
while p < n - 64:
    if chroma_ok(p):
        q = p; cnt = 0
        while q < n - 64 and chroma_ok(q):
            cnt += 1; q += 64
        if cnt >= 6:
            runs.append((p, cnt))
        p = q
    else:
        p += 2
print('chroma-like runs (>=6 slots):', len(runs))
for p, c in sorted(runs, key=lambda t: -t[1])[:15]:
    print(' ', hex(p), 'slots', c)
