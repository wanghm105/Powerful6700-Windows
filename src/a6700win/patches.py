"""把上游 a6700_unlock 的运行期行为改造成 Windows 版本。

上游包（third_party/a6700_unlock，GPL-3.0）本身只支持 macOS/Linux：设备层没有
Windows 的 libusb 解析分支，doctor 直接判定"Windows 适配尚未完成"，因此
DesktopController 的启动检查在 Windows 上永远不通过。

这里不打补丁文件、不 fork 包，而是在进程启动时替换少量模块属性：
- legacy.libusb_library_path   → libusb-package 自带的 libusb-1.0.dll
- legacy.get_libusb_backend    → Windows 上强制 fresh（驱动切换后需要新上下文）
- legacy.run_authentication    → a6700win.usb.windows_auth.run_authentication
- legacy.observed_sony_product_ids / normal_mode_observed → SetupAPI 版本
- doctor.diagnose 与 preparation.diagnose → Windows 版启动检查
- operations.device_lock / make_directory / save_json、backup 的同名助手
  → a6700win.windows_shim（上游用 fcntl 与目录 fsync，Windows 上不可用）
- device_profile.inspect_sectors / operations.inspect_sectors
  → a6700win.guards（结构守卫里有 9 个扇区是 ext2 inode 元数据，
    相机开机自己会刷新时间戳，只放行这 12 字节）
- DesktopController.run_reserved → 出错时释放 busy，界面不再卡在"操作进行中"

用法：在构造 DesktopController 之前调用 install()。
"""

from __future__ import annotations

import ctypes
import os
import sys

from . import guards, paths, windows_shim
from .usb import driver, setupapi, windows_auth

_installed = False

# 供自检与 GUI 展示的补丁清单（顺序即安装顺序）。
_PATCH_NAMES = (
    "legacy.libusb_library_path",
    "legacy.get_libusb_backend",
    "legacy.run_authentication",
    "legacy.observed_sony_product_ids",
    "legacy.normal_mode_observed",
    "doctor.diagnose",
    "preparation.diagnose",
    "a6700_unlock.usb.backend.payloads",
    "a6700_unlock.doctor.payloads",
    "a6700_unlock.desktop.controller.payloads",
    "operations.device_lock",
    "operations.host_lock_path",
    "operations.make_directory",
    "operations.save_json",
    "operations.default_state_dir",
    "backup._ensure_directory",
    "backup._sync_file",
    "planner.os.O_NONBLOCK",
    "backup.os.O_BINARY",
    "controller.run_reserved",
    "controller.reserve",
    "operations._execute_session",
    "operations._restore_session",
    "usb.backend.UsbBackend._file",
    "device_profile.inspect_sectors",
    "operations.inspect_sectors",
    "controller.available_backups",
    "controller.restore_scope",
)


def _windows_get_libusb_backend(original):
    def get_libusb_backend(*, fresh: bool = False):
        # PyUSB 1.2.1 会把 context 永久缓存；驱动切换/重新枚举后必须重建。
        return original(fresh=True)

    return get_libusb_backend


def _windows_diagnose(original):
    def diagnose(profile):
        payload = original(profile)
        checks = payload.get("checks", [])
        for item in checks:
            identifier = item.get("id")
            if identifier == "platform":
                item.update(
                    ok=True,
                    detail=sys.platform,
                    remediation="当前设备连接层为 Windows（WinUSB + libusb）实现。",
                )
            elif identifier == "libusb":
                item.update(**_libusb_status())
        payload["checks"] = checks
        payload["ready"] = all(bool(item.get("ok")) for item in checks)
        payload["device_access"] = True
        return payload

    return diagnose


def _libusb_status() -> dict:
    try:
        path = windows_auth.libusb_library_path()
    except Exception as exc:  # noqa: BLE001
        return dict(ok=False, detail=str(exc), remediation="重新安装本程序以恢复 libusb-1.0.dll。")
    try:
        library = ctypes.CDLL(path)
        for symbol in ("libusb_init", "libusb_exit", "libusb_get_device_list", "libusb_open"):
            getattr(library, symbol)
    except (OSError, AttributeError) as exc:
        return dict(
            ok=False,
            detail="%s：%s" % (path, exc),
            remediation="libusb-1.0.dll 无法加载，请重新安装本程序。",
        )
    return dict(ok=True, detail=str(path), remediation="")


# --------------------------------------------------------------- 载荷校验
_source_provenance: dict = {}


def source_provenance() -> dict:
    """上游 transaction.c 的指纹核对结果（只作溯源记录，不作为封锁条件）。"""
    return dict(_source_provenance)


