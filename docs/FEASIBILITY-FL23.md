# FL2/FL3 与富士创意外观在 A6700 上的可行性调查

> **状态：历史记录，已被 `docs/FL2-ROUTE.md` 取代。** 本文件是最早的可行性判断（当时只有静态证据，尚未打通 CP 读写）。

状态：只读取证，未写代码、未连接相机。调查时间 2026-10-24。
对照物：`refs/a7c2-fl23`（ILCE-7CM2 2.01，完整度基准）与 `refs/a6700-powerful`（ILCE-6700 2.00，本项目底座）。

---

## 1. 结论

| 目标 | 在本工具现有模型下 | 结论 |
| --- | --- | --- |
| 创意外观 **FL2 / FL3**（新增外观类型） | 不可能 | 需要改相机固件**代码**（look→CP 转换器、模式表、gamma 边界、菜单产品标志）并移植 4 组色彩/曲线记录。A7C2 上是 40 处字节补丁，最大偏移 0x59892CA（≈94 MB）。我们的写入窗口是 260 个固定扇区 / 133,120 字节，且目录里 look/color/gamma 相关字段为 **0**。 |
| 富士 **CC / CN** 之类自定义外观 | 研究可行，工程量大 | 取决于落在哪条路线上：只替换既有 look 槽的色彩矩阵/chroma/gamma **数据** → 属于"往已定位的记录里写字节"，是我们模型的自然延伸；需要**新增槽位**（A7C2 那样 8 处代码补丁 + slot16/17 绑定 + 名称资源 + 程序窗口）→ 与 FL2/FL3 同难度，等于第二个产品。 |
| 固件里"菜单权限/型号可用性"类开关（FTP、快门、曝光、声音、双原生 ISO…） | 可行 | 这正是现有 355 条 edits 的范围，已真机验证。 |

一句话：**FL2/FL3 不是在设置里加一项，而是改固件逻辑**；A6700 上做这件事的第一步不是写代码，而是先拿到 ILCE-6700 2.00 的 `appFw.so` 明文并读出它的 look 表与菜单枚举。

---

## 2. 证据：A7C2 的 FL2/FL3 到底是什么

来自 `refs/a7c2-fl23/src/camera_runtime/assets/`：

### 2.1 `patches.json`：40 处字节补丁，2 个镜像

条目 0（`source_sha256` = `2ea02f7ecbc5bb91…`）共 8 处，全部是行为/枚举改动：

| 偏移 | 用途 | 原 → 新 |
| --- | --- | --- |
| 0x3528804 | ordinary look to CP mode converter | `3f24007168030054` → `3f2c007168030054` |
| 0x4B2ED19 | two selection capabilities | `0000` → `0101` |
| 0x4B4A5E4 | ordinary slot 16 initial binding | → `0A` |
| 0x4B4A5EC | ordinary slot 17 initial binding | → `0B` |
| 0x4B3B544 | FL2 factory Fade default | `00000000` → `01000000` |
| 0x4B3B54C | FL3 factory Fade default | `00000000` → `01000000` |
| 0x59892CA | FL2 菜单产品标志（live column 9） | — |
| 0x5989382 | FL3 菜单产品标志 | — |

条目 1（`source_sha256` = `f5a477588698ef96…`）共 32 处，从 0x20140 的"initialized-data length"（容量从 `801b1400` 扩到 `a02a1400`）一直到 0x1100B80 的"four adapted curve records, gamma rows and mode table"，另外还有 MakerNote `0xB020` / SR2 `0x7770` 里的名称表、gamma 表地址与 gamma 上界。

→ 这两条合起来说明：**FL2/FL3 = 代码补丁（让机内接受第 9/10 个外观并把它当 CP 处理）+ 记录移植（色彩矩阵、chroma、4 组 gamma 曲线）**。

### 2.2 被移植的记录来自哪里

