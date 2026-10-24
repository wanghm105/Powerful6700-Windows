# 架构：Windows 适配层

本程序**不 fork** 上游 `a6700_unlock`，而是把它原样放在 `third_party/a6700_unlock`
（GPL-3.0-only，自带 LICENSE 与清单），在启动时按需替换掉平台相关的那几个入口。这样做的好处
是上游的清单、校验、事务与回滚逻辑保持逐字节一致，Windows 差异集中在一个文件里。

## 分层

```
Powerful6700Win/
├─ src/a6700win/
│  ├─ __main__.py      命令行入口（GUI / --offline-self-test / --diagnose / --elevated-worker）
│  ├─ app.py           build_controller()：安装补丁 → 构造 DesktopController
│  ├─ patches.py       全部补丁点：设备层 + doctor + 载荷校验 + POSIX 兼容
│  ├─ windows_shim.py  POSIX 语义的 Windows 等价物：设备锁、目录落盘、二进制写、O_NONBLOCK
│  ├─ paths.py         可写数据目录探测、冻结/源码两套根路径
│  ├─ selftest.py      离线自检（不需要相机）
│  ├─ usb/
│  │  ├─ setupapi.py   纯 ctypes 的 SetupAPI 枚举（不需要管理员、不加载 libusb）
│  │  ├─ driver.py     libwdi 的 wdi-simple.exe：下载、参数、提权安装、轮询结果
│  │  └─ windows_auth.py  Windows 版 run_authentication：驱动准备 + 双阶段 Senser 认证
│  └─ gui/             PySide6 界面（须页/准备页/功能页/结果页/驱动页/诊断页）
├─ third_party/a6700_unlock/   上游运行时 0.2.0（只读，不改一行）
├─ packaging/          PyInstaller spec + 入口 + build.ps1
└─ tests/              pytest：SetupAPI 解析、wdi 参数、补丁幂等、载荷严格性、无头渲染
```

## 补丁点（`patches.install()`，共 27 项，可重复调用）

上游模块在自己的作用域里 `from … import name` 绑定了函数，所以必须**逐个模块**替换属性，
而不是只改定义模块：

