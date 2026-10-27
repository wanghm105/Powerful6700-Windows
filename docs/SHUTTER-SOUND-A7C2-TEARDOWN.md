# A7C2 自定义快门声音实现 · 逐字节拆解

> 取证范围：`refs/a7c2-fl23`（QAQLeonard/a7c2-fl23-research，v3.0.3，HEAD `7827856`）的 `src/shutter_sound/` 全部源码 + `src/fl23/native/` 的 worker 契约。
> 全部为本地只读静态分析，**没有连接任何相机**，没有改动本工程任何已发布文件。
> 本机（A6700）侧的对照结论来自 `firmware/` 下的固件镜像与目录清单，见第 12 节。

---

## 1. 一句话结论

A7C2 的「自定义快门声音」不是改菜单、也不是换 WAV，而是**两处很小的代码补丁 + 两个私有资源文件**：

1. **CP 侧 25 字节**：把「电子快门是否发声」这个分支的 selector 从 `0021` 改成原厂本来就存在的另一块 `0321`，让电子快门走「有声音请求」的路径（机械快门另有一个 filter 把它挡掉）。
2. **AP 侧 16 字节**：在开机日志打印的位置插一条 `bl` 调用，复用原厂自己的「单行 CSV 声音登记表读取器」，让机身把 `/usr/share/avsystemsound/custom.txt` 当成一个额外声音资源读进来。
3. **资源侧两个文件**：`/usr/share/avsystemsound/custom-shutter.bin`（音频字节）+ `custom.txt`（一行 CSV 登记表）。

这三件事都是「用原厂已有的机制，喂一份原厂没发过的资源」，所以才能在不动固件主体的情况下长期存活。

---

## 2. 源码清点（`src/shutter_sound/`，17 文件 3,617 行）

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `candidate.py` | 200 | **CP 25 字节窗口**的定义与状态机（本机是否已改） |
| `boot_sound.py` | 179 | **AP 16 字节 boot 钩子**的补丁与离线仿真 |
| `custom_sound.py` | 192 | 原生登记表单解析、同尺寸替换、40 B 描述报文、PCM 候选 |
| `inspect_native.py` | 160 | 纯离线：解 `beeplist`、切 `SysSound.bin`、AP 属性号反推 |
| `verify_beeplist.py` | 155 | 用 unicorn **仿真原厂 CSV 读取器**验证新 CSV |
| `native/sound_probe.c` | 55 | 只读预检 worker：把 25 个槽的前 48 B + 两个 getter 读出来 |
| `native/sound_files.c` | 196 | 装/删两个私有文件的 worker |
| `native/buffer_probe.c` | 204 | RAM 临时注册 worker（不写 ROM 的试听） |
| `native_codec.py` | 136 | filter0「32 字节块」编码假设 |
| `media.py` | 140 | 音频截取/淡入淡出/音量/重编码 |
| `trial.py` | 309 | 设备会话 + CP 层 preflight/apply/restore |
| `boot_trial.py` | 419 | 资源 + boot 钩子的安装/恢复顺序控制 |
| `buffer_trial.py` | 383 | 临时 RAM 注册试听（不写 ROM） |
| `replacement.py` | 170 | 串行锁、`/tmp/jiritsu` 清理、机身绑定 |
| `sound_cli.py` | 640 | 命令行与状态机 |
| `files_worker.py` | 79 | `sound_files.c` 的离线编译与报告解码 |
| `requirements.txt` | — | numpy/scipy/usb/unicorn/keystone/ziglang… |

仓库 `docs/zh-CN/` 只有 `changelog.md / development.md / lut-formats.md / notices.md`，**没有专门的快门声文档**——本文是第一次把散在代码里的定义整理成文。

---

## 3. CP 层：真正动的 25 个字节

目标文件 `/cp/cpapp-b.bin`（A7C2 2.01），以下全是**文件偏移**。

### 3.1 selector 表（5 B）

```
偏移 0x393570
  before: 1b 26 03 44 03
  after : 44 26 44 44 44
```

含义：把「电子快门」这个 selector 从原厂的 `0x1b` 指向原厂另一块已经存在的 mode-0/mode-3 分支（`0x44` = 另一条既有入口）。不新增代码洞（no code cave），只改指针。

### 3.2 门控上下文（20 B）

```
偏移 0x3935bc
  CONTEXT (before) = db f3 3a fc 03 21 00 28 45 f6 1c 40 18 bf 00 21 21 50 20 44
  GATE_AFTER       = dc f3 a1 fa 41 f2 19 01 41 5c 01 29 16 d1 e0 e7 00 bf 00 bf
  GATE_MUTED       = GATE_AFTER[0:14] + 15 e0 + GATE_AFTER[16:20]
```

### 3.3 单点核心（2 B）

```
偏移 0x3935ca
  BEFORE = 00 21
  AFTER  = 03 21
```

这一处才是「发声 / 不发声」的真正开关：它改的是同一条指令的操作数。

### 3.4 四个状态（`sound_state(cp)`）

| 状态 | selector 表 | 20 B 上下文 | 含义 |
| --- | --- | --- | --- |
| `off` | before | CONTEXT | 原厂 |
| `legacy` | before | LEGACY_GATE | 老版本（只改了 2 B，没过滤机械快门） |
| `electronic_only` | after | GATE_AFTER | 目标态：只有电子快门响 |
| `muted` | after | GATE_MUTED | 关闭时用（不让机械快门重新响起来） |
| `partial` | 任意混合 | — | 拒绝操作 |

其余任何字节组合都 raise：`'Sound-selector context differs from supported 2.01 instructions'`。

### 3.5 原厂指令指纹（7 处，改前必须逐字节对上）

```
0x39356c  df e8 01 f0
0x39358e  45 f6 1c 40 03 21 0f e0
0x3935b6  21 50 20 44 0a e0
0x3935d0  b1 b1
0x3935f8  45 f6 1c 40 00 21 21 50
0x76fb02  4a f6 d0 70 c0 f2 01 20 70 47
0x7b0004  d0 f8 c8 54 41 f2 19 01 01 2d 18 bf 00 25 04 9c 65 54
```

> **关键事实**：`03 21` 与 `00 21` 两个变体在原厂固件里**本来就都存在**（指纹 2 与指纹 5 各持一个）。补丁不是「创造」逻辑，只是把 selector 换成原厂另一个分支。这就是这套改法风险可控的根本原因。

