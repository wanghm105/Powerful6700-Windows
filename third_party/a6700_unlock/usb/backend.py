"""USB execution adapter over the historically verified Senser/Jiritsu path."""
from __future__ import annotations

import contextlib
import hashlib
from importlib.resources import files
import stat
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from ..device_protocol import DeviceError, request, response


def payloads(profile):
    root = files("a6700_unlock").joinpath("data/native")
    manifest = json.loads(root.joinpath("manifest.json").read_text())
    if manifest["profile_sha256"] != profile.digest:
        raise DeviceError("Native payload/profile versions do not match")
    source = files("a6700_unlock").joinpath("native/transaction.c").read_bytes()
    if hashlib.sha256(source).hexdigest() != manifest["source_sha256"]:
        raise DeviceError("Native source changed without rebuilding payloads and manifest")
    result = {}
    for name in ("reader", "writer"):
        data = root.joinpath(name + ".elf").read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["payloads"][name]["sha256"]:
            raise DeviceError(f"Packaged {name} payload hash mismatch")
        result[name] = data
    return result


LOCAL_CAPTURE_HELPER = Path("/usr/local/sbin/a6700-capture")


def _local_capture_helper():
    """Return the one-time-installed privileged helper when it is safe to use."""
    path = LOCAL_CAPTURE_HELPER
    try:
        info = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        return None
    from ..bundled import resource
    current = resource('capture')
    # An older installed helper would reintroduce its reset-before-capture
    # behavior. Use it only if it is the exact current bundled implementation.
    try:
        if current is None or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(current.read_bytes()).digest():
            return None
    except OSError:
        return None
    return path


