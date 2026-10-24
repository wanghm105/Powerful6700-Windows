# 路线二：机身文件写入能力（flash write）

状态：**载荷与主机侧已就绪，尚未在相机上执行任何写入**（首次执行必须是零变化的 probe）。

## 1. 结论先说

我们不需要（也不应该）去操作裸 flash 设备节点。A6700 的固件在运行时把两个分区**挂载成文件系统**：

| 挂载点 | 设备 | 文件系统 | 我们关心的文件 |
| --- | --- | --- | --- |
| `/usr` | `/dev/nflasha15` | ext2（749,731,840 B） | `/usr/lib/appFw.so`（89,027,992 B） |
| `/cp` | `/dev/nflasha8` | FAT12（67,108,864 B） | `/cp/cpapp-b.bin`（17,892,024 B） |

所以写入是**文件内容写入**：ext2/FAT12 负责块映射，`pwrite64` 到文件偏移即可，不需要擦除、不需要碰坏块管理。
这与 A7C2 的做法一致 —— `refs/a7c2-fl23/src/camera_runtime/native/installer.c` 就是
`openat("/usr/lib/appFw.so"|"/cp/cpapp-b.bin")` + `pwrite64` + `fsync`(82) + 回读比对，
必要时用 `mount`(40) 把挂载点重新挂成可写（`0xc30` = REMOUNT|SYNCHRONOUS|NOATIME|NODIRATIME，再按需加 `MS_RDONLY`）。

风险因此只有一类：**写入过程中掉电/断线**，会让该文件处于半写状态。缓解手段是「先全量备份 + 只写小块 + 回读校验 + 随时可用同一工具写回备份」。

## 2. 载荷 `native/flash_write.c`（与只读载荷分开）

- 请求文件 `/tmp/jiritsu/tmmc.jit`，28 字节头与 `dump_range.c` 完全一致；写入数据另放 `/tmp/jiritsu/tmmc.dat`。
- 模式：`0` 读范围、`1` 报长度、`3` 写入、`4` **零变化 probe**（读原字节 → 写回同样字节 → fsync → 回读比对）。
- 硬性拒绝（在载荷里，不是只在主机侧）：
  - 只接受 `/usr/` 与 `/cp/` 开头的路径；含 `/../` 或 `/dev/` 一律拒绝（状态 6）；
  - `geteuid() != 0` 拒绝（状态 6）；
  - 数据文件长度必须**恰好等于**本次 length，否则拒绝（状态 10）——防止陈旧/追加的数据被写进去；
  - 目标范围必须落在文件长度内（状态 12）。
- 每次都 `fsync` 后回读比对；不一致返回状态 9，绝不上报成功。
- 若挂载点是只读，`openat(O_WRONLY)` 返回 `-EROFS` 时重挂为可写一次，操作结束再挂回只读。
- 状态码：0 ok / 1 请求无效 / 2 打开失败 / 3 读取失败 / 4 路径或长度越界 / 5 lseek 失败 / 6 拒绝写入 / 7 写入失败 / 8 fsync 失败 / 9 回读不一致 / 10 数据文件长度不符 / 11 无法改可写 / 12 范围越界。

产物：`native/flash_write.elf`（40,576 B，zig 0.13.0 `aarch64-freestanding` + `ld.lld`），
清单 `native/flash_manifest.json`（含 sha256，主机侧加载前强制核对）。

## 3. 主机侧

- `src/a6700win/flash.py`：`payload()` / `allowed()` / `stat()` / `read_range()` / `probe()` / `write_block()` / `write_windows()`；
  `TARGETS` 记录两个目标的期望长度与 sha256（appfw `721fceae…`、cpapp `43c5d056…`），写入前可比对。
- `tools/flash_write.py`：
  `--stat` 列长度 → `--probe`（零变化自检）→ `--verify BACKUP`（把相机现内容与本地备份对齐）→
  `--write-hex` / `--write-file`（**必须** `--confirm yes-write`，写前记录写前/写后/期望三份 sha256 到 `.data/flash-log/`）。
- 单块上限 `BLOCK = 0x8000`（32 KiB），受 Jiritsu 临时文件 64 KiB 上限约束。

## 4. 首次执行的安全顺序（未执行）

1. `python tools/flash_write.py --stat`：确认 `/usr/lib/appFw.so` 与 `/cp/cpapp-b.bin` 长度与备份一致。
2. `python tools/flash_write.py --probe --target cpapp --offset 0x1000 --length 0x200`：
   写回同样的 512 字节。成功即证明「可写挂载 + pwrite64 + fsync + 回读」这条链在 A6700 上成立。
3. 若 probe 成功，再做**一个字节的真实写入实验**（cpapp 里某段未使用的填充），
   拔电重启后回读，确认「写入真的落盘」（不是缓存）。
4. 才开始动 CC/NC 需要的窗口。

## 5. 备份现状（写前必须核对）

