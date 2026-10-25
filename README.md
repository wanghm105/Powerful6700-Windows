# Powerful6700 · Windows

[![release](https://img.shields.io/github/v/release/wanghm105/Powerful6700-Windows?label=release&color=e0a340)](https://github.com/wanghm105/Powerful6700-Windows/releases/latest)
[![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011%20x64-0078d4)](https://github.com/wanghm105/Powerful6700-Windows/releases/latest)
[![base](https://img.shields.io/badge/based%20on-sony--a6700--powerful%200.2.0-e0a340)](https://github.com/xyzhangxin/sony-a6700-powerful)
[![license](https://img.shields.io/badge/license-GPL--3.0--only-blue)](LICENSE)

给 **Sony A6700（ILCE-6700）固件 2.00** 用的 Windows 桌面工具：解锁机身里被隐藏的几项功能，也能整份关回去；另外可以把菜单里四个外观换成富士与理光的胶片配色，连菜单上显示的名字一起改。

**真机验证过的：四项隐藏功能可以开也可以关回去，菜单的颜色和名字能改也能逐字节还原，每次写入前后都有回读校验。**

## 功能状态

| 功能名称 | 优先级 | 当前状态 |
| --- | --- | --- |
| FTP 功能与设置（RAW+JPEG 双传） | ✅ 已完成 | 已实机验证 |
| 关机关闭快门帘（防尘保护） | ✅ 已完成 | 已实机验证 |
| 电子快门声音（含静音联动） | ✅ 已完成 | 已实机回放验证 |
| 视频独立曝光控制（灵活曝光） | ✅ 已完成 | 已实机写入 + 回读 |
| 免 Pico 的 USB 极简刷写通道 | ✅ 已完成 | 已移植到 Windows（WinUSB + 两次认证），实机验证 |
| 菜单文字改名（官方原名 / 中文简称两套） | ✅ 已完成 | 已实机写入并还原 |
| 富士 / 理光外观颜色（CC / NC / PF / NF） | ✅ 已完成 | 基线版，逐色相矫正率 81.7 / 82.7 / 81.1 / 67.0% |
| 驱动准备（WinUSB 自动绑定） | ✅ 已完成 | 实机验证（`0x0E76` → winusb） |
| 功能状态备份与整份恢复 | ✅ 已完成 | 实机验证（`restored` 134 扇区 / 326 字节） |
| CC 第二轮强度拟合（RMS 0.194 → 0.164） | P1（高） | 离线已验证，待实机观感验收 |
| 蓝端色相校准（矩阵单元 block 4） | P1（高） | 已定位旋钮，待块内二分标定 |
| 录像卡速限制放宽（V60 探索 / 4K120） | P1（高） | 已定位，判定在 `.text`，当前写窗口不含 |
| 颜色 + 名字一键写入（两次会话 + 冷却） | ✅ 已完成 | 已实现，待真机验收 |
| 整单元写回 `BACKUP.BIN`（`/setting/` 载荷） | P2（中） | 载荷已支持，未实机验证 |
| 双原生 ISO 菜单与切换（Base ISO） | P2（中） | 未开始 |
| FL2 / FL3 原生创意外观 | P2（中） | 调查完成：颜色层可达但等价于机身饱和度；菜单字样判定不可行 |
| 机内网络直播（推流） | P3（低） | 未开始 |
| 构图稳定 / 主体位置保持 | P3（低） | 未开始 |
| S-Log3 实时 LUT 照片直出 | P4（探索中） | 未开始；机内只有 12 对色度 + 矩阵，无 3D LUT 层 |
| 动态增强防抖（Dynamic Active） | P1（高） | 跟随上游禁用（功能未完成） |
| 位移多帧合成（Pixel Shift） | 暂缓 | 跟随上游禁用（实机稳定性失败已撤回） |

打勾的是已经能点、能跑、上过真机的。每项做什么、从哪进、验证到哪一步、边界在哪，写在 [docs/FEATURES.md](docs/FEATURES.md)；后续方向见 [docs/PROGRESS.md](docs/PROGRESS.md)；想换个对话接着开发，先看 [docs/AI-HANDOFF.md](docs/AI-HANDOFF.md)，真机状态、协议常量、踩坑清单都在那里。

**只适配 A6700 固件 2.00。** 其他机型（A7C II、A7CR、A7 IV、A7R V、ZV-E10 等）不能用，这个项目也兜不住。

任何写入之前都会先跑一次只读检查，出现未知字节就整次中止，没有强制写入的开关。流程与验收见「[操作指南](#操作指南)」，失败回滚与验证清单见 [docs/VALIDATION.md](docs/VALIDATION.md)。

运行时来自 [**xyzhangxin/sony-a6700-powerful**](https://github.com/xyzhangxin/sony-a6700-powerful) 0.2.0（GPL-3.0）：固件字段表与写入事务是上游的，Windows 连接层、界面和打包是本仓库重写的。对照见「[这个项目和上游是什么关系](#这个项目和上游是什么关系)」。

## 自定义外观与菜单文字

相机菜单里那四个外观可以换成富士和理光的观感，做法两步：改 CP 色度表（`0x02A40001` 的 12 组 (Cb,Cr)，决定颜色），改 UXC 文本（决定菜单上显示的名字）。

| 菜单项 | 改成 | 实测 |
| --- | --- | --- |
| PT（第 2 项） | **Classic Chrome** | 逐色相 RMS 0.183 |
| NT（第 3 项） | **Classic Negative** | 逐色相 RMS 0.173 |
| VV（第 4 项） | Positive Film（理光正片） | 低饱和轻量版 |
| VV2（第 5 项） | Negative Film（理光负片） | 低饱和轻量版 |

四个外观各 12 个色相档，一共 48 个色相单元；参照 19 张官方直出对照图（切出 72 个样本），真机累计 10 轮 × 9 帧 ≈ 90 帧，逐色相矫正率 **81.7% / 82.7% / 81.1% / 67.0%**。公式与「官方 LUT 为什么不能当目标」的审计写在 [docs/CALIBRATION.md](docs/CALIBRATION.md)。

![自定义外观页：四个槽位写成「原厂 → 改写为」，并列出颜色记录与拟合 RMS](docs/images/looks.png)

图形界面走「自定义外观 → 检测当前状态 → 写入配方」，写入后逐条显示状态，其它记录被改动会单独报警。命令行是同一件事：

```powershell
python tools/looks_apply.py --confirm yes-write   # 相机先切到 USB 存储模式
```

两条路都只改 RAM 里那 4 条色度记录（bank 6/4/1/14），写完回读校验；要让它跨关机保留，正常关机一次，让相机自己写回 `BACKUP.BIN`。「还原本页外观」把这四条写回出厂值。

菜单上显示的名字是另一码事，也在这一页：「菜单文字」卡片可切换两套叫法。

- **官方原名**：`Classic Chrome` / `Classic Neg.` / `Positive Film` / `Negative Film`（不加品牌前缀，菜单宽度也不挤）
- **中文简称**：`富士CC` / `富士NC` / `理光正片` / `理光负片`

名字写在固件语言资源里（`/usr/share/app/string_simplifiedchinese_f.uxc`），写下去就持久，不像颜色要等关机落盘。

- 写入前自动把整份资源（约 142 KB）存成基线；还原时整份逐字节写回，并比对哈希。
- 本地没有基线时只把文字改回出厂短名，界面会说明这一档不是逐字节还原。手上有出厂备份就点「导入基线…」，文件先过格式校验。
- 切方案不用重连相机，只换目标文字。实际写进去的是哪一版，由文件内容判定。

要一次把颜色和名字都写对，用「一次写入：颜色 + 名字」那张卡片：选好命名方案点一下，程序先写颜色、断开、等相机复位约 1 分钟、再连上写名字，全程约 2 分钟，中途不用拔线。拆成两次连不是慢，是实测出来的硬要求——一个会话里既写 CP 色度单元又写 145 KB 语言资源，第 13 次传输左右端点就掉，文件会停在一半。前一段失败就整段停下、文字一个字都不动；后一段失败则保留已写好的颜色，并提示可以单独回滚。「一次还原（颜色 + 文字）」走同样的两段。

**边界**：A6700 没有可用的伽马／曲线层（cpapp 里那 9 条斜坡是死数据，改成 gamma 2.2 后实拍和屏幕都没变化），所以只能改颜色倾向，做不出富士的 S 形影调；NC 的窄带品红缺口是用宽把手逼近的；理光正片／负片停在低饱和版；`.cube`／`.dcp` 不能直接导入。整盘固件备份、位移多帧合成、动态防抖、FL2／FL3、机内 3D LUT 也都没有——上游没实现，这里不发明。详见 [docs/LOOKS.md](docs/LOOKS.md) 与 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 其他机型

如果你的机器不是 A6700，下面这些是完全独立的项目，支持范围和风险以各自的说明为准：

| 机型 | 项目 | 内容 |
| --- | --- | --- |
| A7C II | [QAQLeonard/a7c2-fl23-research](https://github.com/QAQLeonard/a7c2-fl23-research) | FL2／FL3、自定义创意外观、电子快门声音、竖屏显示（Windows/macOS 桌面工具） |
| A7C II | [MDHan/a7c2-fl23-macos](https://github.com/MDHan/a7c2-fl23-macos) | 上面那个项目的 macOS 适配 |
| A6700 | [**xyzhangxin/sony-a6700-powerful**](https://github.com/xyzhangxin/sony-a6700-powerful) | **本项目所基于的上游项目**：Pico 接线、Fastboot、备份、功能解锁（macOS） |
| 其它 | [chocotan/a7c2-re](https://github.com/chocotan/a7c2-re)、[YuuLuo/a7c2-camera-tools](https://github.com/YuuLuo/a7c2-camera-tools) | 固件逆向研究与相机侧工具 |

## 目录

- [自定义外观与菜单文字](#自定义外观与菜单文字)
- [其他机型](#其他机型)
- [这个项目和上游是什么关系](#这个项目和上游是什么关系)
- [截图](#截图)
- [功能状态](#功能状态)
- [现有功能逐项说明](docs/FEATURES.md)
- [下载与系统要求](#下载与系统要求)
- [致谢](#致谢)
- [开始前必读](#开始前必读)
- [操作指南](#操作指南)
  - [第 1 步：解压并启动](#第-1-步解压并启动)
  - [第 2 步：驱动准备（只在第一次需要）](#第-2-步驱动准备只在第一次需要)
  - [第 3 步：相机准备](#第-3-步相机准备)
  - [第 4 步：只读检查](#第-4-步只读检查)
  - [第 5 步：解锁或关闭功能](#第-5-步解锁或关闭功能)
  - [第 6 步：备份与恢复](#第-6-步备份与恢复)
- [常见问题](#常见问题)
- [验证状态](#验证状态)
- [命令行与开发](#命令行与开发)
- [来源与许可](#来源与许可)

## 这个项目和上游是什么关系

上游的运行时原样保留，Windows 侧全部重写：

- `third_party/a6700_unlock/` 是上游运行时 [0.2.0](https://github.com/xyzhangxin/sony-a6700-powerful/releases/tag/v0.2.0) 的逐字节副本（GPL-3.0，含 LICENSE／NOTICE）。固件字段表、写入事务、结果分类、界面状态机都来自上游。
- 本项目自己写的只有 `src/a6700win/`（Windows 适配层 + PySide6 界面）、`tools/`、`tests/`、`packaging/`。
- 适配方式不改运行时源码，而是启动时注入 30 个替换点（`src/a6700win/patches.py`，逐项理由见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)），所以上游再发版时可以整目录替换后重新对齐。

我们具体做了什么：

| # | 上游（macOS）的做法 | 本项目（Windows）的做法 |
| --- | --- | --- |
| 1 | `libusb_library_path()` 只认 Homebrew／系统 dylib，没有 Windows 分支 | 走 `libusb-package` 自带的 `libusb-1.0.dll`，冻结包内直接命中 |
| 2 | 靠 macOS 权限弹窗 / 特权 helper 抓 USB（`mac_capture.m`） | **WinUSB 绑定**：用 [libwdi](https://github.com/pbatard/libwdi) 的 `wdi-simple.exe` 把相机 PID 绑到 WinUSB，需要管理员时自动 `ShellExecuteExW(runas)` 提权并回报进度 |
| 3 | 服务模式设备（0x0336）在 libusb 里立即可见 | 该设备在 Windows 上**默认没有任何驱动**（设备管理器 Error 28）→ 先用 SetupAPI 按 PID 发现它，再为它装一次 WinUSB，最后才交给 libusb |
| 4 | PyUSB 单例上下文，反复使用没问题 | PyUSB 1.2.1 会永久缓存一个 libusb context，驱动切换后必须强制重建（`fresh` 已被包装成默认行为） |
| 5 | 设备枚举、产品 ID 观察走 `ioreg` | 走 SetupAPI（`SetupDiGetClassDevsW`），不需要驱动也不需要管理员 |
| 6 | 状态／备份写在 macOS 用户目录 | 可写数据目录探测：`POWERFUL6700_DATA` → exe 同目录 `.data` → `%LOCALAPPDATA%` → 临时目录，保证「提权/不提权」看到同一个目录 |
| 7 | `doctor` 的 `platform` 检查写死 `darwin/linux`，Windows 上恒为 False，会永久阻塞整个流程 | 换成 Windows 判定并把 libusb 行指向实际的 DLL |
| 8 | 写文件用 `os.open(...)` 不带 `O_BINARY`，Windows 会把 `0x0A` 改写成 `0x0D 0x0A`（稀疏备份当场损坏） | 给备份／规划器的 `os` 打上二进制与 `O_NONBLOCK=0` 垫片 |
| 9 | 设备锁、目录 fsync 都是 POSIX 语义 | 用 `msvcrt.locking` 独占锁 + 尽力 fsync；异常时保证放锁并回到正确阶段 |
| 10 | 桌面备份／恢复入口被上游隐藏（`_available_backups()` 返回空，而恢复校验又依赖它 → 永远不可用） | 打开该入口，并让「恢复」按**整份备份**回写（不再受上次勾选残留影响） |
| 11 | SwiftUI 桌面外壳（AppKit + Swift），只出 macOS arm64 包 | PySide6 图形界面 + PyInstaller onedir 冻结包，双击即用，不需要装 Python |
| 12 | 上游在「等待服务模式设备」超时后不会清理，相机会停在 0x0336 | 新增等待期自动退出服务模式（发 `STOP_SENSER` 并等设备回落到 0x0E76），失败给出明确提示 |

顺手回报给上游的两个问题（也已写进 [docs/UPSTREAM-NOTES.md](docs/UPSTREAM-NOTES.md)）：

1. `usb/legacy.py` 的 `run_authentication()` 在「等待服务模式设备」这一步抛错时还没有设备句柄，`except` 里的 `STOP_SENSER` 清理不会执行 → 相机留在服务模式。macOS/Linux 上因为设备立刻可见，不会暴露。
2. `data/native/manifest.json` 的 `source_sha256`（`53cd3393…`）与 `native/transaction.c` 的实际哈希（`f21342ab…`）不一致，全仓库没有这个哈希对应的文件 → `doctor` 的载荷完整性检查在严格模式下必然失败。本项目保留对**真正送到相机的字节**（`reader.elf`／`writer.elf` 与 profile 摘要）的强校验，只把源码文本哈希降级为溯源信息。

## 截图

主界面（功能管理页）。和上面「自定义外观」那一张一样，都是同一份发布包渲染的实际界面，截图时没有连相机。

![功能管理](docs/images/home.png)

## 下载与系统要求

| 系统 | 下载 | 说明 |
| --- | --- | --- |
| Windows 10 / 11 x64 | [`Powerful6700-Windows-x64.zip`](https://github.com/wanghm105/Powerful6700-Windows/releases/latest)（约 46 MB） | 解压即用，绿色版，不需要安装 Python；包内含 `必读.txt` |

- SHA-256：`93761bfc65c196283a20506f0177088bcb0d055ffbe487baf3d491a2017ab366`（v0.3.4-win.1）
- 首次把相机绑到 WinUSB 需要**管理员权限**，建议右键「以管理员身份运行」。
- 也可以从源码运行：建虚拟环境 → `python main.py`，或直接双击 `启动.cmd`；步骤与依赖清单见 [docs/BUILD.md](docs/BUILD.md) 与 [requirements.txt](requirements.txt)。

## 致谢

- [xyzhangxin](https://github.com/xyzhangxin)：上游 Powerful6700，固件字段表、写入事务与全部风险控制逻辑都来自这里。
- [QAQLeonard](https://github.com/QAQLeonard)：A7C II Tools（Windows/macOS 桌面工具）是本项目在「产品完整度」上的参照。
- [pbatard](https://github.com/pbatard)：libwdi／Zadig，Windows 驱动绑定这一环靠它。
- [PySide6](https://www.qt.io/qt-for-python)、[PyUSB](https://github.com/pyusb/pyusb)、[libusb](https://libusb.info/)、[PyInstaller](https://pyinstaller.org/) 及 [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)。

## 开始前必读

> [!IMPORTANT]
> 本工具会**修改相机固件里的设置字段**。断电、断线、机身状态差异或程序错误都可能导致操作失败；失败时程序会尽力回滚并如实报告结果，但**不保证一定成功**。请先读完应用内的「操作前须知」，再动手。
>
> - 只改**已知字段**：260 个扇区里每一个字节都参与校验，出现任何未知偏差就整次中止，**没有强制开关**。
> - 不解锁 Bootloader、不刷固件、不需要 Pico 或测试板。
> - 操作期间保持相机开机、接一根数据线、只接**一台**目标相机；关闭 FTP 与「电脑控制」，USB 连接模式选**海量存储(MSC)**。

## 操作指南

整个流程是**一条直线**：界面左侧导航就是操作顺序，右上角标着「第 N 步 · 共 6 步」，每页底部有「← 上一步 / 下一步」按钮。前一步没做完，下一步会灰着并直接告诉你缺什么（比如「请先勾选上方的阅读确认。」「请先把四项准备全部确认。」），不用猜。

### 第 1 步：解压并启动

解压 zip，得到 `Powerful6700` 目录，双击 `Powerful6700.exe`（建议右键「以管理员身份运行」）。压缩包根目录有一份 [必读.txt](packaging/必读.txt)：解压放哪、SmartScreen 怎么过、驱动组件、四步流程、还原步骤与常见问题都在里面，第一次用先照它走一遍。

先点「开始启动检查」（跑过一次之后这个按钮会变成「重新运行启动检查」）。五项全绿、右下角显示 **● 环境就绪**、并勾选页面上的阅读确认之后，底部的「下一步：驱动准备」才会亮起来。

### 第 2 步：驱动准备（只在第一次需要）

打开左侧「驱动准备」：

1. 点 **扫描设备**，确认相机被识别为 `0x0E76 Sony A6700 - Storage`；
2. 驱动组件（libwdi 的 wdi-simple.exe）随包附带，**不用联网**，第一次运行会自动复制到数据目录的 driver 子目录。从源码运行、包里没带组件时才需要点 **下载驱动组件**；
3. 点 **绑定 WinUSB**（需要管理员）。绑定成功后资源管理器里的相机盘符会消失，这是正常的。

第一次「只读检查」时相机会切到服务模式，出现新的 `0x0336 Sony A6700 - Service`，程序会自动为它补装驱动，不用你手动操作。

### 第 3 步：相机准备

在相机上依次确认四件事（界面上每项都有菜单路径）：

1. **FTP 功能：关**（首次解锁前没有这个菜单，属正常，可直接勾选「没有 FTP 菜单，直接继续」）
2. **USB 连接模式：海量存储(MSC)**（先拔线再改，别选 MTP／电脑控制／USB 流式传输）
3. **自动关机：关**，并确认电量充足
4. **最后再接线**，只接一台 A6700

四项都勾选后点 **开始只读检查**。

### 第 4 步：只读检查

结果页与功能管理页会给出兼容性，以及六个功能项各自的开关状态（四个可用、两个跟随上游禁用）。这一步不写相机；这里就报不兼容的话，停下来把日志贴到 Issue。

### 第 5 步：解锁或关闭功能

在「功能管理」勾选要处理的功能 → **解锁所选功能**／**关闭所选功能**。写入流程是：相机内二次校验前置内容 → 分扇区写入 → fsync → 回读 → 独立再读一遍。结果页会给出状态之一：`completed`／`no-op`／`blocked`／`rolled-back`／`uncertain`／`verification-failed`／`recovery-required`。

看到 `completed` 之后按结果页的「机身验收」提示断电重启，再到菜单里逐项核对。以电子快门声音为例：重启后菜单里应出现 4 项，选中非静音的选项，按下快门能听到对应声音。

### 第 6 步：备份与恢复

- **备份当前功能状态** → 在 `.data\backups` 生成 `.a6700backup`，结果页给出路径与 SHA-256；
- **恢复整份备份** → 选下拉里的备份，整份功能字段写回 + 独立回读（与当前勾选无关）；
- 备份要求**同机型 + 同固件**；跨固件／跨机型会被拒。

## 常见问题

**Q：卡在「正在等待相机进入服务模式…」？**
A：旧构建确实会卡住并把相机留在服务模式。当前版本会先用 SetupAPI 发现 `0x0336`、自动装 WinUSB，失败时会尝试自动退出服务模式；如果仍失败，拔插一次数据线即可回到 `0x0E76`。

**Q：设备管理器里显示「无法安装此设备（错误 28）」？**
A：这就是服务模式设备没驱动。点「驱动准备 → 扫描设备 → 绑定 WinUSB」手动装一次，或者直接重试只读检查让程序自动补装。

**Q：绑定 WinUSB 后相机盘符消失了？**
A：正常。绑定后相机不再以 MTP/MSC 出现在资源管理器，只对 libusb 可见。想恢复，在设备管理器卸载该设备再拔插即可。

**Q：「恢复整份备份」是灰的？**
A：需要先完成只读检查（拿到兼容性），并且备份列表里要有**同机型同固件**的 `.a6700backup`。备份目录在界面下方有显示。

**Q：为什么不提供完整固件备份？**
A：上游没有实现，这个项目也没有自己造。现在能存的是**功能状态**的稀疏快照（260 个扇区），不是整盘镜像，救不了砖。

**Q：Python 需要装吗？**
A：不需要，冻结包自带运行时。源码运行才需要 Python 3.10+，依赖见 [requirements.txt](requirements.txt)。

## 验证状态

**本机真机验证（A6700 + 固件 2.00）**

| 路径 | 结果 |
| --- | --- |
| 只读检查 | 260 扇区 / 133,120 字节，兼容性通过，六项状态读出 |
| 功能状态备份 | 41,582 字节，SHA-256 复算一致（2026-10-23） |
| 解锁写入 | `completed`，相机内二次校验 + 独立回读通过（2026-10-23） |
| 关闭写入 | `completed`，`touched=4`，重启后仍为关闭（2026-10-23） |
| 备份恢复 | `restored`，134 扇区 / 326 字节回写 + 独立回读（2026-10-23） |
| 菜单文字写入 | 145,612 → 145,708 字节，五块全部回读一致；关机重启后菜单显示 `Classic Chrome` / `Classic Neg.` / `Positive Film` / `Negative Film`（2026-10-25） |
| 菜单文字还原 | 145,612 字节 / sha256 `fe263360…`，与出厂资源逐字节一致（2026-10-25） |
| 菜单文字（中文简称） | 145,692 字节，四个槽位显示 `富士CC` / `富士NC` / `理光正片` / `理光负片`，宽度正常（2026-10-25） |

**离线验证**：86 个 pytest 用例通过（1 个按环境跳过）、七页界面离屏渲染、冻结包 `--offline-self-test` 九项通过。

**未验证**：失败回滚（需要人为制造相机内校验失败）、跨固件／跨机型拒绝路径、干净机器上从零开始的驱动引导全流程、`/setting/` 写入通路。细节见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 命令行与开发

```powershell
# 界面
.\Powerful6700.exe

# 离线自检（不接相机）
.\Powerful6700.exe --offline-self-test
.\Powerful6700.exe --offline-self-test --json selftest.json

# 环境诊断（JSON）
.\Powerful6700.exe --diagnose

# 渲染七个页面截图（验证冻结包里的界面）
.\Powerful6700.exe --render-pages shots
```

源码开发：

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m PyInstaller packaging\Powerful6700.spec --noconfirm
```

| 文档 | 内容 |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 30 个补丁点、真实操作顺序、结果分类 |
| [docs/FEATURES.md](docs/FEATURES.md) | 现有功能逐项说明：入口、改了什么、验证到哪一步、边界 |
| [docs/VALIDATION.md](docs/VALIDATION.md) | 已／未验证清单与复现步骤 |
| [docs/BUILD.md](docs/BUILD.md) | 离线建环境、打包、发布 |
| [docs/UPSTREAM-NOTES.md](docs/UPSTREAM-NOTES.md) | 与上游 0.2.0 的逐项差异 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 上游功能计划表对照与后续方向 |
| [docs/PUBLISHING.md](docs/PUBLISHING.md) | 发布硬条件（GPL、路径、运行期数据） |

## 来源与许可

- 上游：[xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) v0.2.0，GPL-3.0-only。运行时副本位于 `third_party/a6700_unlock/`，许可证与 NOTICE 一并保留。
- 本项目同样以 **GPL-3.0-only** 发布：分发本项目的二进制时，请同时提供对应源码（即本仓库同 tag 的代码）。
- 本项目是**非官方**工具，与 Sony 及上游作者均**无隶属关系、也未获其背书**。真实固件修改存在变砖、设置或数据丢失的风险，请自行评估。
- 本项目不含任何固件镜像、密钥、序列号或 ProductInfo 原文；仓库里的转储工具只处理你自己从自己相机读出的文件。
