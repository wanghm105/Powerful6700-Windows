# A6700 自定义快门声：发现、证据链与猜想

机型：Sony A6700（USB 服务模式 054c:0e8a → 054c:0336）
日期：2026-10-26

## 0. 读法

本文件只有三类陈述，正文内以方括号标记：

- 【核对】可用给定文件、偏移、长度、字节、算法重算得到完全相同结果。每条附「复现」一行，写清怎么重算。
- 【推论】由若干条【核对】通过具名步骤推出的结论。每条附「依据」一行，列出所引条目编号。
- 【猜测】未被任何观测直接证实的解释。每条附「依据」「判否」「判定实验」三行。

约定：

- 偏移一律给十六进制，必要时括注十进制
- 文件路径相对工程根
- 未特别说明时，「cpapp 偏移」指 firmware/cp/cpapp-b.bin 的文件偏移，「分区偏移」指 firmware/nflasha8-2.00.bin 的文件偏移
- 「零违规」指解码器在整段数据上没有触发任何一条拒绝条件

### 机器可读锚点

```json
{
  "files": {
    "cpSysSound":   {"path": "firmware/cp/SysSound.bin",   "bytes": 41792,    "sha256": "b60c99ceffe4ec1f0b6eee90b4449eecbcc7a7fc3603b046ce26162ad7a53cad"},
    "cpapp":        {"path": "firmware/cp/cpapp-b.bin",    "bytes": 17892024, "sha256": "43c5d056ed9357957c5e7cd1ae24928b077d26b6761bf193eefb303b0b32510d", "note": "patched: 0x387900 = 03 21"},
    "appFw":        {"path": "firmware/appFw-2.00.so",     "bytes": 89027992, "sha256": "721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d"},
    "partitionCp":  {"path": "firmware/nflasha8-2.00.bin", "bytes": 67108864, "sha256": "3bddcce378438423617a7c647ab862e5fd4ee6d0d4f627b769b4b08007457dcc"},
    "partitionUsr": {"path": "firmware/nflasha5-2.00.bin", "bytes": 314572800}
  },
  "fat12": {"cluster_bytes": 16384, "data_start": "0x10000", "root_dir": "0xC120",
            "SYSSOUNDBIN":  {"cluster": 26,  "offset": "0x70000",  "bytes": 41792},
            "CPAPP-B BIN":  {"cluster": 145, "offset": "0x24C000", "bytes": 17892024}},
  "patch": {"cpapp_offset": "0x387900", "partition_offset": "0x5D3900", "delta": "0x24C000", "before": "0021", "after": "0321"},
  "filter0": {"block_bytes": 32, "blocks": 1306, "samples": 40486, "min": -30720, "max": 30830, "rms": 6696,
              "lag1_coef_60_64": 0.8174, "lag1_coef_1_inverted": 0.9563}
}
```

正文中每条 F 的「复现」、每个 B 的「依据 / 判否 / 判定实验」、每个 L 的「影响 / 我们」都可用上表与 §9 的偏移直接对照。

## 1. 摘要

1. 【核对】A6700 的 /cp 分区里只有一个音频资源：SYSSOUNDBIN，41,792 字节。没有第二个音频文件。
2. 【核对】这 41,792 字节按 A7C2 假设的 32 字节 filter0 块规则可整段解码，1,306 块零违规，得 40,486 个样本。
3. 【核对】A6700 的 AP 侧（appFw-2.00.so）不读 CSV 登记表：avsystemsound 只出现 4 次，全是开机音硬编码路径；beeplist / SysSound / BEEP_ID / SHUTTER_SOUND 命中数均为 0。
4. 【核对】A6700 用函数注册声音：model::sequence_boot::regist_beep_signals(model::beep_sound_id_t, uint64_t)，符号在 0x4079208。
5. 【核对】我们自己的解锁 catalog 改过 cpapp 0x387900 的 2 字节：00 21 → 03 21，并有一次记录（菜单 4 项正常、电子快门有克哒声、重启保持）。
6. 【猜测】这 2 字节就是「曝光起点播哪个声音」的 id，声音内容在 SYSSOUNDBIN 里按 id 索引。缺的是 id 到 (offset, length) 的映射表，和一次真机试听。

结论方向：【推论】A7C2 与 A6700 的编码层大概率同源（依据 F2、F3、4.6）；登记与触发层不同源（依据 F4、F5、F7、4.2）。

## 2. 证据链总览

