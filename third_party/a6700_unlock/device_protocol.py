"""Small fixed-profile requests; no arbitrary paths, addresses or full backups."""
import struct

REQUEST = struct.Struct("<4sI16s32s")
RESPONSE = struct.Struct("<4sI16siIIII")
ERRORS = {1: "preimage changed", 2: "invalid request", 3: "cannot open partition",
          4: "short/read failure", 5: "write failure", 6: "fsync failure", 7: "readback mismatch",
          8: "rollback incomplete"}


class DeviceError(RuntimeError):
    pass


def request(profile, nonce, before=None, after=None):
    if len(nonce) != 16:
        raise ValueError("Nonce must be 16 bytes")
    writing = before is not None
    header = REQUEST.pack(b"A67W" if writing else b"A67Q", 1, nonce, bytes.fromhex(profile.digest))
    if not writing:
        return header
    count = len(profile.entries)
    if after is None or len(before) != count or len(after) != count:
        raise ValueError("Every sparse entry requires a before/after image")
    if any(len(s) != 512 for s in before + after):
        raise ValueError("Every request sector must be 512 bytes")
    for row, old, new, mask in zip(profile.entries, before, after, profile.masks(writable_only=True)):
        if any(a != b and not (mask[i // 8] & (1 << (i % 8))) for i, (a, b) in enumerate(zip(old, new))):
            raise ValueError("Request changes bytes outside available catalog-owned fields")
    return header + b"".join(a + b for a, b in zip(before, after))


def response(data, nonce, expected_count):
    if len(data) < RESPONSE.size:
        raise DeviceError("Truncated native response")
    magic, version, returned, status, count, failed, touched, flags = RESPONSE.unpack_from(data)
    if magic != b"A67R" or version != 1 or returned != nonce:
        raise DeviceError("Invalid/stale native result; request nonce does not match")
    if count != expected_count or len(data) != RESPONSE.size + count * 512:
        raise DeviceError("Native result length/count mismatch")
    return dict(status=status, error=ERRORS.get(status, "unknown native error") if status else None,
                failed_index=None if failed == 0xffffffff else failed,
                touched=touched, rolled_back=bool(flags & 1),
                sectors=[data[RESPONSE.size + i * 512:RESPONSE.size + (i + 1) * 512] for i in range(count)])
