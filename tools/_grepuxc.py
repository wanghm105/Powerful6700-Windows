from pathlib import Path
rows = []
for line in Path("../firmware/ui/string_simplifiedchinese.txt").read_text("utf-8").splitlines():
    rid, _, text = line.partition(" ")
    rows.append((rid, text))
keys = ["标准", "人像", "中性", "鲜明", "亮丽", "胶片", "复古", "通透", "黑白", "棕褐", "外观", "自定义", "风格", "创意"]
out = []
for rid, text in rows:
    if len(text) <= 12 and any(k in text for k in keys):
        out.append("%s %s" % (rid, text))
Path("../firmware/ui/_look-names.txt").write_text("\n".join(out), "utf-8")
print(len(out))