def _vendor_file(*parts: str):
    from importlib.resources import files

    node = files("a6700_unlock")
    for part in parts:
        node = node.joinpath(part)
    return node


def windows_payloads(profile):
    """与上游 payloads() 等价，但把源码文本指纹降级为溯源信息。

    真正送到相机的 reader/writer 载荷与 profile 摘要仍然逐字节严格校验：
    上游发布的 manifest.json 声明了一个与其自身 transaction.c 不一致的
    source_sha256（见 docs/UPSTREAM-NOTES.md），若把该行当硬性条件，
    Windows 上的启动检查会永久失败，而风险并没有降低——载荷本身早已校验。
    """
    import hashlib
    import json

    from a6700_unlock.device_protocol import DeviceError

    root = _vendor_file("data", "native")
    try:
        manifest = json.loads(root.joinpath("manifest.json").read_text())
    except (OSError, ValueError) as exc:
        raise DeviceError("Native payload manifest is unreadable: %s" % exc) from exc
    if manifest.get("profile_sha256") != profile.digest:
        raise DeviceError("Native payload/profile versions do not match")

    try:
        source = _vendor_file("native", "transaction.c").read_bytes()
    except OSError:
        source = b""
    actual = hashlib.sha256(source).hexdigest() if source else ""
    expected = str(manifest.get("source_sha256") or "")
    _source_provenance.clear()
    _source_provenance.update(expected=expected, actual=actual, matches=actual == expected,
                              checked=bool(source))

    result = {}
    for name in ("reader", "writer"):
        try:
            data = root.joinpath(name + ".elf").read_bytes()
        except OSError as exc:
            raise DeviceError("Packaged %s payload is missing: %s" % (name, exc)) from exc
        entry = manifest.get("payloads", {}).get(name) or {}
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise DeviceError("Packaged %s payload hash mismatch" % name)
        if int(entry.get("bytes") or 0) not in (0, len(data)):
            raise DeviceError("Packaged %s payload size mismatch" % name)
        result[name] = data
    return result


def _windows_write_status(result):
    """status=1（preimage 变化、touched=0）应当算“写前校验拒绝”，不是“回读失败”。

    上游的 rejected 分支要求回读结果等于 before，而 status=1 本身就意味着设备内容
    已经不等于 before，那个分支永远走不到。零字节写入被标成 verification-failed，
    界面会提示“不要盲目重试”，用户以为可能已经写了一半。
    """
    if not isinstance(result, dict):
        return result
    native = result.get("native_result") or {}
    if (result.get("status") == "verification-failed"
            and native.get("status")
            and not native.get("touched")):
        result["status"] = "rejected"
        result["error"] = native.get("error") or "写前校验未通过，相机内没有执行修改"
    return result


def _wrap_session(original):
    def session(*args, **kwargs):
        return _windows_write_status(original(*args, **kwargs))

    session._a6700win_wrapped = True
    return session


# 0x4010 = SET_FILE2（配置），0x4007 = SET_FILE（载荷），0x4008 = EXECUTE。
_FILE_STEPS = {0x4010: "配置写入（SET_FILE2）", 0x4007: "载荷写入（SET_FILE）"}


# 相机对临时文件操作返回的状态字（小端 u32）。0x10000004 是 2026-10-25 真机
# 见过的一次：读请求的配置/载荷暂存被拒，界面只看到「状态：04000010」。
_KNOWN_STATUS = {
    0x10000004: "，相机侧含义是临时文件操作被拒（通常是上一次会话没有干净结束）",
    0x10000006: "，相机侧含义是文件不存在",
}


_PROBE_PATH = "/setting/BACKUP.BIN"
_RETRY_DELAYS = (0.5, 1.5, 3.0)
_TEMP_STATUS = 0x10000004
_LATE_DELAY = 8.0
_SMALL_BODY = bytes([0])
_VERSION_COMMAND = 0x400D
_MOUNT_COMMAND = 0x4002

def _status_text(body: bytes) -> str:
    if len(body) < 4:
        return "相机返回了不完整的状态（%s）" % body[:16].hex()
    value = int.from_bytes(body[:4], "little")
    known = _KNOWN_STATUS.get(value, "")
    return "状态 0x%08X%s（原始字节 %s）" % (value, known, body[:16].hex())


def _short(path: str) -> str:
    """日志里只写文件名，/tmp/jiritsu/ 前缀对用户没意义。"""
    return path.rsplit("/", 1)[-1]


