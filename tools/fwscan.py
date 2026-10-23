"""Small scanners over appFw-2.00.so used while mapping the A6700 media-speed model.

Subcommands
  strings <regex>          grep printable strings (latin-1 safe) with file offsets
  slots <hexaddr>          list 8-byte slots holding that exact address, with neighbourhood
  movz <heximm>            MOVZ wN, #imm sites (32-bit), as vaddrs
  cmp <heximm>             CMP wN, #imm sites (imm12), as vaddrs
  warnrate                 list CAUTION_ID_*TRANSFER_RATE* strings
"""
from __future__ import annotations
import re
import struct
import sys
from pathlib import Path
import numpy as np

FW = Path(__file__).resolve().parent.parent.parent / 'firmware' / 'appFw-2.00.so'
DATA = FW.read_bytes()
TEXT_OFF = 0x176d090
TEXT_SIZE = 0x1ec5c30
_WORDS = np.frombuffer(DATA, dtype='<u4', count=TEXT_SIZE // 4, offset=TEXT_OFF)


def printable(addr: int, maxlen: int = 100) -> str:
    if not (0x3000000 <= addr < len(DATA)):
        return ''
    end = DATA.find(b'\0', addr)
    if end < 0 or end - addr > maxlen:
        return ''
    try:
        return DATA[addr:end].decode('ascii')
    except UnicodeDecodeError:
        return ''


def cmd_strings(pattern: str) -> None:
    rx = re.compile(pattern.encode())
    seen = {}
    for m in rx.finditer(DATA):
        text = m.group().decode('latin1')
        if text not in seen:
            seen[text] = m.start()
    for text, off in seen.items():
        print(f'{off:#010x} {text}')


def cmd_slots(target: int) -> None:
    needle = struct.pack('<Q', target)
    start = 0
    while True:
        hit = DATA.find(needle, start)
        if hit < 0:
            return
        start = hit + 1
        print(f'--- slot {hit:#x} holds {target:#x} ({printable(target)})')
        for off in range(hit - 0x18, hit + 0x28, 8):
            value, = struct.unpack_from('<Q', DATA, off)
            marker = ' <-code' if TEXT_OFF <= value < TEXT_OFF + TEXT_SIZE else ''
            print(f'    {off:#010x} {value:#018x} {printable(value)}{marker}')


def _movz_sites(imm: int) -> list[int]:
    base = (0x52800000 | ((imm & 0xFFFF) << 5)) & 0xFFFFFFE0
    idx = np.nonzero((_WORDS & 0xFFFFFFE0) == base)[0]
    return [TEXT_OFF + int(i) * 4 for i in idx]


def _cmp_sites(imm: int) -> list[int]:
    m = ((_WORDS & 0xFFC00000) == 0x71000000) & (((_WORDS >> 10) & 0xFFF) == (imm & 0xFFF))
    return [TEXT_OFF + int(i) * 4 for i in np.nonzero(m)[0]]


def cmd_movz(imm: int) -> None:
    for site in _movz_sites(imm):
        print(f'{site:#010x}')


def cmd_cmp(imm: int) -> None:
    for site in _cmp_sites(imm):
        print(f'{site:#010x}')


def cmd_warnrate() -> None:
    rx = re.compile(rb'CAUTION_ID_[A-Z0-9_]{4,90}')
    seen = {}
    for m in rx.finditer(DATA):
        text = m.group().decode()
        if 'TRANSFER_RATE' in text:
            seen.setdefault(text, m.start())
    for text, off in sorted(seen.items(), key=lambda kv: kv[1]):
        print(f'{off:#010x} {text}')


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == 'strings':
        cmd_strings(args[0])
    elif cmd == 'slots':
        cmd_slots(int(args[0], 16))
    elif cmd == 'movz':
        cmd_movz(int(args[0], 16))
    elif cmd == 'cmp':
        cmd_cmp(int(args[0], 16))
    elif cmd == 'warnrate':
        cmd_warnrate()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
