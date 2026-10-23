import struct
from pathlib import Path
cp = Path('../firmware/cp/cpapp-b.bin').read_bytes()
def rows(base, count, per=8):
    for i in range(0, count, per):
        p = base + i*4
        v = struct.unpack_from('<%dI' % per, cp, p)
        print(hex(p), ' '.join('%08x' % x for x in v), '|', ' '.join(str(x) for x in v))
rows(0x20100, 48)