| 补丁 | 原因 |
| --- | --- |
| `legacy.libusb_library_path` | 上游只有 Linux/macOS 分支，Windows 上必然抛错 |
| `legacy.get_libusb_backend` | 强制 `fresh=True`：PyUSB 1.2.1 永久缓存一个 context，而驱动切换后设备会重新枚举 |
| `legacy.run_authentication` | Windows 需要在打开设备前把 PID 绑定到 WinUSB，服务模式（0x0336）还要再来一次 |
| `legacy.observed_sony_product_ids` | 上游非 darwin 走 libusb 枚举；Windows 上改用 SetupAPI，驱动未绑定时也能枚举 |
| `legacy.normal_mode_observed` | 同上：靠 SetupAPI 判断是否回到 MSC 的 0x0E76 |
| `doctor.diagnose` | 上游 `platform` 检查是 `sys.platform in ('darwin','linux')`，Windows 恒 False → `environment.ready` 永远为假 |
| `preparation.diagnose` | `preparation.py` 在导入时绑定了 `diagnose`，只改 doctor 不生效 |
| `operations.default_state_dir` | 上游 non-darwin 返回 `~/.local/state/a6700-unlock`；改用程序记录目录，与界面显示的"记录目录"一致 |
| `usb.backend.payloads` / `doctor.payloads` / `desktop.controller.payloads` | 见 [UPSTREAM-NOTES.md](UPSTREAM-NOTES.md)：上游清单里的源码哈希与自身 `transaction.c` 不一致 |
| `operations.device_lock` | 上游直接 `import fcntl`，Windows 上抛 `DeviceError("设备执行目前支持 macOS／Linux；Windows 尚未验证")`，所有真实设备操作在碰相机之前就被拦下；改用 `msvcrt.locking` 保持"两把非阻塞独占锁"的语义 |
| `operations.host_lock_path` | 上游把 host 锁放在 `~/.local/state/sony-a6700-ftp/`，普通权限进程在 Windows 上建不出该目录（`WinError 5`）；改放程序数据目录，提权/非提权看到同一把锁 |
| `operations.make_directory` / `operations.save_json` / `backup._ensure_directory` / `backup._sync_file` | 上游对**目录**做 `os.open(dir, O_RDONLY)` + `os.fsync`，Windows 打开目录是 `PermissionError [Errno 13]`；改为递归建目录 + 对文件 fsync，`save_json` 仍用 `O_EXCL` 独占创建、绝不覆盖 |
| `planner.os.O_NONBLOCK` | `planner.LocalImage` 用 `os.O_NONBLOCK` 打开本地镜像，Windows 没有该常量（`AttributeError`）；换成带 `O_NONBLOCK=0` 的 os 代理 |
| `backup.os.O_BINARY` | `backup.py` 用 `os.open(..., O_WRONLY\|O_CREAT\|O_EXCL)` 写 `.a6700backup` 却没带 `O_BINARY`，Windows CRT 文本模式会把 0x0A 改写为 0x0D 0x0A，稀疏备份文件当场损坏 |
| `controller.run_reserved` | 上游 `run_reserved()` 没有 `try/except`：设备出错时异常冒到界面，`busy` 永远为 True，界面卡在"操作进行中"且按钮全灰 |
| `controller.reserve` | 恢复不读勾选，但上游 `reserve()` 会因为"没勾功能"提前拒绝；相机全开时 `selected_features` 为空，恢复永远点不动 |
| `operations._execute_session` / `operations._restore_session` | 设备返回 status=1（写前校验拒绝、零字节写入）时，上游把它归成 `verification-failed`，`rejected` 分支实际不可达；包一层改成 `rejected` |
| `controller.available_backups` | 上游在 physical 模式下除非当前动作已是 backup/restore 就返回空列表，而 `reserve('restore', id)` 先按该列表校验备份 ID 才设置 `self.action` → 桌面端恢复永远不可用；改为照常枚举程序自己的备份目录并按 `profile.digest` 过滤 |
| `controller.restore_scope` | 上游对 restore 也传 `features=sorted(self.selected_features)`，`restore_plan()` 只写回勾选功能；「恢复整份备份」应整份写回，故调用前临时把选择扩到全部已开放功能，调用后还原 |
| `device_profile.inspect_sectors` / `operations.inspect_sectors` | /usr（nflasha15，ext2）里有 9 个结构守卫扇区落在 inode 表上，相机自己会刷新 inode 的 atime/ctime/mtime，导致什么都没做也判 blocked；豁免表 `src/a6700win/data/guard-overlay.json` 只放行每个 inode 记录里的 12 字节时间戳（并同时把期望哈希换成清零后的值），mode/size/blocks 与其余字节仍逐字节校验。归一化**只用于比对**：返回的写入目标会把时间戳按相机原值补回，否则 `device_protocol.request()` 会把这 12 字节判成越界修改、在发 USB 之前整单拒绝（0.3.1 的写入失败即此）|

补丁全部幂等（用 `_a6700win_wrapped_*` 标记与身份比较），`install()` 返回
`{applied, already, libusb, driver}`，自检和「关于与诊断」页都会展示。

## 一次真实操作的顺序

```
SetupAPI 枚举 → 驱动准备（0x047D/0x0E76 → WinUSB）
  → 打开 MSC 设备 → claim interface → START_SENSER + 3 轮挑战（0x0336 用 PMCA 的 keys）
  → 关闭并等待服务模式设备 0x0336 出现 → 再次驱动准备 → 再次认证
  → SenserChannel：0x4010 下发 config → 0x4007 传 reader/writer → 0x4008 执行
  → 结果按 completed / no-op / blocked / rolled-back / uncertain / verification-failed /
    recovery-required 分类
  → 结束时 STOP_SENSER（strict）；未确认则提示拔插 USB，并再查一次是否已回到 0x0E76
```

相机侧载荷是 freestanding 的 aarch64 共享对象（`reader.elf` / `writer.elf`，无 PT_INTERP），
与宿主操作系统无关，因此 Windows 端只要把**字节原样送出**即可，协议与载荷都不需要移植。

写事务的返回码与上游一致：1 preimage 变化、2 非法请求、3 打不开分区、4 读短、5 写失败、
6 fsync 失败、7 回读不一致、8 回滚不完整。任何一个已知字段、守卫或未管理字节不符即阻断，
没有强制开关。

## 界面与状态机

界面不自己发明状态：它只渲染上游 `DesktopController.snapshot()` 的字典，并把用户点击翻译成
`controller.*` 调用。阶段固定为 `notice → preparation → (running) → home | result`；长任务在
`QThread` 里跑，进度经 signal 回到界面，取消走 `controller.cancel_operation()`。