`0x7b0004` 那段是「每次拍摄写入的电子标志」——它保证连拍/单张都走同一条判定。

### 3.6 AP 侧门禁（`candidate.guard`）

```
AP 必须是 ELF，且 len > 0x288549c
0x286cde8 = 20 af 02 90 00 60 13 91 00 8c 40 91 00 80 03 91 c0 03 5f d6   # audio getter
0x2885488 = 40 ae 02 f0 00 60 13 91 00 04 42 91 00 00 2f 91 c0 03 5f d6   # table getter
```
不符即 `'AP sound getter conflicts; no native access planned'`——一行代码都不写。

---

## 4. AP 层：16 字节 boot 钩子 + 7 处读取器补丁

目标文件 `/usr/lib/appFw.so`（A7C2 2.01）。

### 4.1 开机点（16 B）

```
BOOT = 0x3060a24
原: adrp x0, 0x4c14000 ; str x9,[x21,#0xc] ; bl 0x36804c8   (原厂日志)
新: bl 0x2885488 ; add x1,x0,#0x0 ; bl 0x2759ae8 ; ldr x9,[x21,#0xc]
```

即：先取「声音表基址」，再调用原厂自己的「单行 CSV 登记表读取器」，最后补回被它挤掉的那条 `str`。整块只有 4 条指令、16 字节，**不新增代码段**。

### 4.2 读取器的 7 处改造

```
0x2759b3c  fopen 失败的致命路径  ->  b 0x2759bc8         (复用原厂干净收尾)
0x2759ae8  ff 1f 40 d1  ->  1f 20 03 d5                 (去掉 7 页栈 prologue)
0x2759be4  ff 1f 40 91  ->  1f 20 03 d5                 (去掉对应 epilogue)
0x2759af4  02 00 8f d2  ->  02 00 81 d2
0x2759bfc  02 00 8f d2  ->  02 00 81 d2
0x2759c0c  e0 ff 8e d2  ->  e0 ff 80 d2                 (CSV 缓冲 0x7800 -> 0x800 = 2 KiB)
0x2759c28  94 9a 29 91  ->  b 0x2759bc8                 (超长 CSV 干净返回，保留原描述符)
```

### 4.3 私有路径（右侧补 0 覆盖）

```
PATH = 0x48cfa83
原: "/usr/share/avsystemsound/beeplist.txt\0"
新: "/usr/share/avsystemsound/custom.txt" + 0 填充
```

### 4.4 编辑顺序（不可交换）

1. 先准备读取器（4.2）与私有路径（4.3）；
2. **最后**才装 boot 调用（4.1）。

恢复时严格逆序：先撤 boot 调用，再撤读取器。理由：任何中间态下「读取器还没改好但已经被调用」都会让机身拿不到声音表。

### 4.5 离线仿真验证（`boot_sound.verify()`）

用 unicorn 在三种场景下跑那段 boot 块：

- `valid`：必须解出 `(priority, kind, bytes, filename) == (6, 3, len(raw), '/usr/share/avsystemsound/custom-shutter.bin')`；
- `missing`：文件不存在；
- `oversized`：CSV 超 2 KiB。

两个失败场景都要求**原描述符不得被改动**，且原生栈用量 ≤ `0xa90`。

---

## 5. 登记表格式：12 个字段，一行一条

`beeplist.txt` / `custom.txt` 是**纯文本 CSV**，每行必须**正好 12 个字段**：

```
label, number, memory, filename, size, offset, access, priority, kind, continuous, length, first
```

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `label` | 字符串 | 如 `BEEP_ID_SHA` / `BEEP_ID_KA` / `BEEP_ID_KASHA`；A7C2 允许 label 命中这三者或**含 `SHUTTER`** |
| `number` | hex | 属性号，最终属性 = `0x02cf0000 \| number` |
| `memory` | `PIN` / `APP` | 只允许这两个；替换只做 `PIN` |
| `filename` | 相对名 | 与资源根目录拼接 |
| `size` | hex | 字节数，必须 64 的倍数 |
| `offset` | hex | 在 `SysSound.bin` 里的偏移 |
| `access` | `AA_RT` / `AA_FIFO` | 只允许这两个 |
| `priority` | 1..10 | 自定义声音用 6 |
| `kind` | 1..255 | 自定义声音用 **3** |
| `continuous` | 0/1 | 为真时 A7C2 拒绝替换（循环音另需研究） |
| `length` | — | 循环长度 |
| `first` | — | 首段长度 |

注释语法：`/* ... */` 整段注释；行首单个 `/` 表示资源根目录。资源根目录是 **`/usr/share/avsystemsound/`**（不是 `/usr/share/app`）。

重复 beep id 且 file 非 None 时 `raise ValueError('Duplicate native beep identifier')`——A1 II 有未用 RESERVE 别名行，所以是「保留」而不是「覆盖」。

A7C2 实际写入的 CSV 就是一行：

```
/* START */
/usr/share/avsystemsound/
CUSTOM,0x0003,APP,custom-shutter.bin,0xEC0,0x0,AA_RT,6,3,0,0,0
/* END */
```

其中 `0xEC0` 是音频字节数，安装时替换成实际长度。

---

## 6. 机内声音描述符：每槽 176 字节

由 `verify_beeplist.execute()` 的返回值反推（与 `sound_probe.c`、`buffer_probe.c` 的读取偏移互相印证）：

```
[0]      priority      u8
[1]      kind          u8
[4:8]    first_length  u32
[8:12]   loop_length   u32
[16:24]  length        u64      音频字节数
[24:32]  offset        u64      SysSound.bin 内偏移
[44:172] filename      char[128]
```

槽表基址（AP 里）：`0x7ed2098`，第 i 槽 = `0x7ed2098 + 176 * i`，共 25 槽。

**两个不同的「自定义槽」要分清**（源码事实，不是推测）：

- CSV 那一行落进 **slot 2**（偏移 352 = 176×2）；`boot_trial.verify_loaded()` 检查的正是 `entries[2]`：`kind==3`、`length==len(audio)`、`filename_prefix=='/usr'`、`native_handle & 0x8000`（CP 远端租约位）。
- RAM 临时注册（试听用）前，`buffer_probe.c` 校验并替换的是 **slot 24** = `0x7ed2098 + 24*176 = 0x7ed21f8`，要求 `[0]==6 && [1]==3 && len@16 && addr@32`，否则 `status = -71`。