- `colors.json`：每条 `{parameter: 55, slot: 23, chroma: <64 字节>, matrix: <576 字节>}`。
- `fx2_fl23_donor.json`：purpose 写明"ILCE-FX2 1.01 donor values for the ILCE-7CM2 2.01 FL2/FL3 records: CC1 differential coefficients, all 48 block13 slot matrices per look, and the four gamma records actually transplanted"；`looks[]` 里 `target_parameter=55`、`target_slot=23`、`donor_block13_bank=22`、`donor_cc1_bank=22`、`cc1_int16` 为 3×8 int16。
- `r5_fl23_reference.json`：给出换算 `v = [r1,r2,r3,r0,r5/2,r6/2,r7/2,r4/2]` 与 `M = [[a+b+1024,-a,-b],[-c,c+d+1024,-d],[-e,-f,e+f+1024]]`，记录尺寸 `record_chroma_bytes=64`、`record_matrix_bytes=576`。
- 也就是说 FL2/FL3 的"颜色"来自另一台机器（FX2）的 donor 数据，不是从 Sony 更新包里"解开"的。

### 2.3 自定义外观的写入链路

`docs/zh-CN/development.md`：`looktool/direct.py` 的 `DirectJob.plan()` 是纯函数，`run_direct()` 的顺序是"读当前状态 → 计划 → 存 PLANNED → 原生预检 → **先写名称、再写程序窗口** → 整段读回 → 名称资源 → 设置 → WBI → AWAITING_RELOAD"。阶段 `READY/DRIVERS/PREPARED/INSTALLING/WAIT_RELOAD/FINALIZING/COMPLETE`，恢复原厂用 `factory-regions-2.01.json`（只含本项目会改的区域）。

→ 自定义外观要往相机里写**程序窗口 + 名称资源**，是"给相机装一段逻辑"，不是"改一个字段"。

---

## 3. 证据：A6700 现在能写什么

`third_party/a6700_unlock/data/a6700-2.00.json`：

- `scope = offline-known-snapshot-only`、`device_write_supported = false`（由我们的 Windows 端在真机上补上了写入验证）。
- `images`：`app = /lib/appFw.so`（89,027,992 字节）、`wbi`（248,376,320 字节）、`cpapp = nflasha8`（25,008,128 字节）。
- `features` 6 项：ftp / shutter / exposure / sound 可用；pixel_shift / dynamic_active 未完成（上游明示"未开发完成、暂不开放"）。
- `edits` 355 条、219 种 purpose，清一色是"current product column menu permission"、"model-unavailable contribution / native flag at zero reference count"、"0x5a8/0x5a6/0x5ac 型号支持位"这类**菜单权限与型号可用性**字段。
- 匹配 look / color / gamma / creative 的 edit 数量：**0**。
- 落到设备的窗口：`nflasha15`(appFw) / `nflasha5`(WBI) / `nflasha8`(CP) 上 260 个固定扇区、133,120 字节（149 目标 + 111 守卫），profile 摘要 `c20d1b9b…`。

→ 现有工具是"在已知快照里翻开关"，与 FL2/FL3 需要的"改代码 + 移植记录"不是同一层。

---

## 4. 上游自己的状态

`refs/a6700-powerful/开发计划与进展.md`：

- FL2／FL3 原生创意外观 = **P2（中）**，状态"离线验证中，待实机验证"；仓库内除计划表与 README 外**没有任何 FL2/FL3 研究产物**。
- 并列项：录像卡速 V60（P1）、动态增强防抖（P1，README 标注"暂不开放"）、双原生 ISO（P2，"菜单离线验证通过"）、S-Log3 实时 LUT 照片直出（P4，"可行性研究中"）。

→ 我们不是"补一个上游已经做了一半的功能"，而是"上游还没有可复用的产物"。

---

## 5. 三条技术路线

### 路线 A：复用现有 260 扇区窗口，直接改字段
**不可行。** 现有 355 条 edits 内没有任何 look/color/gamma 字段；FL2/FL3 需要的偏移（0x3528804、0x4B3B544、0x59892CA…）也都在窗口之外、且属于代码段而不是设置。

