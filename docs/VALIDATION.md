# 验证边界

## 已在本机验证（无相机）

- `.venv`（Python 3.12.3）里 `import usb / libusb_package / PySide6 / PyInstaller` 全部可用；
- `pytest tests -q` → **93 passed / 1 skipped**（SetupAPI 解析与枚举、wdi 参数与白名单、补丁幂等与
  载荷严格性、Windows 兼容层的设备锁/独占保存/二进制写/异常放锁、结构守卫的时间戳豁免与
  **写入目标回填**、恢复预约/写前拒绝分类、载荷错误文案、驱动页门闸、外观页会话释放、六个页面无头渲染、
  **UXC 语言资源的就地改名/整块后移/幂等，以及菜单文字写入与三档还原的假设备回归**、
  **一次写入的两段顺序与两段各自的失败分支**）；
- `--offline-self-test`（源码运行）：python / platform / vendor / files / data-dir / libusb / setupapi /
  controller 全 OK，wdi 因未下载而 SKIP；
- `build_controller('physical') + check_environment()` → `environment.ready = True`，
  `python / platform / pyusb / libusb / payload-integrity` 五项全绿（platform 一行显示 `win32`
  且 remediation 已换成 Windows 文案，证明 `doctor.diagnose` 补丁生效）；
- 图形界面在 `QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts` 下逐页渲染并截图，
  中文、换行、滚动、卡片高度均正常；
- PyInstaller onedir 冻结包构建成功（`dist/Powerful6700/`，98 MB），
  `Powerful6700.exe --offline-self-test` 通过，libusb 解析到 `_internal\libusb-1.0.dll`；
- Windows 兼容层（`windows_shim`）实测：两把非阻塞独占锁（同进程第二次取锁被拒、退出后可再次取得）、
  `save_json` 用 `O_EXCL` 独占而不覆盖、`backup` 写文件为二进制模式（0x0A 不再被改写成 0x0D 0x0A）、
  `planner.os.O_NONBLOCK` 为 0。

## 已在真机验证（A6700 · 固件 2.00，2026-10-23）

真机链路在本机 Windows 上完整跑通，证据来自 `.data\state\runs\<run>\result.json`：

1. **驱动与两次认证**：`0x0E76 "Sony A6700 - Storage"` 由 `wdi-simple.exe` 绑定 WinUSB；
   只读检查期间相机切到 `0x0336`，工具用 SetupAPI 先发现设备、再自动为它绑定 WinUSB（无需重插），
   两次 Senser 认证均通过，`SenserChannel 0x4010 / 0x4007 / 0x4008` 三段下发正常。
2. **只读检查**（`20261023T141915Z-9620d425d4`）：`status=inspected`、`compatible=true`、`issues=[]`，
   读回 260 扇区 / 133,120 字节，六个功能读到的状态均为 `disabled`。
3. **功能状态备份**（`20261023T141931Z-f5964089ab`）：`status=backup-completed`、`verified=true`，
   写出 41,582 字节 `.a6700backup`，本机 `sha256sum` 复算与界面显示一致
   （`5e07a01ce0263bc9fa7ee6a22e32cb68dc481d9284431265faf192304911b6a4`）——
   证明 `backup.os.O_BINARY` 补丁生效，否则 0x0A 会被 CRT 改写成 0x0D 0x0A。
4. **关闭方向写入 + 机身验收**（`20261023T143727Z-e22ff0f6af`，只选电子快门声音走 `close`）：
   `status=completed`、`verified=true`、
   `native_result={"status":0,"touched":4,"rolled_back":false,"failed_index":null}`，
   回读 `final_features` 里 `sound=disabled`；两分钟后的只读检查
   （`20261023T143943Z-e08b3daf91`）仍读到 `sound=disabled`，证明状态持久化。
   上游 0.2 的 `aftercare`（断电重启 6 步 + 菜单验收路径）已在结果页「机身验收」卡片渲染。
6. **真实写入**（`20261023T142020Z-b9ce355bd1`，四个功能全选 `unlock`）：
   `status=completed`、`verified=true`、`write_attempted=true`、
   `native_result={"status":0,"touched":138,"rolled_back":false,"failed_index":null}`、
   `changed_bytes=333`、`changed_sectors=138`，回读 `final_features` 四项全部 `enabled`，
   `restart_required=true`；相机重启后功能生效（实测出现新的 MTP / 传输相关菜单项）。

