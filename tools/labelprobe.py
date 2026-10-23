"""Probe the record table around 0x537def0 that maps id -> name string."""
import struct, sys
sys.path.insert(0, 'tools')
import rela
d = open('../firmware/appFw-2.00.so', 'rb').read()
pairs = dict(rela.relative_pairs())

def cstr(addr, limit=64):
    if not addr or not (0 < addr < len(d)): return None
    end = d.find(b'\x00', addr, addr + limit)
    if end < 0: return None
    raw = d[addr:end]
    try: s = raw.decode('utf-8')
    except Exception: return None
    if not s or any(ord(ch) < 32 for ch in s): return None
    return s

STRIDE = 0x28
def rec(addr):
    if addr < 0 or addr + STRIDE > len(d): return None
    f = struct.unpack_from('<10I', d, addr)
    s = cstr(pairs.get(addr))
    return f, s

lo, hi = 0x537c000, 0x537f000
print('scan %#x..%#x' % (lo, hi))
for a in range(lo, hi, STRIDE):
    f, s = rec(a)
    if s is None:
        # also show records whose pointer is stored as absolute address (non-relocated)
        f2 = struct.unpack_from('<10I', d, a)
        cand = cstr(f2[0]) if 0 < f2[0] < len(d) else None
        if cand is None: continue
        s = cand
    print('%#010x id=%#07x f1=%d f2=%d f3=%d f5=%#x f6=%d %r' % (a, f[4], f[1], f[2], f[3], f[5], f[6], s))
