import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()

def rows(base, count, per=12):
    for i in range(0, count, per):
        p = base + i*4
        v = struct.unpack_from('<%dI' % per, cp, p)
        print(hex(p), ' '.join('%08x' % x for x in v), '|', ' '.join(str(x) for x in v))

print('--- around first dense ramp cluster 0xcd8a1c')
rows(0xcd8a00, 24)
print('--- 0xcd8e9c record context')
rows(0xcd8e80, 24)
