"""Desktop state machine, independent of SwiftUI, USB, and the JSON transport."""
from __future__ import annotations

from copy import deepcopy
import sys
from threading import Event, RLock

from ..catalog import load_catalog
from ..device_profile import load_device_profile
from ..preparation import assess, STEPS
from ..notice import operation_notice
from ..usb.backend import payloads
from .physical import PhysicalService
from .simulation import SCENARIOS, SimulationService
from .aftercare import build_aftercare


SIMULATION_RESULT_LABELS = {
    'completed': ('模拟操作完成', '所选功能状态已更新，并通过独立回读。'),
    'no-op': ('已经是目标状态', '没有重复执行模拟写入。'),
    'blocked': ('兼容性检查未通过', '模拟内容与预期不一致，所选功能修改已停止。'),
    'error': ('未能完成检查', '检查模拟连接和准备状态后，再主动重新检查。'),
    'cancelled': ('已取消模拟操作', '尚未发送模拟写入。重新准备后可再检查状态。'),
    'uncertain': ('模拟结果待核实', '响应丢失或操作被中断；没有自动重发，请先重新检查状态。'),
    'verification-failed': ('模拟独立回读失败', '当前状态不能确认为目标状态，没有自动重写。'),
    'rolled-back': ('模拟失败，已回退', '回退后的内容已独立回读确认。'),
    'recovery-required': ('模拟回退未能确认', '保留本次结果，不自动重试。'),
    'rejected': ('模拟写前校验拒绝', '没有执行修改，且已核对写前状态。'),
    'backup-completed': ('模拟功能状态备份完成', '已保存模拟设备的功能相关扇区；不是整机镜像。'),
    'restored': ('模拟恢复完成', '已写回模拟备份中的功能字段，并通过独立回读。'),
}

PHYSICAL_RESULT_LABELS = {
    'completed': ('操作完成', '写入与独立回读通过，待机身验收。请按下方步骤断电重启并检查菜单。'),
    'no-op': ('已经是目标状态', '没有重复发送写入器。'),
    'blocked': ('兼容性检查未通过', '设备内容或结构守卫与预期不一致，所选功能修改已停止。'),
    'error': ('未能完成检查', '检查 USB 连接、相机模式和准备状态后，再主动重新检查。'),
    'cancelled': ('已取消操作', '尚未发送写入器。重新准备后可再检查状态。'),
    'uncertain': ('结果待核实', '响应丢失或操作被中断；没有自动重发，请先重新检查状态。'),
    'verification-failed': ('独立回读失败', '当前状态不能确认为目标状态，没有自动重写。'),
    'rolled-back': ('操作失败，已回退', '回退后的内容已独立回读确认。'),
    'recovery-required': ('回退未能确认', '保留本次结果，不自动重试。'),
    'rejected': ('写前校验拒绝', '没有执行修改，且已核对写前状态。'),
    'backup-completed': ('功能状态备份完成', '已保存当前功能相关扇区；这不是整机镜像，不能恢复未由本工具管理的设置。'),
    'restored': ('恢复完成', '已写回备份中的功能字段，并通过独立回读。请正常退出后关机重开验收实际功能。'),
}


def preview_environment():
    """Validate preview prerequisites only; physical USB dependencies are unused."""
    checks = [dict(id='runtime', name='本地运行环境', ok=sys.version_info >= (3, 10),
                   detail='Python ' + sys.version.split()[0], remediation='使用 Python 3.10+ 重新构建预览。')]
    try:
        payloads(load_device_profile(load_catalog()))
        checks.append(dict(id='resources', name='核心程序与适配资源', ok=True,
                           detail='清单、源码与载荷哈希一致', remediation=''))
    except Exception:
        checks.append(dict(id='resources', name='核心程序与适配资源', ok=False,
                           detail='资源缺失或版本混用', remediation='重新构建同版本预览。'))
    checks.append(dict(id='simulation', name='模拟设备服务', ok=True,
                       detail='仅内存数据，不加载物理 USB 后端', remediation=''))
    return dict(ready=all(row['ok'] for row in checks), checks=checks, device_access=False)


