# 外观数据的持久化载体：nflasha2 里的 BACKUP.BIN 与 PSD.BIN

更新时间：2026-10-24　相机：ILCE-6700 / 固件 2.00　方式：静态解析 + 只读分区镜像对比

本文回答一个问题：**我们在 CP（cpapp-b.bin / 单元 RAM）里改的外观数据，到底是什么东西、存到哪、能不能持久、能不能反过来当作「写入落点」。** 结论先给：CP 单元是一块可由相机自己备份回 flash 的内存镜像，落点在 nflasha2 分区的 `BACKUP.BIN`；而同分区的 `PSD.BIN` 是出厂静态数据，从不改变。

---

## 1. nflasha2 是一个 20 MB 的 FAT12 卷

镜像：`firmware/parts/nflasha2-def.bin` / `nflasha2-ext.bin` / `nflasha2-now.bin` / `nflasha2-post.bin`（各 20,971,520 B）。

| 项目 | 值 |
| --- | --- |
| bytes/sector | 512 |
| sectors/cluster | 32（簇 16 KiB） |
| reserved | 1 |
| FAT 份数 | **1** |
| sectors/FAT | **4**（fatsz16；BPB 里的 fatsz32 是垃圾值，不要用） |
| root entries | 512 |
| 根目录 | `0xa00` |
| 数据区起点 | `0x4a00` |
| FAT 表 | `0x200` |

解析工具：`tools/nflasha2.py`（`--list` / `--extract --out DIR` / `--get NAME`；`--extract` 同时写 `manifest.json`，含每个文件的 size 与 sha256）。

19 个文件（def 快照）：

| 文件 | 大小 | 说明 |
| --- | ---: | --- |
| PSD.BIN | 2,895,872 | 出厂静态数据（`PF` 容器），见 `3 |
| BACKUP.BIN | 2,351,065 | **CP 单元镜像（`BK4` 容器）**，见 `2 |
| BACKUP.BAK | 2,351,065 | 上一份备份，与 BACKUP.BIN 不完全相同 |
| DEFDET.BIN | 5,242,880 | 机身缺陷/校准数据，def→post 完全一致 |
| DMMCFG.BIN | 66,772 | 万用表配置 |
| CXD90057.DTB | 16,875 | 设备树 |
| FACEREC0-2.BIN | 57,888 ×3 | 人脸识别库（post 快照里变成 FACEREC0-7） |
| FACEDMY.BIN | 51,200 | 人脸占位 |
| ETOOLS | 4,096 | 工厂工具痕迹 |
| ULOGIO.BIN | 2,852 | 日志 |
| KEMCO.TXT | 1,731 | 文本 |
| .hasp | 88 |  |
| 其余（UPDATER / appfw_infra / development.txt / mode / gps） | 0 | 空占位 |

---

## 2. BACKUP.BIN = CP 单元 RAM 的镜像（关键证据）

容器头：

- `0x0c` 处 magic `BK4`；
- `0x40` 处 ASCII 构建串 `32001_06.20250524 01`；
- 头部若干 u32：`0x333`、`0x9131`、`0x37b60`、`0xabee5`、`0x1e6f43e` …（语义未定）。

19 个 CP 单元按 key 顺序、4 字节对齐、连续存放在 `0x1b0f3c` 之后：

| 单元 key | 在 BACKUP.BIN 里的偏移 | size |
| --- | ---: | ---: |
| 0x02a40000 | 0x1b0f3c | 4,608 |
| 0x02a40001 | 0x1b2140 | 8,192 |
| 0x02a40002 | 0x1b4144 | 768 |
| 0x02a40004 | 0x1b464c | 1,280 |
| 0x02a40005 | 0x1b4b50 | 1,280 |
| 0x02a40006 | 0x1b5054 | 1,280 |
| 0x02a40008 | 0x1b5a5c | 1,280 |
| 0x02a40009 | 0x1b6060 | 1,024 |
| 0x02a4000b | 0x1b6568 | 256 |
| 0x02a4000c | 0x1b666c | 512 |
| 0x02a4000d | 0x1b6870 | 28,672 |
| 0x02a4000e | 0x1bd874 | 1,792 |
| 0x02a4000f | 0x1bdf78 | 512 |
| 0x02a40011 | 0x1be380 | 512 |

