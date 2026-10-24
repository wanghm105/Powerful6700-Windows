# A6700 破解重要突破记录

> 约定：从此以后每有重要突破都追加到本文件（用户 m03543 要求）。
> 项目根：`D:\DSH Desktop\Project`；工具在 `Powerful6700Win\tools`；固件镜像在 `firmware`。

## 2026-10-24 · 突破 1：CP 单元可读可写（19 个单元全部打通）

- 协议：Senser `pFunc 0x40`，正文 `pack('<HH',0x603,0x40|0x41) + pack('<II', key, 1)`；
  读=0x40、写=0x41；单元大小 0x02a40001=8192、0x02a4000d=28672；CP 读需要吃 0x200 结束包。
- 工具：`tools/cp_read.py`、`cp_write.py`、`cp_patch.py`（一次会话多单元）、`cp_survey.py`（19 单元全量）、`probe_slots.py`。
- 实测：19 个单元全部读取成功，落盘 `firmware/cp/units/`。单元目录在 `cpapp-b.bin` 偏移 0xC2A5B0（19 条 12 字节 `{key, ram, size}`）。
- 布局：0x02a40001 参数表 @0x1200、色度 `0x1250 + 槽×64`（32 int16 = 24 有效 + 8 零）；0x02a4000d 参数表 @0x196、矩阵 `0x1e0 + 槽×768`（前 576 B = 3 端点 × 16 × 6 int16）。

## 2026-10-24 · 突破 2：菜单文字 = UXC-v7 资源文件（可改，格式已完全解析）

- 相机 `/usr` = 分区 `/dev/nflasha15`（**ext2**，块 1024、inode 256、164,592 inode），因此
  相机里的 `/usr/share/app` ↔ 分区里的 **`/share/app`**（162 个文件）。
- 语言资源：`string_<语言>.uxc` + 变体 `_f` / `_func_j` / `_g`（**不是** A7CR 的 `_vertical/_horizontal`）。
- UXC-v7 格式（与 `refs/a7c2-fl23/src/looks/looktool/resources.py` 完全一致）：
  魔数 `uxc\x07\0\0\0\0`；`kind=8`；`group`；`descriptor = count | (((count+1)&~1)<<12)`；
  索引区 16 位指针 @0x10；记录 `u32 0x1e000000|(rid&0xffffff)` + UTF-8 + NUL，4 字节对齐；
  `rid = 0x02000000 | ((group<<13)+i)`；`base=(16+count*2+3)&~3`。
- A6700 实测四个文件：主 129,432 B（group 39, count 3545）、`_f` 145,612 B（group 227, count 4785）、
  `_func_j` 167,616 B（group 4, count 4851）、`_g` 100,068 B（group 3, count 2439）。
- `_f` 里找到十个外观缩写 rid：ST 0x021c658e、PT 0x021c6654、NT 0x021c6434、VV 0x021c687b、
  VV2 0x021c689a、FL 0x021c6cc9、IN 0x021c6857、SH 0x021c6961、BW 0x021c65f8、SE 0x021c658a；
  以及 `外观` 0x021c6a6c、`自定义外观` 0x021c6c81 / 0x021c6f50。
- 结论：**现有菜单项可改名**（含六个自定义位）；「新增第 12/13 个外观枚举」不可行——
  appFw 的模型枚举只有 11 个（AUTO..SEPIA）+ 6 个 CREATIVE_BOX，A7C2/A7CR 是固件出厂自带 FL2/FL3。

## 2026-10-24 · 突破 3：出厂基线与「写入是否持久」的实测

- 断电重启后读到的 CP 单元出厂态：`sha256 46fdd14c471714f7`（`firmware/cp/unit-02a40001.factory.bin`）。
  之前用的 `72d3da86…` 是被早前「全色度清零」污染的中间态 —— **任何 CP 实验必须从断电后的出厂态出发**。
- 出厂态下槽 0 的色度本来就是全 0（零化 0 字节差异）→ 槽 0 不参与着色。
- 已知锚点（需要在新基线下复核）：槽 5=VV2、槽 6=PT、槽 8=FL（2FL 同组）、槽 9=SE。
- 可逆性：把出厂基线整份写回 → 回读差异 **0 字节**。
- 未解现象：用户报告 ST / VV / 1ST **缩略图与实际照片都变黑白**，且在拔线、取电池 5 秒后仍存在，
  而当时内存里只有「槽 1 被零化 35 字节」这一处差异。下一步要区分「CP 分区 flash 是否被相机回写」与
  「CP 由备份电容维持」，方法：正确偏移（单元 1 在分区偏移 0x5E8794，色度 0x5E99E4）整段比对 + 彻底放电测试。

## 2026-10-24 · 突破 4：快门声音的可改性（分析中）

- A7C2 的实现分两层（`refs/a7c2-fl23/src/shutter_sound/`）：
  ① on/off 改的是 CP 电子快门分支的一个窄开关，不碰提示音/AF 提示；
  ② install/restore 走独立的「kind3 声音钩子」——**同尺寸替换已编码的原生 BIN** 并保留压缩逆变换，
     另有 PCM16/LPCM 注册模板实验（40 字节 0x200d/0x0329 报文），但官方注明播放链路未验证。
- A6700 侧已知：`firmware/cp/SysSound.bin` 41,792 B 是高熵声音库（无明文名）；
  appFw 里引用 `/usr/share/avsystemsound/Dslr_Emnt_High_{Startup,Shutdown,SelfTimer_2sec,SelfTimer_RemoteRelease}.bin`
  → 快门/提示音很可能就是 `/share/avsystemsound/*.bin`（同一 ext2，可读写）。
- 下一步：列 `/share/avsystemsound`，导出快门音 BIN，判断编码（PCM/ADPCM/专有），再决定同尺寸替换路线。
