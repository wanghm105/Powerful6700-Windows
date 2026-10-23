import re
from pathlib import Path
data = Path("../firmware/appFw-2.00.so").read_bytes()
def strings(buf, minlen=6):
    for m in re.finditer(rb"[ -~]{%d,}" % minlen, buf):
        yield m.start(), m.group().decode("ascii", "replace")
keys = ("CREATIVE_LOOK", "CREATIVE_BOX", "LOOKNAME", "LOOK_NAME", "CUSTOM_LOOK", "CREATIVE_STYLE")
out = []
for off, text in strings(data):
    if any(k in text for k in keys):
        out.append("%08x %s" % (off, text))
Path("../firmware/ui/_appfw-lookstrings.txt").write_text("\n".join(out), "utf-8")
print(len(out))
