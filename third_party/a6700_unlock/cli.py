"""Four-entry user menu, integrated device operations and offline diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .catalog import CatalogError, load_catalog
from .planner import InputError, analyze
from .backup import list_backups, load_backup
from .device_profile import load_device_profile
from .device_protocol import DeviceError
from .operations import execute, execute_backup, execute_restore
from . import preparation


def parser():
    p = argparse.ArgumentParser(description="A6700 功能解锁／关闭与功能状态备份工具")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="查看一期功能及兼容范围")
    commands.add_parser("menu", help="打开四入口操作菜单")
    commands.add_parser("doctor", help="检查本机环境与载荷，不访问相机")
    prepare_cmd = commands.add_parser("prepare", help="本机检查与相机准备向导，不访问相机")
    prepare_cmd.add_argument("--interactive", action="store_true", help="逐步确认相机设置与接线")
    prepare_cmd.add_argument("--confirm", action="append", choices=preparation.STEP_IDS, default=[],
                             help="人工确认指定准备项；不会跳过环境或固件预检")
    license_cmd = commands.add_parser("license", help="查看本地许可证及第三方归属，不访问相机")
    license_options = license_cmd.add_mutually_exclusive_group()
    license_options.add_argument("--full", action="store_true", help="显示 GPL-3.0 全文")
    license_options.add_argument("--third-party", action="store_true", help="显示第三方归属")
    device = commands.add_parser("device", help="通过 USB 检查、按功能解锁／关闭、备份或恢复")
    device.add_argument("action", choices=("inspect", "unlock", "close", "backup", "restore"))
    device.add_argument("--dry-run", action="store_true", help="只做目标预检，不写入功能修改或备份文件")
    device.add_argument("--state-dir", type=Path, help="本机操作记录目录（不是全盘备份）")
    device.add_argument("--backup-dir", type=Path,
                        help="功能状态备份目录；默认 ~/Documents/A6700 Backups")
    device.add_argument("--backup", type=Path,
                        help="要恢复的 .a6700backup 文件；省略时使用备份目录中最新一份")
    device.add_argument("--feature", action="append", default=None,
                        help="只操作指定功能，可重复；功能 ID 见 catalog 输出")
    device.add_argument("--all-missing", action="store_true",
                        help="只补齐当前未解锁的功能（仅 unlock；与 --feature 互斥）")
    device.add_argument("--no-capture", action="store_true", help="macOS 已手动接管接口时使用")
    device.add_argument("--confirm", action="append", choices=preparation.STEP_IDS, default=[],
                        help="非交互使用时逐项确认准备状态，每次操作重新声明")
    device.add_argument("--json", action="store_true", help="输出机器可读报告")
    backups_cmd = commands.add_parser("backups", help="列出本机功能状态备份，不访问相机")
    backups_cmd.add_argument("--backup-dir", type=Path,
                             help="功能状态备份目录；默认 ~/Documents/A6700 Backups")
    backups_cmd.add_argument("--json", action="store_true", help="输出机器可读报告")
    for name in ("inspect", "plan"):
        cmd = commands.add_parser(name, help="只读识别本地镜像" if name == "inspect" else "生成离线修改计划")
        cmd.add_argument("--app", required=True, type=Path, help="已解密的 appFw.so 常规文件")
        cmd.add_argument("--wbi", required=True, type=Path, help="已解密且提取为已知长度的 WBI 内容文件")
        cmd.add_argument("--cpapp", type=Path,
                         help="与固件同源的 nflasha8 分区镜像；包含 CP 字段时必需")
        if name == "plan":
            cmd.add_argument("--action", choices=("unlock", "close"), required=True)
        cmd.add_argument("--output", type=Path, help="JSON 结果，仅创建新文件，不覆盖现有文件")
    return p


def _summary(result):
    labels = {"completed": "写入和独立回读通过，请关机重开验收功能", "no-op": "已处于目标状态，无需修改",
              "blocked": "兼容性检查未通过，未执行设备操作", "inspected": "目标读取与检查完成",
              "dry-run": "预检完成，未写入功能修改", "rolled-back": "本次操作失败，已回退并回读确认",
              "rejected": "写前检查拒绝了本次修改", "uncertain": "通信中断，写入结果待核实，勿盲目重试",
              "recovery-required": "回退未能确认，请保留操作记录", "error": "操作未完成",
              "verification-failed": "独立回读未通过，请保留操作记录", "cancelled": "操作已取消",
              "backup-completed": "功能状态备份已保存（稀疏，不是整机镜像）",
              "restored": "已从功能状态备份恢复，并通过独立回读"}
    print(labels.get(result.get("status"), result.get("status")))
    if result.get("error"):
        print("原因：" + result["error"])
    plan = result.get("plan", {})
    features = result.get("final_features", result.get("features", plan.get("features", [])))
    states = {"enabled": "已解锁", "disabled": "未解锁", "partial": "部分解锁", "unknown": "未知"}
    if features:
        print("回读状态：" if "final_features" in result else "预检识别：")
    for feature in features:
        print(f"  {feature['name']}：{states.get(feature['state'], feature['state'])}")
    if plan.get("issues"):
        print(f"  {len(plan['issues'])} 处内容／结构不匹配；具体位置见操作记录。")
    if result.get("backup_path"):
        print("备份文件：" + result["backup_path"])
    if result.get("backup_sha256"):
        print("备份 SHA-256：" + result["backup_sha256"])
    if result.get("run_directory"):
        print("操作记录：" + result["run_directory"])
    if result.get("cleanup_warning"):
        print(result["cleanup_warning"])
    if result.get("record_warning"):
        print(result["record_warning"])


def _device(args, catalog):
    profile = load_device_profile(catalog)
    progress_stream = sys.stderr
    progress = lambda message: print(message, file=progress_stream, flush=True)
    backup = None
    features = None
    if args.action in ("unlock", "close", "restore"):
        if getattr(args, "all_missing", False) and getattr(args, "feature", None):
            raise DeviceError("--all-missing 与 --feature 不能同时使用")
        if getattr(args, "all_missing", False):
            if args.action != "unlock":
                raise DeviceError("--all-missing 仅用于 unlock")
            features = "missing"
        elif getattr(args, "feature", None):
            features = args.feature
    if args.action == "restore":
        source = args.backup
        if source is None:
            rows = list_backups(args.backup_dir)
            if not rows:
                print("本机没有可用的功能状态备份。请先执行一次备份，或用 --backup 指定文件。")
                return 2
            source = Path(rows[0]["path"])
        # Validate the local archive before connecting to the camera.
        backup = load_backup(source, profile)
    prepared = preparation.guide(profile, getattr(args, "confirm", ()),
                                 interactive=sys.stdin.isatty(), emit=progress)
    if not prepared["ready"]:
        if args.json:
            print(json.dumps(prepared, ensure_ascii=False, indent=2))
        else:
            print("尚未完成前置准备，没有连接维护通道。请按上述提示处理后重新开始。")
        return 2
    from .usb.backend import UsbBackend
    backend = UsbBackend(profile, progress, capture=not args.no_capture)
    if args.action == "backup":
        result = execute_backup(profile, backend, args.backup_dir, args.state_dir,
                                progress, args.dry_run)
    elif args.action == "restore":
        result = execute_restore(profile, backend, backup, args.state_dir,
                                 progress, args.dry_run, features)
    else:
        result = execute(profile, backend, args.action, args.state_dir, progress,
                         args.dry_run, features)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _summary(result)
    return 0 if result["status"] in ("completed", "no-op", "inspected", "dry-run",
                                     "backup-completed", "restored") else 2


def _menu_device_args(action, backup=None):
    return argparse.Namespace(action=action, state_dir=None, backup_dir=None,
                              backup=backup, no_capture=False, dry_run=False, json=False)


def _choose_backup():
    rows = list_backups()
    if not rows:
        print("本机还没有功能状态备份；请先选择 1 创建备份。")
        return None
    print("\n本机功能状态备份（最新在前）：")
    for number, row in enumerate(rows[:20], 1):
        states = "，".join(f"{f['name']}={f['state']}" for f in row.get("features", []))
        print(f"  {number}. {row['created_at']}  {row['id']}")
        if states:
            print("     " + states)
    try:
        raw = input("选择要恢复的备份编号（直接回车取消）：").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return None
    try:
        index = int(raw)
    except ValueError:
        print("请输入列表中的编号。")
        return None
    if not 1 <= index <= min(len(rows), 20):
        print("编号超出范围。")
        return None
    return Path(rows[index - 1]["path"])


def menu(catalog):
    if not sys.stdin.isatty():
        parser().print_help()
        return 0
    startup = preparation.assess(load_device_profile(catalog))
    preparation.show(startup)
    print("准备项未确认时，设备操作会先进入向导；环境或固件不匹配会停止。")
    while True:
        print("\nA6700 2.00 功能工具（开发测试版，只读预检已验证，写入闭环待验收）"
              "\n1. 备份当前功能状态（稀疏，约 126 KB，不是整机镜像）"
              "\n2. 解锁全部功能（或使用 device unlock --feature 选择）"
              "\n3. 关闭全部功能（或使用 device close --feature 选择）"
              "\n4. 从功能状态备份恢复"
              "\nD. 环境检查    L. 许可证    0. 退出")
        print("Copyright (C) 2026 A6700 Unlock contributors · GPL-3.0-only · 无担保")
        try:
            choice = input("选择操作：").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == "0":
            return 0
        if choice == "1":
            try:
                _device(_menu_device_args("backup"), catalog)
            except (DeviceError, OSError, ValueError) as exc:
                print("无法开始：" + str(exc))
        elif choice == "4":
            source = _choose_backup()
            if source is not None:
                try:
                    _device(_menu_device_args("restore", source), catalog)
                except (DeviceError, OSError, ValueError) as exc:
                    print("无法开始：" + str(exc))
        elif choice == "l":
            from .licensing import display
            display()
        elif choice == "d":
            from .doctor import diagnose
            result = diagnose(load_device_profile(catalog))
            for row in result["checks"]:
                print(f"{'✓' if row['ok'] else '✗'} {row['name']}：{row['detail']}")
        elif choice in ("2", "3"):
            try:
                _device(_menu_device_args("unlock" if choice == "2" else "close"), catalog)
            except (DeviceError, OSError, ValueError) as exc:
                print("无法开始：" + str(exc))
        else:
            print("请输入 1、2、3、4、D、L 或 0。")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["menu"]
    args = parser().parse_args(argv)
    try:
        if args.command == "license":
            from .licensing import display
            display(args.full, args.third_party)
            return 0
        catalog = load_catalog()
        if args.command == "menu":
            return menu(catalog)
        if args.command == "device":
            return _device(args, catalog)
        if args.command == "backups":
            rows = list_backups(args.backup_dir)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            elif not rows:
                print("本机没有可用的功能状态备份。")
            else:
                for row in rows:
                    states = "，".join(f"{f['name']}={f['state']}" for f in row.get("features", []))
                    print(f"{row['created_at']}  {row['id']}  {row['size']} 字节"
                          + (f"  [{states}]" if states else ""))
            return 0
        if args.command == "prepare":
            progress_stream = sys.stderr
            report = preparation.guide(load_device_profile(catalog), args.confirm, args.interactive,
                                       emit=lambda message: print(message, file=progress_stream, flush=True))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ready"] else 2
        if args.command == "doctor":
            from .doctor import diagnose
            result = diagnose(load_device_profile(catalog))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 2
        if args.command == "catalog":
            result = catalog.summary()
        else:
            if args.output:
                # Refuse existing files including hard links, symlinks and inputs.
                if args.output.exists() or args.output.is_symlink():
                    raise InputError("Output already exists; choose a new report path")
            paths = {"app": args.app, "wbi": args.wbi}
            if args.cpapp:
                paths["cpapp"] = args.cpapp
            result = analyze(catalog, paths,
                             "inspect" if args.command == "inspect" else args.action)
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if getattr(args, "output", None):
            with args.output.open("x", encoding="utf-8") as f:
                f.write(encoded)
        sys.stdout.write(encoded)
        return 2 if result.get("status") == "blocked" else 0
    except (CatalogError, InputError, DeviceError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "device_access": False, "device_writes": False,
                          "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
