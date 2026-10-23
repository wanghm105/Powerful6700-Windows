"""Synthetic device adapter using the real planner and transaction engine.

No USB imports, device handles, real firmware sectors or physical-device locks.
Addresses below belong to a synthetic catalogue, never the camera catalogue.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..backup import find_backup, list_backups, load_backup
from ..catalog import Catalog
from ..device_profile import DeviceProfile, inspect_sectors
from ..device_protocol import DeviceError
from ..operations import _backup_session, _execute_session, _restore_session


SCENARIOS = {
    'enabled': '已完整解锁',
    'original': '尚未解锁',
    'partial': '已有 FTP，待补快门功能',
    'disconnected': '设备未连接',
    'environment-missing': '环境组件缺失',
    'incompatible': '内容不兼容',
    'communication': '模拟通信中断',
    'verification': '模拟独立回读失败',
    'rollback': '模拟写入失败并回退',
}


def fixture():
    """Small public test data, sufficient for both managed feature states."""
    digest = hashlib.sha256(bytes(512)).hexdigest()
    features = [dict(id='ftp', name='原生 FTP'), dict(id='shutter', name='关机快门帘与静音联动'),
                dict(id='exposure', name='灵活曝光'), dict(id='sound', name='电子快门声音'),
                dict(id='pixel_shift', name='位移多帧合成'), dict(id='dynamic_active', name='动态增强防抖')]
    for feature in features:
        feature['available'] = feature['id'] not in ('pixel_shift', 'dynamic_active')
        if not feature['available']:
            feature['unavailable_reason'] = '开发与验证尚未完成，0.1 测试版暂不开放'
    edits = [dict(id=f'demo-{feature}-{image}', image=image, offset=offset,
                  disabled='00', enabled='01', known_values=['00', '01'],
                  feature=feature, purpose='synthetic preview field')
             for image in ('app', 'wbi') for feature, offset in [('ftp', 10), ('shutter', 20), ('exposure', 30), ('sound', 40), ('pixel_shift', 50), ('dynamic_active', 60)]]
    catalog = Catalog.from_dict(dict(schema_version=1, catalog_id='synthetic-desktop-preview',
        bundle_version='preview', model='Synthetic A6700', firmware='preview', sector_size=512,
        scope='offline-known-snapshot-only', device_write_supported=False,
        features=features, images={name: dict(size=512, normalized_sha256=digest, view='synthetic')
                                   for name in ('app', 'wbi')}, edits=edits))
    entries = [dict(index=i, role='target', image=name, file_offset=0, device=i,
                    device_offset=0, unmanaged_sha256=digest,
                    edit_ids=[edit.id for edit in catalog.edits if edit.image == name])
               for i, name in enumerate(('app', 'wbi'))]
    entries.append(dict(index=2, role='guard', device=0, device_offset=512, sha256=digest))
    profile = DeviceProfile.from_dict(dict(schema_version=2, profile_id='synthetic-desktop-preview',
        hardware_validation='synthetic-only', catalog_sha256=catalog.digest, sector_size=512,
        devices=['/dev/nflasha15', '/dev/nflasha5'], entries=entries), catalog)
    return profile, [bytes(512)] * len(entries)


class MemoryDevice:
    def __init__(self, profile, sectors, scenario):
        self.profile = profile
        self.sectors = list(sectors)
        self.connected = scenario != 'disconnected'
        self.scenario = scenario
        self.failed_once = False
        self.writes = 0
        self.cleanup_warning = None
        self.cleanup_status = 'simulation-only'

    def __enter__(self):
        if not self.connected:
            raise DeviceError('模拟设备未连接。请切换到已连接的场景后重新准备。')
        return self

    def __exit__(self, *unused):
        pass

    def read(self, nonce):
        if not self.connected:
            raise DeviceError('模拟连接已断开，请重新准备并检查状态。')
        data = list(self.sectors)
        if self.scenario == 'verification' and self.writes and not self.failed_once:
            self.failed_once = True
            data[0] = bytes([data[0][0] ^ 1]) + data[0][1:]
        return data

    def write(self, before, after, nonce):
        if not self.connected:
            raise DeviceError('模拟连接已断开。')
        self.writes += 1
        if self.scenario == 'rollback' and not self.failed_once:
            self.failed_once = True
            return dict(status=5, error='模拟写入失败', touched=1, rolled_back=True,
                        failed_index=0, sectors=[])
        self.sectors = list(after)
        if self.scenario == 'communication' and not self.failed_once:
            self.failed_once = True
            raise DeviceError('模拟写入后丢失响应；没有自动重发。')
        return dict(status=0, error=None, touched=sum(a != b for a, b in zip(before, after)),
                    rolled_back=False, failed_index=None, sectors=[])


class SimulationService:
    def __init__(self, directory, scenario='enabled'):
        if scenario not in SCENARIOS:
            raise ValueError('Unknown simulation scenario')
        self.profile, sectors = fixture()
        if scenario == 'enabled':
            _, sectors = inspect_sectors(self.profile, sectors, 'unlock')
        elif scenario == 'partial':
            for index in (0, 1):
                block = bytearray(sectors[index]); block[10] = 1; sectors[index] = bytes(block)
        elif scenario == 'incompatible':
            sectors[2] = b'X' + sectors[2][1:]
        self.backend = MemoryDevice(self.profile, sectors, scenario)
        self.directory = Path(directory)
        self.backup_dir = self.directory / 'backups'
        self.scenario = scenario

    def list_backups(self):
        return list_backups(self.backup_dir)

    def perform(self, action, progress=lambda _: None, backup_id=None, features=None):
        if action not in ('inspect', 'unlock', 'close', 'backup', 'restore'):
            raise ValueError('Unsupported preview operation')
        # This service is never shared by two operations: the desktop controller
        # serializes commands. Only in-memory device data can be changed here.
        if action == 'backup':
            result = _backup_session(self.profile, self.backend, self.backup_dir,
                                     self.directory, progress)
        elif action == 'restore':
            source = load_backup(find_backup(self.backup_dir, backup_id), self.profile)
            result = _restore_session(self.profile, self.backend, source,
                                      self.directory, progress, features=features)
        else:
            result = _execute_session(self.profile, self.backend, action,
                                      self.directory, progress, features=features)
        result['simulation'] = True
        result['simulated_write_attempted'] = result['write_attempted']
        result['write_attempted'] = False
        result['device_access'] = False
        return result
