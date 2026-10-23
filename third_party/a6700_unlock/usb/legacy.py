#!/usr/bin/env python3
"""Collected A6700 USB service tool (historical implementation).

list/auth retain the existing enumeration and double authentication flow.
send-file sends actual file contents; SET_FILE file_id=2 triggers dlopen and
executes the payload. It is not an initialization-only or read-only operation.
The historical name "phase1" was removed to avoid that misleading implication.
This runtime copy adds bounded transfer checks, deterministic handle cleanup,
service-device selection and stage diagnostics. The historical collected copy
and its provenance remain in verified/.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import usb.core
import usb.util
from usb.backend import libusb1
from usb.core import USBError

HERE = Path(__file__).resolve().parent
PMCA_ROOT = HERE / "reference" / "sony_pmca"

from .packet_builder import (  # noqa: E402
    A6700_JIRITSU_CATEGORY,
    A6700_JIRITSU_SET_FILE_CODE,
    A6700_JIRITSU_SET_FILE2_CODE,
    PFUNC_ADJUST_CONTROL,
    build_file_frame,
    parse_frame,
)


SONY_VENDOR_ID = 0x054C
KNOWN_INITIAL_PIDS = {0x047D, 0x0E76}
KNOWN_SENSER_PIDS = {0x02A9, 0x0336}
KNOWN_PID_LABELS = {
    0x02D7: "auto",
    0x0336: "Senser service",
    0x034A: "still image",
    0x03E2: "updater",
    0x047D: "mass storage",
    0x04EF: "bus power",
    0x0641: "remote PC",
    0x06A8: "app download",
    0x0E76: "mass storage (MSC)",
    0x0E78: "PC remote",
}

START_SENSER = (0x43, 0x01, 0x37FF, 0xD7AA)
STOP_SENSER = (0x43, 0x01, 0xC800, 0x2855)
AUTH_PACKET_SIZE = 0x204
AUTH_DATA_SIZE = 0x200
SENSER_HEADER_SIZE = 12
SENSER_MIN_SIZE = 0x200
SENSER_MAX_SIZE = 0x100000


class ProbeError(RuntimeError):
    pass


@dataclass
class UsbTarget:
    device: usb.core.Device
    interface_number: int
    interface: object
    endpoint_in: int
    endpoint_out: int
    product_id: int


def load_module(name: str, path: Path):
    if not path.is_file():
        raise ProbeError(f"required reference module is missing: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"cannot load required reference module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PMCA_CONSTANTS = load_module(
    "a6700_pmca_usb_constants", PMCA_ROOT / "constants.py"
)
PMCA_CRYPTO = load_module(
    "a6700_pmca_usb_crypto", PMCA_ROOT / "crypto.py"
)


def libusb_library_path():
    """Resolve the library without creating a USB context or cached devices."""
    from ..bundled import resource
    bundled = resource('libusb')
    if bundled is not None:
        return str(bundled)
    if sys.platform.startswith("linux"):
        library = ctypes.util.find_library('usb-1.0')
        if library is None:
            raise ProbeError(
                "libusb-1.0 was not found. Install it with: apt install libusb-1.0-0"
            )
        return library

    candidates = [
        Path("/opt/homebrew/lib/libusb-1.0.dylib"),
        Path("/usr/local/lib/libusb-1.0.dylib"),
        Path("/usr/lib/libusb-1.0.dylib"),
    ]
    available = [path for path in candidates if path.is_file()]
    if not available:
        raise ProbeError(
            "libusb-1.0 was not found. On this Mac install it with: brew install libusb"
        )

    return str(available[0])


def check_libusb_library():
    """Check dynamic loading and ABI symbols; never call libusb_init here.

    The macOS capture/surrender step changes the USB registry. Creating a
    PyUSB context before capture can retain stale device objects, so startup
    diagnostics must stop at library loading.
    """
    library = ctypes.CDLL(libusb_library_path())
    for symbol in ('libusb_init', 'libusb_exit', 'libusb_get_device_list', 'libusb_open'):
        getattr(library, symbol)
    return True


_session_backend = None
_session_library = None


class _OwnedLibUSB(libusb1._LibUSB):
    """Keep the context alive through PyUSB 1.2.1 native-object cleanup.

    Its _Device and _DevIterator only hold C pointers, not their backend.
    ResourceManager can drop its backend before its native device is unrefed.
    Pin the owner on those wrappers so their C finalizers run first. Do not
    modify PyUSB globals or retain a growing process-wide list of contexts.
    """
    def enumerate_devices(self):
        iterator = super().enumerate_devices()
        iterator._a6700_backend_owner = self
        for device in iterator:
            device._a6700_backend_owner = self
            yield device

    def get_parent(self, device):
        parent = super().get_parent(device)
        if parent is not None:
            parent._a6700_backend_owner = self
        return parent


def reset_libusb_backend():
    """Drop our cache; PyUSB owns context teardown after device references die.

    Calling libusb_exit directly leaves PyUSB's finalizer armed and retained
    Device/_ResourceManager objects pointing to freed native state. Neither
    refresh nor reconnect may invalidate their context underneath them.
    """
    global _session_backend, _session_library
    _session_backend = None
    _session_library = None


def get_libusb_backend(*, fresh=False):
    global _session_backend, _session_library
    library = libusb_library_path()
    backend = libusb1.get_backend(find_library=lambda _: library)
    if backend is None:
        raise ProbeError(f"PyUSB could not load {library}")
    if fresh:
        # Replacing this reference lets the old backend live as long as any
        # PyUSB device still needs it. Its own finalizer closes it exactly once.
        lib = getattr(backend, "lib", None)
        _session_backend = _OwnedLibUSB(lib) if lib is not None else backend
        _session_library = library
    return _session_backend if _session_library == library else backend


def iter_usb_devices(*, fresh=False):
    backend = get_libusb_backend(fresh=fresh)
    try:
        yield from usb.core.find(find_all=True, backend=backend)
    except usb.core.NoBackendError as exc:
        raise ProbeError(str(exc)) from exc


def device_identity(device: usb.core.Device) -> dict[str, object]:
    result: dict[str, object] = {
        "bus": getattr(device, "bus", None),
        "address": getattr(device, "address", None),
        "vendor_id": f"0x{device.idVendor:04x}",
        "product_id": f"0x{device.idProduct:04x}",
    }
    for key in ("manufacturer", "product", "serial_number"):
        try:
            value = getattr(device, key)
        except (USBError, NotImplementedError, ValueError):
            value = None
        if value:
            result[key] = value
    return result


def find_bulk_endpoints(device: usb.core.Device) -> tuple[object, int, int] | None:
    """Return the first interface containing both bulk IN and bulk OUT."""
    try:
        configuration = device.get_active_configuration()
    except (USBError, ValueError):
        try:
            # Descriptor fallback only: discovery must never set configuration.
            configuration = device[0]
        except (USBError, ValueError):
            return None

    for interface in configuration:
        endpoint_in = None
        endpoint_out = None
        for endpoint in interface:
            endpoint_type = endpoint.bmAttributes & 0x03
            if endpoint_type != usb.util.ENDPOINT_TYPE_BULK:
                continue
            if endpoint.bEndpointAddress & 0x80 == usb.util.ENDPOINT_IN:
                if endpoint_in is None:
                    endpoint_in = endpoint.bEndpointAddress
            elif endpoint_out is None:
                endpoint_out = endpoint.bEndpointAddress
        if endpoint_in is not None and endpoint_out is not None:
            return interface, endpoint_in, endpoint_out
    return None


def describe_device(device: usb.core.Device) -> dict[str, object]:
    info = device_identity(device)
    product_id = device.idProduct
    if product_id in KNOWN_PID_LABELS:
        info["known_pid_label"] = KNOWN_PID_LABELS[product_id]
    try:
        configuration = device.get_active_configuration()
        interfaces = []
        for interface in configuration:
            endpoints = []
            for endpoint in interface:
                endpoints.append(
                    {
                        "address": f"0x{endpoint.bEndpointAddress:02x}",
                        "type": {
                            0: "control",
                            1: "iso",
                            2: "bulk",
                            3: "interrupt",
                        }.get(endpoint.bmAttributes & 0x03, str(endpoint.bmAttributes & 0x03)),
                        "direction": "in"
                        if endpoint.bEndpointAddress & 0x80
                        == usb.util.ENDPOINT_IN
                        else "out",
                        "max_packet_size": endpoint.wMaxPacketSize,
                    }
                )
            interfaces.append(
                {
                    "number": interface.bInterfaceNumber,
                    "class": f"0x{interface.bInterfaceClass:02x}",
                    "subclass": f"0x{interface.bInterfaceSubClass:02x}",
                    "protocol": f"0x{interface.bInterfaceProtocol:02x}",
                    "endpoints": endpoints,
                }
            )
        info["interfaces"] = interfaces
    except (USBError, ValueError):
        info["descriptor_error"] = "configuration or string descriptor unavailable"
    return info


def list_devices(show_all: bool) -> int:
    rows = []
    for device in iter_usb_devices():
        if show_all or device.idVendor == SONY_VENDOR_ID:
            rows.append(describe_device(device))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def watch_for_sony_device(timeout_seconds: float) -> int:
    """Wait for a Sony device and print its descriptors when it appears."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for device in iter_usb_devices():
            if device.idVendor == SONY_VENDOR_ID:
                print(json.dumps(describe_device(device), ensure_ascii=False, indent=2))
                return 0
        time.sleep(0.25)
    raise ProbeError(f"no Sony USB device appeared within {timeout_seconds:g} seconds")


