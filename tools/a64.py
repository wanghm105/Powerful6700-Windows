"""Ad-hoc AArch64 disassembly helper for appFw-2.00.so.

Usage: python tools/dis.py <vaddr_hex> [bytes_before] [bytes_after]
       python tools/dis.py --func <vaddr_hex>
"""
from __future__ import annotations
import sys
from pathlib import Path
import capstone

FW = Path(__file__).resolve().parent.parent.parent / 'firmware' / 'appFw-2.00.so'
DATA = FW.read_bytes()
TEXT_OFF = 0x176d090
TEXT_END = TEXT_OFF + 0x1ec5c30
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
MD.detail = True


def disasm(start: int, stop: int):
    return list(MD.disasm(DATA[start:stop], start))


def show(start: int, stop: int) -> None:
    for ins in disasm(start, stop):
        print(f'{ins.address:#010x}  {ins.bytes.hex():<8} {ins.mnemonic:<8} {ins.op_str}')


def back_to_prologue(addr: int, limit: int = 0x3000) -> int:
    """Walk backwards to the last ret/bti boundary."""
    start = max(TEXT_OFF, addr - limit)
    best = start
    for item in disasm(start, addr):
        if item.mnemonic in ('ret', 'bti') or (item.mnemonic == 'br' and item.op_str == 'x30'):
            best = item.address + 4
    return best


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--func':
        addr = int(args[1], 16)
        start = back_to_prologue(addr)
        print(f'# function containing {addr:#x} starts near {start:#x}')
        show(start, addr + 0x300)
    else:
        addr = int(args[0], 16)
        before = int(args[1], 16) if len(args) > 1 else 0x100
        after = int(args[2], 16) if len(args) > 2 else 0x100
        show(addr - before, addr + after)