def _stale_paths() -> tuple[str, ...]:
    """会话开头要清的三个名字。

    tmmc.jit / tmmc.dat 是 Senser 配置写入与我们载荷共用的临时文件；libJit.so 是
    固件会 dlopen 的入口。/tmp/jiritsu 在独立 flash 分区、断电不消失
    （docs/AI-HANDOFF.md:844），遗留的 libJit.so 会被固件重放——而 0.3.8 的清理
    名单里一直没有它。用户报的 0x10000004 跨电脑、跨平台、断电、相机初始化都不
    消失，和"相机里确实留着东西"相符。
    """
    from . import dump

    return tuple(dump.TEMP_PATHS) + ("/tmp/jiritsu/libJit.so",)


def _clear_stale_temp(backend, progress=None) -> list[str]:
    """清掉上一次会话留在 /tmp/jiritsu 的临时文件，并把每一条的结果说出来。

    以前这里 `except Exception: continue`，失败被静默吞掉，且只在真的删掉时打一行，
    于是「文件本来不在」「文件在但删不掉」「命令直接被拒」三种情况在日志里长得一模一样
    ——2026-10-26 的现场日志正好卡在这一步，谁也判断不了。现在逐条报告，并且把
    「定位（select）被拒」和「删除被拒」分开写。
    """
    from . import dump

    paths = _stale_paths()
    channel = getattr(backend, "channel", None)
    if channel is None:
        if progress is not None:
            progress("没有相机服务通道，这次跳过临时文件清理（%s）。"
                     % "、".join(_short(path) for path in paths))
        return []
    removed = []
    failures = []
    remount_tried = False
    for path in paths:
        try:
            hit = dump.remove(channel, path)
        except Exception as exc:  # noqa: BLE001 - 清理失败要报出来，但不影响主流程
            text = str(exc)
            if "0x10000004" in text and not remount_tried:
                # 分区被卸载时连第一条删除都过不去。先重挂一次（只动挂载表），再重试。
                remount_tried = True
                note = _remount_jiritsu(channel)
                if progress is not None:
                    progress("%s 删不掉（%s），先把相机的临时目录重新挂上：%s"
                             % (_short(path), text, note))
                try:
                    hit = dump.remove(channel, path)
                except Exception as again:  # noqa: BLE001 - 重试失败仍要报出来
                    failures.append("%s：%s（重新挂上后仍然失败：%s）"
                                    % (_short(path), text, again))
                    continue
            else:
                failures.append("%s：%s" % (_short(path), exc))
                continue
        if hit:
            removed.append(path)
            if path.endswith("/libJit.so"):
                # 删掉 libJit.so 会让 Jiritsu 卸载整个 nflasha6 分区（FX30 6.00 与
                # ZV-E10 同族实测，见 docs/AI-HANDOFF.md 的 §24.2 引得那条），不重挂
                # 的话同一会话后面的第一条配置写入一定回 0x10000004——probe5 就白等了。
                note = _remount_jiritsu(channel)
                if progress is not None:
                    progress("%s 已清掉，顺便把相机的临时目录重新挂上：%s"
                             % (_short(path), note))
                    if "成功" not in note:
                        progress("没挂上也不要紧，等下写入时会再试一次。")
    if progress is not None:
        if removed:
            progress("已清掉相机上一次会话留下的临时文件：%s"
                     % "、".join(_short(path) for path in removed))
        for row in failures:
            progress("清理临时文件失败：%s" % row)
        if not removed and not failures:
            progress("相机上没有上次会话留下的临时文件：%s。"
                     % "、".join(_short(path) for path in paths))
    return removed


def _sleep(seconds) -> None:
    """阶梯里的等待；测试里换成空函数，免得跑一遍要等五秒。"""
    import time

    time.sleep(seconds)


def _status_line(status, raw="") -> str:
    if status is None:
        return raw or "返回正文长度不对"
    text = "状态 0x%08X%s" % (status, _KNOWN_STATUS.get(status, ""))
    if raw:
        text += "（原始字节 %s）" % raw
    return text

def _brief(status, raw="") -> str:
    # 错误正文里只留状态码：整段解释在抬头那句已经说过一次，每层重试再重复一遍
    # 界面就会变成一大段谁也读不下去的字。
    if status is None:
        return raw or "返回正文长度不对"
    text = "0x%08X" % status
    if raw:
        text += "（原始字节 %s）" % raw
    return text


def _attempt(backend, command, ident, data):
    try:
        body = backend._command(command, bytes([0, ident, 0]) + data)
    except Exception as exc:  # noqa: BLE001 - 传输层掉线也要进 trace，不能只剩上游原始报错
        return False, None, "传输中断：%s" % exc
    if len(body) == 4 and body == bytes(4):
        return True, 0, ""
    if len(body) >= 4:
        return False, int.from_bytes(body[:4], "little"), body[:16].hex()
    return False, None, body.hex()

