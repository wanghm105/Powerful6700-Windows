"""把每个页面渲染成 PNG 并落盘，供打包后的自检与文档配图使用。

界面回归需要两个环境变量：QT_QPA_PLATFORM=offscreen 才不会开真窗口，
QT_QPA_FONTDIR=C:/Windows/Fonts 才找得到中文字体（否则整页退化成方框）。
"""
from __future__ import annotations

import os
from pathlib import Path

PAGES = ("notice", "driver", "preparation", "home", "looks", "result", "about")


def settle(app, rounds: int = 4) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    for _ in range(rounds):
        app.processEvents()
        # processEvents 不投递 DeferredDelete，不补这一手会叠着旧部件截图。
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def render(out, mode: str = "physical", size: str = "1240x860", check: bool = False) -> dict:
    """渲染全部页面；返回 {out, files, phase, ready} 供调用方打印或校验。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from .window import MainWindow

    width, _, height = size.partition("x")
    app = QApplication.instance() or QApplication([__name__])
    window = MainWindow(mode)
    window.resize(int(width), int(height or 860))
    window.show()
    settle(app)

    if check:
        window.check_environment()
        for _ in range(150):
            settle(app, rounds=1)
            if not window._busy():
                break
        settle(app)

    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for key in PAGES:
        window.goto(key)
        settle(app)
        target = directory / (key + ".png")
        window.grab().save(str(target))
        files.append(str(target))

    snapshot = window.snapshot or {}
    result = dict(
        out=str(directory),
        files=files,
        phase=snapshot.get("phase"),
        ready=(snapshot.get("environment") or {}).get("ready"),
    )
    window.close()
    return result
