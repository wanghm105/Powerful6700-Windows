"""Line-delimited JSON worker for the real USB desktop mode.

This bridge intentionally exposes only the fixed preparation and device
commands.  It does not accept a backend, profile, arbitrary path, shell
command or simulation scenario.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from threading import Lock, Thread

from .controller import DesktopController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=None,
                        help='本机操作记录目录；默认使用系统状态目录')
    parser.add_argument('--backup-dir', type=Path, default=None,
                        help='功能状态备份目录；默认 ~/Documents/A6700 Backups')
    args = parser.parse_args()

    output_lock = Lock()
    # Authentication suppresses raw legacy ProductInfo through a stdout
    # redirect. Keep protocol progress on the original JSON output stream.
    protocol_output = sys.stdout
    def emit(kind, **values):
        with output_lock:
            print(json.dumps(dict(type=kind, **values), ensure_ascii=False), flush=True,
                  file=protocol_output)

    controller = DesktopController(None, mode='physical', physical_state_dir=args.state_dir,
                                   physical_backup_dir=args.backup_dir)
    thread = None

    def run():
        def progress(message):
            emit('progress', message=message)
        try:
            emit('state', state=controller.run_reserved(progress))
        except (Exception, KeyboardInterrupt) as exc:
            with controller.lock:
                controller.busy = False
                controller.compatible = False
                controller.confirmed.clear()
                controller.features = []
                controller.phase = 'result'
                controller.revision += 1
                detail = str(exc).strip() or '重新检查环境、准备状态和 USB 连接后再试。'
                cancelled = isinstance(exc, KeyboardInterrupt)
                controller.result = dict(status='cancelled' if cancelled else 'error',
                    title='连接检查已取消' if cancelled else '真实设备服务发生错误',
                    detail=detail, success=False,
                    error=detail, simulation=False, device_access=True, write_attempted=False)
            emit('state', state=controller.snapshot())

    emit('state', state=controller.snapshot())
    for raw in sys.stdin:
        try:
            if len(raw) > 8192:
                raise ValueError('请求过长。')
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError('无效请求。')
            command = request.get('command')
            if command in ('inspect', 'unlock', 'close', 'backup', 'restore'):
                controller.reserve(command, request.get('backup_id') if command == 'restore' else None)
                emit('state', state=controller.snapshot())
                thread = Thread(target=run, daemon=True)
                thread.start()
                continue
            if command == 'environment':
                state = controller.check_environment()
            elif command == 'acknowledge':
                state = controller.acknowledge_notice(request.get('value'))
            elif command == 'prepare':
                state = controller.begin_preparation()
            elif command == 'confirm':
                state = controller.confirm(request.get('id'), request.get('value'))
            elif command == 'confirm_preparation':
                state = controller.confirm_preparation(request.get('value'))
            elif command == 'restart_preparation':
                state = controller.restart_preparation()
            elif command == 'select_feature':
                state = controller.set_feature_selection(request.get('id'), request.get('value'))
            elif command == 'select':
                state = controller.select_features(request.get('mode'))
            elif command == 'acknowledge_check':
                state = controller.acknowledge_check()
            elif command == 'shutdown':
                state = controller.end_session()
                emit('state', state=state)
                break
            elif command == 'cancel':
                state = controller.cancel_operation()
            elif command == 'home':
                state = controller.home()
            else:
                raise ValueError('未知真实设备命令。')
            emit('state', state=state)
        except (ValueError, TypeError, KeyError):
            emit('error', message='当前操作不可用，请先完成前置步骤或等待当前操作结束。')
    controller.cancel.set()
    if thread is not None:
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
