import struct, sys, re
sys.path.insert(0, 'tools')
import rela
d = open('../firmware/appFw-2.00.so','rb').read()
pairs = rela.relative_pairs()
slots = {}
for off, add in pairs:
    slots.setdefault(off, add)
def cstr(addr, limit=64):
    if not addr or not (0 < addr < len(d)): return None
    end = d.find(b'\x00', addr, addr+limit)
    if end < 0 or end == addr: return None
    raw = d[addr:end]
    try: s = raw.decode('utf-8')
    except Exception: return None
    if any(ord(ch) < 32 for ch in s): return None
    return s
rows = []
for off, add in pairs:
    if off + 0x28 > len(d): continue
    f = struct.unpack_from('<10I', d, off)
    if f[1] or f[2] != 4 or f[3] or f[6] != 1 or f[7] or f[8] or f[9]: continue
    if not (0x100 <= f[4] <= 0x20000): continue
    s = cstr(add)
    if not s: continue
    rows.append((off, f[4], s))
print('shaped records', len(rows))
rows.sort(key=lambda r: r[1])
seen = set()
for off, i, s in rows:
    key = (i, s)
    if key in seen: continue
    seen.add(key)
print('unique (id,name)', len(seen))
cand = {'ST','PT','NT','VV','VV2','FL','IN','SH','BW','SE','CC','CN','FL2','FL3','NN','NC','VVC'}
for off, i, s in rows:
    if s in cand:
        print('  LOOK? %#010x id=%#07x %r' % (off, i, s))
print('--- window around id 0x5c2')
for off, i, s in rows:
    if 0x5b8 <= i <= 0x5d2:
        print('  %#010x id=%#07x %r' % (off, i, s))