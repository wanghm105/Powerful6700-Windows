"""Reference helpers for appFw-2.00.so: adrp page index + targeted disassembly."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import capstone

FW = Path(__file__).resolve().parent.parent.parent / 'firmware' / 'appFw-2.00.so'
DATA = FW.read_bytes()
TEXT_OFF = 0x176d090
TEXT_SIZE = 0x1ec5c30
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
MD.detail = True

_words = np.frombuffer(DATA, dtype='<u4', count=TEXT_SIZE // 4, offset=TEXT_OFF)


def _build_page_index():
    w = _words
    is_adrp = (w & 0x9F000000) == 0x90000000
    idx = np.nonzero(is_adrp)[0]
    addrs = TEXT_OFF + idx.astype(np.int64) * 4
    ww = w[idx].astype(np.int64)
    immlo = (ww >> 29) & 3
    immhi = (ww >> 5) & 0x7FFFF
    imm = (immhi << 2) | immlo
    imm = np.where(imm >= (1 << 20), imm - (1 << 21), imm)
    pages = (addrs & ~0xFFF) + (imm << 12)
    index = {}
    for page, addr in zip(pages.tolist(), addrs.tolist()):
        index.setdefault(page, []).append(addr)
    return index


PAGE_INDEX = _build_page_index()


def adrp_sites(target: int) -> list[int]:
    return PAGE_INDEX.get(target & ~0xFFF, [])


def disasm(start: int, stop: int):
    return list(MD.disasm(DATA[start:stop], start))


def show(start: int, stop: int) -> None:
    for ins in disasm(start, stop):
        print(f'{ins.address:#010x}  {ins.bytes.hex():<8} {ins.mnemonic:<8} {ins.op_str}')


def xrefs(target: int, window_before: int = 0x20, window_after: int = 0x40):
    """Yield (site, disassembly) for every adrp+add pair materialising target."""
    out = []
    for site in adrp_sites(target):
        chunk = disasm(site, site + window_after)
        hit = False
        for ins in chunk:
            if ins.mnemonic == 'add' and len(ins.operands) >= 3:
                try:
                    if ins.operands[2].imm == (target & 0xFFF):
                        hit = True
                        break
                except Exception:
                    pass
            if ins.mnemonic == 'add' and target & 0xFFF == 0:
                hit = True
                break
        if hit:
            out.append(site)
    return out


if __name__ == '__main__':
    cmd = sys.argv[1]
    tgt = int(sys.argv[2], 16)
    if cmd == 'sites':
        for s in adrp_sites(tgt):
            print(hex(s))
    elif cmd == 'xref':
        width = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x30
        for s in xrefs(tgt):
            print(f'--- site {s:#x}')
            show(s, s + width)
    else:
        raise SystemExit('usage: a64xref.py sites|xref <hex> [width]')