分层，箭头表示「由下一层支撑」：

    E5 触发语义（1 字节改了什么）        ← 需要真机，未闭合
    E4 配置层：我们改过的那 2 字节        ← catalog + 分区换算 + 现场字节
    E3 代码层：字符串与符号命中/未命中    ← appFw / cpapp 全量扫描
    E2 资源层：41,792 字节的编码结构      ← filter0 解码器
    E1 容器层：/cp 是 FAT12，只有这一个音频文件 ← 分区镜像目录解析
    E0 文件锚：大小 + sha256              ← 四个文件

E0–E5 的名称在图里就地定义，正文引用某一层时即指图中那一行。

各层之间只允许单向引用：上层结论不得用来反推下层数据。本文所有【推论】都写明引用了哪些【核对】。

## 3.【核对】A6700 侧观察

### F1 /cp 分区是 FAT12，几何参数如下

- 簇大小 16,384 字节，数据区起点 0x10000（扇区 128），根目录 0xC120
- 簇号换算：区偏移 = 0x10000 + (簇号 − 2) × 0x4000
- 复现：读 firmware/nflasha8-2.00.bin（67,108,864 B），解析 0xC120 起 32 字节目录项（name[11] @0、attr @11、起始簇 u16le @26、大小 u32le @28），按上式换算后用整段 bytes.equal 比对目标文件。

验证结果（三条都成立才继续）：

| 8.3 名 | 大小(字节) | 起始簇 | 区偏移 | 校验 |
| --- | --- | --- | --- | --- |
| SYSSOUNDBIN | 41,792 | 26 | 0x70000 | 与 firmware/cp/SysSound.bin 整段相同 |
| CPIMG   DAT | 1,885,696 | 29 | 0x74000 | — |
| CPAPP-B BIN | 17,892,024 | 145 | 0x24C000 | 与 firmware/cp/cpapp-b.bin 整段相同 |
| LOADER~1BIN | 39,184 | 1,238 | 0x13C0000 | — |
| MINI_LDRBIN | 40,752 | 1,241 | 0x13CC000 | — |
| PCIE_P~1BIN | 16,384 | 1,244 | 0x13D8000 | — |
| TOMCO   TXT | 741 | 1,245 | 0x13DC000 | — |
| NOR_LDR IMG | 417,792 | 1,246 | 0x13E0000 | — |

复现：上式代入簇号即可，SYSSOUNDBIN 与 CPAPP-B 应得整段相同；这两个 equal 为真时，本文所有「分区偏移 ↔ 文件偏移」换算成立。

### F2 /cp 只有这一个音频资源

- 目录里 8 个实体文件，除 SYSSOUNDBIN 外无任何音频类文件名
- 「Shutter_Sha / Shutter_Ka / Kasha / KaSha / Shutter_Burst / Dslr_Emnt」在 cpapp-b.bin 与 nflasha8 的 /cp 侧均为 0 命中；nflasha5（/usr 侧）才有那 37 个音效
- 复现：对 cpapp-b.bin 整文件、以及 nflasha8 中 cpapp 之外的两段（0x0–0x24C000 与 0x135C2B8–0x4000000）做 bytes.find 计数，全部为 0

### F3 41,792 字节按 filter0 规则整段可解，零违规

- 41,792 = 1,306 × 32 = 653 × 64
- 每 32 字节一块：第 1 字节为控制字节 ctrl，其后 31 字节为有符号残差 r[0..30]
- scale = 1 << (ctrl & 15)；若 ctrl & 16，则 x = r × scale + (60/64) × last，否则 x = r × scale；last 更新为 x
- 合规条件：ctrl & ~0x1f == 0 且 (ctrl & 15) ≤ 8
- 实测：1,306 块全部合规，ctrl 取值集合 = {0x00–0x08} ∪ {0x10–0x18}，指数最大值 8，保留位恒 0，零次拒绝
- 解出 40,486 个样本；最小 −30,720，最大 +30,830（均落在 int16 内）；RMS 6,696
- 时长：24 kHz 下 1.687 s；48 kHz 下 0.844 s
- lag-1 自相关：系数 60/64 → 0.8174；系数 1.0 且 bit4 取反 → 0.9563；系数 0.938 / 0.9 更低
- 复现：按上述规则逐块解，统计 min/max/RMS/lag-1；系数变体只改 x 的预测项

前三项（块数、ctrl 集合、零违规）是硬约束：换任何一个参数都会立刻出现拒绝。

### F4 AP 侧不读 CSV 登记表