def physical_environment():
    """Run the real operation environment checks without enumerating USB."""
    from ..doctor import diagnose

    environment = deepcopy(diagnose(load_device_profile(load_catalog())))
    for row in environment['checks']:
        if row['id'] == 'payload-integrity':
            row['detail'] = '清单、源码与载荷哈希一致' if row['ok'] else '核心资源校验失败'
        elif not isinstance(row['detail'], str):
            row['detail'] = '检查通过' if row['ok'] else '检查未通过'
    return environment


class DesktopController:
    def __init__(self, directory, environment_provider=None, mode='simulation',
                 physical_state_dir=None, physical_backend_factory=None,
                 physical_backup_dir=None):
        if mode not in ('simulation', 'physical'):
            raise ValueError('未知桌面模式。')
        self.mode = mode
        self.directory = directory
        self.environment_provider = environment_provider or (
            preview_environment if mode == 'simulation' else physical_environment)
        self.lock = RLock()
        self.cancel = Event()
        self.busy = False
        self.revision = 0
        if mode == 'simulation':
            self.service = SimulationService(directory, 'enabled')
            self.scenario = 'enabled'
            self.scenarios = SCENARIOS
            self.result_labels = SIMULATION_RESULT_LABELS
        else:
            self.service = PhysicalService(physical_state_dir, physical_backend_factory,
                                           physical_backup_dir)
            self.scenario = ''
            self.scenarios = {}
            self.result_labels = PHYSICAL_RESULT_LABELS
        self._initialize_state()

    def _initialize_state(self):
        self.confirmed = set()
        self.environment = dict(ready=False, checks=[], device_access=False)
        self.checked = self.compatible = False
        self.notice_acknowledged = False
        self.features = []
        self.result = None
        self.last_report = None
        self.phase = 'notice'
        self.action = ''
        self.backup_id = None
        self.inspect_summary = None
        self.selected_features = set(self.service.profile.catalog.available_features)
        self.device_access = False
        self.write_attempted = False
        self.cancel.clear()

    def reset(self, scenario=None):
        with self.lock:
            if self.busy:
                raise ValueError('操作进行中，请先取消并等待结果。')
            if self.mode == 'physical':
                if scenario not in (None, 'physical'):
                    raise ValueError('真实设备模式不支持模拟场景。')
                self._initialize_state()
                self.service.connected = False
                self.service.reset_capture()
            else:
                if scenario not in SCENARIOS:
                    raise ValueError('未知模拟场景。')
                self.scenario = scenario
                self.service = SimulationService(self.directory, scenario)
                self._initialize_state()
            self.revision += 1

    def check_environment(self):
        with self.lock:
            if self.busy:
                raise ValueError('请等待当前操作结束。')
            if self.mode == 'physical':
                # A recheck is also the user's recovery entry: release any
                # captured/stale session before diagnosing a fresh connection.
                self.service.close_session()
            self.environment = deepcopy(self.environment_provider())
            if self.mode == 'simulation' and self.scenario == 'environment-missing':
                self.environment['checks'].append(dict(id='demo-missing', name='模拟组件故障', ok=False,
                    detail='演示依赖缺失，并非本机检测结论', remediation='切换到其他模拟场景后重新检查。'))
                self.environment['ready'] = False
            self.checked = True
            self.confirmed.clear()
            self.compatible = False
            self.features = []
            self.selected_features = set(self.service.profile.catalog.available_features)
            self.inspect_summary = None
            self.result = None
            self.phase = 'notice'
            self.revision += 1
        return self.snapshot()

    def acknowledge_notice(self, value):
        with self.lock:
            if self.busy or self.phase != 'notice' or type(value) is not bool:
                raise ValueError('当前不能更改阅读确认。')
            self.notice_acknowledged = value
            if not value:
                self.confirmed.clear()
                self.compatible = False
                self.features = []
                self.selected_features = set(self.service.profile.catalog.available_features)
                self.inspect_summary = None
            self.revision += 1
        return self.snapshot()

    def begin_preparation(self):
        with self.lock:
            if self.busy or not self.checked or not self.environment['ready'] or not self.notice_acknowledged:
                raise ValueError('请先阅读操作前须知，并通过启动检查。')
            self.phase = 'preparation'
            self.revision += 1
        return self.snapshot()

    def confirm(self, identifier, value):
        with self.lock:
            if self.busy or self.phase != 'preparation' or not self.environment['ready'] or not self.notice_acknowledged:
                raise ValueError('当前不能修改准备项。')
            if identifier not in {step.id for step in STEPS} or type(value) is not bool:
                raise ValueError('无效准备项。')
            self.confirmed.add(identifier) if value else self.confirmed.discard(identifier)
            self.compatible = False
            self.revision += 1
        return self.snapshot()

    def confirm_preparation(self, value):
        """One explicit human declaration for the four displayed settings."""
        with self.lock:
            if (self.busy or self.phase != 'preparation' or not self.checked
                    or not self.environment['ready'] or not self.notice_acknowledged
                    or type(value) is not bool):
                raise ValueError('请先阅读须知并完成启动检查。')
            self.confirmed = {step.id for step in STEPS} if value else set()
            self.compatible = False
            self.revision += 1
        return self.snapshot()

    def restart_preparation(self):
        """Release the current session before the user changes the connection."""
        with self.lock:
            if self.busy:
                raise ValueError('请等待当前操作结束。')
            if self.mode == 'physical':
                self.service.close_session()
            self.confirmed.clear()
            self.compatible = False
            self.features = []
            self.inspect_summary = None
            self.result = None
            self.phase = self._preparation_phase()
            self.revision += 1
        return self.snapshot()

    def disconnect(self):
        if self.mode == 'physical':
            raise ValueError('真实设备模式由每次操作重新建立连接，不支持模拟断开。')
        with self.lock:
            self.service.backend.connected = False
            self.confirmed.clear()
            self.compatible = False
            self.features = []
            self.selected_features = set(self.service.profile.catalog.available_features)
            self.inspect_summary = None
            if self.busy:
                self.cancel.set()
            else:
                self.phase = self._preparation_phase()
                self.result = None
            self.revision += 1
        return self.snapshot()

    def reconnect(self):
        if self.mode == 'physical':
            raise ValueError('真实设备模式由每次操作重新建立连接，不支持模拟重连。')
        with self.lock:
            if self.busy:
                raise ValueError('请等待当前操作结束。')
            self.service.backend.connected = True
            self.confirmed.clear()
            self.compatible = False
            self.features = []
            self.selected_features = set(self.service.profile.catalog.available_features)
            self.inspect_summary = None
            self.result = None
            self.phase = self._preparation_phase()
            self.revision += 1
        return self.snapshot()

    def cancel_operation(self):
        with self.lock:
            if self.busy:
                self.cancel.set()
            else:
                self.confirmed.clear()
                self.compatible = False
                self.features = []
                self.selected_features = set(self.service.profile.catalog.available_features)
                self.phase = 'notice'
            self.revision += 1
        return self.snapshot()

    def _feature_ids(self):
        return list(self.service.profile.catalog.available_features)

    def _require_selection_editable(self):
        if self.busy or self.phase != 'home' or not self.compatible:
            raise ValueError('请先完成只读检查并回到功能主页。')

    def set_feature_selection(self, identifier, value):
        with self.lock:
            self._require_selection_editable()
            if identifier not in self._feature_ids() or type(value) is not bool:
                raise ValueError('无效功能选择。')
            if value:
                self.selected_features.add(identifier)
            else:
                self.selected_features.discard(identifier)
            self.revision += 1
        return self.snapshot()

    def select_features(self, mode):
        with self.lock:
            self._require_selection_editable()
            ids = self._feature_ids()
            if mode == 'all':
                self.selected_features = set(ids)
            elif mode == 'none':
                self.selected_features = set()
            elif mode == 'missing':
                self.selected_features = {row['id'] for row in self.features
                                          if row['id'] in self._feature_ids() and row.get('state') != 'enabled'}
            elif mode == 'enabled':
                self.selected_features = {row['id'] for row in self.features
                                          if row['id'] in ids and row.get('state') != 'disabled'}
            else:
                raise ValueError('未知功能选择模式。')
            self.revision += 1
        return self.snapshot()

    def end_session(self):
        with self.lock:
            if self.busy:
                raise ValueError('请等待当前操作结束。')
            if self.mode == 'physical':
                self.service.close_session()
            self.compatible = False
            self.features = []
            self.inspect_summary = None
            self.result = None
            self.phase = self._preparation_phase()
            self.revision += 1
        return self.snapshot()

    def acknowledge_check(self):
        with self.lock:
            if self.busy or self.phase != 'home':
                raise ValueError('当前不能关闭检查结果。')
            self.inspect_summary = None
            self.revision += 1
        return self.snapshot()

    def _available_backups(self):
        # The desktop backup UI is hidden. Do not make ordinary connection
        # snapshots enumerate Documents (which may be offline/network-backed).
        # Explicit developer backup/restore commands still receive their list.
        if self.mode == 'physical' and self.action not in ('backup', 'restore'):
            return []
        try:
            rows = self.service.list_backups()
        except (OSError, ValueError):
            return []
        digest = self.service.profile.digest
        return [row for row in rows if row.get('profile_sha256') == digest]

    def reserve(self, action, backup_id=None):
        """Reserve on the transport thread before starting asynchronous work."""
        with self.lock:
            ready = assess(self.service.profile, self.confirmed, self.environment)['ready']
            if action not in ('inspect', 'unlock', 'close', 'backup', 'restore'):
                raise ValueError('未知操作；当前支持检查、解锁、关闭、功能状态备份与恢复。')
            if self.busy:
                raise ValueError('已有操作正在进行，不能重复启动。')
            if not self.checked or not ready or not self.notice_acknowledged:
                raise ValueError('请先阅读操作前须知，完成启动检查与相机准备。')
            if action != 'inspect' and not self.compatible:
                raise ValueError('请先完成只读兼容性检查。')
            if action in ('unlock', 'close', 'restore') and not self.selected_features:
                raise ValueError('请至少选择一个功能。')
            if action in ('unlock', 'close', 'restore') and not self.selected_features <= set(self._feature_ids()):
                raise ValueError('所选功能包含暂未开放的功能。')
            if action == 'restore':
                rows = self._available_backups()
                if not isinstance(backup_id, str) or not any(row['id'] == backup_id for row in rows):
                    raise ValueError('请选择一个本机功能状态备份。')
            elif backup_id is not None:
                raise ValueError('只有恢复操作可以选择备份。')
            self.cancel.clear()
            self.inspect_summary = None
            self.busy = True
            self.action = action
            self.backup_id = backup_id
            self.phase = 'running'
            self.result = None
            self.revision += 1

    def _display_progress(self, message):
        if self.mode != 'simulation':
            return message
        if '检查完成：预计修改' in message:
            return '模拟目标与兼容性检查完成。'
        if '个扇区；' in message:
            return '正在应用所选功能模拟修改，执行前再次检查状态。'
        if '结构守卫' in message:
            return '正在检查模拟设备与已有功能。'
        if '写入及独立回读通过' in message:
            return '模拟操作与独立核验完成。'
        if '备份已保存' in message:
            return '模拟功能状态备份已保存。'
        if '备份恢复及独立回读通过' in message:
            return '模拟恢复与独立核验完成。'
        return message.replace('相机', '模拟设备')

    def run_reserved(self, progress=lambda _message: None):
        with self.lock:
            if not self.busy:
                raise ValueError('没有已预约的操作。')
            action, backup_id = self.action, self.backup_id
            features = (sorted(self.selected_features)
                        if action in ('unlock', 'close', 'restore') else None)

        def checkpoint(message):
            progress(self._display_progress(message))
            if self.cancel.is_set():
                raise KeyboardInterrupt()

        result = self.service.perform(action, checkpoint, backup_id=backup_id, features=features)
        with self.lock:
            self.busy = False
            status = result['status']
            self.device_access = bool(result.get('device_access', self.mode == 'physical'))
            self.write_attempted = bool(result.get('write_attempted', False))
            if action == 'inspect' and status == 'inspected':
                self.compatible = result['plan']['compatible']
                self.features = result['plan']['features']
                self.selected_features = {row['id'] for row in self.features
                                          if row['id'] in self._feature_ids() and row.get('state') != 'enabled'}
                self.inspect_summary = dict(
                    compatible=self.compatible,
                    read_sectors=result['plan'].get('read_sectors'),
                    read_bytes=result['plan'].get('read_bytes'),
                    features=[dict(id=row['id'], name=row['name'], state=row['state'])
                              for row in self.features])
                self.phase = 'home'
                self.result = None
            else:
                self.compatible = (status in ('completed', 'restored', 'no-op', 'backup-completed')
                                   and result.get('verified', False))
                if action == 'backup':
                    self.features = result.get('features', result.get('plan', {}).get('features', []))
                else:
                    self.features = result.get('final_features', result.get('plan', {}).get(
                        'features', [])) if self.compatible else []
                title, detail = self.result_labels.get(status, ('操作未完成', '请重新检查状态。'))
                error = result.get('error', '')
                if self.mode == 'simulation':
                    error = error.replace('相机', '模拟设备')
                self.result = dict(status=status, title=title, detail=detail, success=self.compatible,
                                   error=error, simulation=self.mode == 'simulation',
                                   device_access=self.device_access, write_attempted=self.write_attempted,
                                   backup_path=result.get('backup_path', ''),
                                   backup_sha256=result.get('backup_sha256', ''),
                                   backup_id=result.get('backup_id', ''),
                                   cleanup_warning=result.get('cleanup_warning') or '',
                                   aftercare=build_aftercare(action, result, features,
                                                             self.mode == 'simulation'))
                if action in ('unlock', 'close'):
                    # The result remains visible, but its inspection cannot
                    # authorize another operation after a camera power cycle.
                    self.compatible = False
                self.phase = 'result'
            if not self.compatible:
                self.confirmed.clear()
            self.revision += 1
            self.last_report = result
        return self.snapshot()

    def operate(self, action, progress=lambda _message: None, backup_id=None):
        self.reserve(action, backup_id)
        return self.run_reserved(progress)

    def home(self):
        with self.lock:
            if self.busy or not self.compatible:
                raise ValueError('请先重新检查%s状态。' % ('模拟' if self.mode == 'simulation' else '设备'))
            self.phase = 'home'
            self.revision += 1
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            prepared = assess(self.service.profile, self.confirmed, self.environment)
            connected = self.service.backend.connected if self.mode == 'simulation' else self.service.connected
            backups = self._available_backups()
            return deepcopy(dict(revision=self.revision, phase=self.phase, scenario=self.scenario,
                scenarios=[dict(id=key, name=name) for key, name in self.scenarios.items()],
                environment=self.environment, checked=self.checked, steps=prepared['steps'],
                notice=operation_notice(), notice_acknowledged=self.notice_acknowledged,
                ready=prepared['ready'] and self.notice_acknowledged, compatible=self.compatible, connected=connected,
                features=[dict(row, selected=row['id'] in self.selected_features,
                               requires=next((f.get('requires', []) for f in
                                   self.service.profile.catalog.data['features'] if f['id'] == row['id']), []))
                          for row in self.features],
                inspect_summary=self.inspect_summary,
                backups=backups, backup_dir=str(self.service.backup_dir),
                busy=self.busy, action=self.action, result=self.result,
                simulation=self.mode == 'simulation', device_access=self.device_access,
                write_attempted=self.write_attempted))

    def _preparation_phase(self):
        return 'preparation' if self.checked and self.environment['ready'] and self.notice_acknowledged else 'notice'