## 仍未验证

以下仍没在真机上验证过，不要当作可用性承诺：

1. **一次写入 / 一次还原的真实流程**（0.3.5 颜色 + 名字，两段会话；本地只验了编排）；
2. **失败回滚**（`rolled-back` / `recovery-required`）与写入中断（拔线、相机睡眠）时的行为；
3. **功能状态恢复**（`.a6700backup` 写回、只写回清单字段的稀疏恢复）从未执行过；
4. `0x047D` 这一初始 PID（MSC 的另一种枚举）未验证，本机只见到 `0x0E76`；
5. 多台索尼设备同时连接时的唯一性报错路径；
6. 提权失败、非管理员启动时的 Windows 提示链路（目前只验证了管理员路径）；
7. macOS / Linux 行为（本端口只为 Windows 增加适配，未回归原平台）。

## 复现顺序

`--diagnose` → 驱动准备（先 `0x0E76`；`0x0336` 会在只读检查时自动完成）→ 只读检查 →
功能状态备份 → 选择功能写入 → 重启相机 → 重新只读检查确认状态为 `enabled`。

## 真机：恢复路径的第一轮观察（2026-10-23）

`20261023T144526Z-dc69a1f9c0`：`action=restore`、`status=no-op`、`write_attempted=false`、`verified=true`，备份 SHA-256 与备份文件一致。

结论：恢复链路（备份读取、兼容性校验、回读）本身正常，但作用域不对——上游 `run_reserved()` 对 restore 也按 `selected_features` 传功能子集（当时只剩「电子快门声音」被勾选），而备份里该功能本来就是 disabled，于是 `restore_plan()` 得到零差异，直接走 no-op。已在 `controller.restore_scope` 补丁里改为整份写回，新增回归测试 `test_restore_scope_expands_to_every_available_feature`。真机 restored + 独立回读证据仍待补。

## 真机：备份恢复（restored）通过（2026-10-23）

`20261023T144959Z-d58b6f753c`：`action=restore`、`status=restored`、`verified=true`、
`write_attempted=true`、`native_result={"status":0,"touched":134,"rolled_back":false,"failed_index":null}`、
`plan.changed_sectors=134`、`plan.changed_bytes=326`、`restart_required=true`、
`cleanup_status=null`。`final_features` 六项全部 `disabled`，与备份一致。

`restore-source.json` 记录了来源：`A6700-state-20261023T141931Z-2059d1ac.a6700backup`、
SHA-256 `5e07a01c…b6a4`、`tool_version=0.1.0.dev33`（备份由旧版本创建，按 profile 摘要匹配后仍可恢复）。

至此四条真机写路径全部有证据：只读检查、功能状态备份、解锁写入、关闭写入、备份恢复。
仍未验证：失败回滚（需要人为制造相机内校验失败）、跨固件/跨机型兼容。

## 只读读取（研究用，参考 A7C2 的 Jiritsu 文件命令）

主机侧新增 src/a6700win/dump.py、src/a6700win/research.py、tools/probe_camera.py，
相机侧新增只读载荷 native/dump_range.c → native/dump_range.elf（15,600 字节，
sha256 040916c1...3a82，zig 0.13.0 / aarch64-freestanding + ld.lld 构建）。

- 已在本机验证（无相机）：协议编解码、分块循环、偏移/限长、零长度设备提示、
  载荷清单校验、/tmp/jiritsu/../.. 路径穿越拼装 —— tests/test_dump.py 10 个用例，
  全仓 pytest 75 passed / 1 skipped。
- 已在真机验证（2026-10-23/24，A6700 + 固件 2.00，全程只读）：

  | 对象 | 结果 |
  | --- | --- |
  | `/usr/lib/appFw.so` | 89,027,992 B，已 dump（`firmware/appFw-2.00.so`） |
  | `/dev/nflasha8`（CP 分区） | 67,108,864 B，17 s，≈3,772 KiB/s，sha256 `3bddcce3…57457dcc` |
  | `/dev/nflasha5`（WBI） | 314,572,800 B，82 s，≈3,746 KiB/s，sha256 `56e0e220…4eecb2ab` |
  | 其余 11 个分区 | 全部可读（两轮全分区 dump 已做，镜像在 `firmware/parts/`） |
  | 长读取后的 `STOP_SENSER` | 每轮都发出并确认，相机正常回到 MSC（`0x0E76`） |

  `/dev/nflasha15`（749,731,840 B，cramfs + gzip）只在开头 4 MB 上做过 peek，未做全量 dump；
  `appFw.so` 是通过读文件 `/usr/lib/appFw.so` 取得的，不依赖分区 dump。
  分区表共 14 个可 stat 的 nflashaN（见 `FIRMWARE-MAP.md` §1），上表 2 + 11 = 13 个做过完整 dump。