appFw-2.00.so（89,027,992 B）里 avsystemsound 的 4 处命中，全是绝对路径，同属 sequence/sequence_boot.cpp 的字符串池（池起点 0x4078d6c）：

    0x4078e6c  /usr/share/avsystemsound/Dslr_Emnt_High_SelfTimer_RemoteRelease.bin
    0x4078eb0  /usr/share/avsystemsound/Dslr_Emnt_High_SelfTimer_2sec.bin
    0x4078eeb  /usr/share/avsystemsound/Dslr_Emnt_High_Startup.bin
    0x4078f1f  /usr/share/avsystemsound/Dslr_Emnt_High_Shutdown.bin

命中计数表（bytes.find 全量计数，含重叠）：

| 串 | appFw-2.00.so | cp/cpapp-b.bin | nflasha5-2.00.bin |
| --- | --- | --- | --- |
| avsystemsound | 4 | 0 | 12（全为 appFw 副本，见 F5） |
| BEEP_SET_CUSTOM | 2 | 0 | 2 |
| beep（小写） | 12 | 3 | 12 |
| beeplist | 0 | 0 | 1（仅目录项 @0x67156d8） |
| SysSound | 0 | 0 | 1（仅目录项 @0x6715608） |
| BEEP_ID | 0 | 0 | 0 |
| SHUTTER_SOUND | 0 | 0 | — |
| CUSTOM_SOUND | 0 | 0 | — |

复现：分别对三个文件做 find 计数；nflasha5 的 12 处全落在 0x58e7060 与 0x94eba0 两簇，内容是 appFw 在镜像内的重复副本（同池含 sequence_boot.cpp 与那 4 条路径），因此不构成第二个读取者。

### F5 A6700 用函数注册声音

appFw-2.00.so 0x40791d8–0x4079298 的符号池：

    0x40791d8  void model::sequence_boot::adf_set_volume_i()
    0x4079208  bool model::sequence_boot::regist_beep_signals(model::beep_sound_id_t, uint64_t)
    0x4079260  void model::sequence_boot::regist_beep_signals_i()
    0x4079298  void model::sequence_boot::run_i()

复现：在 appFw 里 find b"regist_beep_signals"，读前后各 0x40 字节的 ASCII 串。

### F6「自定义提示声」这个概念在 A6700 上存在

appFw-2.00.so 0x437daa1–0x437dc47 是一张连续枚举名表：

    EXTERN_VAL_BEEP_SET_CUSTOM_OFF   @0x437db16
    EXTERN_VAL_BEEP_SET_CUSTOM_ON    @0x437db35
    EXTERN_VAL_SYSTEM_SOUND_VOLUME_MUTE / _MINUS_18DB / _MINUS_15DB / _MINUS_12DB / _MINUS_9DB / _MINUS_6DB

cpapp-b.bin 0x93e44 起的设置键名池：base Init / ret_size / startupsound / logodisplay / ee_play / panelout / w_power_mode / logo_type / app_beep_set / beep_set_custom / volume / sublcd / boot_fact.type / liro_topology

cpapp-b.bin 的 ADF 声音接口串：

    0xbab880 27AdfSystemSoundSetBeepVolume
    0xbab8a0 25AdfSystemSoundStartTiming
    0xbab8c0 19AdfSystemSoundTable
    0xbab8e0 25AdfSystemSoundTableBundle
    0xbab960 20AdfSystemSoundVolume
    0xc17e4  SendADF_SysSetBeepVolume ERR_FATAL
    0xe1904a MSG_ID_INFRABB_AUDIO_SET_BEEP_LEVEL
    0xe1a688 MSG_ID_INFRABB_ADF_SYS_SET_BEEP_VOLUME
    0xe1a54e ... MSG_ID_INFRABB_ADF_SYS_GET_SYSTEM_SOUND_ADDRESS

复现：find 上述串并读偏移；枚举表内相邻项间隔 = 串长 + 1。

### F7 我们改过的那 2 字节：位置、换算、记录

- catalog 条目（third_party/a6700_unlock/data/a6700-2.00.json，155,851 B，sound 项共 9 条 edit）：

      id      cp-5d3900
      image   cpapp
      offset  6109440            (= 0x5D3900)
      edit    00 -> 03
      purpose "CP exposure-start sound mark: cpapp-b.bin 0x387900 movne r1,#0 -> movne r1,#3 (A7C II reference)"

