"""Physical USB service adapter for the desktop controller.

The controller remains presentation/state only.  This adapter constructs the
real catalog/profile, delegates to :func:`a6700_unlock.operations.execute`,
and therefore inherits the physical device lock, sparse preflight, journal,
writer and independent readback workflow.
"""
from __future__ import annotations

from pathlib import Path

from ..backup import default_backup_dir, find_backup, list_backups, load_backup
from ..catalog import load_catalog
from ..device_profile import load_device_profile


class PhysicalService:
    """Execute real USB operations while exposing the desktop service shape."""

    def __init__(self, state_dir=None, backend_factory=None, backup_dir=None):
        self.profile = load_device_profile(load_catalog())
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self.backup_dir = (Path(backup_dir) if backup_dir is not None
                           else default_backup_dir())
        self.backend_factory = backend_factory
        self.connected = False
        self.simulation = False
        # Keep one authenticated USB session open for this app process. The
        # first operation asks for authorization; inspection and the chosen
        # write reuse it. Unlock/close then end the session before power-off.
        self._session_backend = None
        self._session_lock = None
        self._last_run_directory = None

    def list_backups(self):
        return list_backups(self.backup_dir)

    def reset_capture(self):
        self.close_session()

    def close_session(self):
        backend, self._session_backend = self._session_backend, None
        lock, self._session_lock = self._session_lock, None
        self.connected = False
        exit_error = None
        try:
            if backend is not None:
                backend.__exit__(None, None, None)
        except BaseException as exc:
            exit_error = str(exc) or type(exc).__name__
            raise
        finally:
            try:
                if backend is not None and self._last_run_directory is not None:
                    from ..operations import save_json
                    try:
                        save_json(self._last_run_directory / 'session-exit.json', dict(
                            cleanup_status=('unconfirmed' if exit_error else getattr(backend, 'cleanup_status', None)),
                            cleanup_warning=exit_error or getattr(backend, 'cleanup_warning', None)))
                    except OSError:
                        pass
            finally:
                self._last_run_directory = None
                if lock is not None:
                    lock.__exit__(None, None, None)
                try:
                    from ..usb.legacy import reset_libusb_backend
                    reset_libusb_backend()
                except Exception:
                    pass

    def _backend(self, progress, capture):
        if self.backend_factory is not None:
            try:
                return self.backend_factory(progress, capture=capture)
            except TypeError:
                return self.backend_factory(progress)
        from ..usb.backend import UsbBackend
        return UsbBackend(self.profile, progress, capture=capture)

    def perform(self, action, progress=lambda _message: None, backup_id=None, features=None):
        if action not in ("inspect", "unlock", "close", "backup", "restore"):
            raise ValueError("未知设备操作；当前支持检查、解锁、关闭、功能状态备份与恢复")
        from ..operations import (_execute_session, _backup_session, _restore_session,
                                  default_state_dir, device_lock)
        directory = self.state_dir if self.state_dir is not None else default_state_dir()
        if self._session_backend is None:
            # Claim the shared lock before capture/auth and keep it until the
            # authenticated session is closed. Calls below must not lock twice.
            lock = device_lock(directory)
            lock.__enter__()
            self._session_lock = lock
            try:
                backend = self._backend(progress, capture=True)
                backend.__enter__()
                self._session_backend = backend
            except BaseException:
                self.close_session()
                raise
        backend = self._session_backend
        backend.progress = progress
        try:
            if action == "backup":
                result = _backup_session(self.profile, backend, self.backup_dir,
                                         directory, progress, manage_backend=False)
            elif action == "restore":
                source = load_backup(find_backup(self.backup_dir, backup_id), self.profile)
                result = _restore_session(self.profile, backend, source, directory,
                                          progress, features=features, manage_backend=False)
            else:
                result = _execute_session(self.profile, backend, action, directory,
                                          progress, features=features, manage_backend=False)
        except BaseException:
            self.close_session()
            raise
        self._last_run_directory = Path(result['run_directory'])
        if action in ('unlock', 'close') or result.get('status') in ('error', 'uncertain'):
            try:
                self.close_session()
            except Exception as exc:
                # A service-exit failure must not erase the recorded write
                # and independent readback result. The lock is released in
                # close_session's finally block, and the next run reconnects.
                result['cleanup_status'] = 'unconfirmed'
                result['cleanup_warning'] = str(exc) or type(exc).__name__
            else:
                result['cleanup_status'] = getattr(backend, 'cleanup_status', None)
                result['cleanup_warning'] = getattr(backend, 'cleanup_warning', None)
        self.connected = self._session_backend is not None and result.get('status') in (
            'inspected', 'dry-run', 'completed', 'no-op', 'backup-completed', 'restored')
        return result
