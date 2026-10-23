import struct
from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()
hits = ['0x36f85b8','0x36f8e70','0x3723598','0x37268b0','0x37f8e2c','0x383db80','0x3ec7210','0x3ecdff8','0x406dc28','0x4086f68']
for h in hits:
    p = int(h, 16)
    v = struct.unpack_from('<24I', app, p)
    print(h, ' '.join('%d' % x if x < 100 else ('0x%x' % x) for x in v))