- 换算：0x5D3900 − 0x387900 = 0x24C000 = 2,408,448 = CPAPP-B BIN 在 nflasha8 里的起始区偏移（F1 已用整段 equal 验证）
- 0x24C000 ÷ 512 = 4,704 → 分区第 4,704 扇区；catalog 用的「扇区 11932 + 扇内 256」等价于同一位置（11932 × 512 + 256 = 6,109,440 = 0x5D3900）
- 现场字节（cpapp 0x3878E8 起 40 字节）：

      61 58 0c e0 94 f8 df 09 01 e0 cc f3 3f f8 03 21
      00 28 45 f6 24 40 18 bf 03 21 21 50 20 44 b1 b1
      41 f2 fa 01 c0 f2 a1 11

  其中两处 03 21：第一处是原厂分支里本来就有的 MOVS r1,#3，第二处（0x387900）是我们改的
- 记录（写入轮次）：菜单 4 项正常、电子快门有克哒声、重启保持；回退方式为同一字段写回 00
- 复现：catalog 的 offset 减去 0x24C000 得文件偏移；读该处 2 字节

### F8 我们手上这份 cpapp-b.bin 是补丁态

firmware/cp/cpapp-b.bin @0x387900 = 03 21（MOVS r1,#3），出厂应为 00 21。依据：A7C2 对应位置原厂为 0021、其 selector 表指向后才是 0321；且我们 catalog 的动作就是把 00 改成 03。
复现：读 2 字节；与 catalog 的 edit 字段对照。

### F9 我们在 /usr 镜像上没解开的地方

- 目录项存在：nflasha5 @0x6715200 起是 ext2 目录块，解出 37 个音效条目（inode 10359–10396），含 beeplist.txt(10391)、SysSound.bin(10385)、Shutter_Sha.bin(10390)、Shutter_Ka.bin(10396)
- superblock 在 0x10600（fs_start 0x10200、bs 1024、inode_size 256、inodes_per_group 2032、blocks_per_group 8192、inodes 164,592、blocks 657,948）
- GD 表在 FS+2048，32 字节/组；按 gd5 的 inode_table = 0xa107 读 inode 10385 得 mode 0o120034 / size 438,907,584（垃圾）
- 全镜像搜 0o40755 的 inode 头字节 ed 41 为 0 命中
- 唯二对上的锚点：image_00_32_IPSX 的 inode 记录 @0x2e47b00、image_01_32_IPSX @0x2df1f00（均 256/128 对齐），但没有任何 GD 组的 inode_table 覆盖 0x2df1f00
- 结论：块号换算仍错着，/usr 侧文件内容尚未取出

## 4.【核对】A7C2 实现（读其仓库得到的理解，出入以源码为准）

来源：QAQLeonard/a7c2-fl23-research v3.0.3，HEAD 7827856，src/shutter_sound/ 共 17 个文件 3,617 行。

清点表（路径相对 refs/a7c2-fl23/src/shutter_sound/，行数为文件总行数）：

| 文件 | 行 | 文件 | 行 |
| --- | --- | --- | --- |
| boot_sound.py | 179 | boot_trial.py | 419 |
| buffer_trial.py | 383 | candidate.py | 200 |
| custom_sound.py | 192 | files_worker.py | 79 |
| inspect_native.py | 160 | media.py | 140 |
| native_codec.py | 136 | replacement.py | 170 |
| sound_cli.py | 640 | trial.py | 309 |
| verify_beeplist.py | 155 | native/buffer_probe.c | 204 |
| native/sound_files.c | 196 | native/sound_probe.c | 55 |
| requirements.txt | 85 B | 合计 | 3,617 |

该目录只有这些文件，没有隐藏的第五种实现路径；文档方面其仓库仅有 docs/zh-CN/{changelog,development,lut-formats,notices}.md，无快门声专章。

### 4.1 CP 层：0x393570 起共 25 字节（a7c2 2.01，cpapp-b.bin 文件偏移）

- selector 表 @0x393570，5 B：1b26034403 → 4426444444（保留 selector 1，复用原有 mode-0 与 mode-3 块，无 code cave）
- 门控块 @0x3935bc，20 B：dbf33afc0321002845f61c4018bf002121502044 → dcf3a1fa41f21901415c012916d1e0e700bf00bf
- 核心 @0x3935ca，2 B：0021 → 0321（唯一改变行为的立即数）
- 静音变体：新块前 14 字节 + 15e0 + 后 4 字节
- 7 处原厂指令指纹：0x39356c dfe801f0；0x39358e 45f61c4003210fe0；0x3935b6 215020440ae0；0x3935d0 b1b1；0x3935f8 45f61c4000212150；0x76fb02 4af6d070c0f201207047；0x7b0004 d0f8c85441f21901012d18bf0025049c6554
- 0321 与 0021 两个变体在原厂固件里本来就都在，补丁只是让 selector 1 指向 0321 那块
- 四状态判定（其 candidate.sound_state() 按字节比对给出）：off = selector 表原样 + 旧门控；legacy = selector 表原样 + 只改核心 2 字节；electronic_only = selector 表改后 + 新门控；muted = selector 表改后 + 新门控且第 15–16 字节换成 15e0；其余组合一律判为不支持的变体
- AP 门禁常量：0x286cde8 = 20af029000601391008c409100800391c0035fd6（audio getter）；0x2885488 = 40ae02f0006013910004429100002f91c0035fd6（table getter）

