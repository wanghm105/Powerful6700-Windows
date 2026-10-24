# 与「刚解锁时备份」的完整对比（2026-10-24）

目的：确认这些天的 CP 实验、UXC 改名、cpapp 曲线实验之后，相机闪存里还剩什么改动。

## 方法与基线

| 目标 | 设备路径 | 大小 | 对比基线 | 基线时间 |
| --- | --- | --- | --- | --- |
| CP 分区 | `/dev/nflasha8` | 67,108,864 | `firmware/parts/nflasha8-ext.bin` | 04:44（刚解锁） |
| 设置分区 | `/dev/nflasha2` | 20,971,520 | `firmware/parts/nflasha2-def.bin` | 04:48 |
| 系统分区 | `/dev/nflasha15` | 749,731,840 | `firmware/parts/nflasha15-full.bin` | 07:51 |
| 应用固件 | `/usr/lib/appFw.so` | 89,027,992 | `firmware/appFw-2.00.so` | 02:16 |

工具：`tools/full_compare.py [cp|setting|usr|appFw]`

- 走 `a6700win.research.ServiceSession`（Jiritsu 通道），块 `0x40000`；`0x100000` 会撞上 `Response exceeds supported result size`。
- 读到 `.data/compare/<label>.bin.part`，可续传；同一进程内先读后比。
- 真机读长块偶发 `[Errno 5] Input/Output Error`（单会话约 80–100 MB 后出现，换新会话即恢复）；脚本对每块重试 6 次并逐次减半，仍失败就保存进度退出，外层最多 8 轮重新认证后续传。750 MB 的 `/usr` 分三段会话读完。

## 结果

| 目标 | 差异 | 性质 |
| --- | --- | --- |
| `/cp` | 406 字节 / 390 段 | 396 字节在 `cpapp-b.bin` 曲线区（0xFE0B50–0xFE2F50），**已用 `tools/restore_cpapp_curves.py` 写回工厂字节并回读一致**；其余 10 字节是根目录里 `cpapp-b.bin` 的目录项时间戳 |
| `/usr` | 23 字节 / 3 段 | 全部是 inode 的 atime/ctime/mtime（0x0284450C、0x02848A0C、0x0600D20D），**没有文件内容差异** |
| `/setting` | 627,926 字节 / 33,628 段 | 运行期文件：`BACKUP.BIN`、`BACKUP.BAK`、`ETOOLS~1`、`FACEREC0/1/2` 内容变化，`FACEREC3–7` 新增（人脸注册）；日志/计数区 |
| `appFw.so` | 0 字节 | 与出厂完全一致 ✓ |

### 关键：`/setting/BACKUP.BIN` 里的 CP 副本已回到出厂

| 单元 | 偏移 | 实时 sha256 | 出厂 sha256 | 差异 |
| --- | --- | --- | --- | --- |
| `0x02A40001` | 0x1B2140 | `72d3da86…` | `72d3da86…` | 0 |
| `0x02A4000D` | 0x1B6870 | `59aed2ed…` | `59aed2ed…` | 0 |

即：CP 的两块颜色/色度单元在 RAM 与持久副本里都是出厂值，之前实验留下的 bank 30/31 涂色也已清掉。
`BACKUP.BIN` 余下的 6,079 字节差异都在设置登记区（头部计数 0x20、0x4CDC0 起的项目表等），属于用户自己改的机身设置。

### UXC 名字已完全还原

`/usr/share/app/string_simplifiedchinese_f.uxc`（145,612 B）实时 sha256 前缀 `fe263360`，与最早的原件备份 `firmware/uxc/string_simplifiedchinese_f.uxc.20261023T233448Z.bin` **逐字节相同**。
（此前以为 07:51 的 `/usr` 备份里已是 CC/CN，实际那次写入因脚本漏写根本没生效，所以这份基线本身就是原名。）

## 结论

1. **内容层面，相机闪存已经回到出厂状态**：`appFw.so`、`cpapp-b.bin`、`*.uxc` 全部与备份一致；CP 颜色单元 RAM/持久副本一致。
2. 剩余差异只有三类，都不影响成像：`cpapp-b.bin` 的目录项时间戳、`/usr` 三个 inode 时间戳、`/setting` 的用户设置与人脸注册数据。
3. 下一轮做 CC/CN 时，改前先跑一次 `tools/full_compare.py cp setting` 存基线，改后再跑一次即可得到「这一轮究竟动了哪些字节」。
