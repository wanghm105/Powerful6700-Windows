import struct
from pathlib import Path
app = Path('../firmware/appFw-2.00.so').read_bytes()

def find_seq(vals32):
    pat = b''.join(struct.pack('<I', v) for v in vals32)
    out = []
    p = app.find(pat)
    while p != -1 and len(out) < 12:
        out.append(p); p = app.find(pat, p+1)
    return out

print('identity u32 0..9 :', [hex(x) for x in find_seq(list(range(10)))])
print('identity u32 0..15:', [hex(x) for x in find_seq(list(range(16)))])
print('u32 10,11:', [hex(x) for x in find_seq([10, 11])][:12])
print('u32 9,10,11:', [hex(x) for x in find_seq([9, 10, 11])][:12])
print('bytes 00..09:', [hex(p) for p in [i for i in [app.find(bytes(range(10)))]] if p != -1])