### 4.2 AP 层：0x3060a24 起 16 字节 boot 钩子 + 7 处读取器补丁

- 原：adrp(x0,0x4c14000) + b53f40f9000c2b91 + bl 0x36804c8
- 新：bl 0x2885488 + 00800591 + bl 0x2759ae8 + b53f40f9（先取声音表，再调单行 CSV 读取器）
- 0x2759b3c（fopen 失败致命路径）→ b 0x2759bc8（复用原生收尾，不新增代码空间）
- 读取器补丁：0x2759ae8 ff1f40d1→1f2003d5；0x2759be4 ff1f4091→1f2003d5；0x2759af4 与 0x2759bfc 02008fd2→020081d2；0x2759c0c e0ff8ed2→e0ff80d2（CSV 缓冲 0x7800→0x800）；0x2759c28 949a2991→b 0x2759bc8
- 私有路径 @0x48cfa83：/usr/share/avsystemsound/beeplist.txt → custom.txt（右侧补 0）
- 顺序：先准备读取器与私有路径，最后装 boot 调用；恢复逆序

### 4.3 登记表 12 字段

label, number, memory, filename, size, offset, access, priority, kind, continuous, length, first
约束：memory ∈ {PIN, APP}；access ∈ {AA_RT, AA_FIFO}；资源根目录 /usr/share/avsystemsound/；重复 beep id 且 file 非空即报错；可替换 label 限 BEEP_ID_KA / BEEP_ID_SHA / BEEP_ID_KASHA 或含 SHUTTER。

### 4.4 描述符 176 字节（由其 dev/ 的 unicorn 仿真反推）

[0]=priority(u8) / [1]=kind(u8) / [4:8]=first_length(u32) / [8:12]=loop_length(u32) / [16:24]=length(u64) / [24:32]=offset(u64) / [44:172]=filename(char[128])

### 4.5 40 字节描述报文 与 48 字节 RAM 注册 ABI

- 报文：@0 <4H = (0x200d, 0x329, 40, 0x8001)；address(u64)@8；length(u32)@16；[21:25] = (priority, 1, audio_format, continuous)；loop_length、first_length @28
- RAM 注册（buffer_probe.c）：u32 enabled, kind；u64 address, length；u32 priority, format, continuous, loop, first, pad
- 其源码记录的实机结论：PCM16 与 format1 试听产生噪声或错误声音，已禁用；只有 filter0 原生编码可用；空缓冲分配释放与 AP→CP DMA 往返已在真机跑通且逐字节相等

### 4.6 filter0

32 字节块，1 控制字节 + 31 有符号残差，scale = 1 << (ctrl & 15)，ctrl & 16 时加 (60/64) × last，补零到 64 字节对齐。

### 4.7 握手与事务

stage 走 /tmp/jiritsu/shutter.staged.so，请求与结果用 jiritsu(16, 00 ff 00 + 数据) 上传、jiritsu(18, 00 ff) 删除，每步回读确认；会话先找 054c:0e8a 走 transport.Session，找不到再找 054c:0336 走 transport.RecoverySession，15 s 超时；工作区外 .sound.lock 串行化，相机上有 libJit.so 就拒绝开始。
顺序：先装文件、后装 boot 钩子；恢复先撤钩子、后删文件；CSV 最后发布；新音频名不得出现在旧 CSV 里；异常一律 needs_review，绝不自动重放。

## 5.【推论】两机型差异

