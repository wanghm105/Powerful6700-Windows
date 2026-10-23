# 卡速判定（appFw.so）调查记录

目标（m01652 / m02039）：把「介质传输速率」这道判定摸清，评估能否让 A6700 把某些录制格式（4K 120p 等）在速率等级不足的存储卡上放开。本文只记录只读分析结果，**没有改动相机任何字节**。

## 一、结论摘要

已确认：

- 固件内有一套完整的「介质速率等级」模型，等级是枚举：`c10` / `u3_v30` / `v60` / `v90` / `cfe200` / `cfe400`（字符串在 `appFw-2.00.so` 0x4391db1–0x4391e48）。**V90 是固件里真实存在的等级**，不是我们编的概念。
- 由等级派生出五个布尔属性：`under_100mbps` / `under_200mbps` / `under_400mbps` / `under_600mbps` / `under_1350mbps`，每个都分 `slot1` / `slot2`（双卡槽）。
- 录制格式被速率挡住时，固件弹的文案是一张阶梯表：族（XAVC / XAVC S-I / PROXY）× 阈值（100/200/400/600/1350 Mbps）× 槽位（slot1/slot2/secondary）。例如 `CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_UNDER_600MBPS_MEDIA_SLOT1_MSG`。这说明判定是「先算出卡属于哪个等级，再和格式要求比较」。
- 固件里存在追踪点 `set_media_transfer_rate`，参数名 `media_index`、`transfer_rate`（追踪点表 0x16f9718 一带，元数据 0x542ea88）。即速率是**运行时探测后写进模型**的，写入点在固件内部。

尚未确定：

- 究竟是哪条指令「把等级和格式要求做比较」。属性 id 的直接引用点大多是自动生成的属性镜像/通知代码（见第三节），没有一个是明显的判定分支。
- 因此目前**没有**可以安全下手的 4 字节补丁；也还不能承诺「改成 V90 就一定能录 4K120」。

## 二、属性 id 与描述符表

属性注册表 `.data.rel.ro` 0x497eac8 起，每项 24 字节 `{char* name, u32 0, u32 id, u64 type}`：

| name | id | type |
| --- | --- | --- |
| media_filesystem_mount_state_slot1 | 0x97c | 0x23 |
| media_filesystem_mount_state_slot2 | 0x97d | 0x23 |
| media_transfer_rate_state_slot1 | 0x97e | 0x20 |
| media_transfer_rate_state_slot2 | 0x97f | 0x20 |
| media_transfer_rate_under_100mbps_slot1 | 0x980 | 0x28 |
| media_transfer_rate_under_100mbps_slot2 | 0x981 | 0x28 |
| media_transfer_rate_under_600mbps_slot1 | 0x98c | 0x28 |

（100/200/400/600/1350 依次排开，slot1/slot2 成对；完整列表可用 `python tools/fwscan.py strings 'media_transfer_rate_[a-z0-9_]+'` 复现。）

同一张表的第二份副本在 0x885bf0 附近（只有 name 指针 + 指针槽，没有 id）。类型名字符串（RTTI）在 0x42f7548 起：`N5model33media_transfer_rate_state_slot1_tE` 等 12 个。

## 三、属性访问 API

- **读**：`0x361810c`，签名近似 `get(model, id, out_ptr, tmp4, 4)`，全固件 7,588 个调用点。
- **通知/置脏**：`0x2d0d52c`，通常在写完属性后紧跟调用。
- 15 个 `mov w?, #0x97e` 与 9 个 `mov w?, #0x980`、31 个 `mov w?, #0x98c` 的引用点，逐一反汇编后性质如下：
  - 0x178e848 / 0x178e8b8 / 0x1852b18 / …：把 `{id, name}` 拼成调试/日志对象；
  - 0x2cd5d20 起：一张 `属性 id → 标志` 的跳转表（0x97c/0x97d/0x97e/0x97f/0x980/0x981 连续处理）；
  - 0x2d17c08 / 0x2d17ca0：属性适配器构造函数；
  - 0x300e404 / 0x33efb8c / 0x33efbd4 / 0x324172c / 0x325b230：成批把模型属性拷进视图模型（`get(id)` → `*out1 = v; *out2 = v`）。

结论：这些点都是**管道**，不是判定。判定要么通过 `under_*` 布尔之间的组合完成，要么在别的模块里以别的 id 出现。

## 四、caution 文案阶梯（判定存在的直接证据）

族 × 阈值 × 槽位，全部在 `.rodata` 0x4315ac0 起连续排列：

