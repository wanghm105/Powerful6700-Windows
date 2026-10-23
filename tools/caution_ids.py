"""Dump the caution/message registry table at 0x4958148 with ids."""
import struct, sys
from pathlib import Path
sys.path.insert(0, 'tools')
import rela as R
DATA = R.DATA
def s(addr, maxlen=100):
    if not (0x3000000 <= addr < len(DATA)): return ''
    end = DATA.find(b'\0', addr)
    if 0 < end - addr < maxlen:
        return DATA[addr:end].decode('latin1', 'replace')
    return ''
def dump_table(base=0x4958148, limit=1200):
    out = []
    prev_id = None
    for i in range(limit):
        off = base + i*16
        name, packed = struct.unpack_from('<QQ', DATA, off)
        text = s(name)
        if not text:
            break
        ident = packed & 0xFFFFFFFF
        ln = packed >> 32
        out.append((ident, ln, name, text))
        if prev_id is not None and ident != prev_id + 1:
            print(f'# id discontinuity at {off:#x}: {prev_id:#x} -> {ident:#x}')
        prev_id = ident
    return out
rows = dump_table()
print('entries', len(rows))
want = ('UNDER_600MBPS', 'UNDER_400MBPS', 'UNDER_1350MBPS', '4K120', 'XAVC_S_I')
for ident, ln, name, text in rows:
    if any(w in text for w in want) and 'CAUTION_ID' in text:
        print(f'id={ident:#06x} len={ln:#04x} {text}')