| 维度 | A7C2 | A6700（本文件证据） |
| --- | --- | --- |
| 声音登记 | 运行时读 beeplist.txt，12 字段 CSV | 编译期表 + regist_beep_signals(beep_sound_id_t, uint64_t)（F5） |
| 资源位置 | AP 侧 /usr/share/avsystemsound/，SysSound.bin 为打包仓 | CP 侧 /cp/SysSound.bin 41,792 B 是唯一音频资源（F1、F2）；AP 侧只硬编码 4 个开机音（F4） |
| 触发点 | AP boot 块 16 B 钩子，把 kind3 登记进表 | CP 曝光起点的一个立即数 r1（F7） |
| 改动面 | CP 25 B + AP 16 B + 读取器 7 处 + 2 个资源文件 | CP 1 字节 + AP 3 个菜单权限 byte（catalog sound 项） |
| 生效条件 | 冷启动 | 冷启动（我们既有记录覆盖过） |
| 缺口 | — | id → (offset, length) 映射表（L1） |

## 6.【猜测】七条

### B1 CP 的 r1 是「曝光起点播哪个声音」的 id，3 = 电子快门自定义声
依据：F7（catalog 条目 purpose 明写 movne r1,#0 → movne r1,#3，且标注 A7C II reference）+ F7 记录（改后电子快门有克哒声、重启保持）+ 4.1（A7C2 在同一语义位置改同一立即数，其源码把该块称为 exposure-start / gate）+ F6（CP 有 beep_set_custom 键与 ADF 取址消息）。
判否：00/01/02 全静音而 03 有音 → r1 只是通道选择，不是 id。
判定实验：L4。

### B2 快门音一定在 41,792 字节里
依据：F2（/cp 无第二个音频文件）+ F1（SYSSOUNDBIN 整段校验通过）+ F6（MSG_ID_INFRABB_ADF_SYS_GET_SYSTEM_SOUND_ADDRESS 表明 CP 向 ADF 取「系统声音地址」，说明库被载入 RAM 按偏移取）+ F8（我们只改 2 字节、不改资源，声音却变了）。
判否：替换库内字节后声音完全不变 → 另有来源。
判定实验：L1 + 一次资源替换（会改 /cp）。

### B3 F3 的 7 段就是 7 个 id 的音，顺序与 id 一致，边界 64 字节对齐
依据：F3（41,792 = 1306×32、零违规、可解）+ F3 的 7 段能量分布（段间有空档，像分段存放）+ 4.6（A7C2 的加载器与资源都按 64 B 单位）。
判否：段边界与 id 无关（id 只管音量或开关）。
把握：偏低——我们没有任何直接证据证明「段 = id」，只证明「能分段」。
判定实验：L4（改 id 听声音）+ L1（找到映射表）。

### B4 AP 侧那 33 个音效在 A6700 上不参与快门声
依据：F4（AP 侧 avsystemsound 仅 4 条、全是开机音；beeplist / BEEP_ID / SHUTTER_SOUND 全 0 命中）+ F1/F2（音频资源只在 /cp）+ F5（AP 用函数注册，不需要文件登记表）。
判否：删除或改名某个 AP 侧音效后快门声变化 → 说明有路径用到它。
判定实验：只读的可做版本 = 比对 AP 侧这些文件在 A6700 与 A7C2 是否同源（L6）。

### B5 beeplist.txt 在 A6700 上是占位或空文件
依据：F9（目录项存在但内容未取出）+ F4（AP 侧读它需要 beeplist 串，而该串 0 命中）。
判否：解出后大小非 0 且内容符合 12 字段格式。
判定实验：L5（解 ext2 inode 表）。

### B6 beep_set_custom 是独立的「自定义提示声」总开关，与快门音两条通路
依据：F6（BEEP_SET_CUSTOM_ON/OFF 枚举 + CP 键 beep_set_custom）+ F4/F6（SHUTTER_SOUND / CUSTOM_SOUND 全 0 命中，说明没有专门的快门音设置项）+ F7（快门音是由曝光分支的立即数决定，不经过设置键）。
判否：改 beep_set_custom 后电子快门声音跟着变 → 同一条通路。
判定实验：真机改设置键试听；索引方式见 L9。

### B7 filter0 变体未定：60/64 且 bit4 为预测标志（lag-1 0.8174），还是系数 1.0 且 bit4 取反（lag-1 0.9563）
依据：F3（两种变体都能零违规解码）+ 4.6（A7C2 假设 60/64）+ 4.5（其 PCM16 路线已失败，原生编码细节未被其源码闭合）。
判否：任一变体在已知原厂音上不能逐字节复现 → 该变体错。
关键限制：回环（先解再编）对任何单一系数都必然回到原字节，因此回环通过证明不了系数正确；只能拿一段内容已知的原厂音比对。
判定实验：L7。

## 7. 证据本身的局限