### 路线 B：扩展目录（新增扇区 + 新守卫哈希）
**可行但必须先离线拿到镜像。** 我们的写入模型是"稀疏扇区 + 每扇区 unmanaged 字节哈希"，新增目标只需要新的扇区描述与守卫哈希，事务/回滚/回读机制原样可用。前提是知道**改哪些偏移**，而这需要 `appFw.so` 明文：

1. 从 Sony 官方 ILCE-6700 v2.00 更新包出发，用 `refs/a7c2-fl23/src/desktopapp/vendor/fwtool`（`sony/{dat,msfirm,wbi,flash,xor55}.py`、`archive/{ext2,cpio,squashfs,axfs}.py`）尝试解析出 `appFw.so`；
2. 在明文里定位 look 表、菜单枚举、以及是否存在**未使用的 17/18 号槽位**；
3. 只有在"数据段替换"（不改代码）时，才可能落回现有稀疏写入模型。

### 路线 C：照抄 A7C2 的直写引擎
**等于第二个产品。** 需要：名称资源 + 程序窗口写入、原生预检、`boot_id` 校验、"结果不明绝不重放"的状态机、恢复原厂区域表。A7C2 为一个机身写了约 3.1 MB Python + 4 个 aarch64 载荷；我们目前在 A6700 上只有 260 个扇区的读写载荷。

---

## 6. 富士 CC/CN 的两条路径

| 路径 | 条件 | 与现有模型的差距 |
| --- | --- | --- |
| 覆盖既有 look 槽的**数据**（chroma 64 B / matrix 576 B / gamma） | 定位到这些记录且不校验 | 只差"新扇区 + 守卫哈希"，属于路线 B 的简单情况；不需要改代码 |
| 新增**槽位**（像 FL2/FL3 那样做第 9/10 项） | 8 处代码补丁 + slot16/17 绑定 + 名称资源 + 程序窗口 | 与 FL2/FL3 同难度（路线 B→C） |

注意：富士 CC/CN 并不是"把 DCP 塞进相机"就行——A7C2 那边要用 `calibration/a7c2-2.01.virtual.npz` 把 LUT/DCP **拟合成机内色表**再写进去，说明机内记录格式是专用格式，需要先有拟合数据。

---

## 7. 关键未知（决定可行性的全部是这几条）

1. ILCE-6700 2.00 的 `appFw.so` 能否从官方更新包解出明文？（未知，未尝试）
2. 它的 look 表在哪个偏移、是否与 7CM2 同构？（未知）
3. 是否有未使用的 17/18 号槽位？（未知；有则"数据替换"路线成立，无则必须改代码）
4. 机内对 look 记录是否有校验（哈希/签名/长度一致性）？（未知）
5. 菜单枚举是否硬编码 8 项？（未知；决定要不要那句 0x59892CA 式的产品标志补丁）

这五条全部**无法在无镜像、无相机的当下回答**。

---

## 8. 建议的下一步（按性价比排序）

1. **（离线，零风险）试着解官方更新包**：拿 ILCE-6700 v2.00 的 Sony 更新包，用 `vendor/fwtool` 走一遍 `dat/msfirm/wbi`，目标是得到 `appFw.so` 明文与 `/usr` 布局。失败则整条路线停在这里，成本只花一次尝试。
2. **（离线，零风险）在明文里做静态定位**：搜 look 名称字符串（FL/IN/VV/Clear/Deep…）、搜 64/576 字节记录的对齐模式、比对 7CM2 的行表结构与 6700 的差异。
3. **（只读，低风险）给 Windows 端加一个"只读探测窗口"**：用新 profile 把候选区域读下来（读取路径已在真机验证），用于在无镜像时也能取证据；这一步会新增一条工具能力，但与写入无关、不动现有守卫。
4. 只有 1–3 全部指向"记录可替换"时，才做写入实现；一旦需要改代码，就应单独立项（路线 C），不要塞进现有产品。

---

## 附：本次调查用到的文件

- `refs/a7c2-fl23/src/camera_runtime/assets/{patches,colors,fx2_fl23_donor,r5_fl23_reference,fl23-native-history,manifest}.json`
- `refs/a7c2-fl23/docs/zh-CN/{development,lut-formats}.md`、`refs/a7c2-fl23/lut.py`、`refs/a7c2-fl23/src/desktopapp/vendor/fwtool/`
- `refs/a6700-powerful/开发计划与进展.md`、`third_party/a6700_unlock/data/a6700-2.00.json`