> 这两个槽谁在什么时机生效，源码里没有一句话讲透，属于**尚未闭合的疑点**（第 13 节列为待办）。

---

## 7. 两种报文：40 B 描述报文 vs 48 B RAM 注册结构

### 7.1 `custom_sound.registration()`：40 字节

主机侧描述用（进 plan / inverse / PCM 候选），不是直接下发的字节流：

```
struct.pack_into('<4H', data, 0, 0x200d, 0x0329, 40, 0x8001)
关闭: data[20] = kind，其余 0
开启: data[8:16]  = <Q address
      data[16:20] = <I length
      data[21]    = priority (1..10)
      data[22]    = 1
      data[23]    = audio_format (0|1)
      data[24]    = continuous (0|1)
      data[28:32] = <I loop_length
      data[32:36] = <I first_length
约束: 1<=kind<=255, address<2**64, length<2**32, audio_format in (0,1), 1<=priority<=10
```

### 7.2 `buffer_probe.c`：48 字节 `struct Registration`（真机 ABI）

```
u32 enabled     @0
u32 kind        @4
u64 address     @8
u64 length      @16
u32 priority    @24
u32 format      @28
u32 continuous  @32
u32 loop        @36
u32 first       @40
u32 pad         @44
```

配套 `struct Allocation`（32 字节）：`u32 type @0, u32 handle @4, u64 address @8, u32 size @16, u32 offset @20, u32 status @24, u32 pad @28`。

---

## 8. 音频编码：filter0「32 字节块」假设

A7C2 试过两条路，结论写在代码注释里：

- **PCM16 / format=1：实机失败**。`buffer_trial.run()` 直接拒绝：`'The first PCM16/format-1 trial produced noise or wrong sound. Temporary audio registration is disabled pending decoder/layout proof; ...'`。
- **filter0 / format=0：目前唯一可用路线**。

`native_codec.py` 对 filter0 的假设（作者自标 `camera_rate_verified=False, hardware_decoder_verified=False`）：

```
每块 32 B = 1 控制字节 + 31 个有符号残差
control & ~0x1f != 0         -> 拒绝
(control & 0x0f) > 8         -> 拒绝
scale  = 1 << (control & 0x0f)
last   = residual * scale + (predictor * last if control & 0x10 else 0)
predictor = 60/64
```

编码侧：取最小指数使样本落在 `±128*(1<<n)` / `±127*(1<<n)`，残差 `round(x/step)` 截到 −128..127，不足 31 用 0 填；**整块补零到 64 字节对齐**（原生资源的 size/offset 与加载器都按 64 B 单位）。

采样与音量：`media.py` 用 ffmpeg（参数数组，从不拼 shell）截到单声道 44.1 kHz PCM16，最多 2.0 s，两端 2 ms 线性淡入淡出，再 `resample_poly` 重采样到 **24000 Hz**、峰值归一 **0.12**；转换后必须 `0 < len(payload) <= 51200` 且 `%64 == 0`。音量调整从**未量化的原始 PCM** 重新编码（防止叠加上一次的失真），增益上限 `20*log10(.95/base_peak)`、下限 −30 dB。

**51200 B** 是整条链路的硬上限（CSV、boot 读取器缓冲、RAM 注册三处共用同一个数字）。

---

## 9. 字节怎么进相机：`/tmp/jiritsu` 文件握手 + 两种 USB 会话

A7C2 不直接写寄存器，而是把 worker 当 ELF 送到相机的 `/tmp/jiritsu/` 执行，靠**文件**收结果：

```
stage   : /tmp/jiritsu/shutter.staged.so        (<= 65536 B)
request : /tmp/jiritsu/a7c2.install.request     (16 B = 'A7SFQ001' + mode + 0)
result  : /tmp/jiritsu/shutter.probe.result
extra   : /tmp/jiritsu/a7c2.probe.result
lease   : /tmp/jiritsu/shutter.custom.lease     (208 B 标记 + 16 B token)
```

写 stage 用 `jiritsu(16, b'\x00\xff\x00' + data)`，删用 `jiritsu(18, b'\x00\xff')`，且必须先 `select` 到该路径。

会话：15 s 内先找 `054c:0e8a`（MSC 正常态）→ `transport.Session`；找不到再找 `054c:0336`（服务态）→ `transport.RecoverySession`。声音任务只用**服务态的机身身份**，不走 LUT 那套 USB 描述符绑定。

`devicesession.invoke()` 的调用形态（从全部调用点反推）：

```
invoke(camera, blob, stage=, request=, result=, contents=, mode=, decode=, record=, save_raw=, extras=)
```

每次调用都把 `native_stage_intent` / `native_intent` / `native_result_verified` / `native_cleanup_verified` 写进 journal，原始报告另存 `evidence/<kind>-<序号>.bin`。

---

## 10. 事务顺序与「绝不重试」语义

### 10.1 装（`boot_trial.install()`）

```
require_power -> 读 native job(须 written + 已回读核对)
-> 二进制约束(len%64==0 且每 32 B 的控制字节 <= 8)
-> CP 若还是 0021，同一会话里先补做 trial.preflight/change
-> 已装? replace_connected()（只换音频，保留钩子） : 走下面
-> prepare() / update_plan() / backup() / programs_pinned = True
-> probe()
-> sound_files mode 0   （写 .tmp，不发布）
-> program mode 0       （installer 预检，不落字节）
-> phase creating_audio_before_boot_hook
-> sound_files mode 1   （rename 发布：CSV 最后）
-> 回读两个文件必须等于本地，否则 'Sound-file complete readback differs; AP hook was not invoked'
-> phase audio_verified_installing_boot_hook
-> program mode 1       （真正装 boot 钩子）-> camera_firmware_written = True
-> 回读 appFw.so / cpapp-b.bin 逐字节比对
-> check_settings -> installed_reload_pending -> wbi mode 1 -> installed_cold_test_pending
```

**文件先装、钩子后装**。断电最坏只会留下「有两个没人用的资源文件」，不会留下「钩子指向不存在的文件」。

### 10.2 声音文件 worker 的原子性（`sound_files.c`）