1. 我们这份 cpapp-b.bin 是补丁态（F8），任何「以我们这份为基线」的偏移推导都会错。
2. 绝对偏移不可平移：A7C2 的 cpapp 18,090,880 B，我们的 17,892,024 B。
3. 回环测试判定不了 filter0 系数（B7）。
4. F3 的 7 段是按能量切的，不是原厂 id 表。
5. 41,792 字节未必是全部声音（B2 的判否分支）。
6. 写 /cp 前需整盘备份 nflasha8（64 MiB），它在启动链上。
7. 本文对 A7C2 的理解全部来自源码阅读，无一条来自 A7C2 真机；其源码自报 unresolved 项包括「电子曝光静音点未确立」「原生 pin 路由与物理喇叭未实测」。

## 8. 尚未闭合的点

每条给：现状 / 影响哪些猜测 / 什么事实能定下来 / 我们这边能不能做。

- L1 库内 id → (offset, length) 映射表
  现状：只切出 7 段能量，未找到表结构；CP 侧存在取址消息（F6）说明有可寻址表。
  影响：B2、B3。定下来的事实：任何把 id 与 offset/length 对上号的结构。
  我们：做不了（需真机或解开 /cp 代码段）。

- L2 41,792 字节是否跨机型一致
  现状：只有 A6700 一份，sha256 = b60c99ceffe4ec1f0b6eee90b4449eecbcc7a7fc3603b046ce26162ad7a53cad。
  影响：B3。定下来的事实：A7C2 若也有 /cp/SysSound.bin，比大小与 sha256；一致则 F3 的统计可直接引用。
  我们：做不了（无 A7C2 机身）。

- L3 出厂机 cpapp 0x387900 的取值
  现状：我们这份是 03 21（F8），出厂应为 00 21。
  影响：B1。定下来的事实：出厂机 cpapp-b.bin 0x387800–0x387A00 这 512 字节。
  我们：做不了（手上只有补丁态）。

- L4 r1 = 0/1/2/3 分别是什么
  现状：只有一个数据点（03 有克哒声）。
  影响：B1、B3。定下来的事实：依次改 00/01/02/03 并每次冷启动试听；会改 /cp。
  我们：做不了（相机已不可用）。

- L5 /usr 侧 beeplist.txt 的内容与大小
  现状：卡在 F9 的 ext2 inode 表定位。
  影响：B5、B4。定下来的事实：读出该文件即可（12 字段则证明 A6700 也有 CSV 路径）。
  我们：理论上可做（离线反推 ext2），目前失败。

- L6 A7C2 是否有 regist_beep_signals 与 beep_set_custom 对应物
  现状：未知。
  影响：B4、B6。定下来的事实：其 appFw 里这两个串的命中情况。
  我们：做不了（无 A7C2 固件）。

- L7 filter0 变体的定解
  现状：两种变体都零违规。
  影响：B7。定下来的事实：用一段内容已知的原厂音（例如某个 AP 侧 .bin 若确知是 filter0 编码）双向验证。
  我们：做不了（缺已知原文的样本）。

- L8 菜单「音频信号」的实际项数与文案
  现状：中文串表 firmware/ui/string_simplifiedchinese.txt（135,158 B）里「快门声」0 命中；「电子快门」6 处（line 589/842/1222/1976/2299/2462）全部属连拍速度 Hi/Mid/Lo。文案与菜单项可能不对应。
  影响：B6、B1。定下来的事实：该菜单实际有几项、各叫什么。
  我们：做不了（无真机；串表只能证明文案存在与否）。

- L9 ADF「系统声音表」的索引方式：按 id 还是按名字
  现状：只知道 AdfSystemSoundTable / AdfSystemSoundTableBundle / AdfSystemSoundVolume 三个名字（F6），不知其结构。
  影响：B1、B3。定下来的事实：该结构体字段布局，或一次「换 id 后取到的地址变化」的观测。
  我们：做不了（无真机）。

