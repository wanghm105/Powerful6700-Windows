"""按 docs/looks-profile.json 一次性写入四个自定义外观（幂等，可反复执行）。

用法：
  python tools/looks_apply.py --dry-run
  python tools/looks_apply.py --confirm yes-write

profile 里每条 look = {name, menu, bank, base, factor, pairs:[{index, factor}]}，
其中 base 是出厂副本里的基底 bank（支持 "4+14" 这类合成），pairs 覆写 12 组
(Cb,Cr) 里指定组的系数。写入前会把整单元读出来做基线，写完回读比对。
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))

import look_write  # noqa: E402

DEFAULT_PROFILE = ROOT / "docs" / "looks-profile.json"


def specs_from(profile: dict) -> list[str]:
    out = []
    for item in profile["looks"]:
        spec = "%s=%d:%s:%.4f" % (item["name"], int(item["bank"]), str(item["base"]), float(item["factor"]))
        pairs = ",".join("%d*%.4f" % (int(p["index"]), float(p["factor"])) for p in item.get("pairs") or [])
        if pairs:
            spec += "@" + pairs
        out.append(spec)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--confirm", default="")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args(argv)

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    specs = specs_from(profile)
    print("profile: %s" % args.profile)
    for item, spec in zip(profile["looks"], specs):
        print("  %-3s %-22s -> %s" % (item["name"], item.get("menu", ""), spec))
    if args.dry_run:
        return 0
    if args.confirm != "yes-write":
        print("需要 --confirm yes-write")
        return 2
    cli = ["--confirm", "yes-write", "--timeout", str(args.timeout)]
    for spec in specs:
        cli += ["--look", spec]
    return look_write.main(cli)


if __name__ == "__main__":
    raise SystemExit(main())