```
写 .a7c2-sound-audio.tmp / .a7c2-sound-csv.tmp -> fsync -> 逐字节比对 -> renameat(sc(38))
CSV 最后发布
新音频名不得出现在旧 CSV 里: 命中则 status = -22
```

注释原文：「The new audio slot may never be the currently referenced slot」。含义：更新时永远换一个新文件名（`custom-shutter-a.bin` → `-b` → `custom-shutter.bin` 轮转），保证任何时刻机身要么读到整套旧资源、要么读到整套新资源。

删除时**先删 CSV、后删音频**（`for (j = 2; j; j--)`）——即使钩子残留，也只会回落到原厂库。

### 10.3 恢复（`boot_trial.restore()`）

只接受 phase ∈ (`installed_cold_test_pending`, `loaded_owner_confirmation_pending`, `owner_confirmed_working`)。
按**相机当前字节**生成逆窗口（不依赖旧记录），`program mode0 + mode1` 撤钩子 → 回读（`'Restored AP readback differs; audio files must remain in place'`）→ 删两个文件 → 确认都不存在 → `restored_cold_test_pending`。

### 10.4 失败语义

- 任何异常 → `phase = needs_review`，**保留证据、绝不自动重放、绝不自动回滚、绝不自动断电**。
- 报告不完整 = 结果未知，不是「可以重试」的许可。
- `sound.private.json` 里 `pending` 未清时，`require_idle()` 连**连接相机**都拒绝。
- 只有「确证未写入」的占用才允许退役（`retire_*`：install 要求 `journal==[]` 且 `camera_firmware_written is False`）。

---

## 11. 偏移速查表（A7C2 2.01）

### CP `/cp/cpapp-b.bin`

| 偏移 | 长度 | 内容 |
| --- | --- | --- |
| `0x393570` | 5 | selector 表 `1b 26 03 44 03` → `44 26 44 44 44` |
| `0x3935bc` | 20 | 门控上下文 CONTEXT / GATE_AFTER / GATE_MUTED |
| `0x3935ca` | 2 | `00 21` → `03 21`（核心开关） |
| `0x39356c` `0x39358e` `0x3935b6` `0x3935d0` `0x3935f8` `0x76fb02` `0x7b0004` | — | 7 处原厂指纹 |

### AP `/usr/lib/appFw.so`

| 偏移 | 长度 | 内容 |
| --- | --- | --- |
| `0x3060a24` | 16 | boot 调用（4 条指令） |
| `0x2759ae8` `0x2759be4` `0x2759af4` `0x2759bfc` `0x2759c0c` `0x2759c28` `0x2759b3c` | — | 读取器 7 处改造 |
| `0x48cfa83` | ~40 | `beeplist.txt` → `custom.txt` |
| `0x286cde8` | 20 | audio getter（指纹） |
| `0x2885488` | 20 | table getter（指纹） |
| `0x7e735b8` | 4 | Audio Signals 开关（注册前必须为 0） |
| `0x7ed2098 + 176*i` | 176 | 25 个声音槽 |

### AP 里被调用的原生函数（worker 用）

| 地址 | 用途 |
| --- | --- |
| `0x3552790` | 分配声音缓冲 |
| `0x3552978` | 释放声音缓冲 |
| `0x3514f54` | AP↔CP DMA 搬运 |
| `0x34ec05c` | 注册（替换 kind3） |
| `0x2885488` | 取声音表基址 |

### 名字表/属性（离线反推用）

`ap_set_table 0x3439620`、`ap_audio_run 0x3439758`、`ap_audio_request 0x34ebcec`、`cp_pin_predicate 0x67f692`、`cp_get_request 0x67e1ce`、`cp_request_state 0x10ef2d8`、`cp_get_mode 0x66679e`、`cp_read_mode 0x6667ac`、`cp_mode_state 0x10d9bbc`、`cp_send_sound 0xb0a02e`、`cp_capture_dispatch 0xb19e5c`、`cp_capture_start 0x4a09f4`、`cp_capture_end 0x4a0a74`、`ap_signals_name 0x4f24114`、`ap_menu_setting_name 0x4f4adad`、`ap_name_table 0x582c248`、`ap_menu_name_table 0x58381d8`、`ap_lookup_cases 0x4b8a940`、`ap_lookup_base 0x2d99a94`。

另有一整套 `a1ii-4.00` 的等价偏移（`ap_set_table 0x30fcb3c`、`ap_audio_run 0x30fcc6c`、`cp_send_sound` 同族…），**证明这套结构可跨机型**，不是 A7C2 独有。

---

## 12. 对我们 A6700 的映射

### 12.1 已经有的（不需要打补丁）

`firmware/nflasha5-2.00.bin`（314,572,800 B，即 `/usr` 侧镜像）@`0x6715200` 是标准 ext2 目录块，能解出 37 个音效条目（inode 10359–10396），其中：

```
Dslr_Emnt_High_Shutter_Sha.bin      (10390)
Dslr_Emnt_High_Shutter_Ka.bin
Dslr_Emnt_High_Shutter_Burst.bin    (10383)
Dslr_Emnt_High_10FPS_Kasha.bin
20fps_KaSha.bin                     (10360)
beeplist.txt                        (10391)
SysSound.bin                        (10385)
+ 30 个 UI/提示音（T_*, Menu_*, WPS_*, Rec_*, SelfTimer_*, Startup, Shutdown, Caution …）
```

也就是说：**A7C2 要打 native 补丁才能新增的那个「自定义声音槽」，我们机身上本来就有 5 个快门槽 + 一份自己的登记表**。结构上是同源的（都是 Sony 这套 12 字段表 + 176 B 描述符 + 64 B 对齐音频）。

### 12.2 已知的差异与未解点

| 项目 | A7C2 | 我们的 A6700 |
| --- | --- | --- |
| 登记表文件名 | `beeplist.txt` | `beeplist.txt`（目录里有） |
| 读取器字符串 | appFw 里能定位 `beeplist` 路径串 | **`beeplist` / `SysSound` / `BEEP_ID` 在 `appFw-2.00.so`、`cpapp-b.bin` 里全 0 命中** |
| 音频容器 | 非 WAV；filter0 32 B 块 | 全镜像 `RIFF` 仅 1 处、`WAVE` 1 处 → **也不是 WAV**，格式未解 |
| 开关位 | CP 25 字节 | 尚未定位（我们没有 cpapp 的等价值映射） |
| 现有解锁 | 整套自研 | 我们自己的 catalog 6 项（`sound` = 电子快门声音开关，落在 `/dev/nflasha8` 扇区 11932 扇区内偏移 256） |