def _probe_file_service(channel) -> str:
    """读一个普通文件，判断相机的文件服务整段通不通。

    临时区坏了、和整个文件服务被拒，是两种完全不同的病：前者还能靠清理救回来，
    后者只能换相机状态或找固件原因。分不清就只能一直猜，所以失败路径上顺手读一个
    一定存在的文件（/setting/BACKUP.BIN），把结论写进日志。
    """
    from . import dump

    if channel is None:
        return "没有相机服务通道，读不了普通文件"
    try:
        data = dump.camera_file(channel, _PROBE_PATH, missing=True)
    except Exception as exc:  # noqa: BLE001 - 探测只为记录，不影响主流程
        return "读 %s 失败：%s" % (_PROBE_PATH, exc)
    if data is None:
        return "读 %s：相机回答 0x10000006（文件不存在，说明文件服务本身是通的）" % _PROBE_PATH
    return "读 %s：成功 %d 字节" % (_PROBE_PATH, len(data))


def _inspect_temp_paths(channel) -> str:
    """逐条查 /tmp/jiritsu 的临时路径：只 SELECT，不写不删。

    0x10000004 到底是「文件不存在也报这个码」还是「连定位都被拒」，只看 remove 抛什么
    分不出来——dump.remove 内部先 select 再 remove，两种失败长得一样。这里单独把 select
    的结果写进日志，整个过程只发只读命令，不改相机里任何东西。
    """
    from . import dump

    if channel is None:
        return "没有相机服务通道，查不了临时路径"
    parts = []
    for path in _stale_paths():
        try:
            dump.select(channel, path, missing=True)
        except Exception as exc:  # noqa: BLE001 - 探测只为记录
            parts.append("%s：%s" % (_short(path), exc))
        else:
            parts.append("%s：定位没被拒" % _short(path))
    return "逐条查临时路径：" + "、".join(parts)

def _version_text(body: bytes) -> str:
    """0x400D 的 4 字节回文：大版本、次版本、保留、0x10（FX30 6.00 → 06 00 00 10）。"""
    if len(body) == 4 and body[3] == 0x10:
        value = int.from_bytes(body, "little")
        hint = ""
        if value in _KNOWN_STATUS:
            # 同一串字节也等于一个状态码（0x10000004 与「4.00」）：提醒别读串了。
            hint = "；同一串字节按状态读是 0x%08X" % value
        return "固件版本 %d.%02d（原始字节 %s%s）" % (body[0], body[1], body.hex(), hint)
    if len(body) >= 4:
        return "固件版本回文不认识（%d 字节：%s）" % (len(body), body[:8].hex())
    return "固件版本回文太短（%d 字节：%s）" % (len(body), body[:8].hex())


def _probe_version(channel) -> str:
    """只读地问一次相机固件版本（0x400D）。

    为什么要问：0x10000004 在四个人、四台机器上跨 Windows 版本、跨断电都没消失，而
    从没有一份日志记过固件版本。0x400D 与我们用的文件命令同在 category 0x1001：它答得
    出来，说明这条命令面是活的、坏的是文件服务；它也被拒，说明整条命令面没挂上。两种
    情况的下一步完全不同，所以第一步先问一句。它不含任何机身唯一信息。
    """
    from . import dump

    if channel is None:
        return "没有相机服务通道，读不到固件版本"
    try:
        code, body = dump.service(channel, _VERSION_COMMAND)
    except Exception as exc:  # noqa: BLE001 - 探测只为记录，不影响主流程
        return "读固件版本失败：%s" % exc
    if code:
        return "读固件版本被拒：返回码 %s" % code
    if len(body) == 4 and body[3] == 0x10:
        return _version_text(body)
    if len(body) >= 4:
        status = int.from_bytes(body[:4], "little")
        return "读固件版本被拒：状态 0x%08X%s（原始字节 %s）" % (
            status, _KNOWN_STATUS.get(status, ""), body[:8].hex())
    return "读固件版本：回文只有 %d 字节（%s）" % (len(body), body[:8].hex())