## 9. 偏移速查

    A6700 cpapp-b.bin      0x387900   2 B    00 21 ↔ 03 21（声音 id）
    A6700 nflasha8         0x5D3900         同一位置的分区视图
    A6700 换算差           0x24C000         分区偏移 = 文件偏移 + 0x24C000
    A6700 cp/SysSound.bin  0x0000           1,306 × 32 B filter0 块，41,792 B
    A6700 nflasha8         0x70000          SYSSOUNDBIN 区偏移（簇 26）
    A6700 nflasha8         0x24C000         CPAPP-B BIN 区偏移（簇 145）
    A6700 nflasha8         0xC120           FAT12 根目录
    A6700 appFw            0x4078d6c        4 条 avsystemsound 硬编码路径的串池
    A6700 appFw            0x437db16 / 0x437db35   EXTERN_VAL_BEEP_SET_CUSTOM_OFF / _ON
    A6700 appFw            0x4079208        regist_beep_signals 符号
    A6700 cpapp            0x93e44          设置键名池（含 beep_set_custom）
    A6700 cpapp            0xbab880         ADF 声音 API 名表
    A6700 nflasha5         0x6715200        ext2 目录块（37 个音效条目）
    A7C2  cpapp-b.bin      0x393570   5 B   selector 表
    A7C2  cpapp-b.bin      0x3935bc  20 B   门控块
    A7C2  cpapp-b.bin      0x3935ca   2 B   核心 00 21 → 03 21
    A7C2  appFw            0x3060a24 16 B   boot 钩子
    A7C2  appFw            0x2759ae8        CSV 单行读取器
    A7C2  appFw            0x48cfa83        beeplist.txt 路径串

## 10. 复算伪码

FAT12 目录与簇换算：

    img = read("firmware/nflasha8-2.00.bin")        # 67,108,864 B
    off = lambda cl: 0x10000 + (cl - 2) * 0x4000
    for i in range(16):
        e = img[0xC120 + i*32 : 0xC120 + (i+1)*32]
        if e[0] == 0: break
        name = e[0:11]; attr = e[11]
        cl = u16le(e[26:28]); size = u32le(e[28:32])
        assert img[off(cl) : off(cl)+size] == read(name)   # 只对 SYSSOUNDBIN、CPAPP-B BIN 成立（本地有副本）；其余 6 项仅核对大小与起始簇

filter0 解码：

    def decode(buf):
        assert len(buf) % 32 == 0
        out, last = [], 0
        for b in range(0, len(buf), 32):
            ctrl = buf[b]
            assert (ctrl & ~0x1F) == 0 and (ctrl & 15) <= 8
            scale = 1 << (ctrl & 15)
            for i in range(1, 32):
                r = s8(buf[b+i])
                last = r * scale + ((60 * last) >> 6 if ctrl & 16 else 0)
                out.append(last)
        return out                      # 40,486 样本，min −30,720，max +30,830

字符串计数：

    for f in ("firmware/appFw-2.00.so", "firmware/cp/cpapp-b.bin", "firmware/nflasha5-2.00.bin"):
        for s in (b"avsystemsound", b"BEEP_SET_CUSTOM", b"beeplist", b"SysSound", b"BEEP_ID", b"SHUTTER_SOUND", b"regist_beep_signals"):
            print(f, s, count_all_occurrences(read(f), s))

catalog → 分区偏移：

    partition_offset = catalog["offset"]           # 0x5D3900
    file_offset      = partition_offset - 0x24C000  # 0x387900

## 11. 来源文件与锚

| 文件 | 大小(字节) | sha256 |
| --- | --- | --- |
| firmware/cp/SysSound.bin | 41,792 | b60c99ceffe4ec1f0b6eee90b4449eecbcc7a7fc3603b046ce26162ad7a53cad |
| firmware/cp/cpapp-b.bin（补丁态） | 17,892,024 | 43c5d056ed9357957c5e7cd1ae24928b077d26b6761bf193eefb303b0b32510d |
| firmware/appFw-2.00.so | 89,027,992 | 721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d |
| firmware/nflasha8-2.00.bin（/cp 分区镜像） | 67,108,864 | 3bddcce378438423617a7c647ab862e5fd4ee6d0d4f627b769b4b08007457dcc |

其余引用文件：firmware/nflasha5-2.00.bin（314,572,800 B，/usr 分区镜像）、firmware/ui/listing-share-app.txt、firmware/ui/string_simplifiedchinese.txt（135,158 B）、third_party/a6700_unlock/data/a6700-2.00.json（155,851 B）。
SysSound.bin 前 64 字节（可作为切片定位锚）：1702f40a00f30e04fbf4f020ea0406d53219e7cf2137e9e505c22af3390cfc0717ec0c0a1fb90449c3cb5506ecfd5ddb199e3202ceefece25edd0125f13eb100

配套文件：docs/SHUTTER-SOUND-A7C2-TEARDOWN.md（同一仓库，逐字节拆解与原始记录，§1–§22）。本文是它的精简对照版，编号不通用。
以上全部为本地文件，无真机读取数据。
