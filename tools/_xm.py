import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
blob_end = 0x11002b8
unit_end = 0x16fa594 + 0x700
delta = unit_end - blob_end
print('candidate delta', hex(delta), '=> unit end maps to blob end')
def f(addr): return addr - delta
for key, addr, size in ((0x02a40000,0x16efe94,0x1200),(0x02a40001,0x16f1094,0x2000),(0x02a4000d,0x16f3594,0x7000)):
    p = f(addr)
    seg = cp[p:p+size]
    print('unit', hex(key), 'file', hex(p), 'nonzero', sum(1 for b in seg if b))
p = f(0x16f1094)
seg = cp[p:p+0x2000]
print('param table @+0x1200:', seg[0x1200:0x1200+80].hex(' '))
print('chroma slot0 @+0x1250:', ' '.join('%6d' % x for x in struct.unpack_from('<24h', seg, 0x1250)))
print('chroma slot23 @+0x1250+23*64:', ' '.join('%6d' % x for x in struct.unpack_from('<24h', seg, 0x1250+23*64)))
print('chroma slot25:', ' '.join('%6d' % x for x in struct.unpack_from('<24h', seg, 0x1250+25*64)))
p2 = f(0x16f3594)
seg2 = cp[p2:p2+0x7000]
print('unit0d nonzero', sum(1 for b in seg2 if b))
print('unit0d params @+0x196:', seg2[0x196:0x196+80].hex(' '))
print('matrix slot0:', ' '.join('%6d' % x for x in struct.unpack_from('<48h', seg2, 0x1e0))[:150])
print('matrix slot23:', ' '.join('%6d' % x for x in struct.unpack_from('<48h', seg2, 0x1e0+23*768))[:150])
