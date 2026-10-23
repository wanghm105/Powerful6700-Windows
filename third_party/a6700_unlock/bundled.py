"""Locate verified app resources without consulting developer paths or the network."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from .device_protocol import DeviceError


def resource_root():
    root = Path(__file__).resolve().parents[2]
    config = root / 'runtime.json'
    if not config.is_file():
        return None
    try:
        return root if json.loads(config.read_text()).get('kind') == 'bundled' else None
    except (ValueError, OSError) as exc:
        raise DeviceError('应用运行配置损坏，请重新获取完整应用。') from exc


def resource(name):
    """An app must use its own verified helper/library; source installs return None."""
    root = resource_root()
    if root is None:
        return None
    if name not in ('capture', 'libusb'):
        raise DeviceError('未知应用组件。')
    try:
        manifest = json.loads((root / 'bundle-manifest.json').read_text())
        if manifest['schema'] != 1:
            raise ValueError('schema')
        item = manifest['resources'][name]
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('path')
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('symlink')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('digest')
        return path
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise DeviceError('应用内置组件缺失或损坏，请重新获取完整应用。') from exc
