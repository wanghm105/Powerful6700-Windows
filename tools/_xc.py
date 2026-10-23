import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
B = 0x5EA9DC
n = len(cp)
print('len', hex(n), 'B', hex(B))
def at(addr, size=None):
    p = addr - B
    return p
for key, addr, size in ((0x02a40000,0x16efe94,0x1200),(0x02a40001,0x16f1094,0x2000),(0x02a4000d,0x16f3594,0x7000),(0x02a4000e,0x16fa594,0x700)):
    p = at(addr)
    print('unit', hex(key), 'file', hex(p), 'end', hex(p+size), 'inrange', p+size <= n)
p = at(0x16f1094)
seg = cp[p:p+0x2000]
print('unit01 nonzero', sum(1 for b in seg if b), 'head', seg[:32].hex(' '))
print('param table @+0x1200:', seg[0x1200:0x1200+64].hex(' '))
print('chroma @+0x1250:', ' '.join('%6d' % x for x in struct.unpack_from('<24h', seg, 0x1250)))
print('chroma slot1  :', ' '.join('%6d' % x for x in struct.unpack_from('<24h', seg, 0x1250+64)))
p2 = at(0x16f3594)
seg2 = cp[p2:p2+0x7000]
print('unit0d nonzero', sum(1 for b in seg2 if b))
print('unit0d param @+0x196:', seg2[0x196:0x196+48].hex(' '))
print('unit0d matrix @+0x1e0 slot0:', ' '.join('%6d' % x for x in struct.unpack_from('<48h', seg2, 0x1e0)))
print('unit0d matrix slot23 @+0x1e0+23*768:', ' '.join('%6d' % x for x in struct.unpack_from('<48h', seg2, 0x1e0+23*768))[:200])
