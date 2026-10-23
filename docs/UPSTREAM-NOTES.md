# 上游说明与已知偏差

## 1. 上游清单的源码哈希已过期（本项目做了降级处理）

`third_party/a6700_unlock/usb/backend.py` 的 `payloads(profile)` 会校验三件事：

1. `data/native/manifest.json` 里的 `profile_sha256` == `profile.digest`；
2. `native/transaction.c` 的 sha256 == 清单里的 `source_sha256`；
3. `data/native/reader.elf`、`writer.elf` 的 sha256 与字节数 == 清单里的值。

实测（vendored 副本与 `refs/a6700-powerful/应用/src/a6700_unlock` 逐字节相同）：

| 项 | 结论 |
| --- | --- |
| `profile.digest` | `c20d1b9ba7114ef1bc3cff3ae1787b5334ac899cc8f3aa806ec3bea3039db82f` = 清单值 ✅ |
| `reader.elf` | `88491c37c20fa4324023613e1980fd970adf79dd44ad4d7771afa43b9c9e4ece` / 26992 B ✅ |
| `writer.elf` | `17d852656848faefae6743ebc79456c3d2d0212c7f0058311145a4954a8255a4` / 27088 B ✅ |
| `transaction.c` | 实际 `f21342ab22688f98455e03d93a7fca9fc29a420cd6757e445496c21fa8bb60ef`，清单写 `53cd3393c07dfdb7a219cf73906862ac389df9d853a90d762deec777c0e37e82` ❌ |

对 `refs/a6700-powerful` 下所有小于 2 MB 的文件做过哈希扫描，**没有任何文件**的 sha256 等于
清单里的 `53cd3393…`：这说明上游发布时清单早于它自己的 `transaction.c`，属于发布缺陷，
不是移植过程中的篡改或缺文件。

上游把这条不一致变成硬失败（`DeviceError('Native source changed without rebuilding payloads and manifest')`），
结果是 `doctor` 的 `payload-integrity` 恒 False → `environment.ready=False` →
`acknowledge_notice` / `begin_preparation` / `reserve` 全部被拒，整个程序在 Windows（以及任何平台
的新克隆上）都走不到第二步。

本项目 `patches.windows_payloads()` 的处理：

- **保持严格**：清单可读、`profile_sha256` 相等、两个 ELF 的 sha256 与字节数全部相等，任何一条
  不满足仍然抛 `DeviceError`（文案沿用上游，如 `Packaged writer payload hash mismatch`）；
- **降级为溯源信息**：源码文本哈希只记录 `{expected, actual, matches, checked}`，通过
  `patches.status()['payload_source']`、「关于与诊断」页和自检展示，不再阻断。

依据：真正送进相机的是两个 ELF 与 260 扇区的 profile，这两者的校验依旧全严；源码文本哈希
只影响「载荷是否由这份源码构建」的可追溯性，而这一条在上游仓库里已经不成立了。

## 2. 上游只有 macOS 打包

`应用/desktop/macos/` 是 SwiftUI 外壳（`A6700Preview`、`WorkspaceView`、`OperationViews` 等），
由 `scripts/build_macos_app.py` 打包成 .app，并附带 `native/mac_capture.m` 用 IOKit/IOUSBHost 抢
设备。这些在 Windows 上既不能编译也没有意义，因此本项目：

- 用 PySide6 重写外壳（`src/a6700win/gui/`），状态机仍由上游 `DesktopController` 承担；
- 用 `setupapi.py` + libwdi 的 `wdi-simple.exe` 取代 `mac_capture.m` 的「抢设备」路径；
- 不用上游的 `desktop/worker.py` + line-JSON bridge（那是给 SwiftUI 子进程用的），Windows 端
  在进程内直接持有 controller。

## 3. 未移植/未实现的功能

- 上游 `docs/动态增强防抖.md` 描述的位移多帧合成与动态增强防抖：上游自己就处于关闭状态；
- 完整备份 / 固件恢复：上游只做到「功能状态稀疏备份」；
- `usb/legacy.py` 的 CLI 自测入口（`self_test`、`run_auth_command` 等）：属于 macOS 调试工具。

## 4. 与上游 0.2.0 的同步（2026-10-23）

上游在 `42f67b3`「发布 0.2 版，修复 USB 连接并优化交互」里改了这些地方，本项目的
`third_party/a6700_unlock` 已整目录同步到该版本（`__version__ = "0.2.0"`）：

- `usb/legacy.py`：新增 `_OwnedLibUSB` 与 `reset_libusb_backend()`，把后端对象钉在
  PyUSB 的 `_Device` / `_DevIterator` 上，避免上下文先于设备被回收；`iter_usb_devices(*, fresh=False)`
  新增 `fresh` 参数。本项目的 `get_libusb_backend` 补丁仍然一律 `fresh=True`（驱动切换后必须重新枚举），
  现在它返回的是 `_OwnedLibUSB`，上下文生命周期由 PyUSB 自己管。
- `desktop/physical.py`：`unlock` / `close` 结束后主动 `close_session()`（写完后本来就要断电重启），
  退出失败时把 `cleanup_status='unconfirmed'` 写进结果，而不是把已记录的回读结果丢掉。
- `desktop/aftercare.py`（新文件）：写入成功后给出「断电重启 6 步 + 每个功能的菜单验收路径」。
  本项目界面的「机身验收」卡片直接渲染上游这份数据，没有自己发明文案。
- `desktop/controller.py`：结果里新增 `aftercare` 与 `cleanup_warning`；写入成功后把
  `compatible` 置 False（断电重启后旧的只读检查不再授权新操作）。
- `notice.py`：须知文案更新为 0.2 的表述；`PHYSICAL_RESULT_LABELS['completed']` 改为
  「写入与独立回读通过，待机身验收」。

补丁面没有变化：20 个补丁点仍然全部有效（`pytest` 25 passed）。上游 0.2 **仍然没有** Windows
分支——`libusb_library_path()` 只有 Linux 与 macOS 两个分支，`doctor` 的 platform 检查仍然是
`sys.platform in ('darwin','linux')`，所以本项目的那几个补丁依旧是必需的。