| 对象 | 本地备份 | sha256 / 长度 |
| --- | --- | --- |
| `/usr/lib/appFw.so` | `../firmware/appFw-2.00.so` | `721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d`，89,027,992 B |
| `/cp/cpapp-b.bin` | `../firmware/cp/cpapp-b.bin` | `43c5d056ed9357957c5e7cd1ae24928b077d26b6761bf193eefb303b0b32510d`，17,892,024 B |
| `/dev/nflasha15` 整卷 | `../firmware/parts/nflasha15-full.bin` | `e900dd9eb938827fe7c300a2ca48fadfc95ebf81dc46cf364826e779973ddd33`，749,731,840 B |
| `/dev/nflasha8` 整卷 | `../firmware/nflasha8-2.00.bin` | `3bddcce378438423617a7c647ab862e5fd4ee6d0d4f627b769b4b08007457dcc`，67,108,864 B |
| `/dev/nflasha2` | `../firmware/parts/nflasha2-*.bin` | 见 `docs/FIRMWARE-MAP.md` |

## 6. 恢复方案

任何一次写入都能用同一工具写回：`--write-file <offset> <备份片段> --confirm yes-write`。
如果相机因 `appFw.so` 半写而无法正常启动，只要**服务模式（0x0336）仍能进**，就还能用同样的链路写回；
这是本方案相对「改裸 flash」的关键优势。若连服务模式都进不去，只能走索尼售后 —— 所以在 `appFw.so` 上动手之前，必须在 `cpapp-b.bin` 上先完成步骤 2、3 的全部验证。

## 7. 与 CC/NC 的关系

CC/NC 需要两件事，都落在这两个文件里：

1. **颜色/色调**：`/cp/cpapp-b.bin` 的初始化数据块（文件偏移 `[0xFBF000, 0x11002B8)`）里有 9 条 1024 字节的曲线记录（`0xfe0b50` 起、步长 `0x400`，目前全是恒等曲线）；A7C2 的做法是在这里追加/替换 gamma 记录（其 `patches.json` 写 3,872 字节到 `0x1100b80`）。
2. **外观枚举与菜单**：`/usr/lib/appFw.so` 的 look 表与 16 个槽位绑定（A7C2 改 `0x3528804` 的 `cmp w1,#9` → `#11` 并加两个槽）。

显示名（CC/NC 这两个**名字**）不走固件，走 `/usr/share/app/*.uxc` 资源（`refs/a7c2-fl23/src/looks/looktool/resources.py` 的编解码器可用）；这一步同样是 `nflasha15` 上的 ext2 文件写入，走本工具。

## 8. 待办

- [ ] 相机切 MSC 后执行 `4 步骤 1、2（probe）。
- [ ] probe 通过后做 `4 步骤 3（1 字节真实写入 + 断电回读）。
- [ ] 在 cpapp 里定位「运行时灌入的曲线来自哪段初始化数据」，把 CC/NC 的曲线做出来。
- [ ] 决定显示名：改「自定义外观 2/3」的字符串，或扩 `.uxc` 的记录数。


## 真机进展（写入链路已打通）

### 首个 bug：回读用了只写句柄
- 现象：所有 probe（mode 4/5）返回状态 3，载荷回传 errno `18446744073709551607`（= -9 = EBADF），读通道（mode 0/1）却完全正常。
- 定位手段：给载荷加 `phase` 追踪（失败时把 phase 放进结果头的 length 字段），主机侧 `_parse` 打印 phase；新增 mode 9「临时目录自测」（在 /tmp/jiritsu/scratch.bin 上走同样的 open→write→fsync→pread→pwrite→回读→删除），一次会话即可判断是宿主代码问题还是目标文件问题。
- 结论：phase 13 = `compare_file()` 里的 `pread64(fd, ...)`，而 `fd` 是 `open_writable()` 得到的 **O_WRONLY** 句柄 → 对只写句柄读回必然 EBADF。
- 修复：fsync 后先 close 写句柄，再用独立的 O_RDONLY 句柄回读比对（与 A7C2 installer 的 verify 一致）。修复后八项 probe 全部 `verified=True`：/usr/lib/appFw.so 与 /cp/cpapp-b.bin，pread 与顺序各一遍。

### 内存对齐/编译层面的两个坑
- 内联 `svc #0` 的 asm 必须声明 `"cc"` clobber：`svc` 会改写条件码，缺了会让编译器在系统调用之后误用旧的标志位。
- 加载/store 掩码要精确：MOVZ 用 `0xFF800000 == 0x52800000`，MOVW/MOVT 用 `0xFBF0`；掩码写错会得到成批的假命中（本轮踩过两次）。

### 首次真实写入（单字节、可回滚）
- 目标：`/usr/share/app/string_simplifiedchinese.uxc` 偏移 `0x1CD8`，某条记录（'子网掩码'）末尾的补齐字节，解码在 NUL 处停止，所以这一字节不参与任何语义。
- 步骤：`tools/flash_persist.py write` → 读原值 `00` → 写 `ff` → fsync → 回读 `ff` 一致 → 记录到 `.data/flash-log/persist-byte.json`。
- 结果：**A6700 固件 2.00 的 /usr（nflasha15，ext2）可写**；写前自动 remount rw、写后 remount ro。
- 待验证：断电重启后该字节是否仍为 `ff`（`tools/flash_persist.py check`），确认后 `restore` 还原。

### 工具
- `tools/uxc.py`：UXC-v7 通用解码（kind/group/descriptor/索引/记录/补齐校验）、按文字查找、列出带补齐的记录、就地改名（新文字不超过原容量即可，不动索引表）。
- `tools/flash_persist.py`：单字节持久性验证（write / check / restore）。
