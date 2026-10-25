# AI-HANDOFF · 交接现场

> **用法**：换一个对话、换一个人、或者上下文爆了，**只看这一个文件**就能接着干。
> **规则**：每完成一小步（一次真机写入、一次构建、一次结论），**先改这里再往下走**；末尾「更新记录」按时间追加一行。
> **最后更新**：2026-10-25 17:55（Australia/Brisbane）

---

## 目录

1. [项目是什么](#1-项目是什么)
2. [一句话现状](#2-一句话现状)
3. [工程结构与环境](#3-工程结构与环境)
4. [已验证能力清单](#4-已验证能力清单)
5. [Windows 侧技术路线（为什么这么写）](#5-windows-侧技术路线为什么这么写)
6. [相机侧协议与物理基础](#6-相机侧协议与物理基础)
7. [颜色子系统（CP 单元）](#7-颜色子系统cp-单元)
8. [颜色拟合现状（正在做的事）](#8-颜色拟合现状正在做的事)
9. [菜单文字子系统（已完成）](#9-菜单文字子系统已完成)
10. [当前真机状态（接手先复核）](#10-当前真机状态接手先复核)
11. [踩过的坑（照抄，别重犯）](#11-踩过的坑照抄别重犯)
12. [待办与下一步的具体做法](#12-待办与下一步的具体做法)
13. [已知限制与能力边界](#13-已知限制与能力边界)
14. [历史调查结论（省得重做）](#14-历史调查结论省得重做)
15. [文件地图](#15-文件地图)
16. [未提交改动](#16-未提交改动)
17. [更新记录](#17-更新记录)

---

## 1. 项目是什么

把上游 **`xyzhangxin/sony-a6700-powerful`**（A6700 固件 2.00 的非官方解锁工具，GPL-3.0，**只支持 macOS arm64**）做成一个 **Windows 桌面工具**，完整度对齐 **`QAQLeonard/a7c2-fl23`**（A7C2 的逆向研究工程：能读能写、有 GUI、有备份还原、有文档）。

产物：`Powerful6700 · Windows`（PySide6 GUI + PyInstaller 单目录包），不是「脚本合集」。

功能面：只读兼容性检查 → 功能解锁/关闭 → 功能状态备份还原 → 自定义外观（颜色 + 菜单文字）→ 操作结果 → 驱动准备 → 关于与诊断。

许可：GPL-3.0，随包带 `NOTICE` / `THIRD_PARTY_NOTICES`（从上游复制）。

---

## 2. 一句话现状

**主链路全部真机打通**：只读检查、功能解锁关闭、功能状态备份还原、CP 外观色度写入与逐字节还原、菜单文字改写与还原（英文名 / 中文名两套，都验过）。
**当前正在做**：外观颜色对 A7C2 直出的**定量拟合**——卡在两点：① 蓝端压不下去（旋钮在矩阵单元，未标定）；② 「名字+颜色一键写」还没做成产品功能（技术上必须拆两个会话）。

---

## 3. 工程结构与环境

### 3.1 路径

下表用 `<repo>` 表示本仓库根目录，`<workspace>` 表示它在磁盘上的上级目录。

| 用途 | 路径 |
|---|---|
| 工程（写） | `<repo>` |
| 上游只读参考 | `<workspace>/refs/a6700-powerful` |
| A7C2 只读参考 | `<workspace>/refs/a7c2-fl23` |
| 固件/素材/备份 | `<workspace>/firmware`（`cp/` `uxc/` `lut/` `photos/`） |
| 运行时数据 | `.data`（可用 `POWERFUL6700_DATA` 覆盖） |
| 基线与日志 | `.data/looknames/`、`.data/backups/`、`.data/run/`、`.data/flash-log/` |
| 冻结包 | `dist/Powerful6700/Powerful6700.exe` |

上游 vendored 代码在 `third_party/a6700_unlock`（不改源，靠 `src/a6700win/patches.py` 打补丁）。

### 3.2 Python 环境

- `.venv`（Python **3.12.3**）：`pyusb 1.3.1`、`libusb-package 1.0.30.0`、`PySide6-Essentials 6.8.3`、`pytest 8.3.5`、`numpy`、`rawpy`
- **没有** PIL / cv2 / imageio → 读 JPEG 一律 `PySide6.QtGui.QImage`（`convertToFormat(Format_RGB888)` + `constBits()` + `bytesPerLine` 切片）
- 安装坑：pip 走阿里云镜像会挂、pypi 建索引也卡 → 用 urllib 直连 `files.pythonhosted.org` 下 wheel 再 `--no-index` 装

### 3.3 每次跑命令的前置

```powershell
cd '<repo>'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='<repo>\src'
$env:POWERFUL6700_DATA='<repo>\.data'
.\.venv\Scripts\python.exe <脚本>
```

- 不设 `PYTHONPATH` → `ModuleNotFoundError: No module named 'a6700win'`
- 不设 `PYTHONIOENCODING` → GBK 控制台把中文日志打成乱码/抛异常
- GUI 渲染（`--render-pages`）还需要 `QT_QPA_FONTDIR=C:/Windows/Fonts`，否则中文全是方块

### 3.4 测试与构建

```powershell
# 测试（最近一次：86 passed / 1 skipped）
.\.venv\Scripts\python.exe -m pytest tests -q

# 打包（内部先 pytest，再 PyInstaller，再 --offline-self-test）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

构建注意：
1. `build.ps1` **会清空 dist** → 重建后必须重新 seed 基线库（§9.4）。
2. pwsh 退出码常是 **1**（CLIXML/stderr 噪音），成败看末尾「完成…（自检通过，x.y.z）」那行。
3. PyInstaller 的 `pefile` 必须显式钉 **2023.2.7**（新版被它排除）。
4. 冻结包自检九项：python / platform / vendor `a6700_unlock` / files / data-dir / libusb / setupapi / wdi / controller。
5. 窗口化 exe 无 tty 时用 `AttachConsole(-1)` 取回 stdout。

---

## 4. 已验证能力清单

| 能力 | 入口 | 真机证据 |
|---|---|---|
| 只读兼容性检查（260 扇区 / 133,120 字节） | GUI 相机准备 | 多轮通过，`docs/VALIDATION.md` |
| 功能解锁 / 关闭（FTP、快门声、灵活曝光…） | GUI 功能管理 | 实拍验证，`docs/VALIDATION.md` |
| 功能状态备份 / 恢复 | GUI 功能管理 | 备份文件 SHA-256 记录在案；恢复曾需两个补丁（隐藏门闸 + 选择面扩到全部） |
| CP 外观色度写入 / 逐字节还原 | GUI 自定义外观 / `tools/looks_apply.py` | 回读一致 + `/setting/BACKUP.BIN` 三方比对 |
| 菜单文字改写 / 还原（official / zh 两套） | GUI 自定义外观 → 菜单文字卡片 | 英文名 145,708 B、中文名 145,692 B 都在相机菜单里显示正确；还原回出厂 145,612 B |
| 写 `/usr` 文件 | `src/a6700win/flash.py` + `native/flash_write.elf` | 已真机写、断电持久 |
| 写 `/cp`、`/setting` 文件 | 同上（`WRITABLE_ROOTS`） | 代码已完成并重编，**`/setting` 分支尚未真机跑过** |
| 载荷自检 / 零变化写探测 | `tools/flash_write.py --probe` | 通过 |
| 离线自检、页面离屏渲染 | `Powerful6700.exe --offline-self-test / --render-pages` | 通过（九项 + 7 张 PNG） |

**结果类别**（GUI 与日志统一用这套词）：`completed` / `no-op` / `blocked` / `rolled-back` / `uncertain` / `verification-failed` / `recovery-required`。

---

## 5. Windows 侧技术路线（为什么这么写）

- **USB 绑定**：SetupAPI 枚举 PnP → 用 libwdi 的 `wdi-simple.exe` 把相机接口绑到 **WinUSB** → `pyusb` + `libusb-package` 自带的 `libusb-1.0.dll`。纯 MTP/HID 驱动下 pyusb 拿不到 bulk 端点。
- **提权**：`ShellExecuteExW` + `runas`（绑驱动需要管理员）；提权与非提权进程**必须落到同一个数据目录**，否则状态读写分裂。
- **上游移植**：上游对 `sys.platform` 硬编码 darwin/linux，Windows 上 doctor 恒 False → `src/a6700win/patches.py` 统一补丁（`patches.install()` 实测 **30 项**：applied 28 + already 2），覆盖 legacy 的 libusb 路径/backend/auth、doctor、preparation、usb.backend.payloads、operations 的锁与目录、`planner.os.O_NONBLOCK`、`backup.os.O_BINARY`、`controller.run_reserved` 等。
- **为什么用属性替换**：vendored 的 bridge 不传 `backend_factory`，只能替换模块属性。
- **POSIX 语义**：`src/a6700win/windows_shim.py` 提供 `host_lock_path` / `default_state_dir` / `make_directory` / `sync_file` / `save_json`（`O_BINARY` 防 `0x0A`→`0x0D0A` 损坏稀疏备份）、`device_lock`（`msvcrt.locking` 锁首字节）、`OsProxy`（给 `planner.os` 补 `O_NONBLOCK=0`、给 `backup.os` 补 `O_BINARY`）、`wrap_run_reserved`（异常时清 busy/回 phase）。

### 5.1 相机侧 PID 与驱动状态

| PID | 含义 | 驱动 |
|---|---|---|
| `0x0E76` | 海量存储 MSC（正常操作入口） | `USBSTOR` / 绑 WinUSB 后 `winusb` |
| `0x0E8A` / `0x0336` | 服务模式（认证后切过来） | **无驱动**（`CM_PROB_FAILED_INSTALL`）→ 需 `wdi` 绑 WinUSB |
| `0x096F` | HID / HidUsb（掉线后常见落点） | `HidUsb`，**不是 MSC，救不回来** |

`src/a6700win/usb/windows_auth.py` 里 `_wait_service()` 会在认证后先轮询 SetupAPI 等 `0x0336`、用 wdi 绑 WinUSB，再交给 libusb；`_recover_service_mode()` 处理相机卡在 `0x0336` 的情况（认证 + vendored `STOP_SENSER` 退出）。

---

## 6. 相机侧协议与物理基础

### 6.1 基本帧与命令

- Senser 头 12 字节：`'<IHHBBBB'`
- `0x10` ProductInfo、`0x40` 命令通道
- 命令流程：`0x4010` config → `0x4007` ident2 + ELF 载荷 → `0x4008` 执行
- 固定读写窗口：**260 扇区 / 133,120 字节**（只读检查、功能状态备份都在这个窗口内）
- 文件访问走 **Jiritsu 文件命令**（A7C2 的 cmd 15/16/17/18）：open/read/write/close，路径 + 偏移 + 长度

### 6.2 挂载表（从 initrd 的 fstab 挖出）

| 分区 | 挂载点 |
|---|---|
| nflasha2 | `/setting` |
| nflasha3 | `/system` |
| nflasha8 | `/cp` |
| nflasha10 | `/tmp` |
| nflasha11 | `/log` |
| nflasha12 | `/cert` |
| nflasha15 | `/usr`（ext2，ro 挂载但可写） |
| nflasha18 | `/lens` |

### 6.3 写入载荷（自研）

- 源码 `native/flash_write.c`，交叉编译：`zig cc -target aarch64-freestanding -fPIC -O2 -ffreestanding -fno-builtin -fno-stack-protector -c` + `zig ld.lld -shared -Bsymbolic -z noexecstack`
- 编译前必须把 `ZIG_GLOBAL_CACHE_DIR` / `ZIG_LOCAL_CACHE_DIR` 指到 `.data/zig-cache`（否则 AccessDenied）
- 内联 `svc #0` 必须声明 `"cc"` clobber
- 当前产物：`native/flash_write.elf` **74,040 B**，sha256 `94b45897f48b26d606cc41d2b3fee3e74bd1c767a3eef0553c57df246d022c6c`（带 `/setting` 支持，**未跑过真机**）
- 只读版 `native/dump_range.elf` 18,528 B（模式 2 = `getdents64` 目录列举）
- 载荷模式：0 读 / 1 长度 / 2 列目录 / 3 写 / 4 零变 probe / 5 顺序 probe / 6 顺序写 / 9 临时目录自测 / 10 截断；状态码 0..14（12 = 范围超出文件长度，6 = 路径不在白名单）
- 可写白名单：`/usr/`、`/cp/`、`/setting/`；拒绝 `/../` 与 `/dev/`
- 写大文件流程：先 `truncate` 到目标长度（`SYS_FTRUNCATE=46`，可扩零延长）→ 按 `0x8000` 分块 `write_block` → 整份回读比对
- 硬教训：**fsync 后 close，再用独立 O_RDONLY 句柄回读**（拿 `O_WRONLY` 句柄 `pread` 必然 EBADF / -9）

---

## 7. 颜色子系统（CP 单元）

### 7.1 单元布局（A6700）

| 单元 | 大小 | 结构 |
|---|---|---|
| `0x02A40001`（色度） | 8,192 B | 参数表 @`0x1200`（`0x1200 + N*2`，N=40..49 是外观 profile 号）；色度记录 @`0x1250 + bank*64`，每条 **64 B = 12 组 `(Cb,Cr)` int16 + 尾 8 个 0** |
| `0x02A4000D`（矩阵） | 28,672 B | 参数 @`0x196`；矩阵 @`0x1e0 + slot*768` |

出厂 profile 号：`[16, 8, 14, 10, 12, 9, 15, 11, 13, 19]`（外观 0..9）。

### 7.2 外观 ↔ bank（实测，通道置换验证过）

| 外观 | 菜单 | 色度 bank |
|---|---|---|
| ST 标准 | ST | 0 |
| VV 鲜艳 | VV | 1 |
| NT 中性 | NT | 4 |
| PT 人像 | PT | 6 |
| FL 影视 | FL | 8 |
| SE 棕褐 | SE | 9 |
| VV2 鲜艳2 | VV2 | 14 |
| BW 黑白 | BW | 无独立色度 |

- 菜单 16 项顺序：`ST, PT, NT, VV, VV2, FL, IN, SH, BW, SE, 1ST, 2FL, 3IN, 4SH, 5VV2, 6BW`
- 后 6 个「自定义外观」**是内建外观的别名**，没有独立颜色 bank（bank0 改粉 → ST 与 1ST 同时变）
- 色度 bank 由**外观序号**决定，与 profile 号无关
- 出厂副本：`.data/../firmware/cp/unit-02a40001.backup-def.bin`（sha `72d3da868cc0`）、`unit-02a4000d.backup-def.bin`（sha `59aed2edd1b0`）

### 7.3 持久化语义（关键）

- CP 单元是 **RAM**；**正常关机时相机把它写进 `/setting/BACKUP.BIN`**（色度 @`0x1B2140` 8192 B、矩阵 @`0x1B6870` 28672 B），开机读回。
- **关机后立刻开机 → 改动丢**；**正常关机等满 1 分钟再开机 → 稳定落盘**（2026-10-25 实测：内存与 BACKUP 都是 `72d3da868cc0`，0 字节差异）。
- 只还原 RAM 不还原 BACKUP → 「当场对、重启又变」。
- 复位到出厂的正确顺序：逐单元比对出厂副本 → 写回 RAM → **正常关机再开机**让相机覆盖 BACKUP。

### 7.4 协议入口

```
cp_read  = (0x603, 0x40, pack('<II', key, 1))   # 读单元，额外要吃 0x200 结束包
cp_write = (0x603, 0x41, ...)                   # 写单元
```

`src/a6700win/cp.py` 的 `CpChannel` 提供 `read_unit` / `write_unit`；`session(progress)` 带**会话冷却**（见 §11.1）。

---

## 8. 颜色拟合现状（正在做的事）

### 8.1 目标向量（A7C2 直出，19 张对照图 × 72 样本中位色度比）

```
CC：0.77 0.81 0.74 0.48 0.61 0.62 0.69 0.83 0.99 1.06 0.76 0.53
NC：0.63 0.79 0.34 0.58 0.67 0.74 0.91 0.77 0.91 0.85 0.63 0.44
PF：0.86 0.88 1.16 0.63 0.66 1.03 1.18 0.79 0.62 0.75 0.69 0.64
NF：1.46 1.10 0.58 0.38 0.71 0.83 0.87 0.86 0.97 0.72 0.35 0.23
```

12 档 = 每 30° 一段：`0-30` 蓝 / `30-60` 蓝紫 / `60-90` 紫红 / `90-120` 红 / `120-150` 橙 / `150-180` 黄 / `180-210` 黄绿 / `210-240` 绿 / `240-270` 绿青 / `270-300` 青 / `300-330` 青蓝 / `330-360` 蓝。

### 8.2 指标口径

```
s   = Σ(m·t) / Σ(m·m)          # 最优整体缩放
RMS = √(mean((s·m − t)²))      # 逐档误差
矫正率 = 1 − RMS
```

`docs/LOOKS.md` §9 记录值 → 矫正率：CC **81.7%**、NC **82.7%**、PF **81.1%**、NF **67.0%**（见 `docs/CALIBRATION.md`）。

### 8.3 已测配方（单场景，CC）

| 配方 | 写入指令 | RMS |
|---|---|---|
| pair2×0.35 | `--look "CC=6:6:1.00@2*0.35"` | 0.259 |
| **pair2×0.52**（旧定稿） | `--look "CC=6:6:1.00@2*0.52"` | 0.194 |
| **pair2×0.60 + pair6=0**（现用） | `--look "CC=6:6:1.00@2*0.60,6*0.00"` | **0.164** |
| pair2×0.56 + pair7/10/11×0.40 | 卷4 | 0.178 |
| pair2×0.70 / 0.85 | `@2*0.70` / `@2*0.85` | 未测（观感更浓，中段更低于目标） |

工具：`tools/look_write.py`，语法 `菜单名=目标bank:基底bank:系数[@pair*系数,...]`，必须 `--confirm yes-write`。
其它配方（定稿）：NT bank4 `1.00@2*0.62`、PF bank1 `1.00@2*0.75`、NF bank14 `1.00@2*0.85`（PF/NF 只做低饱和版）。

### 8.4 蓝端结论（别再重复试错）

- **色度记录这层压不动**：`pair1×0.40` 把青蓝从 1.07 推到 **1.37**（方向反）；`pair7/10/11×0.40` 只到 1.08（组效应、边际）；同参数不同轮次蓝端自己在 0.95–1.20 晃。
- **旋钮在矩阵单元 `0x02A4000D` 的 block 4**：整块填 20000 时，PT 蓝 0–30° 档到 **6.20 倍**，其余档 ≤1.68 → 有把手，但只做过粗暴整块填充，**没做块内二分/线性范围标定**。
- CC 实测 `0.95 / 1.06` vs 目标 `0.77 / 0.53` 是 RMS 的大头；中段（60–270°）在 0.52 时误差只有 0.03–0.09。

---

## 9. 菜单文字子系统（已完成）

### 9.1 资源格式（UXC v7）

- 路径：`/usr/share/app/string_simplifiedchinese_f.uxc`
- 出厂：**145,612 B**，sha256 `fe263360c15b5530508bf7b098c96ec39cd4c38536b23653d15e6ea977b80e42`，**4,785 条**记录，`base = 0x2574`
- 结构：
  ```
  magic  b'uxc\x07\0\0\0\0'
  u16    kind = 8
  u16    group
  u32    descriptor = count | (((count+1) & ~1) << 12)
  [16]   count 个 u16 索引（0xFFFF = 空槽）
  base   (16 + count*2 + 3) & ~3，记录区
  记录   u32(0x1E000000 | rid & 0xFFFFFF) + UTF-8 + NUL + 补齐到 4
  rid    0x02000000 | ((group << 13) + index)
  ```
- 记录可用容量 = 下一条记录起始 − 本记录 − 4（**按 NUL 算会低估**）

### 9.2 外观文字的两条记录（改名必须一起改）

| 外观 | rid |
|---|---|
| ST | `0x021C658E` |
| PT | `0x021C6654`、`0x021C6F8B` |
| NT | `0x021C6434`、`0x021C7002` |
| VV | `0x021C687B`、`0x021C6F80` |
| VV2 | `0x021C689A`、`0x021C6F4D` |
| FL | `0x021C6CC9` |
| IN | `0x021C6857` |
| SH | `0x021C6961` |
| BW | `0x021C65F8` |
| SE | `0x021C658A` |

出厂文字就是槽位缩写（`PT` / `NT` / `VV` / `VV2` …）。

### 9.3 两套命名

| 预设 | key | 文字 |
|---|---|---|
| 官方原名 | `official`（默认） | Classic Chrome / Classic Neg. / Positive Film / Negative Film |
| 中文简称 | `zh` | 富士CC / 富士NC / 理光正片 / 理光负片 |

- 存在 `docs/looks-profile.json` 的 `menu_names`，界面下拉切换、**切换只改显示不写盘**；预设持久化在 `.data/looknames/settings.json`
- 实测字节：official → **145,708 B**（sha `9fd0bb497171…`）；zh → **145,692 B**（sha `4a2a05e814a0…`）
- 改回短名 → 与出厂**逐字节相同**（145,612 / `fe263360…`）。这是实测行为，**不当承诺**；无损仍靠基线

### 9.4 写入与还原

- 写入：`uxc.rename_all` 整块后移 + 重写索引表 → `flash.truncate` 到新长度 → `0x8000` 分块写 → 整份回读比对
- 还原三档：① 有出厂基线 → 逐字节写回（`mode="baseline"`）；② 无基线 → 把记录改回短名（`mode="labels"`），若回写后哈希恰与出厂一致则自动登记为基线（`mode="labels-factory"`）；③ 拒绝写入
- 基线库 `.data/looknames/`（6 份，best = 出厂 145,612 / `fe263360…`，source `string_simplifiedchinese_f.uxc.20261023T233448Z.bin`）；source 目录 `<workspace>/firmware/uxc`
- **`build.ps1` 清 dist 后必须重新 seed**：
  ```powershell
  $env:POWERFUL6700_DATA='<repo>\dist\Powerful6700\.data'
  .\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'src');from a6700win import looknames;print(looknames.auto_import())"
  ```
- 恢复手法（掉线撕裂时）：`live_repair.py` 只重写差异块（先读全 5 块 → 逐块比 → 只写不同的块 → 只回读这些块）

---

## 10. 当前真机状态（接手先复核）

复核（**一次会话读全，别连两次**）：

```powershell
.\.venv\Scripts\python.exe .data\scratch\live_check_units.py
```

按最后一次操作记录：

| 项 | 状态 |
|---|---|
| 菜单文字 | **英文原名**，145,708 B，sha `9fd0bb497171…` |
| CP 色度单元 | PT(bank 6) = **pair2×0.60 + pair6=0**（刚写入，只在 RAM）；NC/PF/NF 为定稿配方 |
| `/setting/BACKUP.BIN` 色度副本 | 仍是 **pair2×0.70** 那版（用户误关机时落盘）→ 与 RAM 不一致，需正常关机落盘 |
| 矩阵单元 `0x02A4000D` | 与出厂逐字节相同（未动） |
| FL | 偏橙是**原厂 FL 本来的样子**（bank 8 与出厂逐字节相同） |

⚠️ **不要在一个会话里既写 CP 单元又写 145 KB 文字**（实测 3 次，第 5～13 次传输必崩）。

---

## 11. 踩过的坑（照抄，别重犯）

### 11.1 会话与掉线（最贵的三条）
1. **同一会话混写 CP 单元 + 145 KB 文件 → 必掉线**；拆两个会话 + 冷却 **50–60 s**（`cp.SESSION_GAP`，环境变量 `POWERFUL6700_SESSION_GAP`）。
2. **掉线后普通「关机再开」无效**：要拔线 + 关机 + **取电池约 1 分钟**（A7C2 文档原话：只关机再开机不算断电重开），否则第一个块就崩。
3. **USB 3 高速口时相机不进服务模式**（认证后跳回放画面、`0x0336` 不出现）→ 换 USB 2.0 口/线。端点坏掉的唯一恢复是**物理拔插**。

### 11.2 写入器
4. 先 `truncate` 再写：grow 场景（145,612→145,708）最后一块落在原长度之外 → 状态码 12「范围超出文件长度」。
5. 加「载荷缓存」或改分包大小 → 读到陈旧数据（`flash.stat` 返回 225 其实是路径字符串长度、`read_range` 返回路径文本）。已回滚，**别再加**。
6. 回读必须用新的 `O_RDONLY` 句柄，且要 `fsync` + `close` 之后。

### 11.3 基线
7. 整单元写入**必须以当前实时单元为基线**，不能用历史快照（曾把 ST/VV 写黑白）。
8. `restore()` 的基线来自本地 store；`apply()` 前若无同 sha 基线会自动 capture（事故就是这么救回来的）。
9. 曾用被污染的「出厂快照」当基线 → 每轮「还原」都写回旧数据；`BASELINE` 一律用 `unit-02a40001.backup-def.bin`。

### 11.4 环境
10. GBK 控制台必须 `PYTHONIOENCODING=utf-8`。
11. 每轮写入结束要让相机退出服务模式（发 `STOP_SENSER`），否则停在 `0x0336`。
12. bash heredoc 里 `'\\n'` 会被吞成真换行 → 用数值 10 / `chr(10)`；绝对 POSIX 路径要 `MSYS_NO_PATHCONV=1`。
13. exe 运行时不能删除/改名 `dist` 目录（`base_library.zip` 被占用）。

---

## 12. 待办与下一步的具体做法

### 12.1 蓝端标定（优先级 1）
```powershell
# 目标：找到 0x02A4000D block 4 里管 PT 蓝端的那几个 int16 与线性范围
# 结构：矩阵 @0x1e0 + slot*768；PT 的 slot 需先从菜单 slot 表确认
```
做法建议：先整块填小值（如 2000 / 5000）看响应是否线性，再逐个 int16 二分；每轮写前存当前单元，写后立即回读，**每轮都要能一键写回出厂**（`tools/cp_write.py` + 出厂副本）。

### 12.2 客观验收（优先级 2）
```powershell
# 拍一帧 RAW+JPEG（PT 槽位），然后把卡插上直接读
.\.venv\Scripts\python.exe tools\look_loop.py measure --raw <ARW> --jpeg <jpg>
```
把 0.164 从「历史最优」变成「当前实测」；同一场景重拍还能对比 0.52 / 0.60 / 0.70 / 0.85。

### 12.3 一键写入（优先级 3，产品级要求）
用户原话（m09376）：「软件里的所有更改都要对应，比如我要中文的富士或者英语版的富士滤镜，就要写入富士滤镜和对应名字」。
实现约束：
- **必须两个连续会话**：会话 1 写 CP 色度 → 冷却 50–60 s → 会话 2 写文字文件
- 界面要讲明白：约 2 分钟、中途不要拔线、失败要**取电池等 1 分钟**再试
- 语义：颜色按外观（CC/NC/PF/NF）写；文字按命名方案（official/zh）写；两者都不能只写一半
- 还原同理：颜色回出厂记录、文字回基线（或短名回写），也要拆两个会话

### 12.4 版本与发布（优先级 4）
- `src/a6700win/version.py` 仍是 `0.3.3` → 升 `0.3.4`
- `packaging\build.ps1` 重建 → seed 基线库 → `--offline-self-test` 九项
- 文档收尾：`docs/LOOKS.md` §7.1、`docs/RELEASE-NOTES.md` 补两套命名与本次真机结论
- git 提交；Release 资产上传等用户授权

---

## 13. 已知限制与能力边界

- **只能从机身 dump 取明文**：官方固件 `BODYDATA-2.00.dat`（1,024,017,848 B）是加密容器（DATV/PROV/UDID/FDAT/DEND），12 种 Sony-PMCA-RE crypter 全解不开。
- **固定窗口只有 260 扇区 / 133,120 字节**：`.text` / `.data.rel.ro` 不在窗口内，改判定逻辑（如卡速）需要新的写窗口，风险高。
- **没有影调层**：A6700 的 CP 只有「12 对 (Cb,Cr) + 增量表」，矩阵+曲线拟合残差 0.148 已是模型极限；`.cube` 那种 33³ 曲线+LUT 表达不进来。
- **完整备份未实现**（只有功能状态的稀疏备份 254 个固定扇区）。
- **整机验证**仍记 `pending-unified-selection`。
- **payload-integrity 降级**：上游 `manifest.json` 的 `source_sha256` 与自身的 `transaction.c` 不符（全仓库无该哈希），已降级为溯源信息（记录 expected/actual），**实际送相机的字节仍严格校验**。
- **PF/NF 只是低饱和版**：目标里「压红抬黄绿」「压红压蓝抬正蓝」是局部反向，pair 基函数叠加不出来。
- **卡速（V90 判定）没改**：速率等级是固件真实枚举，caution 文案表在 `.data.rel.ro 0x4958148` 起每项 16 B `{name, u32 id, u32 len}`，共 1981 条；属性 id `0x97e` / `0x98c` / `0x19f`。用户卡是 V60，4K120 被速率门挡住 → 要改需新写窗口，已搁置。
- **REA 无可用 provider**（只支持 Linux x64），Windows 上不能用它做运行时逆向。

---

## 14. 历史调查结论（省得重做）

- **外观↔CP 映射工具**：A6700 的 look→CP mode 转换器在 `0x34e5604`（A7C2 是 `0x3528804`）；索引表 `0x40b6024`；两机同一套 look/mode 编号体系。
- **A7C2 的 patches.json**（`list[2]`：appFw 8 处 + cpapp 32 处）：`0x20140` 初始化长度 `0x141B80 → 0x142AA0`（差 `0xF20` = 3872，即 `0x1100B80` 追加的曲线记录）；FL2/FL3 参数 55/56 → CP 槽 23/25；gamma 上界 `0x2f → 0x32`；菜单 product flag。A7C2 的 CP 布局与 A6700 同构（8192 / 28672，参数 @`0x1200`，矩阵 @`0x1e0 + slot*768`）。
- **cpapp 静态镜像**：`/cp/cpapp-b.bin` 17,892,024 B，ARM32 Thumb 裸镜像，60,408 条字符串，含 `SET_LOOKNAME` / `SET_LUT` / `init_cc_3DLUT` / `CheckSetPictureProfile`；但**单元 RAM 地址只在单元目录里**，运行时快照与静态字节几乎不匹配 → 矩阵/色度是运行时算出或主机下发，静态里挖不到现成表。
- **cpapp 里 9 条 1024 B 恒等斜坡（`0xFE0B50` 起，长 `0x400`）是死数据**：改成 gamma 2.2 后实拍三张差异 <2.7/255，屏幕无变化（已写回恒等）。
- **外观八参数（对比度等）不在 `/setting/BACKUP.BIN`、不在 PSD/DEFDET、不在 CP 单元**（全文件搜元组 0 命中）。
- **自定义外观是内建别名**（见 §7.2），bank 22–31 / 40–53 涂色无任何变化。
- **官方富士 3D LUT 包（x-h2s / x-pro3 / x-t4）接不上**：19 张表全是 F-Log / F-Log2 / F-Log2C（F-Gamut）→ ETERNA / ETERNA-BB / WDR 的**录制域→显示域**转换，**没有任何胶片模拟**；A6700 只有 S-Log3/HLG。
- **达芬奇导出的 `Fuji_CC.cube` / `Fuji_CN.cube` 不能当参照**：灰阶被烤成强 S 曲线（0.25→0.083、0.5→0.690、0.75→0.937，与恒等偏差 −0.167/+0.190/+0.187），四种域解释应用到实拍帧后与相机 CC 的 12 档 RMS 0.53–1.19。干净 CST cube 的自检标准：灰阶与恒等偏差 <0.02、色相旋转 <3°。
- **tint 被证伪**：蓝基座 `v6` 两个方向都降饱和且偏暖（1.00/0.80→0.763、1.00/1.20→0.658），它只是白点配平项，不是色相旋钮。
- **CC/NC 定稿写法的由来**：`pair2` 是「暖区抑制」基函数，`pair6` 是「绿区抬升」，`pair1` 会把青蓝推向错方向。

---

## 15. 文件地图

### 15.1 源码（`src/a6700win/`）

| 文件 | 职责 |
|---|---|
| `paths.py` | 数据目录解析（`POWERFUL6700_DATA` → `project_root()/.data` → `LOCALAPPDATA` → temp）、`bundled_root()`、`state_dir()`、`backup_dir()` |
| `patches.py` | 上游 30 项补丁（`install()`） |
| `windows_shim.py` | POSIX 语义垫片（锁、目录、`O_BINARY`、`O_NONBLOCK`） |
| `usb/setupapi.py` | PnP 枚举（`present_pids()`） |
| `usb/driver.py` | `wdi-simple.exe` 下载与绑定 |
| `usb/windows_auth.py` | `_wait_service()` / `_recover_service_mode()` |
| `cp.py` | `CpChannel`（`read_unit` / `write_unit`）、`session()` + **会话冷却** |
| `flash.py` | 文件读写（`stat` / `read_range` / `write_block` / `truncate`）、`WRITABLE_ROOTS`、`TARGETS` |
| `looks.py` | CP 色度配方（`profile` / `read_state` / `apply` / `restore`，均支持 `channel=`） |
| `uxc.py` | UXC v7 格式（`decode` / `patch_text` / `grow` / `rename_all` / `texts`） |
| `looknames.py` | 菜单文字（`PRESETS` / `targets` / `read` / `apply` / `restore` / `capture` / `auto_import` / `_write_blob`） |
| `app.py` / `controller.py` | 状态机与主控 |
| `selftest.py` | 离线自检九项 |
| `gui/` | `window` / `pages` / `render`（`settle()` 处理 `deleteLater`）/ `looks_page` 等 |
| `version.py` | `APP_NAME="Powerful6700Win"`、`APP_TITLE="Powerful6700 · Windows"`、`APP_VERSION="0.3.3"` |

### 15.2 工具（`tools/`）

| 工具 | 用途 |
|---|---|
| `look_write.py` | 写色度配方（支持 pair 系数） |
| `look_loop.py` | `pairs` / `measure`（`--raw <ARW> --jpeg <jpg>`）/ `simulate` / `solve` |
| `look_diff.py` / `look_calibrate.py` | 差异与标定 |
| `looks_apply.py` | 按配方一次性写四条 |
| `cp_read.py` / `cp_write.py` / `cp_patch.py` / `cp_probe_unit.py` | CP 单元读写与探测（写前自动存 `<file>.orig`） |
| `cp_verify_factory.py` | 14 个单元与出厂副本比对（**直接 `run_authentication`，无冷却/无锁**） |
| `uxc_grow.py` | 菜单文字改名（离线预览 / 真机写） |
| `flash_write.py` | 载荷读写（`--probe` / `--stat` / `--verify` / `--write-hex` / `--write-file`，写要 `--confirm yes-write`） |
| `dump_camera.py` / `ls_camera.py` | 机身 dump 与目录列举 |
| `build_write_payload.py` | 重编 `flash_write.elf` 并更新 manifest |

### 15.3 诊断脚本（`.data/scratch/`，不进仓库）

`live_dev.py`（枚举 PID）、`live_check_units.py`（CP/矩阵/BACKUP 三方比对）、`live_repair.py`（块级修复）、`live_diff.py`（逐字节比对）、`live_cc085.py`（识别当前 CC 系数并写新档）、`live_state.py`、`cube_*.py`（.cube 解析/域解释/色相统计）、`rate_*.py` / `verify_rate*.py`（矫正率复算）。

### 15.4 文档（`docs/`）

| 文档 | 内容 |
|---|---|
| `AI-HANDOFF.md` | **本文**（接手第一站） |
| `LOOK-COLOR.md` | 颜色机制、pair 基函数、四卷实验、能力边界 |
| `LOOKS.md` | 配方、§9 验收表、§7.1 菜单文字 |
| `CALIBRATION.md` | 矫正率口径、官方 LUT 审计、样本量与分带误差 |
| `VALIDATION.md` | 真机验收记录（含 USB 掉线、冷启动、关机等待） |
| `CC-CN-PLAYBOOK.md` | 操作手册（怎么拍、怎么还原） |
| `ARCHITECTURE.md` | 分层与模块表 |
| `BUILD.md` / `PUBLISHING.md` / `RELEASE-NOTES.md` | 构建、发布、版本记录 |
| `CP-PARTITION.md` / `FIRMWARE-MAP.md` / `PERSIST-STORE.md` / `FLASH-WRITE.md` | 底层调查 |
| `FL23-INVESTIGATION.md` / `FL2-ROUTE.md` / `FEASIBILITY-FL23.md` / `CPAPP-STATIC.md` | FL2/FL3 与 cpapp 静态分析 |
| `CARD-SPEED.md` | 卡速等级与 caution 表 |
| `BREAKTHROUGHS.md` / `ROADMAP.md` | 结论与路线 |

---

## 16. 未提交改动

```
 M README.md                                M docs/RELEASE-NOTES.md
 M docs/ARCHITECTURE.md                     M docs/VALIDATION.md
 M docs/CC-CN-PLAYBOOK.md                   M docs/looks-profile.json
 M docs/LOOK-COLOR.md                       M native/flash_manifest.json
 M docs/LOOKS.md                            M native/flash_write.c
                                            M native/flash_write.elf
 M src/a6700win/cp.py                       M src/a6700win/flash.py
 M src/a6700win/gui/looks_page.py           M src/a6700win/looks.py
 M src/a6700win/version.py
?? docs/AI-HANDOFF.md  ?? docs/CALIBRATION.md
?? src/a6700win/looknames.py  ?? src/a6700win/uxc.py
?? tests/test_looknames.py
```

---

## 17. 更新记录

- **2026-10-25 17:47** · 建立本文件：真机状态（文字=英文 145,708/9fd0bb49；PT=pair2×0.60+pair6=0 仅在 RAM；BACKUP 仍 0.70）、蓝端结论、8 条踩坑、待办 6 项。
- **2026-10-25 17:55** · 扩写成完整交接：补 §1 项目背景、§5 Windows 路线与 PID 表、§6 协议/挂载/载荷细节、§7 单元布局与持久化语义、§9 UXC 格式与 rid 全表、§13 能力边界、§14 历史调查结论（LUT/cube/cpapp/卡速）、§15 文件地图。
- **2026-10-25 18:2x** · 查「只读检查 状态：04000010」：从源码复现不出来（三步探针全 OK，同会话连读 3 次 + 闲置 90 s 再读全 OK，GUI 全路径 headless 跑通得到「预计修改 0 字节」）。判断是一次性设备侧拒绝，与同日多次掉线同源。0.3.4 只做「下次能看懂」：`_windows_backend_file` 报出是哪一步（`配置写入（SET_FILE2）` / `载荷写入（SET_FILE）`）、file_id、状态字含义与恢复步骤（拔线 → 关机 → 取电池 1 分钟 → 装回 → 重连 MSC）。诊断脚本：`.data/scratch/live_inspect_steps.py`、`live_session_reuse.py`、`live_gui_inspect.py`、`live_inspect_plan.py`。同时版本 0.3.3 → 0.3.4（两套命名 + `/setting/` 白名单 + 状态码可读化）。