- 风险边界：载荷只以 O_RDONLY 打开文件，源码中没有 pwrite64 调用路径；
  主机侧只发 SELECT/READ 与 SET_FILE/EXECUTE，不发送写入器。

## CP 单元读写（研究用，路线 C）

- 读：`tools/cp_read.py` —— pFunc `0x40` + `0x603/0x40` + `struct('<II', key, 1)`，按 `0x8000` 分块，
  结束包（`0x200` 读、timeout 1000）按 A7C2 的语义处理。真机读到单元 `0x02a40001`（8,192 B，
  非零 2,815，sha256 `91d5e040…c066c`）与 `0x02a4000d`（28,672 B，非零 8,752，
  sha256 `64ceb9aa…d9b209`）；`tools/cp_survey.py` 又把 19 个单元全部读出。
- 写：`tools/cp_write.py` / `tools/cp_patch.py`（`0x603/0x41`）。写入前自动留 `.orig`，写完立刻回读比对，
  每次结果都是「回读一致 ✅」。
- 关键行为：CP 是**活的 RAM** —— 发 `STOP_SENSER`、拔插 USB、重新枚举回 `0x0E76` 之后内容仍然保留，
  只有真正掉电（关机 / 取电池）才回原厂。因此所有探测都不必写回，关机即恢复。
- 已用这条通路完成的观测（详见 `FL2-ROUTE.md`）：19 个单元批量读取；全部色度归零 → 所有外观变灰；
  槽 5/6/8/9 分别归零或放大 → 定位到 VV2 / PT / FL / SE；矩阵槽归零 → 只影响饱和度。
- 未验证：CP 写在大块（28,672 B）上的失败语义与重试边界；两个颜色单元之外的写路径。

## 0.3.1 写入失败的根因与修复（2026-10-24）

用户报告：解锁／关闭在 0.3.1 上报 `Request changes bytes outside available catalog-owned fields`，
状态 `uncertain`、`写操作：是`。

根因（离线复现，未连接相机）：0.3.1 的结构守卫豁免把 `inspect_sectors()` 的输入换成
「时间戳清零」的副本，上游又用这份副本生成写入目标 `after`；`before` 是相机原始字节。
`device_protocol.request()` 用只允许改目录字段的掩码逐字节复核，9 个守卫扇区里
每个 inode 的 12 字节时间戳被判成越界修改，整单在发 USB 之前被拒。
复现脚本：`.data/repro_guard_write.py`（不在仓库内）。

修复：归一化只用于比对，返回前把时间戳按相机原值补回 `after`（`guards.restore_volatile()`）。
新增回归用例 `test_write_target_matches_camera_timestamps`：用真实 profile 与真实
`request()` 跑一次 `unlock` 目标校验，回到 0.3.1 的实现会直接抛错。

影响面：只读检查、功能状态备份、备份恢复不走这条路径，未受影响；失败时相机没有收到任何
USB 数据（`request()` 在 `backend.write()` 内部、发 USB 之前抛错），功能状态未变。

未验证：修复后的真实写入。0.3.1 起没有做过实机写入，0.3.2 的解锁／关闭需要在真机上重新验收
一次（`status=completed` + 独立回读 + 重启后状态保持）才能说这条路径恢复。

## 菜单文字写入与还原（2026-10-25 真机，已闭环）

真机结论（A6700 · 固件 2.00）：

