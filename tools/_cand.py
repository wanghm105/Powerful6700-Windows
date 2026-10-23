import re
from pathlib import Path
pat = re.compile(r"^(自定义\s*[1-9]|自定义外观.*|外观\s*[1-9]?|Creative.*|ST|PT|NT|VV2?|FL|IN|SH|BW|SE|[1-6](ST|FL|IN|SH|VV2|BW))$")
for name in ["string_simplifiedchinese.txt", "f-entries.txt"]:
    p = Path("../firmware/ui") / name
    if not p.exists():
        continue
    lines = []
    for line in p.read_text("utf-8").splitlines():
        rid, _, text = line.partition(" ")
        if pat.match(text):
            lines.append("%s %s" % (rid, text))
    out = Path("../firmware/ui") / ("_cand-" + name)
    out.write_text("\n".join(lines), "utf-8")
    print(name, len(lines))
