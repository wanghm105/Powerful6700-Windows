import struct, sys
sys.path.insert(0, 'tools')
import rela
d = open('../firmware/appFw-2.00.so','rb').read()
pairs = dict(rela.relative_pairs())
def cstr(addr, limit=40):
    if not addr or not (0 < addr < len(d)): return None
    end = d.find(b'\x00', addr, addr+limit)
    if end < 0: return None
    raw = d[addr:end]
    try: s = raw.decode('utf-8')
    except Exception: return None
    if not s or any(ord(ch) < 32 for ch in s): return None
    return s
STRIDE = 0x28
def shaped(addr):
    if addr < 0 or addr + STRIDE > len(d): return False
    f = struct.unpack_from('<10I', d, addr)
    ptr = pairs.get(addr)
    s = cstr(ptr) if ptr else None
    return bool(s) and f[1] == 0 and f[2] == 4 and f[3] == 0 and f[6] == 1 and f[7] == 0 and f[8] == 0 and f[9] == 0 and 0x100 <= f[4] <= 0x20000
start = 0x537df68
while shaped(start - STRIDE): start -= STRIDE
end = start
while shaped(end): end += STRIDE
print('table %#x..%#x records %d' % (start, end, (end - start)//STRIDE))
for a in range(start, end, STRIDE):
    f = struct.unpack_from('<10I', d, a)
    print('  %#010x id=%#07x  %r' % (a, f[4], cstr(pairs.get(a))))