0. **写入成功并持久**（16:47 写入 official 方案）：`PT→Classic Chrome`、`NT→Classic Neg.`、
   `VV→Positive Film`、`VV2→Negative Film`，共 8 条记录；145,612 → 145,708 B（+96），
   分 5 块写完再整份回读，`sha256 9fd0bb497171`、`kind=renamed`、四条 `installed`。
   用户关机开机后菜单四个槽位分别显示这四个英文名，**重启后再读文件仍是 `9fd0bb49`** →
   `/usr` 上的 ext2 写入是一写就持久的（跟 CP 那种「内存 + 关机落盘」不是一回事）。
   随后 `restore()` 走出厂基线：`mode=baseline`、145,612 B、`sha fe263360c15b5530`、四条 `factory`。
1. **还原成功**：一次会话内 `truncate(145,708 → 145,612)` + 写 5 块 + 整份回读，
   得到 `mode=baseline bytes=145612 sha=fe263360c15b5530 kind=factory`，四条外观 state 全部 `factory`。
2. **写入路径的坑（已修）**：grow 场景（145,612 → 145,708）先分块写再截断会失败——
   最后一块落在原长度之外，载荷回 `状态 12（范围超出文件长度）`；正确顺序是**先 `ftruncate` 扩到目标长度再覆盖写**。
   修在 `src/a6700win/looknames.py` 的 `_write_blob()`。
3. **两次服务会话之间必须冷却**：同一次插线里隔几秒开第二个会话，认证能过但随后 USB 端点必掉
   （`[Errno 32] Pipe error` / `[Errno 19] No such device`，相机 PID 在 0x096F / 0x0E76 之间反复跳），
   文件会停成「前半新、后半零」的撕裂状态。间隔 50–60 秒再连则稳定。
   修在 `src/a6700win/cp.py` 的 `SESSION_GAP`（默认 50 s，可用 `POWERFUL6700_SESSION_GAP` 覆盖）。
4. 端点坏掉之后只能**物理拔插**或关机重启才能恢复；`_recover_service_mode` 救不回来
   （PID 停在 0x096F 时会报 `service-mode device did not appear (expected 0x0336)`）。

## CP 色度还原与「关机等待」实测（2026-10-25 真机）

- 事故现场：菜单文字改回之后用户发现「滤镜没回去」。诊断：CP 单元 `0x02A40001` 与出厂副本
  `72d3da868cc0` 差 **57 字节**（bank 1 VV 23 B、bank 4 NT 2 B、bank 6 PT 3 B、bank 14 VV2 29 B），
  `/setting/BACKUP.BIN` @0x1B2140 的副本与内存完全相同（`b0cab23b`）——**文字在 `/usr`、颜色在 CP 单元，两处独立坏**。
- 写回 8192 字节整单元 → 回读 `72d3da86…` 一致；但**关机后立刻开机，内存与 BACKUP 都退回 `b0cab23b`**。
- 重做一次：写内存出厂值 → **正常关机等 7 分钟再开机** → 内存与 BACKUP 两处都是 `72d3da86…`，
  整单元 0 字节差异。→ 落盘发生在关机流程里且需要时间，**等满 1 分钟是必要条件**，
  断电或立刻开机会丢。界面与文档都按这个措辞写。

## 一次写入（颜色 + 名字）：本地编排回归（0.3.5，真机未跑）

`tests/test_bundle.py`（7 个用例，假实现替掉 `looks` / `looknames`，不接触相机）：

- 顺序：`bundle.apply()` 先调 `looks.apply` 再调 `looknames.apply`，**是两次独立调用**（对应两次 USB 会话），
  报告的 `steps` 为 `["colors", "names"]`；
- 预设：不传 `preset` 时用 `looknames.load_preset()`，并原样传给菜单文字那一段；
- 还原：`bundle.restore()` 走 `looks.restore` + `looknames.restore`；
- 颜色段失败 → 抛 `BundleError`，文案含「菜单文字一个字都没动」，且 `looknames.apply` 未被调用；
- 文字段失败 → 不抛，`report["steps"] == ["colors"]`、`wrote=True`、`error` 里写明
  「颜色已经写进相机了…可以单独点『还原本页外观』回滚」；
- `bundle.summary()` 两段都有结果时给「颜色：CC=已写入」与「菜单文字：改了 1 条记录（官方原名）」，
  只有颜色时不出现菜单文字行。

真机上还要验的四条（顺序同上）：① 一次写入后关机重启，颜色与名字都要对；② 再点一次同一按钮应报
「已是目标状态，没有写入」；③ 一次还原后颜色回 `72d3da86…`、文字回 145,612 / `fe263360…`；
④ 中途拔线应停在可解释的失败上（文字段失败要保留颜色并提示单独回滚）。