def _remount_jiritsu(channel) -> str:
    """发 0x4002（MOUNT）重新挂载 /tmp/jiritsu 所在的 nflasha6 分区。

    为什么想到这一条：同族机器（FX30 6.00、ZV-E10）的实测是——删掉
    /tmp/jiritsu/libJit.so 会让 Jiritsu 卸载整个 nflasha6，此后所有文件操作一律被拒
    （读 /tmp/jiritsu 直接回 130 = 分区已卸载），唯一补救就是 0x4002。我们 0.3.9 的
    清理名单里正好有 libJit.so，而失败现场连第一条删除都过不去：分区在上一次会话里
    就已经被卸掉了。这条命令只重挂分区，不打开、不写任何文件。
    """
    from . import dump

    if channel is None:
        return "没有相机服务通道，没发出去"
    try:
        code, body = dump.service(channel, _MOUNT_COMMAND)
    except Exception as exc:  # noqa: BLE001 - 探测只为记录
        return "命令没发出去：%s" % exc
    if code:
        return "返回码 %s（130 表示临时目录还没挂上，可以再发一次）" % code
    if len(body) >= 4:
        status = int.from_bytes(body[:4], "little")
        if status:
            return "状态 0x%08X（原始字节 %s）" % (status, body[:8].hex())
    return "成功"



