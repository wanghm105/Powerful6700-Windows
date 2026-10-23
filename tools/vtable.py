import struct, sys
sys.path.insert(0, 'tools')
from rela import DATA
RELA_OFF, RELA_SIZE = 0xe440, 0x1756dd0
N = RELA_SIZE // 24
pairs = []
by_addend = {}
for i in range(N):
    off, info, add = struct.unpack_from('<QQq', DATA, RELA_OFF + i*24)
    if (info & 0xffffffff) == 1027:
        pairs.append((off, add))
        by_addend.setdefault(add, []).append(off)
def s_at(a, maxlen=100):
    if not (0 < a < len(DATA)): return ''
    e = DATA.find(b'\x00', a)
    if e < 0 or e - a > maxlen: return ''
    try: return DATA[a:e].decode('ascii')
    except UnicodeDecodeError: return ''
name = sys.argv[1] if len(sys.argv) > 1 else 'N5model68sequence_notify_update_display_string_list_creative_look_image_styleE'
na = DATA.find(name.encode())
print('name str at', hex(na))
slots = by_addend.get(na, []) + by_addend.get(na | 1, [])
print('name ptr slots (typeinfo+8):', [hex(s) for s in slots][:8])
for s in slots[:4]:
    ti = s - 8
    print('  typeinfo candidate', hex(ti), 'vptr=', hex(struct.unpack_from('<Q', DATA, ti)[0]))
    vt = by_addend.get(ti, [])
    print('    vtable ptr slots (addend==typeinfo):', [hex(v) for v in vt][:8])
    for v in vt[:4]:
        start = v + 8
        print('    vtable at', hex(start))
        for k in range(8):
            val = struct.unpack_from('<Q', DATA, start + k*8)[0]
            print('      [%d] %#x %s' % (k, val, s_at(val, 60)))