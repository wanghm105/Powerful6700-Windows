import capstone
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
before = bytes.fromhex('3f24007168030054a0ba009000f03d9100486138610000102088208b00001fd660008052f5ffff1740008052f3ffff1720008052f1ffff1700028052efffff17e0018052edffff1720028052ebffff1740028052e9ffff17a0008052e7ffff17a0018052e5ffff175f000039c0035fd6')
after = bytes.fromhex('3f2c007168030054800000100048613840000039c0035fd600030201100f1112050d13141f2003d51f2003d51f2003d5')
for name, blob in (('BEFORE (2.01 stock, 10 looks)', before), ('AFTER (FL2/FL3 patched, 12 looks)', after)):
    print('==', name)
    base = 0x3528804
    for ins in MD.disasm(blob, base):
        print('  %#010x  %-8s %s' % (ins.address, ins.mnemonic, ins.op_str))