"""命令行跑一次真机只读检查，走的是界面里那条 controller 路径。

用途：在冻结包里复验「只读检查」这一步（界面点按钮与这里调用的是同一套代码），
出问题时把结论落成 JSON，便于对照界面上的报错。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _say(message: str) -> None:
    print("  | " + message, flush=True)


def main(argv: list[str] | None = None) -> int:
    from . import app, paths, patches

    paths.ensure_vendor_on_path()
    args = list(sys.argv[1:] if argv is None else argv)
    target = args[0] if args else None

    patches.install()
    controller = app.build_controller("physical")
    controller.check_environment()
    report = {"environment_ready": bool(controller.environment.get("ready"))}
    try:
        controller.acknowledge_notice(True)
        controller.begin_preparation()
        controller.confirm_preparation(True)
        controller.reserve("inspect")
        controller.run_reserved(_say)
        # 检查成功时 controller.result 会被清空，结论落在 inspect_summary；
        # 失败时才写 result。两处都读，避免只看到一半。
        result = dict(controller.result or {})
        plan = dict(result.get("plan") or {})
        summary = dict(controller.inspect_summary or {})
        status = result.get("status") or ("inspected" if summary else None)
        features = plan.get("features") or summary.get("features") or []
        report.update(
            ok=status == "inspected",
            status=status,
            error=result.get("error") or None,
            compatible=plan.get("compatible", summary.get("compatible")),
            device_access=result.get("device_access", controller.device_access),
            write_attempted=result.get("write_attempted", controller.write_attempted),
            read_sectors=plan.get("read_sectors", summary.get("read_sectors")),
            read_bytes=plan.get("read_bytes", summary.get("read_bytes")),
            changed_bytes=plan.get("changed_bytes"),
            changed_sectors=plan.get("changed_sectors"),
            features=[{"id": row.get("id"), "state": row.get("state")} for row in features],
        )
    except Exception as exc:  # noqa: BLE001 - 失败原因要原样带出去
        report.update(ok=False, error=type(exc).__name__, message=str(exc))
    finally:
        try:
            controller.service.close_session()
        except Exception:  # noqa: BLE001
            pass

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(text)
    if target:
        Path(target).write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 1