- `CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_MEDIA_SLOT1_MSG`（无阈值，通配）
- `CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_UNDER_100MBPS_MEDIA_SLOT1_MSG`
- `…_UNDER_100MBPS_MEDIA_SLOT1_FILE_FORMAT_MSG`（切换文件格式时用）
- `…_UNDER_200MBPS_…` / `…_UNDER_400MBPS_…` / `…_UNDER_600MBPS_…`
- `CAUTION_ID_XAVC_S_I_TRANSFER_RATE_DISABLE_UNDER_400MBPS_MEDIA_SLOT1_MSG`（XAVC S-I 单独一族）
- `CAUTION_ID_PROXY_SLOW_AND_QUICK_XAVC_TRANSFER_RATE_DISABLE_UNDER_400/600/1350MBPS_…`（代理录制 / 慢快动作）

文案表本身在 `.data.rel.ro` 0x4958148 起，条目 `{char* name, u32 id, u32 len}`，例：

| 地址 | 文案 | id | len |
| --- | --- | --- | --- |
| 0x4958148 | CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_MEDIA_SLOT1_MSG | 0x16a | 0x36 |
| 0x4958188 | …_UNDER_100MBPS_MEDIA_SLOT1_MSG | 0x16e | 0x44 |
| 0x4958398 | SLOW_AND_QUICK_…_UNDER_200MBPS_MEDIA_SLOT1_MSG | 0x18f | 0x53 |

注意：「SLOW_AND_QUICK」正是慢快动作（S&Q）相关的族，和用户想放开的「慢动作 120fps」直接对应。

## 五、工具

| 工具 | 用途 |
| --- | --- |
| `tools/a64.py <vaddr>` | 线性反汇编窗口；`--func <vaddr>` 回溯到上一个 ret/bti 边界 |
| `tools/a64xref.py sites/xref <vaddr>` | 全 .text 的 adrp 页索引（352,549 条 adrp → 1,474 个页），按页找 adrp+add 引用 |
| `tools/rela.py <addr>…` | 解析 `.rela.dyn`（1,006,507 条 R_AARCH64_RELATIVE），查「哪个全局槽持有某地址」 |
| `tools/fwscan.py strings/slots/movz/cmp/warnrate` | 字符串、指针槽、指令立即数扫描 |

依赖：capstone 5.0.7、numpy 2.5.4（都在 `.venv` 里，离线 wheelhouse 装好）。

## 六、为什么现在还不能改

1. **写窗口**：本工具只写清单里那 260 个固定扇区（133,120 字节，appFw / WBI / CP 各一个窗口），判定代码在 `.text` 里、caution 表在 `.data.rel.ro` 里，都不在现窗口内。要动它们必须先按新目标扇区重做 catalog（含每个扇区的「已知字段清零后哈希」结构守卫），这是独立的一步工程。
2. **定位未完成**：还没有找到那条比较指令，无法给出「改 4 字节」的具体地址。
3. **语义风险**：即使找到并改掉，卡本身写不了那么快，录制会在写入阶段失败（掉帧、录制中断），不是变砖但可能得到坏文件。

## 七、下一步（候选）

- 路线 A（继续静态定位）：从 `under_600mbps` 的**消费方**入手——找同时引用 caution 文案 id（0x16a–0x191 区间）与 `under_*` 属性的函数，通常是「格式可用性计算」。需要先建立「文案 id → 引用该 id 的代码」的索引（目前文案表没有 adrp 直接引用，说明它由 id 查表，需换用字符串池 + 偏移的方式找）。
- 路线 B（运行时验证）：在只读前提下，用 dump 能力读取相机内部日志（如有）确认实际等级与判定顺序，减少猜测。
- 路线 C（换目标）：先做 Creative Look（FL2/FL3）那条——A7C2 的 `patches.json` 已给出参数表地址与写法，证据链比卡速这条完整得多。

## 八、需要用户确认的信息

1. 用的是哪张卡（型号 + 卡面等级：U3/V30/V60/V90、或 CFexpress Type A）？
2. 现在相机里**看不到**的是哪一项：4K 120p？还是 S&Q 的 120fps？还是 XAVC S-I 的某个档？菜单里是「灰掉」还是「完全不出现」？

这两点决定目标到底是「速率判定」还是「产品标志/区域限制」——如果是后者，这条技法完全走别的表，现在的方向要换。

## 第二轮：文案 id 映射 + id 引用点复查（2026-10-24）