## 菜单文字：离线回归（0.3.3 之前）

已在无相机的条件下确认的：

- 出厂资源 `string_simplifiedchinese_f.uxc`：145,612 B，
  sha256 `fe263360c15b5530508bf7b098c96ec39cd4c38536b23653d15e6ea977b80e42`（2026-10-23 备份）；
  解码得 4,785 条记录，四条目标外观各有两条记录（PT `0x021C6654`/`0x021C6F8B`、
  NT `0x021C6434`/`0x021C7002`、VV `0x021C687B`/`0x021C6F80`、VV2 `0x021C689A`/`0x021C6F4D`）。
- 离线改名 8 条记录 → 文件 145,676 B（+64），二次执行幂等（`changes == []`、字节不变）；
  把四条改回短名后重新得到 145,612 B 且 sha256 与出厂逐字节相同。
  **这是实测行为，不是承诺**：无损回滚依赖写入前存下的整份基线，界面文案照这个说。
- 写入路径的假设备回归（`tests/test_looknames.py` 的 `_FakeDevice`）：apply → 设备字节等于
  `rename_all` 结果、写前自动落基线；二次 apply 不写盘；restore 走 `mode=baseline` 后设备字节
  逐字节回原样；无基线时走 `mode=labels` 且字节恰好回原样。`pytest tests -q` → 86 passed / 1 skipped。
- 冻结包：`dist/Powerful6700/Powerful6700.exe`（0.3.3）自检九项 OK，`--render-pages` 能构造
  含「菜单文字」卡片的外观页；PYZ 里 `a6700win.looknames` / `a6700win.uxc` 均存在，
  且两个模块的字节码里都能找到 `labels-factory` 分支。

未验证（真机，必须接相机）：

1. ~~中文方案在菜单里的实际显示宽度~~ —— 2026-10-25 真机已跑：写入 145,692 B（8 条记录），
   用户确认「文字没问题」，四个槽位显示 富士CC / 富士NC / 理光正片 / 理光负片；
2. 断电正好落在 `write_block` 中间时，文件停在半截（ext2 没有事务）。这一条**已经真实发生过一次**
   （2026-10-25 16:0x，会话间隔太短导致端点掉线），靠出厂基线整份写回修好了；
   程序现在的对策是「写前自动存基线 + 还原时整份覆盖」，不是「永不发生」。

## 只读检查报 `状态：04000010`（2026-10-25 排障，未定位到可复现条件）

- 现象：界面「只读检查」失败，错误 `文件写入或载荷执行失败，状态：04000010`，
  `写操作=否`、`设备访问=是`。这串来自 `usb/backend.py:184` 的 `_file`，即相机对
  `0x4010`（配置）或 `0x4007`（载荷）暂存返回了 4 字节状态，原始字节 `04 00 00 10`
  → 小端 u32 = **0x10000004**，与已知的 `0x10000006`（文件不存在）同族。
- 源码侧复现不出来：同一台相机、同一份代码，`.data/scratch/live_inspect_steps.py` 逐步发
  `0x4010` / `0x4007` 均返回 `00000000`；`live_session_reuse.py` 在**一个会话里连读 3 次**
  也全部成功（含闲置 90 秒后再读）；`.data/scratch/live_gui_inspect.py` 走完整 GUI 路径
  （`check_environment → acknowledge_notice → begin_preparation → confirm_preparation →
  reserve("inspect") → run_reserved`）得到「检查完成：预计修改 0 字节／0 个扇区」。
  → 当时相机刚从多次掉线里恢复，判断是一次性的设备侧拒绝，不是代码分支问题。
- 本版做的事（不是「修好」，是让它下次能被看懂）：`_windows_backend_file` 现在报出
  **是哪一步**（`配置写入（SET_FILE2）` / `载荷写入（SET_FILE）`）、file_id、状态字与含义，
  并给出恢复步骤（拔线 → 关机 → 取电池约 1 分钟 → 装回 → 重连 MSC）。
- 观察到的旁证：`0x10000004` 出现的那段时间，正是同一天多次「同会话写 CP + 写 145 KB 文件」
  掉线之后；取电池冷启 1 分钟之后同类写入一次成功。
