"""应用装配：装好 Windows 补丁，再构造上游的 DesktopController。

上游 desktop/controller.py 在构造时就把 environment_provider 绑定为
physical_environment（内部懒导入 doctor.diagnose），因此补丁必须在
DesktopController(...) 之前安装。
"""

from __future__ import annotations

from . import patches, paths


def vendor_ready() -> bool:
    paths.ensure_vendor_on_path()
    try:
        import a6700_unlock.desktop.controller  # noqa: F401
    except Exception:  # noqa: BLE001 - 缺包时要能给出可读错误
        return False
    return True


def build_controller(mode: str = "physical"):
    """构造控制器；两种模式都先装 Windows 补丁。"""
    if not vendor_ready():
        raise RuntimeError(
            "内置的 a6700_unlock 运行时缺失，请重新安装本程序或重新解压完整发布包。"
        )
    # 预览（simulation）也要装：doctor 的 platform 检查与载荷校验在两种模式下同样成立，
    # 不装的话演示模式的启动检查会被上游清单里的 source_sha 不一致卡死。
    patches.install()
    from a6700_unlock.desktop.controller import DesktopController

    return DesktopController(
        str(paths.run_dir()),
        mode=mode,
        physical_state_dir=paths.state_dir(),
        physical_backup_dir=paths.backup_dir(),
    )
