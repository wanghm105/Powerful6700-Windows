# A6700 固件 / 分区地图（只读取证）

相机：ILCE-6700，固件 2.00。所有数据来自**只读** dump（Jiritsu 文件命令 + dump_range.elf，
openat 恒为 O_RDONLY，载荷里没有 pwrite 路径），没有向相机写入任何字节。

工具：tools/dump_camera.py（单文件/分区，可续传）、tools/dump_parts.py（一次会话 dump 多个分区）、
tools/probe_camera.py（只读探针）。

## 1. 分区表（/dev/nflashaN，stat 实测）

| 分区 | 字节 | 文件系统 / 形态 | 内容要点 |
| --- | ---: | --- | --- |
| nflasha1 | 25,100,288 | FAT（mkdosfs，spc 32） | BOOT/、P1CHKSUM、DAT2、DAT3 |
| nflasha2 | 20,971,520 | FAT | UPDATER/（BACKUP.BIN、CXD90057.DTB）、APPFW_*/（DEFDET、PSD、FACEREC0-2、FACEDMY、ULOGIO） |
| nflasha3 | 78,643,200 | 非 FAT（固件/镜像区） | 待判定 |
| nflasha4 | 12,582,912 | 非 FAT | 待判定 |
| nflasha5 | 314,572,800 | WBI2 容器 | 资源 blob 库（见 §3） |
| nflasha6 | 26,214,400 | FAT | TMMC.JIT、LIBJIT.SO（JIT 缓存） |
| nflasha7 | 16,777,216 | 头部全 0 | 待判定（疑似镜像/备用区） |
| nflasha8 | 67,108,864 | FAT12 | CP 分区：cpapp-b.bin 等 12 个文件（见 §4） |
| nflasha10 | 12,582,912 | FAT | 相机 /etc：HOSTS、PASSWD、PAM/、SSH/、REGROOT.PEM |
| nflasha11 | 314,572,800 | 与 WBI 同尺寸 | 第二份 WBI 形态数据（内容与 nflasha5 不同） |
| nflasha12 | 41,943,040 | FAT | 空根目录（预留/日志区） |
| nflasha13 | 4,194,304 | FAT | HASH/、HISTORY/ |
| nflasha15 | 749,731,840 | cramfs(偏移 0x5479C) + gzip 流(0xD552E) | 应用固件分区；/usr/lib/appFw.so 从这里来 |
| nflasha18 | 20,971,520 | FAT | LENSFILE.BIN |

不存在：nflasha0 / 9 / 14 / 16 / 17 / 19 / 20（stat 直接失败）。

## 2. 已落盘的镜像（本地 `firmware/` 目录，不入库）

| 文件 | 字节 | sha256 |
| --- | ---: | --- |
| appFw-2.00.so | 89,027,992 | 721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d |
| nflasha8-2.00.bin | 67,108,864 | 3bddcce378438423617a7c647ab862e5fd4ee6d0d4f627b769b4b08007457dcc |
| cp/cpapp-b.bin | 17,892,024 | 43c5d056ed935795…（完整值见 cpapp-b.bin.json） |
| nflasha5-2.00.bin（WBI） | 314,572,800 | 56e0e220cf0956f2ee8d524a8b805c4da8f700b40ce667f63151d00f4eecb2ab |
| parts/nflashaN-{ext,def}.bin | 见分区表 | 极端参数态 / 默认参数态两轮全分区快照 |
| BODYDATA-2.00.dat（官方固件包） | 1,024,017,848 | d3c7db5b9b40c89b11ecf03addf0f6ff1d9b917acf9f55e46360462e86db847c |

dump 命令（相机在 MSC 0x0E76，已绑 WinUSB）：

```bash
cd Powerful6700Win
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe tools/dump_camera.py --path /dev/nflasha8 --out ../firmware/nflasha8-2.00.bin
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe tools/dump_parts.py ext nflasha13 nflasha4 nflasha10   # 一次会话多个分区
```

实测速率 3.7–3.9 MiB/s（67 MB 约 17 s，314 MB 约 82 s）。

## 3. nflasha5（WBI）里的资源名字

容器头是 WBI2，内部按名字注册 blob。与创意外观直接相关的名字：

- CREATIVE_STYLE_PLUS_{STANDARD,VIVID,NEUTRAL,PORTRAIT,FILM,SEPIA,RETRO,AIRY,BRILLIANT,BLACK_WHITE,INVALID}
- CREATIVE_STYLE_PLUS_CREATIVE_BOX_1 … _6 ← 相机菜单里的 1ST / 2FL / 3IN / 4SH / 5VV2 / 6BW 六个自定义位
- ICON_TOUCH_FUNCTION_AUTO_CUSTOMIZE_CREATIVE_LOOK_*、CINEMATIC_MODE_LOOK_*（含 USER1..USER16）

> 注意：这些只是 **blob 名**。外观的显示文字与参数值都不是明文——WBI 内容整体是压缩/加密的，
> 明文搜索（UTF-8 / UTF-16 / zlib）全部 0 命中，详见 FL2-ROUTE.md §1.5。

## 4. nflasha8（CP 分区）是 FAT12，不是裸程序

- 引导扇区：bps 512 / spc 32 / rsvd 32 / nfats 2 / rootent 512 / fatsz16 32；根目录 0xC000，
  数据区 0x10000，簇 16 KiB。fatsz32 字段是垃圾值，算偏移必须用 fatsz16。
- 12 个文件：cpapp-b.bin 17,892,024 / cpImg.dat 1,885,696 / nor_ldr.img 417,792 /
  OldAmtCL.bin 161,766 / MIS.bin 119,296 / DmmCfg.bin 43,972 / SysSound.bin 41,792 /
  mini_ldr.bin 40,752 / loader_spi.bin 39,184 / DGU.bin 24,336 / pcie_phy_fw.bin 16,384 / tomco.txt 741。
- cpapp-b.bin 是 ARM32 Thumb 裸镜像（首 4 字节 e59f1004 = ldr r1,[pc,#4]），不是 ELF；
  它自己内部还有一个 CP 单元目录（见 FL2-ROUTE.md §1.2）。

## 5. 与现有写窗口的关系

本项目只写 260 个固定扇区（133,120 B）：nflasha15（appFw）、nflasha5（WBI）、nflasha8（CP）各一小段。
研究阶段的所有结论都**不进**这个窗口：要动新地址必须另做 catalog（新增 target 扇区 + 结构守卫 +
未管理字节哈希），并重新走四步验收（离线预检 → 只读检查 → dry-run → 真机写入）。