> 最后一行很重要：**我们 catalog 里的 `sound` 是「开关」，不是「换音色」**。两者不冲突，但也不要混为一谈。

### 12.3 硬风险

1. 相机是砖，**任何写入都无法验证**；换音频是「看不见的错误」——写错只会静音或变调，不会报错。
2. 我们的 beeplist 字段布局未解（ext2 inode 表定位失败，抠不出 `beeplist.txt` 正文）。
3. AP 侧读取器位置未知：`beeplist` 串 0 命中意味着读取路径可能完全不同，**不能照抄 A7C2 的 16 字节钩子**。

### 12.4 离线可做的事（零风险）

1. 反推 ext2 表基址，把 37 个音效 + `beeplist.txt` 正文抠出来（当前 superblock 在 `0x10600`、`fs_start=0x10200`、bs=1024、inode_size=256、ipg=2032、bpg=8192，但 GD→inode 表的换算仍未成立）。
2. 解出 filter0 的块编码是否与本机 `SysSound.bin` 一致（41,792 B）。
3. 与 A7C2 逐行比对 12 字段表，标注「可复用 / 需改 / 不可用」。
4. 找出本机 AP 侧「谁在读声音表」——这是能否在不打补丁的前提下换音色的**唯一关键问题**。

---

## 13. 待办与未闭合的疑点

- [ ] slot 2（CSV 行）与 slot 24（RAM 注册）的生效时机关系未讲透。
- [ ] `SysSound.bin` 与同名 `.bin` 必须逐字节相同（`'Resource differs from native SysSound packing: '`）——本机是否同规则未验。
- [ ] filter0 的 predictor 常量 `60/64` 是从一个机型反推的，未见第二个机型佐证。
- [ ] `custom_sound.registration()` 的 40 B 与 `buffer_probe` 的 48 B 是两套形态，二者在真机上的对应关系未公开。
- [ ] 声音默认片段 0.15 s → 0.5 s 的改动（3.0.x changelog）对应哪个参数未见代码。

---

## 14. 证据出处

```
refs/a7c2-fl23/src/shutter_sound/candidate.py          CP 25 字节窗口 / 状态机 / AP getter 指纹
refs/a7c2-fl23/src/shutter_sound/boot_sound.py         AP 16 字节钩子 / 读取器 7 处 / 离线仿真
refs/a7c2-fl23/src/shutter_sound/custom_sound.py       12 字段表 / 同尺寸替换 / 40 B 报文 / PCM 候选
refs/a7c2-fl23/src/shutter_sound/inspect_native.py     PROFILE 偏移表 / inventory() 逐字节校验
refs/a7c2-fl23/src/shutter_sound/verify_beeplist.py    CSV 常量 / unicorn 仿真 / 176 B 描述符
refs/a7c2-fl23/src/shutter_sound/native/sound_probe.c  1256 B 只读预检
refs/a7c2-fl23/src/shutter_sound/native/buffer_probe.c 208 B RAM 注册 / 48 B Registration ABI
refs/a7c2-fl23/src/shutter_sound/native/sound_files.c  88 B 报告 / .tmp + rename 原子发布
refs/a7c2-fl23/src/shutter_sound/native_codec.py       filter0 32 B 块
refs/a7c2-fl23/src/shutter_sound/trial.py              两种 USB 会话 / preflight / change
refs/a7c2-fl23/src/shutter_sound/boot_trial.py         安装与恢复顺序
refs/a7c2-fl23/src/shutter_sound/buffer_trial.py       临时注册 / 标记 / 试听结果
refs/a7c2-fl23/src/shutter_sound/media.py              ffmpeg 参数数组 / 24 kHz / 峰值 0.12
```

本机（A6700）侧：

```
firmware/nflasha5-2.00.bin          314,572,800 B  /usr 侧镜像（含 37 个音效 + beeplist.txt）
firmware/nflasha8-2.00.bin          /cp 侧镜像，FAT12，SysSound.bin 在目录项里
firmware/cp/SysSound.bin            41,792 B，无 ASCII 标签
firmware/ui/listing-share-app.txt   /usr/share/app 目录清单（只有 _32_ IPSX 图库，无 _23_）
firmware/appFw-2.00.so              89,027,992 B，beeplist/SysSound/BEEP_ID 全 0 命中
firmware/cp/cpapp-b.bin             17,892,024 B（= cpapp-live.bin，sha256 43c5d056…）
```

---

## 15. 一句话给决策用

> A7C2 的改法是「原厂已有分支 + 原厂已有读取器 + 自备资源」，不是发明新功能；
> 我们的机身**有同样的资源槽和同样的登记表**，但**还没找到本机 AP 侧读表的那段代码**。
> 在找到它之前，任何写入都是盲写；找到了，才谈得上「同尺寸替换 + zlib 逆变换回退」这套可控方案。

---
# 增补（2026-10-26 夜）：A6700 侧的实测证据、与 A7C2 的架构差异、猜想清单与验证步骤

> 本增补覆盖 §12、§13 中已被推翻的判断。原文保留不动，作为当时的推理记录。
> 全部证据均为本地离线读取（firmware/ 下的镜像与 third_party/a6700_unlock/data/a6700-2.00.json），没有连接相机。

## 16. A6700 侧的新证据（推翻了「AP 侧完全没有声音代码」这一判断）

### 16.1 之前的空白结论是怎么来的

先前只搜了 beeplist、SysSound、BEEP_ID 三个串，在 appFw-2.00.so 与 cp/cpapp-b.bin 里全 0 命中，于是推测「本机 AP 侧没有读表代码」。
这次改搜目录串 avsystemsound、枚举 BEEP_SET_CUSTOM、以及大小写变体 beep，结论立刻变了：

| 镜像 | avsystemsound | BEEP_SET_CUSTOM | beep | beeplist | SysSound |
| --- | --- | --- | --- | --- | --- |
| firmware/appFw-2.00.so（89,027,992 B） | 4 处 | 2 处 | 12 处 | 0 | 0 |
| firmware/cp/cpapp-b.bin（17,892,024 B） | 0 | 0 | 3 处 | 0 | 0 |
| firmware/nflasha5-2.00.bin（314,572,800 B） | 12 处 | 2 处 | 12 处 | 1（目录项） | 1（目录项） |