def _windows_backend_file(self, command, ident, data):
    """上游把三种失败写成同一句“文件写入或载荷执行失败”，界面看不出卡在哪一步。

    这里保留同样的校验，只把步骤、命令号和相机状态写清楚；错误发生在固件写入之前，
    相机里没有动任何功能字段，文案也直接告诉用户下一步该做什么。

    0x10000004（临时文件操作被拒）以前只做一件事：清一遍 /tmp/jiritsu、再重发一次。
    2026-10-26 的现场证明不够：三个人、三台机器、跨平台都卡在同一个状态字上，而
    0.3.9-probe1 的日志显示连 select 都被拒（本该是 0x10000006 文件不存在）。所以
    这一版在**同一条会话里**把能想到的办法按希望从大到小一次试完，哪一步成的直接继续，
    全都不成再把每一步的状态报出来：
    ① 清临时文件——0.3.7 唯一真救回过一次的动作，且几乎零代价；
    ② 等相机把临时区挂好——0.5 / 1.5 / 3 秒各重试一次，覆盖切模式后的时间窗；
    ③ 只写 1 个字节——如果是正文太大才被拒，小正文能过，再补完整配置；
    ④ 读一个普通文件——把「只有临时区坏」和「整个文件服务被拒」分开（判定用）；
    ⑤ 重挂 /tmp/jiritsu 所在分区——0x4002 MOUNT，相机侧唯一还没试过的杠杆；
    ⑥ 逐条定位临时路径——只读，把「定位被拒」和「删除被拒」分开（判定用）；
    ⑦ 再多等 8 秒——时间窗的加长版，希望最低所以放最后。
    危险动作一律不做：不发 0x4008（EXECUTE）——相机里若残留旧的 libJit.so，那会执行未知
    代码；不跨会话重来——那要改上游会话代码，且已知有 Pipe error。
    健康相机上这些都不会发生：写一次就成；整条路上多了 1 条只读的 0x400D（读固件版本），
    不往相机里写任何东西。
    """
    from a6700_unlock.device_protocol import DeviceError

    progress = getattr(self, "progress", None)
    channel = getattr(self, "channel", None)

    def say(message):
        if progress is not None:
            progress(message)

    if command == 0x4010 and not getattr(self, "_a6700win_version_read", False):
        setattr(self, "_a6700win_version_read", True)
        say("先只读地问一句相机固件版本…" + _probe_version(channel))

    if command == 0x4010 and not getattr(self, "_a6700win_temp_cleared", False):
        setattr(self, "_a6700win_temp_cleared", True)
        _clear_stale_temp(self, progress)

    step = _FILE_STEPS.get(command, "文件写入 0x%04X" % command)
    ok, status, raw = _attempt(self, command, ident, data)
    if ok:
        return None
    if status != _TEMP_STATUS or command != 0x4010:
        raise DeviceError(
            "相机拒绝了%s（file_id=%d），%s；这次没有写入任何功能字段。"
            "恢复办法：拔掉数据线 → 相机正常关机 → 取出电池约 1 分钟 → 装回开机 →"
            "重新连 MSC 线，然后再检查一次。如果相机开始重复重启变砖，先别插线，"
            "等它停下再取电池。要是连电脑都认不出来了，就只剩硬件办法：上游「硬件说明」"
            "里有接线和步骤（https://github.com/xyzhangxin/sony-a6700-powerful/blob/main/硬件说明.md）。"
            % (step, ident, _status_line(status, raw)))

    trace = ["第一次写入 —— " + _brief(status, raw)]
    say("相机拒绝了%s（file_id=%d，状态 0x10000004）。这一版会在同一条会话里把能想到的办法按希望从大到小都试一遍。"
        % (step, ident))

    say("第 1 种（最可能）：清掉相机上一次会话留下的临时文件，再写一次…")
    _clear_stale_temp(self, progress)
    ok, status, raw = _attempt(self, command, ident, data)
    if ok:
        say("…清完临时文件后写入成功，继续。")
        return None
    trace.append("清掉临时文件后重写 —— " + _brief(status, raw))

    say("第 2 种：等相机把临时区挂好，0.5 秒 / 1.5 秒 / 3 秒各重写一次…")
    for delay in _RETRY_DELAYS:
        _sleep(delay)
        ok, status, raw = _attempt(self, command, ident, data)
        if ok:
            say("…等了 %.1f 秒后写入成功，继续。" % delay)
            return None
        trace.append("等 %.1f 秒后重写 —— %s" % (delay, _brief(status, raw)))

    say("第 3 种：只写 1 个字节，看是不是正文太大才被拒…")
    ok, status, raw = _attempt(self, command, ident, _SMALL_BODY)
    if ok:
        say("…1 个字节写进去了，说明相机要的是小正文；接着补完整配置。")
        ok, status, raw = _attempt(self, command, ident, data)
        if ok:
            say("…补完整配置也成功，继续。")
            return None
        trace.append("1 个字节写进去了、补完整配置仍被拒 —— " + _brief(status, raw))
    else:
        trace.append("只写 1 个字节 —— " + _brief(status, raw))

    say("第 4 种：读一个普通文件，看相机的文件服务整段通不通…")
    probe = _probe_file_service(channel)
    say("…" + probe)
    if "0x10000006" in probe:
        trace.append("读 /setting/BACKUP.BIN —— 文件不存在（0x10000006）")
    elif "成功" in probe:
        trace.append("读 /setting/BACKUP.BIN —— 读成功")
    elif "没有相机服务通道" in probe:
        trace.append("读 /setting/BACKUP.BIN —— 没有通道，没测成")
    else:
        trace.append("读 /setting/BACKUP.BIN —— 读失败（0x10000004）")
    ok, status, raw = _attempt(self, command, ident, data)
    if ok:
        say("…读完普通文件后写入成功，继续。")
        return None
    trace.append("读完普通文件后再写 —— " + _brief(status, raw))

    say("第 5 种：把相机的临时目录重新挂上（0x4002 MOUNT），再写一次…")
    mount_note = _remount_jiritsu(channel)
    say("…把相机的临时目录重新挂上：" + mount_note)
    if "成功" in mount_note:
        ok, status, raw = _attempt(self, command, ident, data)
        if ok:
            say("…重新挂上后写入成功，继续。")
            return None
        trace.append("重挂分区后再写 —— " + _brief(status, raw))
        probe = _probe_file_service(channel)
        say("…重新挂上后再读一次普通文件：" + probe)
        trace.append("重挂分区后读 /setting/BACKUP.BIN —— "
                     + ("读成功" if "成功" in probe else "读失败"))
    else:
        trace.append("重挂 /tmp/jiritsu 分区 —— " + mount_note)

    say("第 6 种：逐条查临时路径能不能定位（只读），再清一遍重写…")
    inspect = _inspect_temp_paths(channel)
    say("…" + inspect)
    if inspect.count("定位没被拒") == len(_stale_paths()):
        trace.append("逐条定位三个临时路径 —— 都定位到了")
    else:
        trace.append("逐条定位三个临时路径 —— " + inspect)
    _clear_stale_temp(self, progress)
    ok, status, raw = _attempt(self, command, ident, data)
    if ok:
        say("…查过临时路径、清完再写成功，继续。")
        return None
    trace.append("查过临时路径、清完再写 —— " + _brief(status, raw))

    say("第 7 种（最不可能）：再多等 %.0f 秒，有的机器把临时区挂得慢，然后重写一次…" % _LATE_DELAY)
    _sleep(_LATE_DELAY)
    ok, status, raw = _attempt(self, command, ident, data)
    if ok:
        say("…等了 %.0f 秒后写入成功，继续。" % _LATE_DELAY)
        return None
    trace.append("再多等 %.0f 秒重写 —— %s" % (_LATE_DELAY, _brief(status, raw)))

    # 0.3.9-probe4r 试过「把会话整个关掉再重新认证一次」：唯一的增量动作，结果是
    # 相机从 0x0E76(MSC) 被推到 0x096F(HidUsb)——那是文档里写「救不回」的落点，写入
    # 一次都没成。所以这条路已经删掉，别再放回来。

    if "成功" in probe:
        conclusion = "普通文件读得出来，说明文件服务是通的，坏的是 /tmp/jiritsu 这个临时区。"
    elif "0x10000006" in probe:
        conclusion = "普通文件回答「文件不存在」，说明文件服务本身是通的，坏的只是 /tmp/jiritsu。"
    elif "没有相机服务通道" in probe:
        conclusion = "这次没拿到相机服务通道，探测没做成，不能据此判断是临时区还是整个文件服务。"
    else:
        conclusion = "连普通文件都没读出来（原因见上面那行），先不下结论：把日志发我，我按状态码判断。"
    say("能想到的办法都试过了，仍然 0x10000004。" + conclusion)
    parts = [
        "相机拒绝了%s（file_id=%d）：%s。" % (step, ident, _status_line(status, raw)),
        "同一条会话里按希望从大到小试了 %d 种办法，全部被拒：" % len(trace),
    ]
    parts.extend("%d. %s" % (index, item) for index, item in enumerate(trace, 1))
    parts.append("能想到的办法都试过了，仍然 0x10000004。" + conclusion)
    parts.append(
        "这次没有写入任何功能字段。恢复办法：拔掉数据线 → 相机正常关机 → "
        "取出电池约 1 分钟 → 装回开机 → 重新连 MSC 线，然后再检查一次。")
    parts.append(
        "如果相机开始重复重启变砖，先别插线，等它停下再取电池；连电脑都认不出来时"
        "只剩硬件办法，上游「硬件说明」里有接线和步骤"
        "（https://github.com/xyzhangxin/sony-a6700-powerful/blob/main/硬件说明.md）。")
    parts.append("把这一页和日志一起发给我：日志里每一条尝试的结果都在。")
    raise DeviceError(chr(10).join(parts))

