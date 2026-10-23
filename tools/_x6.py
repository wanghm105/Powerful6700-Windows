import struct, collections
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
n = len(cp)
c = collections.Counter()
for p in range(0, n-4, 4):
    v = struct.unpack_from('<I', cp, p)[0]
    if 0x100000 <= v <= 0x2000000 and v >= p:
        c[v - p] += 1
print('len', hex(n))
for k, cnt in c.most_common(12):
    print(hex(k), cnt, '=> file offset of that addr range? sample', hex(k + 0))