def open_target(device: usb.core.Device) -> UsbTarget:
    selected = find_bulk_endpoints(device)
    if selected is None:
        raise ProbeError(
            f"Sony 0x{device.idProduct:04x} has no interface with bulk IN/OUT endpoints"
        )
    interface, endpoint_in, endpoint_out = selected

    try:
        try:
            device.detach_kernel_driver(interface.bInterfaceNumber)
        except (NotImplementedError, USBError) as detach_exc:
            pass

        usb.util.claim_interface(device, interface)
    except USBError as exc:
        hint = ""
        if sys.platform == "darwin" and getattr(exc, "errno", None) in (13, 1):
            hint = (
                "\n\n[macOS IOUSBMassStorageDriver Lock Detected]\n"
                "macOS kernel driver IOUSBMassStorageDriver holds exclusive access to the MSC interface.\n"
                "From the release source directory, capture the device first:\n\n"
                "    sh verified/macos/capture-usb.sh\n"
            )
        raise ProbeError(
            f"cannot claim interface {interface.bInterfaceNumber} on "
            f"0x{device.idProduct:04x}: {exc}{hint}"
        ) from exc
    return UsbTarget(
        device=device,
        interface_number=interface.bInterfaceNumber,
        interface=interface,
        endpoint_in=endpoint_in,
        endpoint_out=endpoint_out,
        product_id=device.idProduct,
    )


