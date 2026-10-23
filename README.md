# Powerful6700 · Windows

Sony A6700（ILCE-6700，固件 2.00）桌面工具的 **Windows 端实现**。它以
[xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful)（GPL-3.0）
的 Python 运行时代码为底座，把原先**只支持 macOS / Apple Silicon** 的设备连接层、驱动准备、
桌面外壳与打包方式整体替换为 Windows 实现；产品完整度对齐
[QAQLeonard/a7c2-fl23-research](https://github.com/QAQLeonard/a7c2-fl23-research)（A7C2 的
Windows/macOS 桌面工具）：同样是「安装包 + 图形界面 + 驱动一键准备 + 只读预检 → 备份 → 写入 →
回读校验」的完整闭环。

上游应用在 Windows 上完全跑不起来（README 明写「Windows 与 Intel Mac 暂不提供安装包」、
「设备框架当前支持 macOS／Linux…Windows 尚未适配」），因此本项目的价值不是换皮，而是补上
三块 Windows 独有的东西：

1. **设备连接层**：WinUSB 绑定 + libusb-package 的 libusb-1.0.dll + Senser 协议双阶段认证，
   含进入服务模式后 0x0336 新设备的第二次驱动准备；
2. **可写数据目录与诊断**：路径探测、离线自检、环境诊断（上游 doctor 的 `platform` 检查
   在 Windows 上恒为 False，会永久阻塞整个流程）；
3. **桌面外壳与打包**：PySide6 图形界面 + PyInstaller onedir 冻结包，不需要用户装 Python。

## 兼容范围（与上游一致，不做扩展）

- 机型：Sony A6700（ILCE-6700）
- 固件：2.00
- 其它机型或固件版本**未经任何验证**，本程序不提供、也无法提供兜底。
- 固定写窗口：`/dev/nflasha15`（appFw）、`/dev/nflasha5`（WBI）、`/dev/nflasha8`（CP）
  上的 260 个扇区 / 133,120 字节，其中 149 个目标扇区 + 111 个结构守卫；每个目标扇区的
  校验值是「把已知字段清零后对未管理字节求哈希」，因此同一扇区内的不同功能互不干扰。
- 单个未知字节即阻断整次写入，没有强制开关。

## 能做什么

| 功能 | 说明 |
| --- | --- |
| 只读兼容性预检 | 读 260 个扇区，逐项校验已知字段、守卫与未管理哈希，得到每个功能的开关状态 |
| 解锁 / 关闭功能 | FTP、关机快门帘、灵活曝光、电子快门声音（以清单里的可用项为准） |
| 功能状态备份 / 恢复 | `.a6700backup` 稀疏快照，要求同机型 + 同固件 + 同适配版本 |
| 驱动准备 | 一键下载并运行 libwdi 的 `wdi-simple.exe`，把 0x047D / 0x0E76 / 0x0336 绑定到 WinUSB |
| 环境诊断 / 离线自检 | 不接相机也能验证运行环境、载荷完整性与界面可用性 |

> **真机状态（2026-10-23，A6700 + 固件 2.00）**：只读检查、功能状态备份、解锁写入、关闭写入、
> 备份恢复五条路径都已在本机 Windows 上跑通（恢复 `status=restored`、`verified=true`、
> `touched=134` 扇区 / 326 字节，回读六项状态与备份一致）。
> 失败回滚（人为制造相机内校验失败）与跨固件/跨机型兼容尚未验证——细节见 `docs/VALIDATION.md`。

**没有**的能力（上游也没实现，本程序不发明）：整盘/完整固件备份与恢复、位移多帧合成、
动态增强防抖。关闭解锁功能不等于恢复官方固件。

## 快速开始

### 直接用打包好的程序

```
dist/Powerful6700/Powerful6700.exe
```

首次使用按界面顺序走：**操作前须知 → 相机准备 → 驱动准备（按需）→ 只读检查 → 选择功能 →
解锁/关闭/备份/恢复**。数据目录默认就在**程序目录下的 `.data`**（驱动组件、备份、状态、
运行日志都在里面，绿色副本整包拷走即可带走备份）；该目录不可写时才退到
`%LOCALAPPDATA%\Powerful6700Win` 或系统临时目录，可用环境变量 `POWERFUL6700_DATA` 覆盖。

> 为什么不用 `%LOCALAPPDATA%` 打头：以管理员身份运行时该目录可写、普通权限运行时可能被拒，
> 同一个程序就会在两种权限下落到两个不同的数据目录，驱动组件与备份互相“看不见”。

### 从源码运行

```bash
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pytest tests -q        # 37 passed / 1 skipped
./.venv/Scripts/python.exe main.py                   # 启动图形界面
./.venv/Scripts/python.exe main.py --offline-self-test
./.venv/Scripts/python.exe main.py --diagnose
./.venv/Scripts/python.exe main.py --demo            # 演示模式，不连相机
```

依赖安装、离线 wheel 与打包细节见 [docs/BUILD.md](docs/BUILD.md)。

## 相机准备（缺一不可）

1. 关机状态下把相机的 USB 连接模式设为「海量存储（MSC）」，不要用 MTP / 电脑遥控 / USB 流式传输；
2. FTP 菜单保持关闭（仅当机身已有该菜单时；首次解锁通常没有 FTP 菜单）；
3. 关闭自动关机，确认电量充足；
4. 只连接一台目标相机，操作期间保持开机。

顺序错误时程序会给出具体原因（找不到 MSC 设备、找到多台、服务模式设备未出现等），按提示
处理完重试，不要反复拔插。

## 文档

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Windows 适配层结构、补丁点与数据流
- [docs/BUILD.md](docs/BUILD.md) — 依赖、测试、PyInstaller 打包与产物
- [docs/VALIDATION.md](docs/VALIDATION.md) — 已离线验证 / 仍需实机验证的边界
- [docs/UPSTREAM-NOTES.md](docs/UPSTREAM-NOTES.md) — 上游清单哈希过期问题及处理依据

研究记录（只读取证，不属于应用运行路径）：

- [docs/FIRMWARE-MAP.md](docs/FIRMWARE-MAP.md) — 分区地图、镜像哈希、只读 dump 命令、WBI blob 名
- [docs/CP-PARTITION.md](docs/CP-PARTITION.md) — CP 分区（nflasha8）解剖：FAT12 卷、12 个文件、look/LUT 字符串证据
- [docs/FL2-ROUTE.md](docs/FL2-ROUTE.md) — **FL2/FL3 权威记录**：已确认偏移、19 个 CP 单元全景、真机槽位归属、外观标签判定不可行、剩余方向（CP tone 单元）与判据
- [docs/CARD-SPEED.md](docs/CARD-SPEED.md) — 「介质速率 → 允许录制格式」判定的静态调查（结论：没有可改的默认档位，判定端只传档位索引）
- [docs/FL23-INVESTIGATION.md](docs/FL23-INVESTIGATION.md) — 早期调查中间记录（历史，含当时的错误假设）
- [docs/FEASIBILITY-FL23.md](docs/FEASIBILITY-FL23.md) — 最早的可行性判断（历史）
- [docs/ROADMAP.md](docs/ROADMAP.md) — 上游功能计划表与本项目的进度

## 许可与声明

本项目是非 Sony 官方的开源工具，按现状提供，不承诺无缺陷、操作安全或恢复成功。
与 Sony、上游作者均无从属关系，也未获得其背书。

上游运行时代码为 GPL-3.0-only（见 `third_party/a6700_unlock/LICENSE`），因此本项目整体
按 GPL-3.0-only 发布（`LICENSE`）。`third_party/a6700_unlock/` 是
[xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful) 0.2.0 的
原样副本（未修改），本项目的全部改动都在 `src/a6700win/` 里，逐项记录在
`docs/ARCHITECTURE.md`（22 个补丁点）与 `docs/UPSTREAM-NOTES.md`（与上游的差异）。
按 GPL-3.0 要求，分发二进制时必须同时提供对应源码——发布本项目的 zip 时请一并附上同一
提交的源码包。

真实固件修改存在无法启动（变砖）、设置或数据丢失的风险；非官方固件修改可能影响保修资格与
官方售后支持，具体取决于当地适用政策与法律。