用户给出卡规格：**V60、读 280 MB/s、写 100 MB/s**（m02156）。V60 的持续写下限是 60 MB/s，
而 4K120 XAVC S HS（280 Mbps）只需要约 35 MB/s，物理带宽不是瓶颈 → 卡的是**等级判定**，不是实测速度。

### caution 文案注册表（.data.rel.ro 0x4958148，16 字节/项 {char* name, u32 id, u32 len}，43 项）

| id | 文案 |
| --- | --- |
| 0x16a / 0x16b / 0x16c / 0x16d | XAVC_TRANSFER_RATE_DISABLE_MEDIA（SLOT1 / SLOT2 / SECONDARY1 / SECONDARY2） |
| 0x16e–0x171 | XAVC … UNDER_100MBPS（四槽） |
| 0x172–0x175 | … UNDER_100MBPS 的 FILE_FORMAT 变体 |
| 0x17a–0x17d | XAVC … UNDER_400MBPS（四槽） |
| 0x17e–0x181 | XAVC_S_I … UNDER_400MBPS（四槽） |
| **0x182–0x185** | XAVC … UNDER_600MBPS（四槽；0x182 = SLOT1, len 0x44） |
| 0x186–0x189 | XAVC … UNDER_1350MBPS（四槽） |

注意 0x4968148 是 {u64 hash, char* name} 的 EVENT_INPUT_KEY_* 表，与文案无关。

### 用 id 立即数找判定：失败

- movz 0x182 命中 0x17727ec、0x17cf6dc、0x17d6510、0x17d9d2c、0x17e2e28、0x17e2e7c、0x190e374、0x190f658…；
  0x186 / 0x17a / 0x16a 各 8+ 处。
- 逐点反汇编后：0x17ceexx–0x17cfxxx 是一段**巨型诊断快照构造**（把 0x160…0x189 依次写进栈上结构体并拼名字），
  0x17d6510 是把「选中的文案 id」写进全局，0x190e374 是 0x40000000|x 编码值的分派器 —— 全是管道，没有判定分支。
- 阈值数字（100/200/400/600/1350）扫描同样走不通：cmp 1350 命中 0；cmp 600 的 5 处
  （0x1943d68、0x1943ef0、0x29c845c、0x3511b38、0x3511ca8）分别是 u16 状态值比较与事件码分派，与介质速率无关。
- 结论：速率是**枚举等级**，under_* 布尔是派生量；判定不读裸 Mbps 数字，也不在引用属性 id 的地方。

### 因此下一步的两条路

1. **继续定位比较点**：沿 set_media_transfer_rate（追踪点名 0x4366bdb）找它的实现，
   或找「格式 → 要求等级」的查表（表里应是 v60/v90 这类序号而非 Mbps）。
2. **并行确认到底哪一档被挡**：让用户看相机在选到目标格式时的提示文案，
   文案能直接映射到 0x16a / 0x17a / 0x182 / 0x186（或 XAVC S-I 变体），从而反推是哪条要求不满足。

两条路之外还有一个工程前提未变：这些代码位于 .text，不在当前可写的 260 扇区窗口内，
真要落地必须先按新目标扇区重建 catalog 与结构守卫。

## 第三轮：用相机提示文案反推命中哪一级（2026-10-24）

用户实测（m02198）：S&Q 模式下**根本没有 240fps 选项**；切到 S&Q 时相机提示
「再次记录设置中不能记录。切换高于 SDXC V90 的存储卡或者更改记录设置」。

### 命中的是 600 Mbps（=V90）那一级，不是 1350

文案里的「V90」直接对上 `UNDER_600MBPS` 这一档（V90 = 90 MB/s ≈ 720 Mbps，门槛取 600）。
结合模式（S&Q）、卡槽（slot1）与「under」语义，命中的提示 id 应是：

- `0x19f` CAUTION_ID_SLOW_AND_QUICK_XAVC_TRANSFER_RATE_DISABLE_UNDER_600MBPS_MEDIA_SLOT1_MSG（len 0x5d）
- 同族可对照：`0x18a` S&Q/under_100、`0x197` S&Q/under_400、`0x186` 普通/under_1350、`0x1d4` PROXY S&Q/under_1350

S&Q 族整体从 `0x18a` 起、PROXY S&Q 族从 `0x1bf` 起，普通族从 `0x16a` 起；每族内部按
100/80/200/400/600/1350 × slot1/slot2/secondary1/secondary2 × （部分带 FILE_FORMAT 变体）排列。

### 完整注册表已导出，换掉逐次反汇编