def close_target(target: UsbTarget | None) -> None:
    if target is None:
        return
    try:
        usb.util.release_interface(target.device, target.interface_number)
    except (USBError, ValueError):
        pass
    try:
        target.device.attach_kernel_driver(target.interface_number)
    except (NotImplementedError, USBError, AttributeError):
        pass
    finally:
        # Release the libusb handle before a gadget re-enumeration. Merely
        # releasing the interface leaves the macOS device handle alive.
        usb.util.dispose_resources(target.device)


def vendor_request_out(device: usb.core.Device, request: tuple[int, int, int, int], *, strict: bool = False) -> None:
    request_type, request_number, value, index = request
    try:
        device.ctrl_transfer(request_type, request_number, value, index, 0, timeout=3000)
    except USBError as exc:
        if strict:
            raise
        # The A7C II reference records that this control status may stall while
        # authentication remains available.
        print(f"note: start/stop control transfer returned {exc}; continuing", file=sys.stderr)


def send_auth_packet(target: UsbTarget, command: int, data: bytes = b"") -> tuple[int, bytes]:
    if len(data) > AUTH_DATA_SIZE:
        raise ProbeError("authentication data exceeds 512 bytes")
    frame = struct.pack(
        ">HH",
        (~command) & 0xFFFF,
        0,
    ) + data.ljust(AUTH_DATA_SIZE, b"\0")
    target.device.write(target.endpoint_out, frame, timeout=5000)
    response = bytes(target.device.read(target.endpoint_in, AUTH_PACKET_SIZE, timeout=5000))
    if len(response) != AUTH_PACKET_SIZE:
        raise ProbeError(f"authentication response was {len(response)} bytes, expected 516")
    response_command, salt = struct.unpack_from(">HH", response, 0)
    result = (~response_command & 0xFFFF) - salt
    return result, response[4:]


