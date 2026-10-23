"""A6700 Jiritsu AdjustControl wire frames (corrected 2026-10-18).

Wire layout confirmed from libsencore.so 2.00:

    12-byte Senser header  (u32 size=4+N, u16 pFunc=0x40, u16 sequence, 4x u8)
    4-byte AdjustControl code (u16 category LE, u16 command LE)
    N-byte raw payload     (area, file_id, transfer_mode, file data)

There is no separate OSAL packet on the wire. libsencore copies the 4-byte code
into packet+0x24/+0x26, copies min(size-4, 0x124) payload bytes to packet+0x28,
runs the phase-1 DMM initialisation, and then automatically chains the phase-4
execute in the same frame. The 0x124 is the payload-area limit, not a packet.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

SENSER_HEADER_SIZE = 12
CODE_SIZE = 4
PFUNC_ADJUST_CONTROL = 0x0040
A6700_JIRITSU_CATEGORY = 0x1001
A6700_JIRITSU_SET_FILE_CODE = 0x4007     # low byte 0x07 -> JIRITSU_SET_FILE
A6700_JIRITSU_SET_FILE2_CODE = 0x4010    # low byte 0x10 -> JIRITSU_SET_FILE2
PAYLOAD_LIMIT = 0x124                    # packet+0x28 .. +0x14b

AREA_JIRITSU = 0x00
AREA_GLOBAL_MNT = 0x01
AREA_DMM = 0xFF
FILE_ID_LIB_JIT_SO = 0x02
TRANSFER_MODE_PLAIN = 0x00
TRANSFER_MODE_AES_CTR = 0x01


@dataclass
class SenserHeader:
    size: int
    pfunc: int
    sequence: int
    version: int = 0
    micon_type: int = 0
    offset_type: int = 0
    response: int = 0


def pack_senser_header(header: SenserHeader) -> bytes:
    return struct.pack("<IHHBBBB", header.size, header.pfunc, header.sequence,
                       header.version, header.micon_type, header.offset_type,
                       header.response)


def parse_senser_header(packet: bytes) -> SenserHeader:
    return SenserHeader(*struct.unpack_from("<IHHBBBB", packet, 0))


def jiritsu_aes_key() -> bytes:
    return hashlib.md5(b"jiritsu team" + b"\x00" * 4).digest()


def jiritsu_aes_iv() -> bytes:
    return bytes(range(16))


def aes_ctr_transform(data: bytes) -> bytes:
    """libCommuTalk AES-128-CTR; CTR is symmetric (host encrypts, camera decrypts)."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher = Cipher(algorithms.AES(jiritsu_aes_key()), modes.CTR(jiritsu_aes_iv()))
        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()
    except ImportError:
        pass
    try:
        from Crypto.Cipher import AES
        from Crypto.Util import Counter

        counter = Counter.new(128, initial_value=int.from_bytes(jiritsu_aes_iv(), "big"))
        return AES.new(jiritsu_aes_key(), AES.MODE_CTR, counter=counter).encrypt(data)
    except ImportError:
        pass
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-ctr", "-K", jiritsu_aes_key().hex(),
         "-iv", jiritsu_aes_iv().hex()],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return proc.stdout


def build_payload(area: int = AREA_JIRITSU,
                  file_id: int = FILE_ID_LIB_JIT_SO,
                  transfer_mode: int = TRANSFER_MODE_PLAIN,
                  data: bytes = b"") -> bytes:
    if area not in (AREA_JIRITSU, AREA_GLOBAL_MNT, AREA_DMM):
        raise ValueError(f"unsupported area: {area:#x}")
    if not 0 <= file_id <= 0xFF:
        raise ValueError("file_id must fit in one byte")
    if transfer_mode not in (TRANSFER_MODE_PLAIN, TRANSFER_MODE_AES_CTR):
        raise ValueError(f"unsupported transfer mode: {transfer_mode:#x}")
    body = data if transfer_mode == TRANSFER_MODE_PLAIN else aes_ctr_transform(data)
    return bytes([area, file_id, transfer_mode]) + body


def build_frame(payload: bytes, command: int = A6700_JIRITSU_SET_FILE2_CODE,
                sequence: int = 1, category: int = A6700_JIRITSU_CATEGORY,
                pfunc: int = PFUNC_ADJUST_CONTROL) -> bytes:
    """Build one complete wire frame: Senser header + code + raw payload."""
    body = category.to_bytes(2, "little") + (command & 0xFFFF).to_bytes(2, "little") + payload
    header = SenserHeader(size=len(body), pfunc=pfunc, sequence=sequence)
    return pack_senser_header(header) + body