def local_capture_available():
    """True only when the one-time helper is present and NOPASSWD works."""
    local = _local_capture_helper()
    if local is None:
        return False
    try:
        result = subprocess.run(['/usr/bin/sudo', '-n', '-l', str(local)],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def capture_macos(progress):
    local = _local_capture_helper()
    if local is not None:
        progress('正在使用本机已授权的接管组件…')
        result = subprocess.run(['/usr/bin/sudo', '-n', str(local)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and 'capture: OK' in getattr(result, 'stdout', ''):
            return
        if result.returncode == 1 and 'password is required' in (getattr(result, 'stderr', '') or '').lower():
            # No NOPASSWD rule on this machine: use the normal one-prompt path.
            pass
        else:
            detail = (getattr(result, 'stderr', '') or getattr(result, 'stdout', '') or '').strip().splitlines()
            raise DeviceError('本机已授权接管组件未能接管相机：' + (detail[-1] if detail else '未知错误'))
    from ..bundled import resource
    helper = resource('capture')
    if helper is not None:
        progress('请在 macOS 弹窗授权接管 USB（Mac 管理员密码或 Touch ID）…')
        script = ('on run argv\n'
                  'tell application "System Events" to activate\n'
                  'do shell script (quoted form of (item 1 of argv)) with administrator privileges\n'
                  'end run')
        result = subprocess.run(['/usr/bin/osascript', '-e', script, str(helper)],
                                capture_output=True, text=True)
        if result.returncode:
            raise DeviceError('系统授权或相机接口接管未完成，请确认连接与授权后再试。')
        return
    _capture_macos_source(progress)


def _capture_macos_source(progress):
    clang = shutil.which("clang")
    if not clang:
        raise DeviceError("macOS 接口接管需要 Command Line Tools 中的 clang")
    progress("正在接管相机 MSC 接口，系统可能请求管理员授权…")
    source = files("a6700_unlock").joinpath("native/mac_capture.m").read_bytes()
    sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    clang = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="a6700-capture-") as folder:
        folder = Path(folder)
        (folder / "capture.m").write_bytes(source)
        build = subprocess.run([clang, '-isysroot', sdk, "-fobjc-arc", "-framework", "Foundation", "-framework", "IOUSBHost",
                                "-framework", "IOKit", "-o", str(folder / "capture"), str(folder / "capture.m")],
                               capture_output=True, text=True)
        if build.returncode:
            raise DeviceError("macOS helper 编译失败：" + build.stderr[-1500:])
        # With a terminal sudo can prompt on /dev/tty. In a batch process fail
        # promptly instead of hiding a password prompt or waiting indefinitely.
        sudo = ["sudo"]
        try:
            with open("/dev/tty", "rb"):
                pass
        except OSError:
            sudo.append("-n")
        result = subprocess.run(sudo + [str(folder / "capture")], capture_output=True, text=True)
        if result.returncode:
            detail = (result.stdout + "\n" + result.stderr).strip()[-1500:]
            raise DeviceError("macOS 接口接管失败；需要授权时请在终端运行启动工具：" + detail)


class UsbBackend:
    def __init__(self, profile, progress=lambda message: None, capture=True):
        self.profile, self.progress, self.capture_mac = profile, progress, capture
        self.captured = not capture
        self.target = None
        self.cleanup_warning = None
        self.cleanup_status = None
        self.assets = payloads(profile)

    def __enter__(self):
        try:
            from . import legacy
        except ImportError as exc:
            raise DeviceError("缺少 USB 依赖，请安装 a6700-unlock[usb] 和系统 libusb") from exc
        self.legacy = legacy
        if sys.platform == "darwin" and self.capture_mac:
            capture_macos(self.progress)
            self.captured = True
        try:
            legacy.get_libusb_backend()
        except Exception as exc:
            raise DeviceError("无法加载系统 libusb：" + str(exc)) from exc
        self.progress("正在认证相机 USB 服务模式…")
        # Old diagnostics include raw ProductInfo. Do not put device identifiers
        # in user reports or ordinary stdout; the sparse layout guards establish
        # supported firmware compatibility below.
        stage = "USB 认证"
        def authentication_progress(message):
            nonlocal stage
            stage = message
            self.progress(message)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.target, self.channel = legacy.run_authentication(None, 0x0336, 12.0, True,
                                                                      progress=authentication_progress)
        except Exception as exc:
            notes = getattr(exc, "__notes__", [])
            self.cleanup_warning = getattr(exc, "cleanup_warning", None) or ("；".join(notes) if notes else None)
            raise DeviceError(f"USB 认证失败（{stage}）；确认 MSC、关闭 FTP、相机唤醒且仅连接一台目标相机：" + str(exc)) from exc
        return self

    def _command(self, command, payload):
        code, body = self.channel.send(0x40, struct.pack("<HH", 0x1001, command) + payload)
        if code != 0:
            raise DeviceError(f"USB 服务命令失败：0x{command:04x}, code={code}")
        return body

    def _file(self, command, ident, data):
        body = self._command(command, bytes([0, ident, 0]) + data)
        if len(body) != 4 or body != b"\0" * 4:
            raise DeviceError("文件写入或载荷执行失败，状态：" + body[:16].hex())

    def _run(self, name, config, nonce, count):
        try:
            self._file(0x4010, 0, config)
            self._file(0x4007, 2, self.assets[name])
            body = self._command(0x4008, bytes([0, 0, 0]))
            if len(body) < 4 or body[:4] != b"\0" * 4:
                raise DeviceError("无法读取载荷结果")
            return response(body[4:], nonce, count)
        except DeviceError:
            raise
        except Exception as exc:
            raise DeviceError("USB 会话中断；写入器不会自动重发：" + str(exc)) from exc

    def read(self, nonce):
        result = self._run("reader", request(self.profile, nonce), nonce, len(self.profile.entries))
        if result["status"]:
            raise DeviceError(f"目标读取失败：{result['error']}, index={result['failed_index']}")
        return result["sectors"]

    def write(self, before, after, nonce):
        return self._run("writer", request(self.profile, nonce, before, after), nonce, 0)

    def __exit__(self, *unused):
        if self.target is not None:
            try:
                self.legacy.vendor_request_out(self.target.device, self.legacy.STOP_SENSER, strict=True)
                self.cleanup_status = "stop-sent"
            except Exception as exc:
                self.cleanup_status = "unconfirmed"
                self.cleanup_warning = "无法确认退出服务模式，请拔插 USB：" + str(exc)
            finally:
                try:
                    self.legacy.close_target(self.target)
                except Exception as exc:
                    warning = "释放 USB 接口失败，请拔插 USB：" + str(exc)
                    self.cleanup_warning = ((self.cleanup_warning + "；") if self.cleanup_warning else "") + warning
                finally:
                    self.target = None
            if self.cleanup_status == "unconfirmed":
                try:
                    observed = self.legacy.normal_mode_observed()
                except Exception:
                    observed = False
                if observed:
                    self.cleanup_status = "msc-observed"
                    # Preserve a separate interface-release error if any.
                    if "释放 USB 接口失败" not in (self.cleanup_warning or ""):
                        self.cleanup_warning = None
