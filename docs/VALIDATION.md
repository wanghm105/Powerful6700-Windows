# 验证边界

## 已在本机验证（无相机）

- `.venv`（Python 3.12.3）里 `import usb / libusb_package / PySide6 / PyInstaller` 全部可用；
- `pytest tests -q` → **37 passed / 1 skipped**（SetupAPI 解析与枚举、wdi 参数与白名单、补丁幂等与
  载荷严格性、Windows 兼容层的设备锁/独占保存/二进制写/异常放锁、六个页面无头渲染）；
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

1. **失败回滚**（`rolled-back` / `recovery-required`）与写入中断（拔线、相机睡眠）时的行为；
2. **功能状态恢复**（`.a6700backup` 写回、只写回清单字段的稀疏恢复）从未执行过；
3. `0x047D` 这一初始 PID（MSC 的另一种枚举）未验证，本机只见到 `0x0E76`；
4. 多台索尼设备同时连接时的唯一性报错路径；
5. 提权失败、非管理员启动时的 Windows 提示链路（目前只验证了管理员路径）；
6. macOS / Linux 行为（本端口只为 Windows 增加适配，未回归原平台）。

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
  全仓 pytest 37 passed / 1 skipped。
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