_windows_backend_file._a6700win_wrapped = True


def _windows_available_backups(self):
    """物理模式下也列出本机功能状态备份。

    上游把桌面端的备份列表藏了起来（controller.py 的 "The desktop backup UI is
    hidden." 注释）：physical 模式下只要当前动作不是 backup/restore 就返回空列表。
    但 reserve('restore', backup_id) 在设置 self.action *之前* 就按这份列表校验
    backup_id，于是桌面端永远无法选择备份——先有鸡先有蛋。本移植在界面上明确提供
    备份/恢复，且备份目录是本程序自己的 .data\backups，枚举代价可以忽略。
    """
    try:
        rows = self.service.list_backups()
    except (OSError, ValueError):
        return []
    digest = self.service.profile.digest
    return [row for row in rows if row.get('profile_sha256') == digest]


_windows_available_backups._a6700win_wrapped = True


def install() -> dict:
    """安装全部补丁；可重复调用。返回补丁清单供自检展示。"""
    global _installed
    paths.ensure_vendor_on_path()
    from a6700_unlock import doctor, preparation
    from a6700_unlock.desktop import controller as controller_module
    from a6700_unlock.usb import backend, legacy

    applied = []
    if not _installed or legacy.libusb_library_path is not windows_auth.libusb_library_path:
        legacy.libusb_library_path = windows_auth.libusb_library_path
        applied.append("legacy.libusb_library_path")

    if not getattr(legacy, "_a6700win_wrapped_backend", False):
        legacy._a6700win_original_backend = legacy.get_libusb_backend
        legacy.get_libusb_backend = _windows_get_libusb_backend(legacy.get_libusb_backend)
        legacy._a6700win_wrapped_backend = True
        applied.append("legacy.get_libusb_backend")

    for name, replacement in (
        ("run_authentication", windows_auth.run_authentication),
        ("observed_sony_product_ids", windows_auth.observed_sony_product_ids),
        ("normal_mode_observed", windows_auth.normal_mode_observed),
    ):
        if getattr(legacy, name) is not replacement:
            setattr(legacy, name, replacement)
            applied.append("legacy." + name)

    if not getattr(doctor, "_a6700win_wrapped_diagnose", False):
        original_doctor = doctor.diagnose
        doctor._a6700win_original_diagnose = original_doctor
        patched_diagnose = _windows_diagnose(original_doctor)
        doctor.diagnose = patched_diagnose
        preparation.diagnose = patched_diagnose
        doctor._a6700win_wrapped_diagnose = True
        preparation._a6700win_wrapped_diagnose = True
        applied.append("doctor.diagnose")
        applied.append("preparation.diagnose")

    # payloads 在 doctor / backend / controller 三处各自绑定，必须逐个替换。
    for module in (backend, doctor, controller_module):
        if getattr(module, "payloads", None) is not windows_payloads:
            if not hasattr(module, "_a6700win_original_payloads"):
                module._a6700win_original_payloads = module.payloads
            module.payloads = windows_payloads
            applied.append(module.__name__ + ".payloads")

    # --- POSIX → Windows 兼容层（设备锁、目录落盘、planner 的 O_NONBLOCK） ---
    from a6700_unlock import backup as backup_module, operations, planner

    if operations.device_lock is not windows_shim.device_lock:
        operations.device_lock = windows_shim.device_lock
        applied.append("operations.device_lock")

    if operations.host_lock_path is not windows_shim.host_lock_path:
        operations.host_lock_path = windows_shim.host_lock_path
        applied.append("operations.host_lock_path")

    if operations.make_directory is not windows_shim.make_directory:
        operations.make_directory = windows_shim.make_directory
        applied.append("operations.make_directory")

    if operations.save_json is not windows_shim.save_json:
        operations.save_json = windows_shim.save_json
        applied.append("operations.save_json")

    if operations.default_state_dir is not windows_shim.default_state_dir:
        operations.default_state_dir = windows_shim.default_state_dir
        applied.append("operations.default_state_dir")

    if backup_module._ensure_directory is not windows_shim.make_directory:
        backup_module._ensure_directory = windows_shim.make_directory
        applied.append("backup._ensure_directory")

    if backup_module._sync_file is not windows_shim.sync_file:
        backup_module._sync_file = windows_shim.sync_file
        applied.append("backup._sync_file")

    # planner.LocalImage 用 os.O_NONBLOCK 打开本地固件镜像；Windows 没有该常量，
    # 换成带 O_NONBLOCK=0 的 os 代理，行为等价于普通阻塞只读打开。
    if planner.os is not windows_shim.PLANNER_OS:
        planner.os = windows_shim.PLANNER_OS
        applied.append("planner.os.O_NONBLOCK")

    # backup.py 写 .a6700backup 时没带 O_BINARY，Windows 文本模式会改写 0x0A，
    # 稀疏备份文件会直接损坏。
    if backup_module.os is not windows_shim.BINARY_OS:
        backup_module.os = windows_shim.BINARY_OS
        applied.append("backup.os.O_BINARY")

    applied.extend(guards.install())

    controller_class = controller_module.DesktopController
    if not getattr(controller_class.run_reserved, "_a6700win_wrapped", False):
        controller_class._a6700win_original_run_reserved = controller_class.run_reserved
        controller_class.run_reserved = windows_shim.wrap_run_reserved(
            controller_class.run_reserved)
        applied.append("controller.run_reserved")

    if not getattr(controller_class.run_reserved, "_a6700win_restore_scope", False):
        controller_class.run_reserved = windows_shim.wrap_restore_scope(
            controller_class.run_reserved)
        applied.append("controller.restore_scope")

    if not getattr(controller_class._available_backups, "_a6700win_wrapped", False):
        controller_class._a6700win_original_available_backups = controller_class._available_backups
        controller_class._available_backups = _windows_available_backups
        applied.append("controller.available_backups")

    # 恢复不读勾选；相机全开时 selected_features 为空，上游 reserve 会在看备份之前拒绝。
    if not getattr(controller_class.reserve, "_a6700win_wrapped", False):
        controller_class.reserve = windows_shim.wrap_reserve(controller_class.reserve)
        applied.append("controller.reserve")

    # status=1（写前校验拒绝、零字节写入）不能报成“独立回读失败”。
    for name in ("_execute_session", "_restore_session"):
        current = getattr(operations, name)
        if not getattr(current, "_a6700win_wrapped", False):
            setattr(operations, name, _wrap_session(current))
            applied.append("operations." + name)

    # 相机拒绝配置/载荷时要说清是哪一步、状态码是多少。
    if not getattr(backend.UsbBackend._file, "_a6700win_wrapped", False):
        backend.UsbBackend._file = _windows_backend_file
        applied.append("usb.backend.UsbBackend._file")

    _installed = True
    already = [name for name in _PATCH_NAMES if name not in applied]
    return dict(applied=applied, already=already, libusb=_libusb_status(), driver=driver.scan())


def _refresh_provenance() -> None:
    """status() 也要能看到载荷溯源信息，无需先跑一次真实检查。"""
    if _source_provenance:
        return
    try:
        from a6700_unlock.catalog import load_catalog
        from a6700_unlock.device_profile import load_device_profile

        windows_payloads(load_device_profile(load_catalog()))
    except Exception:  # noqa: BLE001 - 诊断信息缺失不应让 status() 失败
        pass


def status() -> dict:
    """不触发任何写操作的当前状态，给 GUI 与自检用。"""
    paths.ensure_vendor_on_path()
    _refresh_provenance()
    return dict(
        platform=sys.platform,
        python=sys.version.split()[0],
        installed=_installed,
        paths=paths.describe(),
        libusb=_libusb_status(),
        driver=driver.scan(),
        devices=setupapi.summary(),
        payload_source=source_provenance(),
    )