（全零单元 0x03 / 0x07 / 0x10 / 0x12 无法用内容定位，但目录给了它们的 size：512 / 512 / 1,280 / 1,280。）

**决定性对比**：

- `nflasha2-post`（07:06 快照）里的 BACKUP.BIN，其 unit 0x02a40001 与 0x02a4000d 与 **07:19 从相机实时读到的 CP 内容逐字节相同**（diff 0）；
- `nflasha2-def`（04:48 快照）则与它们差 34 / 453 字节；
- def → post 的 CP 区域共变 487 字节（136 段）。

→ **相机自己会把 CP 单元状态写回 nflasha2:\BACKUP.BIN**。BACKUP.BIN 就是 CP 的持久化副本，而不是随机数据。

---

## 3. PSD.BIN 是出厂静态数据（不随时间变）

容器 `PF`：

- u32 `0x00904650`（`PF` magic）、头部长度 `0x150`、文件长度 `0x2c3000`；
- 两个 32 位摘要 `0xddd197de` / `0xdf43cfb2`；
- `0x14` 处计数 **0x11 = 17**（17 个段）；
- `0x40` 起是曲线形状 u16 递增序列：1780、2036、2389、2864、3575、4699、6983、13087，随后 `0x0f57`、`0xffda`；
- `0xf0` 起是 u32 偏移表，步长 `0x6f70`（28,528）= 记录长度。

**def / now / post 三个快照的 PSD.BIN 完全一致（sha256 相同）** → 出厂数据，不承载运行时外观改动，也不是写入落点。

---

## 4. 负结果：机身里改「自定义外观参数」不进 CP

用户把 `2FL` 的八个参数全部拉到 9（ext 态），之后调回默认（def 态），两次都 dump 了 nflasha2。用 `tools/nflasha2.py` 各自取出 BACKUP.BIN，逐个单元比对：

    unit 0x02a40000 … 0x02a40011    ext ≠ def 的字节数：全部 0
    BACKUP.BIN 总差异 1,975 字节 / 117 段，全部落在 CP 单元区之外
    （头部 0x20-0x2c、0x66514-0x66634、0xabae0 一带的单字节计数器等）

→ **外观参数（contrast / fade / saturation …）不写在 CP 单元里**。此前全分区 diff 也没在 nflasha5 / nflasha8 / nflasha10 / nflasha11 里找到它们，唯一没全量 dump 的是 **nflasha15**（749,731,840 B，只存了前 4 MB）。

相机根目录列表里存在 `setting/` 目录（`tools/ls_camera.py` 实测：`/` 有 34 项，含 `setting/`、`var/`），而 `/usr` 已确认就是 nflasha15 的根分区（`/usr/lib/appFw.so` = 89,027,992 B 与 appFw 镜像同源）。**因此外观参数与 UI 资源最可能都在 nflasha15 的文件系统里**，这是下一个要取的东西。

---

## 5. appFw 里没有「静态外观数据表」，但有 16 个外观槽位的完整标签族

- `.rela.dyn`：`0xe440`，大小 `0x1756dd0`（1,019,710 条 `R_AARCH64_RELATIVE`）。
- `VAL_setting_creative_style_plus_CREATIVE_STYLE_PLUS_STANDARD` 字符串在 `0x42087aa`，其字面量槽在 **`0x4926e40`**（另有 `0x7e6620`）。
- 从 `0x4926e40` 起是 16 字节记录 `{char* name, 0}` 的资源名字典：`creative_style_plus` 的 STANDARD / PORTRAIT / NEUTRAL / VIVID / BRILLIANT / FILM / RETRO / AIRY / BLACK_WHITE / SEPIA + CREATIVE_BOX 1-6 + INVALID + PRM_ALL。
- 紧接着 `0x4926ed0` 起是 `VAL_creative_look_option_look0 … look15`，**每个 lookN 都是 10 个基础外观名（16 组 × 10 = 160 条）**，同一族里还有 `creative_look_option_{contrast,fade,clarity,fineness,…}0..15`。

