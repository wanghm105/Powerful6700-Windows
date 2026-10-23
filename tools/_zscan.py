from pathlib import Path
import zlib

b = Path('../firmware/appFw-2.00.so').read_bytes()
n = len(b)
ok = 0
found = []
keys = (b'VV2', b'Sepia', b'Standard', b'FL2', b'FILM', b'Creative', b'creative')
i = 0
tried = 0
while i < n - 2:
    if b[i] == 0x78 and b[i+1] in (0x01, 0x5e, 0x9c, 0xda):
        tried += 1
        try:
            d = zlib.decompressobj()
            out = d.decompress(b[i:i+262144], 200000)
            if len(out) > 64 and d.eof is False or d.eof:
                pass
            if len(out) > 64:
                ok += 1
                if any(k in out for k in keys):
                    found.append((i, len(out), [k for k in keys if k in out]))
        except Exception:
            pass
    i += 1
print('tried', tried, 'ok', ok, 'found', found[:20])
