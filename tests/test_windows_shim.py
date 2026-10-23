"""Windows 兼容层：设备锁、目录创建、独占保存。"""

import json

import pytest

from a6700win import windows_shim


@pytest.fixture()
def patched():
    from a6700win import patches

    patches.install()
    from a6700_unlock import operations

    return operations


def test_device_lock_is_exclusive(patched, tmp_path):
    with patched.device_lock(tmp_path):
        with pytest.raises(Exception) as excinfo:
            with patched.device_lock(tmp_path):
                pass
    assert "相机工具运行" in str(excinfo.value)


def test_device_lock_is_released(patched, tmp_path):
    for _ in range(3):
        with patched.device_lock(tmp_path):
            pass


def test_host_lock_lives_in_data_root(patched):
    from a6700win import paths

    assert patched.host_lock_path() == paths.data_root() / "host.lock"


def test_make_directory_creates_parents(patched, tmp_path):
    patched.make_directory(tmp_path / "a" / "b" / "c")
    assert (tmp_path / "a" / "b" / "c").is_dir()


def test_save_json_is_exclusive(patched, tmp_path):
    target = tmp_path / "record.json"
    patched.save_json(target, {"x": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}
    with pytest.raises(FileExistsError):
        patched.save_json(target, {"x": 2})


def test_planner_can_open_local_images(patched):
    from a6700_unlock import planner

    assert planner.os.O_NONBLOCK == 0


def test_backup_writes_binary_mode(patched, tmp_path):
    from a6700_unlock import backup

    target = tmp_path / "state.a6700backup"
    fd = backup.os.open(target, backup.os.O_WRONLY | backup.os.O_CREAT | backup.os.O_EXCL, 0o600)
    with backup.os.fdopen(fd, "wb") as out:
        out.write(b"\n\x00\n")
    assert target.read_bytes() == b"\n\x00\n"


def test_run_reserved_releases_busy_on_error(patched, tmp_path):
    from a6700_unlock.desktop.controller import DesktopController

    controller = DesktopController(str(tmp_path), mode="simulation")
    controller.check_environment()
    controller.notice_acknowledged = True
    controller.checked = True
    controller.busy = True
    controller.action = "inspect"

    def boom(action, progress=lambda _message: None, backup_id=None, features=None):
        raise RuntimeError("usb failed")

    controller.service.perform = boom
    with pytest.raises(RuntimeError):
        controller.run_reserved()
    snapshot = controller.snapshot()
    assert snapshot["busy"] is False
    assert snapshot["action"] == ""