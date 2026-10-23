import struct
from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()
def rows(base, nbytes, per=8):
    for i in range(0, nbytes, per*4):
        p = base + i
        v = struct.unpack_from('<%dI' % per, app, p)
        print(hex(p), ' '.join('%08x' % x for x in v))
for base in (0x36f8598, 0x3ec71f0, 0x406dc08):
    print('=== around', hex(base))
    rows(base, 0x60)
