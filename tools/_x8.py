import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()

def good(p):
    s = struct.unpack_from('<6h', cp, p)
    return all(abs(x) <= 1500 for x in s) and (s[0]+s[1]) > 0 and all(v != 0 for v in s)

runs = []
for p in range(0xb00000, 0xc40000-96, 2):
    if good(p):
        q = p; cnt = 0
        while q < 0xc40000 and good(q):
            cnt += 1; q += 12
        if cnt >= 12:
            runs.append((p, cnt))
print('runs in 0xb00000-0xc40000:', len(runs))
for p, c in sorted(runs, key=lambda t: -t[1])[:12]:
    print(' ', hex(p), 'groups', c, 'span', hex(c*12))

# also show the neighbourhood of the chroma run
base = 0xc24d62
print('chroma run head file 0x%x' % base)
for i in range(4):
    p = base + i*64
    print(' slot', i, ' '.join('%6d' % x for x in struct.unpack_from('<24h', cp, p))[:120])
print('bytes before:', cp[base-32:base].hex(' '))
