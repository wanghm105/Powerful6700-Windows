import struct, sys
sys.path.insert(0, 'tools')
from rela import DATA
RELA_OFF, RELA_SIZE = 0xe440, 0x1756dd0
N = RELA_SIZE // 24
by_addend = {}
for i in range(N):
    off, info, add = struct.unpack_from('<QQq', DATA, RELA_OFF + i*24)
    if (info & 0xffffffff) == 1027:
        by_addend.setdefault(add, []).append(off)
def s_at(a, maxlen=90):
    if not (0 < a < len(DATA)): return ''
    e = DATA.find(b'\x00', a)
    if e < 0 or e - a > maxlen: return ''
    try: return DATA[a:e].decode('ascii')
    except UnicodeDecodeError: return ''
for name in ['sequence_notify_update_display_string_list_creative_look_image_style','to_remote_event_creative_look']:
    a = DATA.find(name.encode())
    print('==', name, hex(a), '=> slots', [hex(x) for x in by_addend.get(a, [])][:6])
    for slot in by_addend.get(a, [])[:2]:
        base = slot & ~0xf
        for k in range(-4, 6):
            off = base + k*8
            v = struct.unpack_from('<Q', DATA, off)[0]
            print('    %#x %#x %s' % (off, v, s_at(v)))