---

## 9. 附：官方 2.00 更新包的取证结果（2026-10-24）

已成功找到并下载 Sony 官方更新文件，用于判断"能否离线拿到 \`appFw.so\` 明文"。

| 项 | 值 |
| --- | --- |
| 支持页 | https://www.sony.com/electronics/support/e-mount-body-ilce-6000-series/ilce-6700/software/00298441 |
| 下载入口 | \`https://support.d-imaging.sony.co.jp/download/NEX/tF4c94033c/BODYDATA.DAT?fm=am\` → 302 → \`https://di.update.sony.net/NEX/tF4c94033c/BODYDATA.DAT\` |
| 文件 | \`BODYDATA.DAT\`，版本 2.00，发布日期 2025-10-06 |
| 大小 | 1,024,017,848 字节（与页面标注完全一致） |
| SHA-256 | \`d3c7db5b9b40c89b11ecf03addf0f6ff1d9b917acf9f55e46360462e86db847c\` |
| 本地副本 | \`D:\DSH Desktop\Project\firmware\BODYDATA-2.00.dat\`（不进仓库） |

### 9.1 容器结构

\`895546550d0a1a0a\`（UFU magic）后依次是：

| 偏移 | 类型 | 大小 |
| --- | --- | --- |
| 0x8 | DATV | 4 |
| 0x14 | PROV | 4 |
| 0x20 | UDID | 108 |
| 0x94 | FDAT | 1,024,017,680 |
| 0x3D0945AC | DEND | 4 |

UDID 里 13 个描述符，mode=1（普通模式）12 个 PID：\`0x0448 0x047D 0x0D15 0x0D16 0x0D19 0x0D1A 0x0DA4 0x0DA5 0x0E0A 0x0E0E 0x0E72 0x0E76\`，mode=2（更新模式）1 个：\`0x03E2\`。其中 \`0x047D\` 与 \`0x0E76\` 正是本项目使用的 MSC 身份，本文件确实覆盖 A6700。

### 9.2 结论：离线解密不可行

- FDAT 载荷首 32 字节是哈希，其余全为密文：文件里搜不到 \`UDTRFIRM\`、\`MSFIRM\`、\`\x7fELF\`、\`nflasha\`、\`appFw\` 任何明文特征。
- 用 Sony-PMCA-RE 公开的 12 种 crypter（CXD4105 / MB8AC102 / CXD4115 / CXD4115_ilc / CXD4120 / CXD4120_pro / CXD4132 / CXD90014 / CXD90045_k0 / CXD90045_k8 / CXD90057_k0 / CXD90057_k8）逐个尝试，全部 \`BlockCryptException\`（块校验不通过，说明密钥不匹配，不是解析错误）。
- 因此 **BODYDATA.DAT 无法用来做离线静态分析**；这也与上游文档一致：\`/dev/nflasha15\`、\`/dev/nflasha5\` 是机身内的**明文视图**，而 Pico 原始镜像是密文——明文 \`appFw.so\` 来自机身取证，不是来自更新包。

### 9.3 这条路线剩下的唯一缺口

读明文的通道已经存在：\`native/transaction.c\` 编译成 ARM64 共享库，经 Jiritsu \`SET_FILE\` \`file_id=2\` 加载 \`/tmp/jiritsu/libJit.so\` 后在维护进程里执行；我们只需要把"读 260 个固定扇区"改成"读指定范围"，就能把 \`appFw.so\`（89,027,992 字节）分段读出来。

当前缺的不是相机、不是协议，而是**一个 aarch64 交叉编译器**：本机 \`zig\` / \`clang\` / \`gcc\` / \`aarch64-linux-gnu-gcc\` 全都没有（上游是在 macOS 上用 Xcode 的 clang 构建的）。装上 zig 或 clang 后，"取明文 → 定位 look 表" 才具备条件。