→ A6700 的数据模型就是 **16 个外观槽位**（10 基础 + 6 自定义），没有 look16 / look17。这与用户看到的 16 项菜单（ST,PT,NT,VV,VV2,FL,IN,SH,BW,SE,1ST,2FL,3IN,4SH,5VV2,6BW）一致。

**纠正**：`docs/FL2-ROUTE.md` `1.2 曾把 appFw `0x49e34d0` 的 16 字节记录表当作「11 条外观注册表」。实际那是 `RECORD_SETTING_600M_422_10BIT` … `150M_420_8BIT` 的**码率/记录设置表**（key 指针 0x42c6cf4 起）。外观标签在 `0x4926e40`，而 `ICON_TOUCH_*` 那 11 条字符串没有重定位槽（只被 pcrel 引用）。

---

## 6. cpapp 初始化数据块里有 9 个 1,024 字节的曲线记录（当前全是恒等曲线）

- 初始化数据块 `[0xFBF000, 0x11002B8)`（长度字段在 cpapp `0x20140`，本机值 `0x001412B8`）。
- 块内 `0xfe0b50` 起，步长 `0x400`（1,024 B），共 **9 条**：`0xfe0b50 / 0xfe0f50 / 0xfe1350 / 0xfe1750 / 0xfe1b50 / 0xfe1f50 / 0xfe2350 / 0xfe2750 / 0xfe2b50`。
- 每条前 61 个 u16 是一条单调递增曲线：`0x0000, 0x1000, 0x2000 … 0xf000`（16 点，步长 0x1000），然后 `0xf100, 0xf200 … 0xffff`（45 点，步长 0x100），其余填 `0xff`。即**当前全部是恒等曲线**（没有做色调压缩）。
- 假设（未验证）：这是一族 tone / gamma 曲线槽，运行时由 CP 代码按外观灌入实际曲线；若成立，它就是「不写 flash 也能改色调」的候选落点（对应 FL2-ROUTE.md 路线 C′）。
- 注意：不能用「文件偏移 + 0x108900」这种简单换算出 RAM 地址再去代码里找引用 —— 那是 A7C2 在它自己的 `patches.json` 里给出的关系，A6700 的加载基址还没坐实。

---

## 7. 这对 CC/CN 意味着什么

| 需求 | 载体 | 现状 |
| --- | --- | --- |
| 颜色倾向（矩阵 + 色度） | CP 单元 0x02a40001 / 0x02a4000d | 可读可写（RAM），**已证明会掉电恢复** |
| 持久化颜色 | nflasha2:\BACKUP.BIN（相机自己回写） | 已定位；我们还没有写 flash 的能力 |
| 色调（CC/CN 的 S 曲线） | cpapp 曲线记录 / appFw 管线 | 曲线记录位置已找到但恒等，语义未验证 |
| 外观文字（CC/CN 的名字） | nflasha15 的 `/usr/share/app/string_*.uxc` | 格式已解码，**需要写 flash 才能改名** |
| 外观参数（contrast/fade…） | 未定位，最可能在 nflasha15 | 需要先全量 dump nflasha15 |

**因此下一步的顺序是**：先把 nflasha15 全量只读 dump 下来（749,731,840 B，只读、无风险），在它的 ext2 文件系统里找 `setting/` 与外观参数的实际落点；有了落点再谈写 flash 的载荷。

---

## 8. 全量 dump nflasha15 之后的文件系统地图（2026-10-24 补）

`firmware/parts/nflasha15-full.bin`：749,731,840 B，sha256 `e900dd9eb938827fe7c300a2ca48fadfc95ebf81dc46cf364826e779973ddd33`
（只读 dump，49 s / 15 MB/s）。解析方式：`tools/ext4_walk.py --local <镜像>`（本段新增 `--local` 离线模式）。

| 分区 | 大小 | 文件系统 | 内容 |
| --- | ---: | --- | --- |
| nflasha7 | 16,777,216 | ext2 | **相机根文件系统**：bin / cert / cp / dev / etc / initrd / kmod / lens / lib / log / mnt / nmnt / proc / root / sbin / **setting** / sys / system / tmp* … 共 36 项 |
| nflasha15 | 749,731,840 | ext2 | 固件应用卷：bin / codec / data / kmod / lib / local / sabin / sbin / scenario / **share**（`share/app` 就是 162 个 `.uxc` 资源）/ tool / wifi-scripts / wlan |
| nflasha10 | 12,582,912 | FAT12 | 相机 `/etc`：PASSWD / SERVICES / HOSTS / MTAB / PAM.D / SSH / JIRITSU / KIKILOG.DAT(4.2 MB 日志) … |
| nflasha1 | 25,100,288 | FAT12 | BOOT / P1CHKSUM / DAT2 / DAT3（启动与校验） |
| nflasha11 | 314,572,800 | FAT16 | ACCESS~1.DAT / ACCESS~1.BAK（访问日志） |
| nflasha13 | 4,194,304 | FAT12 | HASH / HISTORY |
| nflasha18 | 20,971,520 | FAT12 | LENSFILE.BIN（镜头文件） |
| nflasha3 | 78,643,200 | FAT12 | ADAM_APP.BIN / AV-CAM.BIN / BONOBO.BIN / BT_FIRM.HCD / INITRD.IMG / SABIN / VMLINUX.BIN / WOLE_APP.BIN（内核与固件） |
| nflasha12 | 41,943,040 | FAT12 | 空目录 |
| nflasha4 | 12,582,912 | 非 FAT | 原始数据（无目录项） |

**关键负结果**：nflasha15 的 `/data/lut` 与 `/data/gridline` 都是**空目录**（相机自带的 LUT 目录没有被使用），nflasha7 的 `setting/` 在镜像里也是空的。也就是说：**外观参数（contrast/fade…）没有以文件形式出现在我们 dump 到的任何卷里**，最可能是关机时从 RAM 刷入、而两次 dump 都没赶上那次刷写；也可能是我们还没识别出承载它的那一段（`BACKUP.BIN` 0x664c0 一带是带 0x7f 高位的运行时指针，属 RAM 残渣，不是结构化参数表）。

因此「外观参数落盘」仍然**未闭环**；要闭环需要一次「改参数 → 正常关机 → 开机 → dump」的对比。但它已经不影响 CC/CN 的判断：真正的观感差异来自管线（appFw 矩阵 / cpapp 曲线），两者都要写 flash。

## 追加：CP RAM 写入的持久性被推翻（2026-10-24）

- 实验：把 unit 0x02a40001 slot6/slot4 改成降饱和值 → 回读一致 → **用户关机再开**。
- 结果：开机后 RAM unit 0x02a40001 = `91d5e040…`（**工厂值**），`/setting/BACKUP.BIN` 的同区段（0x1B2140）也是工厂值 → 本次写入既没留在 RAM，也没进 BACKUP。
- 与早前 mark 实验（unit 0x02a4000d 色度写入 64×0x11 后关机，BACKUP 0x1B7D00 出现标记）矛盾 → 结论修正为：
  1. CP RAM 的写入**不是必然持久**，取决于是否触发机身自身的「保存」路径；
  2. 上一次写入用的是自写脚本，结尾没有走 STOP_SENSER（正常退出服务模式），可能因此被丢弃；
  3. 任何 CP 写入实验都应走 `tools/cp_patch.py` / `cp_write.py`（它们会发 STOP_SENSER），并在关机前后各读一次 RAM + BACKUP 才能下结论。
- 对产品的影响：靠「写 CP RAM 让 CC/CN 长期存在」不成立；要么写 `/setting/BACKUP.BIN`（boot 时被读入），要么走 A7C2 的 cpapp 固件路线。