`tools/caution_registry.py` 把 0x4958148–0x4968148 整段（16 字节/项）导出到
`firmware/caution-registry.txt`，共 **1981 条**，格式 `id len 表内偏移 名字`。
以后查文案 id 直接 grep 这个文件即可（`grep SLOW_AND_QUICK firmware/caution-registry.txt`）。
注意该区域不止 CAUTION_ID_*，还混有 PID_*（如 0x40e7 PID_SET_SLOW_AND_QUICK_MODE）、LED_*、EID_*。

### 又一处排除项：id 立即数只到「广播」，不到「判定」

- `movz 0x19f` 全固件 85 处；其中 `0x249c4c0` 起的密集簇是**观察者广播**：
  代码把 `w3 = 0x19f` 依次传给从栈上取出的十几个 handler（`bl 0x2273330`、`bl 0x2276300`、`bl 0x2276a58` …）。
- 也就是说 id 常量只出现在「快照构造」和「广播」两类代码里；真正的判定是**算出来**的 id
  （族基址 + 模式偏移 + 等级序号 + 槽位偏移），所以按 id 立即数永远找不到分支。

### 对「240 选项直接消失」的解释

选项列表和提示走同一个等级判定：能力检查先按 `under_600mbps` 把 S&Q 的 240 档过滤掉，
用户在菜单里看不到该项；切到 S&Q 时再弹同一条 600 级提示。因此只要让固件认为该槽位不是
「under 600」，选项和提示会一起恢复 —— 目标仍是那一个派生布尔，而不是两处逻辑。

## 第四轮：假设「只有一道门」+ 两个新线索（2026-10-24）

用户明确：暂时拿不到 V90 卡，先按「只有速率等级这一道门」推进，并继续找线索（m02244）。

### 线索 A：id → 内部 code 的映射表（不是判定，但确定了结构）

- `0x2cd05c0`–`0x2cd0b00` 是一整片 24 字节小桩：`mov w2,#1` / `mov w1,#<id>` / `b 0x2cb2b10`，
  id 从 0x132 连续递增到 0x1d7（正好覆盖普通族 0x16a 起、S&Q 族 0x18a 起、PROXY S&Q 族 0x1bf 起）。
- 说明固件把「文案 id」翻译成内部 code 走的是**表驱动**，判定端只用 code，不直接用 id。
  这也是「按 id 立即数找判定」必然失败的第二个原因（第一个是 0x249c4c0 的观察者广播）。
- 家族基址共现页统计（tools/_fam.py）：0x16a 161 处、0x18a 90 处、0x1bf 70 处、0x1d4 95 处；
  三族同页的只有 0x17d9000、0x2cd0000 两处，且都属映射/快照代码 —— 判定代码里**不出现** id 常量。

### 线索 B（更值钱）：240 选项消失可能跟卡无关，而是文件格式

A6700 的 S&Q 帧率上限跟**文件格式**绑定：XAVC S HD 才有 240fps；XAVC HS 4K / XAVC S-I 最高 120。
所以「S&Q 里直接没有 240」+「切 S&Q 时提示 V90」这两件事**可能来自不同原因**：

- 240 不在列表里 → 文件格式是 4K 一类，菜单根本不会列出 240（无需任何破解）；
- V90 提示 → 当前选的是 4K 120p 档，而 4K120 在 Sony 的规则里要求 V90（营销/保守门槛，物理上 280 Mbps ≈ 35 MB/s，V60 完全够）。

验证成本为零：在相机里把 **文件格式改成 XAVC S HD**，再看 S&Q 帧率列表里有没有 240。
如果有 → 240 本来就能用，真正需要破解的只有 4K120 的 V90 门。

### 推进方式

按用户要求先假设只有一道门（速率等级 ≥ V90），把目标收敛成：
**让 `under_600mbps_slot1` 不再为真**（属性 id 0x98c）。剩下要定位的就是它的计算/读取点；
已知判定端不用 id 常量、不用裸 Mbps 数字，因此下一步改从「格式 → 要求等级」的数据表与
`set_media_transfer_rate`（0x4366bdb）的实现两侧夹逼。

## 第五轮：id 追踪这条线正式关闭（2026-10-24）

### 判定代码不碰 id —— 三路证据齐了

1. `movz` 立即数：命中的全是「诊断快照构造」和「观察者广播」（0x249c4c0 起把 `w3=id` 喂给十几个 handler）。
2. 字面量池：扫遍 `.text`（0x176d090 + 0x1ec5c30）找 u32 等于 0x98c / 0x97e / 0x980 / 0x981 / 0x182 / 0x19f 的常量 —— **0 命中**。
   说明 `ldr w?, =id` 这种取常量方式也没被用。