结论修正：A6700 的 AP 侧确实认得 /usr/share/avsystemsound/，但只认得 4 个文件；它不使用 A7C2 那套 12 字段 CSV 黄页。

### 16.2 appFw 里 4 条硬编码路径（sequence/sequence_boot.cpp，字符串池起于 0x4078d6c）

    0x4078e6c  /usr/share/avsystemsound/Dslr_Emnt_High_SelfTimer_RemoteRelease.bin
    0x4078eb0  /usr/share/avsystemsound/Dslr_Emnt_High_SelfTimer_2sec.bin
    0x4078eeb  /usr/share/avsystemsound/Dslr_Emnt_High_Startup.bin
    0x4078f1f  /usr/share/avsystemsound/Dslr_Emnt_High_Shutdown.bin

同池还有 /setting/sig.txt、userID = %d、%s:%s():%d:retry_count = %d，可以确认这 4 条属于开机序列，不是快门音。
快门音、菜单音、触摸音在任何 AP 字符串里都没有出现过：Shutter_Sha、Shutter_Ka、Kasha、KaSha、Shutter_Burst 在 appFw-2.00.so 与 cpapp-b.bin 里全部 0 命中。

### 16.3 新发现的原生符号（model::sequence_boot，0x40791d8–0x4079298）

    0x40791d8  void model::sequence_boot::adf_set_volume_i()
    0x4079208  bool model::sequence_boot::regist_beep_signals(model::beep_sound_id_t, uint64_t)
    0x4079260  void model::sequence_boot::regist_beep_signals_i()
    0x4079298  void model::sequence_boot::run_i()

→ A6700 是开机序列里用函数调用逐条注册声音（regist_beep_signals(beep_sound_id_t, uint64_t)），参数是「声音 id + 一个 64 位值」（大概率是 RAM 地址或偏移+长度）。
这是编译期内建表 + 运行时注册，与 A7C2「运行时读 CSV 黄页」是两条完全不同的路。

### 16.4 「自定义提示声」在 A6700 上真实存在（设置系统枚举）

appFw-2.00.so 的 0x437daa1–0x437dc47 是一张连续枚举名表：

    EXTERN_VAL_PARAM_REMOCON_LIVE
    EXTERN_VAL_PARAM_WIFI_POWER_MODE_STANDARD / _HIGH
    EXTERN_VAL_BEEP_SET_CUSTOM_OFF      @0x437db16
    EXTERN_VAL_BEEP_SET_CUSTOM_ON       @0x437db35
    EXTERN_VAL_SYSTEM_SOUND_VOLUME_MUTE / _MINUS_18DB / _MINUS_15DB / _MINUS_12DB / _MINUS_9DB / _MINUS_6DB

CP 侧也有对应物：cpapp-b.bin 的设置键名字符串池 0x93e44 起——
base Init / ret_size / startupsound / logodisplay / ee_play / panelout / w_power_mode / logo_type / app_beep_set / beep_set_custom / volume / sublcd / boot_fact.type / liro_topology。

也就是说：beep_set_custom 这个设置键在 CP 侧真实存在，EXTERN_VAL_BEEP_SET_CUSTOM_ON/OFF 在 AP 侧真实存在。A6700 有「自定义提示声」这个概念，只是当前菜单里没暴露（或没本地化）。

### 16.5 CP 的声音是「ADF 子系统」管的，不是 AP 开文件放的

cpapp-b.bin 里的证据：

    0xa2da0  callbackAsfc_beep_level cb_err->code(0x%08x)
    0xc17e4  SendADF_SysSetBeepVolume ERR_FATAL
    0xbab880 27AdfSystemSoundSetBeepVolume
    0xbab8c0 19AdfSystemSoundTable
    0xbab8e0 25AdfSystemSoundTableBundle
    0xbab960 20AdfSystemSoundVolume
    0xe1904a MSG_ID_INFRABB_AUDIO_SET_BEEP_LEVEL
    0xe1a688 MSG_ID_INFRABB_ADF_SYS_SET_BEEP_VOLUME
    0xe1a54e ... MSG_ID_INFRABB_ADF_SYS_GET_SYSTEM_SOUND_ADDRESS ...

最后一条是关键：CP 会向 ADF 子系统要「系统声音地址」，即声音库被加载到 RAM，播放时按 id + 编译期偏移直接取。

### 16.6 /cp 分区的真实目录（FAT12，根目录 0xc120，逐字节解出）

| 8.3 名 | 大小 | 起始簇 |
| --- | --- | --- |
| SYSSOUNDBIN | 41,792 | 26 |
| CPIMG   DAT | 1,885,696 | 29 |
| CPAPP-B BIN | 17,892,024 | 145 |
| LOADER~1BIN | 39,184 | 1,238 |
| MINI_LDRBIN | 40,752 | 1,241 |
| PCIE_P~1BIN | 16,384 | 1,244 |
| TOMCO   TXT | 741 | 1,245 |
| NOR_LDR IMG | 417,792 | 1,246 |

firmware/cp/SysSound.bin = 41,792 B 就是这里的 SYSSOUNDBIN，是整个 CP 唯一的声音库文件。

### 16.7 我们自己的 catalog 早就在动这一个字节（且已真机验证）

third_party/a6700_unlock/data/a6700-2.00.json 的 sound feature（available: true，verification: hardware-playback-verified）写了 9 条 edit，其中 CP 那条是：

    { "id": "cp-5d3900", "image": "cpapp", "offset": 6109440,
      "disabled": "00", "enabled": "03",
      "purpose": "CP exposure-start sound mark: cpapp-b.bin 0x387900 movne r1,#0 -> movne r1,#3 (A7C II reference)" }

6109440 = 0x5D3900 = nflasha8 扇区 11932 + 扇内 256（与 limits 文字完全对应），换算到 cpapp-b.bin 文件偏移 0x387900（差 0x24B800）。
本地 firmware/cp/cpapp-b.bin 在 0x387900 已经是 03 21（MOVS r1,#3）——本地副本是打过补丁的现场态，不是出厂态，别再拿它当「原厂字节」用。
这条 edit 的 purpose 自己写着「A7C II reference」，说明当初就是照 A7C2 的思路找的；而它已经在真机上验证过（「菜单 4 项正常，电子快门有克哒声」）。

