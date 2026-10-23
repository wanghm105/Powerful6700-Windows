"""Query .rela.dyn of appFw-2.00.so: which globals hold a given address."""
from __future__ import annotations
import struct, sys
from pathlib import Path

FW = Path(__file__).resolve().parent.parent.parent / 'firmware' / 'appFw-2.00.so'
DATA = FW.read_bytes()
RELA_OFF, RELA_SIZE = 0xe440, 0x1756dd0
N = RELA_SIZE // 24
R_AARCH64_RELATIVE = 1027


def relative_pairs():
    out = []
    for i in range(N):
        off, info, add = struct.unpack_from('<QQq', DATA, RELA_OFF + i*24)
        if (info & 0xffffffff) == R_AARCH64_RELATIVE:
            out.append((off, add))
    return out


def globals_holding(target: int):
    return [off for off, add in relative_pairs() if add == target]


if __name__ == '__main__':
    pairs = relative_pairs()
    print('relative entries', len(pairs))
    for arg in sys.argv[1:]:
        t = int(arg, 16)
        hits = [off for off, add in pairs if add == t]
        print(f'{t:#x}: {len(hits)} slot(s) -> {[hex(h) for h in hits[:10]]}')
