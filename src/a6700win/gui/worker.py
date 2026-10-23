"""后台任务线程：把控制器调用移出界面线程。"""
from __future__ import annotations

import traceback
from typing import Callable

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    """在后台执行一次控制器调用。

    被调用的函数接收一个 progress(message) 回调，返回值通过 finished_ok 传出。
    """

    progressed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, label: str, fn: Callable[[Callable[[str], None]], object],
                 parent=None, cancel: Callable[[], None] | None = None):
        super().__init__(parent)
        self.label = label
        self._fn = fn
        self._cancel = cancel
        self._cancelled = False

    def request_cancel(self) -> None:
        self._cancelled = True
        if self._cancel is not None:
            try:
                self._cancel()
            except Exception:  # noqa: BLE001 - 取消不应打断界面
                pass

    def progress(self, message: str) -> None:
        self.progressed.emit(str(message))

    def run(self) -> None:  # noqa: D401 - QThread 入口
        try:
            result = self._fn(self.progress)
        except KeyboardInterrupt:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - 统一转成界面提示
            detail = str(exc) or exc.__class__.__name__
            self.failed.emit(detail)
            traceback.print_exc()
        else:
            if self._cancelled:
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
