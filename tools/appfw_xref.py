"""Offline xref helper for the dumped A6700 appFw.so (ELF64 AArch64).

Stage 1: locate target strings, resolve their virtual addresses, and find
data slots (RELATIVE relocations / raw pointers) that reference them.
"""
import os, struct, sys, json
from pathlib import Path

PATH = Path(os.environ.get('A6700_APPFW', sys.argv[1] if len(sys.argv) > 1 else 'firmware/appFw-2.00.so'))
if not PATH.exists():
    raise SystemExit(f'appFw image not found at {PATH}; pass a path or set A6700_APPFW')
data = PATH.read_bytes()

def sections(blob):
    shoff, = struct.unpack_from('<Q', blob, 0x28)
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', blob, 0x3a)
    raw = []
    for i in range(shnum):
        o = shoff + i * shentsize
        name, typ, flags, addr, off, size, link, info, align, entsize = struct.unpack_from('<IIQQQQIIQQ', blob, o)
        raw.append(dict(name=name, type=typ, flags=flags, addr=addr, off=off, size=size, entsize=entsize, link=link))
    str_off = raw[shstrndx]['off']
    for r in raw:
        end = blob.index(b'\0', str_off + r['name'])
        r['sec'] = blob[str_off + r['name']:end].decode()
    return raw

SECS = sections(data)
BY = {s['sec']: s for s in SECS}
for n in ('.text', '.rodata', '.data.rel.ro', '.data', '.rela.dyn', '.init_array'):
    s = BY[n]
    print(f"{n:14s} addr={s['addr']:#012x} off={s['off']:#010x} size={s['size']:#x} entsize={s['entsize']}")

def vaddr_of(off):
    for s in SECS:
        if s['type'] != 8 and s['size'] and s['off'] <= off < s['off'] + s['size']:
            return s['addr'] + (off - s['off']), s['sec']
    return None, None

TARGETS = [b'CAUTION_ID_SLOW_AND_QUICK_XAVC_TRANSFER_RATE_DISABLE_UNDER_200MBPS_MEDIA_SLOT1_MSG',
           b'CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_UNDER_100MBPS_MEDIA_SLOT1_MSG',
           b'T_CONFIRMED_LICENSE_TYPE_4K120P_NOT_AVAILABLE_FILE_FOMRAT_XAVC_HS_4K',
           b'SQ_REC_FRAME_RATE_XAVC_HS_4K_120P']
found = {}
for t in TARGETS:
    i = data.find(t)
    va, sec = vaddr_of(i)
    print(f'{t[:50]!r} file={i:#x} va={va:#x} sec={sec}')
    found[t.decode()] = dict(file=i, va=va, sec=sec)

# RELATIVE relocations: R_AARCH64_RELATIVE == 1027
rel = BY['.rela.dyn']
addends = {}
n = rel['size'] // 24
print('rela.dyn entries', n)
for i in range(n):
    o = rel['off'] + i * 24
    r_offset, r_info, r_addend = struct.unpack_from('<QQq', data, o)
    if (r_info & 0xffffffff) == 1027:
        addends.setdefault(r_addend, []).append(r_offset)
print('relative addends', len(addends))

for name, info in found.items():
    slots = addends.get(info['va'], [])
    raw_hits = []
    needle = struct.pack('<Q', info['va'])
    start = 0
    while True:
        j = data.find(needle, start)
        if j < 0:
            break
        raw_hits.append(j)
        start = j + 1
    print(f"{name[:44]}: reloc-slots={[hex(s) for s in slots]} raw8={[hex(h) for h in raw_hits[:8]]}")
