from pathlib import Path
import re
b = Path('../firmware/parts/nflasha15-head.bin').read_bytes()
print('size', len(b), 'head', b[:64].hex())
print('ascii head', repr(b[:128]))
# look for filesystem magics
for magic, name in ((b'\xeb\x3c\x90','FAT'), (b'hsqs','squashfs'), (b'\x27\x05\x19\x56','uImage'), (b'ANDROID!','android'),
                    (b'\x85\x19','cramfs'), (b'UBI#','ubi'), (b'CrAU','update'), (b'BZ','bzip'), (b'\x1f\x8b','gzip')):
    print(name, b.find(magic))
strs = re.findall(rb'[ -~]{6,}', b)
print('strings sample:', [s.decode() for s in strs[:40]])