### 16.8 声音库格式：A7C2 的 filter0 假设在 A6700 的 CP 库上成立

firmware/cp/SysSound.bin 41,792 B = 1306 个 32 字节块（41,792 / 32 = 1306），同时也是 64 字节整数倍（41,792 / 64 = 653）。
按本文 §8 的 filter0 规则（每块 1 字节控制 + 31 个有符号残差；scale = 1 << (ctrl & 15)；ctrl & 16 时 x = r*scale + (60/64)*last）整段解码无一处违规：

- 控制字节全落在 0x00–0x08 与 0x10–0x18（指数部分恒 ≤ 8，保留位恒 0）；
- 解出 40,486 个样本，幅度 −30,720 … +30,830（正好在 int16 范围内），RMS 6,696；
- 相邻样本相关系数 0.817（音频量级）；把预测系数改成 1.0 且把 bit4 取反则升到 0.956 —— 说明具体是哪种变体还需要用真机的原厂音去校验，但「32 字节块 + 1 控制 + 31 残差」这个骨架是确定的；
- 按 24 kHz 计全长 1.687 s，能量分段（64 样本窗）为：

    段  起始样本   长度(样本)   @24kHz    @48kHz
    1        0        6016       250.7 ms  125.3 ms
    2     6080        1280        53.3 ms   26.7 ms
    3     7488        1216        50.7 ms   25.3 ms
    4     9664        3136       130.7 ms   65.3 ms
    5    12928       21888       912.0 ms  456.0 ms
    6    35264        2048        85.3 ms   42.7 ms
    7    37888        2048        85.3 ms   42.7 ms

解码结果已落盘，可直接试听判断是不是快门音：Powerful6700Win/.data/tmp/cp-syssound-decoded-24k.wav（24 kHz / 单声道 / 16 bit）。
这是纯离线产物，没有碰相机；如果听起来像快门/提示音，就说明这条路通了。

## 17. A6700 与 A7C2 的架构差异（为什么不能照搬）

| 维度 | A7C2（本文 §1–§11 拆的就是它） | A6700（本机实测） |
| --- | --- | --- |
| 注册方式 | 运行时读 /usr/share/avsystemsound/beeplist.txt，12 字段 CSV | 编译期表 + regist_beep_signals(beep_sound_id_t, uint64_t) 逐条注册；无 CSV |
| 资源位置 | AP 侧 /usr/share/avsystemsound/，SysSound.bin 是打包仓 | CP 侧 /cp/SysSound.bin（41,792 B）是唯一声音库；AP 侧只硬编码 4 个开机音 |
| 触发口 | AP boot 块 16 字节钩子，把 kind3 登记进表 | CP 曝光起点的一个立即数（r1 = 3），不是钩子 |
| 改动面 | CP 25 B + AP 16 B + 读取器 7 处 + 两个资源文件 | CP 1 字节（movs r1,#3）+ AP 3 个菜单权限 byte |
| 生效条件 | 冷启动 | 冷启动（我们已真机验证过） |
| 我们缺的 | — | CP 声音库里 id→(偏移,长度) 的映射；哪个 id 是哪段音 |

一句话：A7C2 是「AP 侧换文件 + 打钩子」，A6700 是「CP 侧换库 + 改 id」。
本文 §3–§10 的 CP/AP 字节虽然不能直接用，但 filter0 音频格式、/tmp/jiritsu 两文件握手、48 B RAM 注册 ABI、原子发布顺序这些结构性知识全部可复用。

## 18. 我们的猜想清单（每条都可证伪）

每条都写明「怎么判定」「预期」「判否怎么办」。判定手段分 L0 离线／L1 真机只读／L2 真机写入（L2 必须可回退，而且必须在相机不是砖的时候做）。

### H1（CP 的 r1 是声音 id）

- 内容：cpapp-b.bin 0x387900 的 r1 就是「曝光起点要播哪个声音」的 id；3 = 电子快门自定义声，0/1/2 是别的音（或静音）。
- 判定（L2）：在同一会话里把该字节改成 00/01/02，冷启动后逐一试听；改回 03 复原。单字节、可回退、不需要动库。
- 预期：不同值听到不同音（或静音）。
- 判否：若 00/01/02 全部静音且 03 有音，说明 id 是「通道选择」而不是「音色选择」，转 H2。

### H2（CP 只认 /cp/SysSound.bin，ADF 取地址播放）

- 内容：CP 开机把 SYSSOUNDBIN 读进 RAM，MSG_ID_INFRABB_ADF_SYS_GET_SYSTEM_SOUND_ADDRESS 拿到的就是这块缓冲；快门音一定在这 41,792 B 里。
- 判定（L0+L2）：L0 用 filter0 解码确认它确实是音频（已做）；L2 把库内某段字节整体换成另一段（同长度），冷启动试听是否变化。
- 预期：声音变化。
- 判否：声音不变 → 库里不是正在播的数据（可能另有 RAM 内生成或 AP 侧提供）。

### H3（库内按 id 顺序切片，段边界 = id 边界）

- 内容：16.8 那 7 个能量段就是 7 个 id 的音，顺序与 id 一致；每个 id 的 (offset,length) 以 64 B 为单位对齐。
- 判定（L0）：把每段起点换算成字节偏移（sample/31*32 后向下取 64 的整数倍）与长度，看是否能造出一张自洽表；再用 H1 改 id 观察到「听到第 N 段」来对号。
- 预期：能对号入座。
- 判否：段边界与 id 无关（比如 id 只是音量/开关），转 H6。

### H4（AP 侧那 37 个 .bin 在 A6700 上不参与快门声）

- 内容：appFw 只引用 4 个开机音；其余 33 个文件是平台图里带过来的存货。
- 判定（L0）：/usr 镜像里搜 AA_RT / AA_FIFO / CUSTOM,0x / BEEP_ID 全部 0 命中 → 没有 CSV 黄页 → 没有「按文件名登记」的机制。
- 结论：已判定为真（本次扫描）。

### H5（beeplist.txt 在 A6700 上是空文件/占位）