3. 指针/重定位：`rela.py` 查 0x363cde9（SQ_REC_FRAME_RATE_XAVC_HS_8K_30P）等枚举名，**0 个槽**持有；`fwscan slots` 同样 0 命中。

结论：固件内部把「文案 id」先过 `0x2cd05c0`–`0x2cd0b00` 那张桩表翻成内部 code（`b 0x2cb2b10`），
判定端只面对内部 code 与**类型化模型字段**。**从 id 出发的静态追踪到此为止，不要再试。**

### 另一条线索：固件是共享平台二进制

`0x363cde9` 起的枚举名里有 `SQ_REC_FRAME_RATE_XAVC_HS_8K_30P/25P/24P` —— A6700 不可能有 8K，
说明 appFw.so 是**多机型共用**的平台构建，机身功能差异靠机型配置/能力位裁剪。
这与 A7C2 项目 `assets/patches.json` 里那几条「菜单产品标志」（0x59892ca / 0x5989382）是同一套机制。

因此 A6700 上「S&Q 没有 240」有两种可能，目前分不开：

- (a) 纯速率门：卡片等级不够，菜单把该档隐藏（与 V90 提示同源）；
- (b) 机型能力位：该机型配置里就没有这一档。

区别很重要：若是 (b)，改速率是白费。要分开只能拿到「机型配置块」，或做动态观察。

### 剩下的三条路（成本从低到高）

| 路线 | 做法 | 障碍 |
| --- | --- | --- |
| B 静态换骨架 | 从模型属性框架入手：找 id → 类型/偏移的访问器表，拿到 `media_transfer_rate_state` 字段偏移，再反查读该偏移的判定代码 | 纯离线可行，但没有时间保证 |
| C 扩容写窗口 | 把「单扇区补丁 + 结构守卫 + 回读验收」做成工程能力 | 与定位解耦、可先做；任何结论最终都要靠它落地；有真机风险 |
| A 动态 QEMU | 仿社区 `chocotan/a7c2-qemu`（系统级仿真整机固件） | 需 Linux + 32 GiB 内存 + 自建 QEMU 11.1.2；这台 Windows 机器上不现实 |

建议：**B 继续查、C 并行立项**（C 是 B 的前置落地条件，且可以先写设计与守卫算法，不碰相机）。

## 第六轮：文案选择链 vs 判定点（2026-10-24 追加）

`movz imm ∈ [0x180,0x1d4)` 在全 `.text` 有 7,802 处。按「所属函数」聚合后，出现一批
**每个函数引用 10–25 个连续 id** 的函数，例如：

- `0x31d96b4` / `0x31d1834` / `0x31c9af0`：id 从 0x198 起、**步长 2**（slot1/slot2 成对），17 项；
- `0x32042b8` / `0x31ee69c` / `0x31e1604`：id 从 0x180 起连续，25 项；
- `0x227beec` / `0x227c3e0` / `0x227c8d4`：PROXY 族的 0x1a6…/0x1b6…/0x1c6… 各 14 项。

`bl` 反查得到它们的调用者（如 0x31e134c、0x31e137c、0x3203764、0x31f9448、0x320f068）。
反汇编 0x31e1320 起可见调用形状是 `selector(ctx, x1, x2) -> char*`，随后 `bl 0x190af4c` 取格式化结果 ——
**这些是「文案选择器」，不是判定点**。真正的判定把「档位索引」当参数传进来，所以判定代码里不会出现 0x19f 这类 id。

推论（重要）：**任何基于「消息 id / 属性 id 立即数」的定位都不可能成功**，前面的 0 命中不是工具问题。
要定位判定，只剩「类型化字段语义」或「动态执行」两条路。

### 另外两个结论（2026-10-24）

1. **CP 侧（cpapp-b.bin，ARM32，17.9 MB）没有卡速判定**：`TRANSFER_RATE` 0 次、`MBPS` 0 次、
   `V90`/`SpeedClass`/`SDXC`/`CARD` 均 0 次（只有 `SLOW_AND_QUICK` 1 次、`SPEED` 22 次，属其它语义）。
   判定只在主控 appFw.so 里，换 CP 侧查是死路。
2. **没有「默认卡速率」这种配置项**：速率是每次插卡探测后写进模型的运行时状态（追踪点
   `set_media_transfer_rate(media_index, transfer_rate, file_system_type)`），不是可改的偏好值。
   想「默认 V90」在字节层面不存在单一开关；只能伪造探测结果或判定读取端，两者都还没定位到。