def authenticate_target(target: UsbTarget) -> None:
    vendor_request_out(target.device, START_SENSER)
    for round_index in range(3):
        result, challenge = send_auth_packet(target, 1)
        if result not in (2, 8):
            raise ProbeError(f"authentication challenge returned invalid result {result}")

        if target.product_id == 0x0336:
            keys = (
                PMCA_CONSTANTS.senserKeysSha1
                if result == 2
                else PMCA_CONSTANTS.senserKeysSha256
            )
            challenge_data = challenge + keys[round_index]
        else:
            challenge_data = challenge[:4]

        digest = (
            PMCA_CRYPTO.sha1_faulty(challenge_data)
            if result == 2
            else hashlib.sha256(challenge_data).digest()
        )
        result, _ = send_auth_packet(target, 3, b"\x01" + digest)
        if result != 4:
            raise ProbeError(f"authentication proof round {round_index + 1} returned {result}")

    result, completion = send_auth_packet(target, 5)
    if result != 6:
        raise ProbeError(f"authentication completion returned {result}")
    if not completion or completion[0] != 1:
        raise ProbeError(f"authentication completed with camera error {completion[:1].hex()}")


def candidates(
    vendor: int = SONY_VENDOR_ID,
    require_bulk: bool = True,
) -> list[usb.core.Device]:
    rows = []
    for device in iter_usb_devices():
        if device.idVendor != vendor:
            continue
        if require_bulk and find_bulk_endpoints(device) is None:
            continue
        rows.append(device)
    return rows


def choose_initial_device(initial_pid: int | None) -> usb.core.Device:
    # A mounted SD volume, an openable libusb handle and usable bulk endpoints
    # are not prerequisites for *finding* an MSC camera. Check them on open,
    # after the one necessary macOS capture, instead of filtering the camera out.
    rows = [device for device in candidates(require_bulk=False) if is_msc_device(device)]
    if initial_pid is not None:
        rows = [device for device in rows if device.idProduct == initial_pid]
        if not rows:
            raise ProbeError(f"no Sony MSC device with product ID 0x{initial_pid:04x}")
    if not rows:
        raise ProbeError(
            "no Sony MSC device found. Set the camera to Mass Storage/USB storage mode."
        )
    if len(rows) > 1:
        detail = ", ".join(f"0x{device.idProduct:04x}@{device.bus}/{device.address}" for device in rows)
        raise ProbeError(f"multiple Sony MSC cameras found ({detail}); connect exactly one camera")
    return rows[0]


def is_msc_device(device):
    if device.idVendor != SONY_VENDOR_ID:
        return False
    if device.idProduct in KNOWN_INITIAL_PIDS:
        return True
    try:
        return any(interface.bInterfaceClass == 0x08 for interface in device[0])
    except (USBError, ValueError):
        return False


def wait_for_service_device(
    initial_pid: int,
    service_pid: int | None,
    timeout_seconds: float,
) -> usb.core.Device:
    deadline = time.monotonic() + timeout_seconds
    last_seen: list[int] = []
    while time.monotonic() < deadline:
        # Filter the expected service PID before opening any descriptors. A
        # just-reenumerated service can exist before its endpoints are openable.
        rows = candidates(require_bulk=False)
        last_seen = [device.idProduct for device in rows]
        if service_pid is not None:
            matching = [device for device in rows if device.idProduct == service_pid]
            if len(matching) > 1:
                raise ProbeError("multiple service-mode cameras found; connect exactly one camera")
            if matching:
                return matching[0]
        else:
            known = [
                device for device in rows if device.idProduct in KNOWN_SENSER_PIDS
            ]
            if known:
                return known[0]
            different = [device for device in rows if device.idProduct != initial_pid]
            if len(different) == 1:
                return different[0]
        time.sleep(0.25)
    suffix = f" (expected 0x{service_pid:04x})" if service_pid is not None else ""
    raise ProbeError(
        "service-mode device did not appear"
        + suffix
        + f"; Sony bulk product IDs seen: "
        + ", ".join(f"0x{pid:04x}" for pid in last_seen)
    )