- 内容：目录项存在（inode 10391），但内容不是 CSV。
- 判定（L0）：把 /usr 镜像的 ext2 inode 表解出来，读 inode 10391 的 size。当前卡在这里：superblock 在 0x10600（fs_start 0x10200、bs 1024、inode_size 256、inodes_per_group 2032、blocks_per_group 8192），GD 表在 FS+2048、32 字节描述符，但按 gd5 的 inode_table=0xa107 读 inode 10385 得到 mode 0o120034 / size 438,907,584（垃圾）；全镜像搜 0o40755 的 ed 41 为 0 命中。已知可用锚点：image_00_32_IPSX 的 inode 记录在 0x2e47b00、image_01_32_IPSX 在 0x2df1f00（都 256/128 对齐），但没有任何 GD 组的 inode_table 覆盖 0x2df1f00 → GD 基址或块号换算还有错。
- 预期：size 很小（0–4 KB）或内容非 CSV。

### H6（beep_set_custom 是「自定义提示声」总开关，可能与快门声是两条通路）

- 内容：EXTERN_VAL_BEEP_SET_CUSTOM_ON/OFF + CP 的 beep_set_custom 键说明有独立的「自定义提示声」概念；A7C2 没有对应物。
- 判定（L1）：真机读该设置当前值（只读）；如为 OFF，看菜单里是否根本没有入口（串表里「快门声」0 命中 → 没有本地化文案）。
- 预期：OFF 且无菜单入口。

### H7（filter0 的具体变体待定：60/64 + bit4 预测，还是 1.0 + bit4 取反）

- 内容：两种解释都能解码，lag-1 相关分别 0.817 / 0.956。
- 判定（L0）：找一段已知内容的原厂音（例如 /usr/share/avsystemsound/Dslr_Emnt_High_Startup.bin，AP 侧硬编码引用、肯定会被播）用同一套规则解码，比较哪种变体更「像声音」。注意：任何单一 p 都能精确回环（解码后再编码必然回到原字节），所以回环测试不能用来判定 p，只能用来判定「32 字节块 + 1 控制 + 31 残差」这个骨架。
- 判否：两种都不像 → 说明 CP 库不是 filter0，而是另一种编码。

## 19. 验证步骤（按风险从低到高，可直接照做）

### L0 离线（不需要相机，任何人都能做）

1. 用 filter0 规则解码 cp/SysSound.bin，落成 WAV，人工试听（本文件 16.8 已给出结果与样本数）。
2. 用同一脚本解码 AP 侧已知会被播的音（Dslr_Emnt_High_Startup.bin 等），确认「解码出来像人耳能认的声音」，以此定 H7 的变体。
3. 解 /usr 镜像的 ext2 inode 表（H5），拿到 beeplist.txt 的真实大小与内容；顺带把 37 个音效文件全部抠出来，作为「原厂音素材库」。
4. 把 H3 的段边界换算成 64 B 对齐的 (offset,length) 候选表，和 A7C2 的 176 B 描述符字段（[16:24]=length、[24:32]=offset）对照，看是不是同一种结构。

### L1 真机只读（不写任何字节）

5. 读 /cp/SysSound.bin 全程 41,792 B 并回算 sha256 → 确认与本地 firmware/cp/SysSound.bin 一致（说明本地这份就是现场态）。
6. 读 cpapp-b.bin 0x387900 附近 64 B → 确认当前是 03 21 还是 00 21（本地这份是打过补丁的，现场若已还原就是 00 21）。
7. 读设置项 beep_set_custom / EXTERN_VAL_BEEP_SET_CUSTOM_* 的当前值。

### L2 真机写入（必须可回退；建议上游在非主力机上做）

8. 单字节实验（H1）：0x387900 依次写 00/01/02/03，每次冷启动试听；每次写前先读回 1 字节存证，写后立即回读校验。这不触碰声音库，风险最低。
9. 同长度换段（H2/H3）：把库内 A 段的字节整段覆盖到 B 段（长度必须完全相同、64 B 对齐），冷启动试听是否 B 位置出现了 A 的音。
10. 整库替换（最后一步）：用我们自己的 filter0 编码器生成一段同长度音频替换库文件，冷启动试听。这一步才真正实现「自定义快门声」。
11. 每一步之间按老规矩：拔数据线 → 正常关机 → 等存取灯灭 → 拔电池 ≥ 1 分钟。写入前先备份原始 41,792 B。

## 20. 需要上游回传的东西

1. /cp/SysSound.bin 的完整 41,792 B + sha256（是否与我们这份一致）。
2. cpapp-b.bin 0x387800–0x387A00 的 512 B（确认现场是 00 21 还是 03 21，以及周围指令有没有版本差异）。
3. 把 0x387900 依次改成 00/01/02/03 后的试听结论（能听到几个不同的音、分别像什么），这是 H1 的唯一判据。
4. 菜单里「音频信号」（AUDIO_SIGNALS_*）到底有哪几项、选「仅快门」时电子快门有没有声音。
5. AP 侧 /usr/share/avsystemsound/ 的完整目录清单（文件数、大小），以及 beeplist.txt 的真实大小。

## 21. 只有上游能回答的问题

1. A7C2 上 MSG_ID_INFRABB_ADF_SYS_GET_SYSTEM_SOUND_ADDRESS 有没有对应物？如果有，ADF 的「系统声音表」是按 id 索引还是按名字？
2. A7C2 的 CP 侧是否也有一份 SysSound.bin（41,792 B）？如果有，和我们的逐字节是否相同——相同就说明这套库跨机型共用，我们的 H3 可以直接用 A7C2 的结论。
3. A7C2 有没有 regist_beep_signals 的对应物？（A7C2 走 CSV，A6700 走函数注册；如果 A7C2 也有这个符号，说明两者共用一套底层，只是 A7C2 多了一层 CSV。）
4. A7C2 的 beep_set_custom 设置键存在吗？如果存在但菜单没暴露，它是怎么被使用的？

## 22. 本节结论（给上游的一句话）

A7C2 那条「AP boot 钩子 + CSV 黄页」的路，在 A6700 上不存在；A6700 的等价物是「CP 侧一个 41,792 B 的声音库 + 曝光起点的 1 字节 id」。
声音库用的确实是 A7C2 假设的 32 字节 filter0 块格式（已离线解码成功，7 段约 1.7 s 音频）；剩下缺的只是「id → 库里哪一段」这张表，以及一次真机试听确认。
