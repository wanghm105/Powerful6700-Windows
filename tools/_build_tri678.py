from pathlib import Path
import struct, hashlib

raw = Path('../firmware/cp/unit-02a40001.bin').read_bytes()
u = bytearray(raw)
CH, SL = 0x1250, 64

def mutate(slot, fn):
    off = CH + slot*SL
    vals = list(struct.unpack_from('<32h', u, off))
    new = [fn(v) for v in vals[:24]] + vals[24:]
    struct.pack_into('<32h', u, off, *new)

mutate(6, lambda v: max(-8192, min(8191, v*4)))
mutate(7, lambda v: max(-8192, min(8191, -v)))
mutate(8, lambda v: 0)

out = Path('../firmware/cp/unit-02a40001.tri_678.bin')
out.write_bytes(bytes(u))
print('slot6 x4, slot7 invert, slot8 zero; sha256', hashlib.sha256(bytes(u)).hexdigest())
for s in (6,7,8):
    print(s, list(struct.unpack_from('<32h', bytes(u), CH+s*SL))[:6])