def observed_sony_product_ids():
    if sys.platform != "darwin":
        return [d.idProduct for d in iter_usb_devices() if d.idVendor == SONY_VENDOR_ID]
    # Observe via IOKit independently: the current libusb context may retain the
    # pre-STOP gadget until its event thread catches up with re-enumeration.
    import plistlib
    tree = plistlib.loads(subprocess.check_output(["ioreg", "-p", "IOUSB", "-l", "-a"], timeout=3))
    def collect(node):
        if isinstance(node, dict):
            if node.get("IOObjectClass") == "IOUSBHostDevice" and node.get("idVendor") == SONY_VENDOR_ID:
                yield node.get("idProduct")
            for value in node.values():
                yield from collect(value)
        elif isinstance(node, list):
            for value in node:
                yield from collect(value)
    return list(collect(tree))


def normal_mode_observed(timeout_seconds=3.0):
    """Observe descriptors only; a STOP status can vanish during re-enumeration."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        sony = observed_sony_product_ids()
        if sony == [0x0e76]:
            return True
        if len(sony) > 1 or time.monotonic() >= deadline:
            return False
        time.sleep(0.25)


class SenserChannel:
    def __init__(self, target: UsbTarget):
        self.target = target
        self.sequence = 1

    def send(self, pfunc: int, body: bytes) -> tuple[int, bytes]:
        if len(body) > SENSER_MAX_SIZE:
            raise ProbeError("this probe only sends single Senser packets")
        header = struct.pack(
            "<IHHBBBB",
            len(body),
            pfunc,
            self.sequence,
            0,
            0,
            0,
            0,
        )
        frame = header + body
        sent = self.target.device.write(self.target.endpoint_out, frame, timeout=10000)
        if sent != len(frame):
            raise ProbeError("Short USB transfer; do not automatically retry a writer")

        # The public PMCA implementation pads non-0336 service responses to
        # 0x200 bytes. Keep that behavior for unknown A6700 service IDs.
        minimum = 0 if self.target.product_id == 0x0336 else SENSER_MIN_SIZE
        expected_header_and_padding = max(SENSER_HEADER_SIZE, minimum)
        response = bytes(
            self.target.device.read(
                self.target.endpoint_in, expected_header_and_padding, timeout=10000
            )
        )
        if len(response) < SENSER_HEADER_SIZE:
            raise ProbeError("Senser response is shorter than its 12-byte header")
        size, response_pfunc, sequence, _, _, _, response_code = struct.unpack_from(
            "<IHHBBBB", response, 0
        )
        if sequence != self.sequence:
            raise ProbeError(
                f"Senser response sequence {sequence} does not match request {self.sequence}"
            )
        if response_pfunc != pfunc:
            raise ProbeError(
                f"Senser response pFunc 0x{response_pfunc:04x} does not match 0x{pfunc:04x}"
            )

        payload = response[SENSER_HEADER_SIZE:]
        if size < len(payload):
            payload = payload[:size]
        if size > len(payload):
            remaining = size - len(payload)
            if size > SENSER_MAX_SIZE:
                raise ProbeError("Response exceeds supported result size")
            while remaining:
                part = bytes(self.target.device.read(self.target.endpoint_in, remaining, timeout=10000))
                if not part or len(part) > remaining:
                    raise ProbeError("Truncated or oversized USB response")
                payload += part
                remaining -= len(part)
        self.sequence += 1
        return response_code, payload


def run_authentication(
    initial_pid: int | None,
    service_pid: int | None,
    timeout_seconds: float,
    read_product_info: bool,
    progress=lambda message: None,
) -> tuple[UsbTarget, SenserChannel]:
    if sys.platform == 'darwin':
        get_libusb_backend(fresh=True)
    progress("正在寻找唯一的 MSC 相机…")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            initial_device = choose_initial_device(initial_pid)
            break
        except ProbeError as exc:
            # macOS capture/surrender briefly removes the old registry entry.
            # Only wait for absence; ambiguity and other errors are immediate.
            if not str(exc).startswith("no Sony MSC device") or time.monotonic() >= deadline:
                raise
            time.sleep(0.25)
    initial_pid = initial_device.idProduct
    print(f"initial Sony device: 0x{initial_pid:04x}")

    initial_target = open_target(initial_device)
    try:
        progress("正在进行第一次 USB 认证…")
        authenticate_target(initial_target)
        print("first Senser authentication: OK")
    finally:
        close_target(initial_target)

    progress("正在等待相机进入服务模式…")
    if sys.platform == 'darwin':
        get_libusb_backend(fresh=True)
    service_device = wait_for_service_device(initial_pid, service_pid, timeout_seconds)
    service_pid = service_device.idProduct
    print(f"service Sony device: 0x{service_pid:04x}")

    service_target = open_target(service_device)
    try:
        progress(f"正在进行第二次 USB 认证（接口类别 0x{service_target.interface.bInterfaceClass:02x}）…")
        authenticate_target(service_target)
        print("second Senser authentication: OK")
        channel = SenserChannel(service_target)
        if read_product_info:
            progress("正在确认相机服务响应…")
            response_code, body = channel.send(0x10, struct.pack("<HH", 0, 0x001F) + b"\x00")
            if response_code != 1:
                raise ProbeError(f"ProductInfo response code was {response_code}")
            print(f"ProductInfo: response={response_code}, body={len(body)} bytes")
            print(body.hex())
        return service_target, channel
    except BaseException as original:
        try:
            vendor_request_out(service_target.device, STOP_SENSER, strict=True)
        except Exception:
            original.cleanup_warning = "退出服务模式未获确认，请拔插 USB"
            if hasattr(original, "add_note"):
                original.add_note(original.cleanup_warning)
        finally:
            close_target(service_target)
        raise


def run_auth_command(args: argparse.Namespace) -> int:
    target = None
    try:
        target, channel = run_authentication(
            args.initial_pid,
            args.service_pid,
            args.timeout,
            read_product_info=True,
        )
        vendor_request_out(target.device, STOP_SENSER)
        print("ProductInfo readback and service stop request completed")
        return 0
    finally:
        close_target(target)


def run_send_file_command(args: argparse.Namespace) -> int:
    """Send actual file data using the already tested wire-frame flow."""
    file_data = args.file.read_bytes()
    command = (A6700_JIRITSU_SET_FILE_CODE if args.op == "set-file"
               else A6700_JIRITSU_SET_FILE2_CODE)
    frame = build_file_frame(
        file_data,
        file_id=args.file_id,
        area=args.area,
        transfer_mode=args.transfer_mode,
        sequence=1,
        command=command,
    )
    parsed = parse_frame(frame)
    print(
        "request: "
        + json.dumps(
            {
                "length": len(frame),
                "pfunc": parsed["pfunc"],
                "sequence": parsed["sequence"],
                "category": parsed["category"],
                "command": parsed["command"],
                "payload_len": parsed["payload_len"],
                "area": parsed["area"],
                "file_id": parsed["file_id"],
                "transfer_mode": parsed["transfer_mode"],
            },
            indent=2,
        )
    )

    target = None
    try:
        target, channel = run_authentication(
            args.initial_pid,
            args.service_pid,
            args.timeout,
            read_product_info=True,
        )
        response_code, body = channel.send(PFUNC_ADJUST_CONTROL, body=frame[12:])
        print(f"response code: {response_code}")
        print(f"response body: {len(body)} bytes")
        print(body.hex())
        status = int.from_bytes(body, "little") if len(body) == 4 else None
        if status is not None:
            print(f"status: 0x{status:08x}" + (" (OK)" if status == 0 else " (error)"))
        if args.read_result and status == 0:
            # Existing GET_FILE wire operation: fixed area=0/file_id=0, whose
            # content is /tmp/jiritsu/tmmc.jit. This is payload result retrieval,
            # not an independent read of the patched flash target.
            code, result = channel.send(PFUNC_ADJUST_CONTROL,
                                        struct.pack("<HHBBB", A6700_JIRITSU_CATEGORY, 0x4008, 0, 0, 0))
            print(f"GET_FILE response code: {code}")
            print(f"GET_FILE body: {result.hex()}")
            if len(result) >= 4 and result[:4] == b"\0" * 4:
                print("payload result: " + result[4:].decode("utf-8", errors="replace"))
        vendor_request_out(target.device, STOP_SENSER)
        print("file transfer and service stop request completed")
        return 0 if status == 0 else 1
    finally:
        close_target(target)


def self_test() -> int:
    sample = bytes(range(64))
    frame = build_file_frame(sample, file_id=0, command=A6700_JIRITSU_SET_FILE2_CODE)
    parsed = parse_frame(frame)
    assert len(frame) == 83
    assert parsed["size"] == 0x47  # header size = 4 + N
    assert parsed["pfunc"] == PFUNC_ADJUST_CONTROL
    assert parsed["category"] == A6700_JIRITSU_CATEGORY
    assert parsed["command"] == A6700_JIRITSU_SET_FILE2_CODE
    assert parsed["payload_len"] == 0x43
    assert frame[12:16] == b"\x01\x10\x10\x40"

    auth = struct.pack(">HH", (~1) & 0xFFFF, 0) + b"\0" * AUTH_DATA_SIZE
    assert len(auth) == AUTH_PACKET_SIZE
    assert struct.unpack_from(">HH", auth, 0)[0] == 0xFFFE
    print("usb_service_probe self-test passed")
    print("wire frame length for 64 bytes: 83")
    return 0


def parse_int(text: str) -> int:
    return int(text, 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="enumerate descriptors only")
    list_parser.add_argument("--all", action="store_true", help="show non-Sony devices too")
    list_parser.set_defaults(func=lambda args: list_devices(args.all))

    watch_parser = subparsers.add_parser(
        "watch", help="wait for a Sony device, then enumerate descriptors only"
    )
    watch_parser.add_argument("--timeout", type=float, default=60.0)
    watch_parser.set_defaults(func=lambda args: watch_for_sony_device(args.timeout))

    auth_parser = subparsers.add_parser(
        "auth", help="authenticate and perform a ProductInfo readback"
    )
    auth_parser.add_argument("--initial-pid", type=parse_int, default=None)
    auth_parser.add_argument("--service-pid", type=parse_int, default=None)
    auth_parser.add_argument("--timeout", type=float, default=8.0)
    auth_parser.set_defaults(func=run_auth_command)

    phase_parser = subparsers.add_parser(
        "send-file", help="send actual file contents; file_id=2 with SET_FILE executes code"
    )
    phase_parser.add_argument("file", type=Path, help="local file whose actual contents will be sent")
    phase_parser.add_argument("--initial-pid", type=parse_int, default=None)
    phase_parser.add_argument("--service-pid", type=parse_int, default=None)
    phase_parser.add_argument("--timeout", type=float, default=8.0)
    phase_parser.add_argument("--area", type=parse_int, default=0x00)
    phase_parser.add_argument("--file-id", type=parse_int, default=0x02)
    phase_parser.add_argument("--transfer-mode", type=parse_int, default=0x00, choices=(0, 1))
    phase_parser.add_argument("--op", choices=("set-file", "set-file2"), default="set-file2")
    phase_parser.add_argument("--read-result", action="store_true", help="read payload result from fixed file_id=0 after status=0")
    phase_parser.set_defaults(func=run_send_file_command)

    self_test_parser = subparsers.add_parser("self-test", help="offline frame validation")
    self_test_parser.set_defaults(func=lambda args: self_test())
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except USBError as exc:
        print(f"USB error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