def build_file_frame(data: bytes = b"", file_id: int = FILE_ID_LIB_JIT_SO,
                     area: int = AREA_JIRITSU,
                     transfer_mode: int = TRANSFER_MODE_PLAIN,
                     sequence: int = 1,
                     command: int = A6700_JIRITSU_SET_FILE_CODE) -> bytes:
    payload = build_payload(area, file_id, transfer_mode, data)
    return build_frame(payload, command=command, sequence=sequence)


def parse_frame(packet: bytes) -> dict[str, object]:
    header = parse_senser_header(packet)
    body = packet[SENSER_HEADER_SIZE:]
    category = int.from_bytes(body[0:2], "little")
    command = int.from_bytes(body[2:4], "little")
    payload = body[CODE_SIZE:]
    return {
        "size": header.size,
        "pfunc": header.pfunc,
        "sequence": header.sequence,
        "version": header.version,
        "response": header.response,
        "category": category,
        "command": command,
        "payload_len": len(payload),
        "area": payload[0] if payload else None,
        "file_id": payload[1] if len(payload) > 1 else None,
        "transfer_mode": payload[2] if len(payload) > 2 else None,
        "data": payload[3:],
    }


def self_test() -> None:
    # Canonical minimal frame from phase1-layout.md §0.2
    minimal = bytes.fromhex("070000004000010000000000" "0110" "1040" "000200")
    built = build_file_frame(data=b"", file_id=2, command=A6700_JIRITSU_SET_FILE2_CODE)
    assert built == minimal, (built.hex(), minimal.hex())
    parsed = parse_frame(built)
    assert (parsed["size"], parsed["pfunc"], parsed["sequence"]) == (7, 0x40, 1)
    assert (parsed["category"], parsed["command"]) == (0x1001, 0x4010)
    assert (parsed["area"], parsed["file_id"], parsed["transfer_mode"]) == (0, 2, 0)

    # 64-byte sample: area=0, file_id=0, N=0x43
    sample = bytes(range(64))
    frame = build_file_frame(data=sample, file_id=0, command=A6700_JIRITSU_SET_FILE2_CODE)
    assert len(frame) == SENSER_HEADER_SIZE + CODE_SIZE + 3 + 64 == 83
    assert frame[:4] == (4 + 0x43).to_bytes(4, "little")
    assert frame[12:16] == b"\x01\x10\x10\x40"
    assert frame[16:19] == b"\x00\x00\x00"
    assert frame[19:] == sample
    assert parse_frame(frame)["data"] == sample

    # SET_FILE uses 0x4007 but the low byte selects the same table entry family
    set_file = build_file_frame(data=b"", file_id=2, command=A6700_JIRITSU_SET_FILE_CODE)
    assert set_file[14:16] == b"\x07\x40"
    assert parse_frame(set_file)["command"] == 0x4007

    # AES-CTR round-trip
    encrypted = build_payload(transfer_mode=TRANSFER_MODE_AES_CTR, data=sample)
    assert aes_ctr_transform(encrypted[3:]) == sample
    print("packet_builder self-test passed (corrected wire format)")
    print(f"minimal frame: {minimal.hex()}")
    print(f"64-byte frame: {len(frame)} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--file", type=Path, help="file data to embed")
    parser.add_argument("--file-id", type=lambda v: int(v, 0), default=FILE_ID_LIB_JIT_SO)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--command", choices=("set-file", "set-file2"), default="set-file")
    parser.add_argument("--transfer-mode", choices=("plain", "aes"), default="plain")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.file:
        parser.print_help()
        return
    data = args.file.read_bytes()
    command = (A6700_JIRITSU_SET_FILE_CODE if args.command == "set-file"
               else A6700_JIRITSU_SET_FILE2_CODE)
    frame = build_file_frame(data, file_id=args.file_id,
                             transfer_mode=(TRANSFER_MODE_PLAIN if args.transfer_mode == "plain"
                                            else TRANSFER_MODE_AES_CTR),
                             sequence=args.sequence, command=command)
    if args.output:
        args.output.write_bytes(frame)
        print(f"wrote {len(frame)} bytes to {args.output}")
    else:
        print(frame.hex())
    if len(frame) - SENSER_HEADER_SIZE - CODE_SIZE > PAYLOAD_LIMIT:
        print(f"warning: payload exceeds {PAYLOAD_LIMIT:#x}; needs multi-frame/DMA continuation")


if __name__ == "__main__":
    main()
