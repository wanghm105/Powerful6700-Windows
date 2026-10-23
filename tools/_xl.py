from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
pairs = [
 ('0x32345a', '48f60c5b', '49f2804b'),
 ('0x323464', 'c0f2101b', 'c0f2201b'),
 ('0x323d82', '48f60c51', '49f28041'),
 ('0x323d8a', 'c0f21011', 'c0f22011'),
 ('0x9cf436', '48f60c51', '49f28041'),
 ('0x9cf43e', 'c0f21011', 'c0f22011'),
 ('0x3231da', '42f2805f', '49f6f810'),
 ('0x3231de', 'c0f2e000', 'c0f22010'),
]
for off, b, a in pairs:
    print(off, 'BEFORE', [(i.mnemonic, i.op_str) for i in md.disasm(bytes.fromhex(b), 0x1000)])
    print(off, 'AFTER ', [(i.mnemonic, i.op_str) for i in md.disasm(bytes.fromhex(a), 0x1000)])
