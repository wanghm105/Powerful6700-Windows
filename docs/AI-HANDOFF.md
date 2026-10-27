# AI-HANDOFF · 交接现场

> **用法**：换一个对话、换一个人、或者上下文爆了，**只看这一个文件**就能接着干。
> **规则**：每完成一小步（一次真机写入、一次构建、一次结论），**先改这里再往下走**；末尾「更新记录」按时间追加一行。
> **最后更新**：2026-10-27 16:10（Australia/Brisbane）

---

## 目录

0. [2026-10-26 · 0.3.8 现阶段交接](#0-2026-10-26--038-现阶段交接最新先读这一节)
1. [项目是什么](#1-项目是什么)
2. [一句话现状](#2-一句话现状)
3. [工程结构与环境](#3-工程结构与环境)
4. [已验证能力清单](#4-已验证能力清单)
5. [Windows 侧技术路线（为什么这么写）](#5-windows-侧技术路线为什么这么写)
6. [相机侧协议与物理基础](#6-相机侧协议与物理基础)
7. [颜色子系统（CP 单元）](#7-颜色子系统cp-单元)
8. [颜色拟合现状（正在做的事）](#8-颜色拟合现状正在做的事)
9. [菜单文字子系统（已完成）](#9-菜单文字子系统已完成)
10. [当前真机状态（接手先复核）](#10-当前真机状态接手先复核)
11. [踩过的坑（照抄，别重犯）](#11-踩过的坑照抄别重犯)
12. [待办与下一步的具体做法](#12-待办与下一步的具体做法)
13. [已知限制与能力边界](#13-已知限制与能力边界)
14. [历史调查结论（省得重做）](#14-历史调查结论省得重做)
15. [文件地图](#15-文件地图)
16. [未提交改动](#16-未提交改动)
17. [同代项目调研（A7C2 / A7R5）](#17-同代项目调研a7c2--a7r5)
18. [同机型项目：Himpq/FireHydrant（A6700 侧）](#18-同机型项目himpqfirehydranta6700-侧)
19. [更新记录](#19-更新记录)
20. [2026-10-26 · FL2/FL3 真机战役与炸机](#20-2026-10-26--fl2fl3-真机战役与炸机最新接手先读这一节)
21. [2026-10-26 · 0.3.8 诊断层](#21-2026-10-26--038-诊断层blocked-为什么只有一句话)
22. [0.3.9-probe1 取证版](#22-2026-10-26-晚--039-probe1-取证版单文件-exe已发布)·[probe2](#23-039-probe2一次会话试完三种可能未发布截至本文件写入时)·[probe5](#24-039-probe5get_version-0x400d-与-mount-0x4002-两个新旋钮未发布2026-10-27)

---

## 0. 2026-10-26 · 0.3.8 已发布；晚上补发了 0.3.9-probe1 取证版（最新，先读这一节）

> 这一节是权威现状：只写「现在是什么状态、还差什么、怎么验」。历史调查见 §14 / §19 / §20；§0.3 里的「口径沿革」只解释为什么这么写，不是待办。

### 0.1 一句话

0.3.8 已经发出去了：Release `v0.3.8-win.1`（id `423755708`，2026-10-26T00:39:36Z，draft / prerelease 都是 false），资产 `Powerful6700-Windows-x64.zip` 47,983,337 字节 / sha256 `e1f6449fbcb802bf983083389b022472f685d2e0413e9a68902ee6ae1337e913`；把资产整个下载回来重算过 sha256，一致。

2026-10-26 晚上又发了一个**取证版**（不是正式版）：Release `v0.3.9-probe1-win.1`（Pre-release，draft false，tag 指向 `4a3e30c`），唯一资产 `Powerful6700-0.3.9-probe1.exe` 48,066,148 字节 / sha256 `1919ab5e373b01dc4fdbbe9ab11f3b53dfbd969fe5b8c907c1c0c49f7cecc013`（onefile，单个 exe 双击就能用）。它只干一件事：把界面日志写进文件、把「清相机临时文件」的结果逐条说出来，用来抓 `0x10000004` 的现场。0.3.8 仍是 Latest，zip 资产一字未改；`src/a6700win/version.py` 现在是 `0.3.9-probe1`，**README / 必读 / zip 仍是 0.3.8，故意不重打包**（所以 `tools/check_publish.py` 现在会报版本不一致，属预期）。细节见 §22。

git 里**只提交了 README**：`3845574` → `cd09525` → `4a3e30c`，`HEAD == origin/main == 4a3e30c`。0.3.8 的代码与其余文档仍在工作树里、未提交未 push（三批，见 §0.4），所以 tag 指向的源码包里 `src/a6700win/version.py` 还是 `0.3.7`——Release 正文末段专门写明了这件事。**别为了「让源码包对上」单独提交 `version.py`**，那会把三批改动切得更碎。

`docs/PUBLISH-RISK-REVIEW.md` 的 P0 已全部落到工作树：一次写入加锁、首屏两条风险须知、`0x10000004` 自愈、界面文案口语化、**写入前确认框摊开「分区／字节／回滚方式」**、**失败结果页三步自救**（逐项见 §0.6）。README 已整篇换版（本地 37,079 B / 382 行 / LF；`4a3e30c` 里那份是 37,098 B，差的就是本地待提交的那一行，见 §0.8）。

**相机还是一块砖，正在等硬件恢复**：不许 `--inspect-once`、不许 `cp.*` / `looks` / `flash` / `looknames` 的读写、不许 GUI 的「真实设备模式」。全部验收只走离线：`pytest` / `--render-pages` / `tools/check_publish.py`。

### 0.2 仓库与发布面

- `HEAD = 4a3e30c`（`docs: README 验证状态补记机友实测，包校验值同步到必读新版`），与 `origin/main` 同步；上一版的 `73e36a3` 已经是旧基线。
- 已发 Release（新 → 旧）：`v0.3.8-win.1`（0.3.8，47,983,337 B，`e1f6449f…`）、`v0.3.7-win.1`（tag → `3e3e676`，47,925,929 B，`6dd1c13b…`）、`v0.3.4-win.1`、`v0.3.2-win.1`、`v0.3.1-win.0`、`v0.2.0-win.1`。
- 取证版 Release：`v0.3.9-probe1-win.1`（0.3.9-probe1，Pre-release，单 exe 48,066,148 B，`1919ab5e…`），tag 同样指向 `4a3e30c`。脚本与文案：`.data/tmp/publish_probe.sh` / `.data/tmp/verify_publish.sh`、`.data/release-body-039-probe1.md`、`.data/announcement-039-probe1.md`。
- **源码包版本号与二进制不一致是故意的**：tag `v0.3.8-win.1` → `4a3e30c`，那个提交里 `version.py` 仍是 `0.3.7`（代码批没提交）。Release 正文末段原文：「源码包说明：这次只更新了二进制和文档，源码包里 version.py 仍是 0.3.7，下面这个 zip 是 0.3.8。」
- 0.3.8 Release 标题 `0.3.8 · 软件界面修复`（用户定的九个字；我起的「被拦下时说清差在哪」被否了）。正文改了六轮，最终稿备份在 `.data/tmp/release-0.3.8-final.md`，要点：只动界面与提示、写进相机的东西一字节没变、已有多位机友刷机成功但不能 100% 保证、页面 SHA-256、适用机型、源码包说明、`★写入过程中不能拔线、不能断电、不能关相机★`。正文里**故意没有**「下载：GitHub Releases」「项目名称」「国内打不开代下」这些行（用户 m01602 要求删）。
- 0.3.7 的「一次写入」确实是 `Primary`、无锁、无确认（已核对 `3e3e676` 的 `src/a6700win/gui/looks_page.py`）——0.3.8 的发布理由就是这个。
- **Issue #1「只读检查失败」仍 open**（yianZHK，2026-10-25T17:24Z，3 条评论）。我按备稿发过两次回复（id `6405654119` / `6405663820`），**两次都被删了**；用户自己回了一条「新版本已修复，下载最新版0.3.8」。→ **这个 issue 不要再回**，也不要再发置顶 issue（用户 m01524 / m01566 明确不做）。
- **不做**（用户已明确）：给 0.3.7 Release 正文加「那版按钮裸奔」的提醒、发置顶 issue、隐藏仓库。

### 0.3 这轮落地了什么（按文件）

**A. 首屏风险声明（`src/a6700win/notices.py`，新文件仍未跟踪）**
- `NOTICE_SECTIONS: tuple[dict, ...]` 两条 risk：`id="internal-storage"` 标题「改的是相机机身里的东西，不是 SD 卡」、`id="power-cycle"` 标题「写完要拔线、关机、等满 60 秒再开机」；常量 `HARDWARE_RECOVERY_URL = "https://github.com/xyzhangxin/sony-a6700-powerful/blob/main/硬件说明.md"`。
- `src/a6700win/gui/pages.py`：`NoticePage.render` 里 `sections = list(NOTICE_SECTIONS) + list(notice.get("sections", []))`，壳层两条排在 vendor 五条之前。
- **没有动** `third_party/a6700_unlock/notice.py`（一字节没改）：动它会改 `catalog_sha256`，让用户已有的 `.a6700backup` 全部失效。理由写在 `notices.py` 的模块 docstring 里。

**B. 「一次做完（颜色 + 名字）」加锁（`src/a6700win/gui/looks_page.py`）**
- 按钮由 `Primary` 改 `Ghost` 且默认 `setEnabled(False)`；勾 `self.bundle_ack` 才解锁，`_bundle_apply` 每写完一次就 `setChecked(False)` 重新上锁。勾选文案：「我知道这一步会改相机固件里的文件，写入途中不能拔线、断电、关相机；被打断可能变砖，仍然要解锁」。
- 文案里不再出现「实验性 / 未在真机验收 / 未验证」（用户 m00581 / m00790 / m00817 三次要求），功能表与验证状态表都只写机制和「中途不能拔线、断电、关相机」。
- 「名字用哪一套」（英文原名 / 中文简称）选择器搬到最上面「这一页改什么」卡里，控件名仍是 `self.names_preset_box` / `self.preset_hint`；选择落在数据目录 `looknames/settings.json`（`looknames.load_preset` / `save_preset` / `preset_labels`，`DEFAULT_PRESET = "official"`）。

**C. `0x10000004` 自愈（`src/a6700win/patches.py`）**
- `_clear_stale_temp(backend, progress=None)` 删成功时打日志「已清掉相机上一次会话留下的临时文件：%s」。
- `_windows_backend_file`：① `command == 0x4010` 且本 backend 实例没清过 → 先删 `/tmp/jiritsu/tmmc.jit`、`/tmp/jiritsu/tmmc.dat`（`_a6700win_temp_cleared` 标记，每会话一次；`physical.py` 每会话新建 backend）；② 首写被拒且状态 `0x10000004` → **无条件**再清一次并重发一次（旧逻辑是「删到了才重试」，截图那次一个文件都没删掉，所以一次都没重试，这就是 0.3.7 没兜住的原因）；③ 仍失败 → 首句「清理临时文件后仍被拒，这次会话本身没恢复干净；」，尾部讲「重复重启变砖」+ 上游硬件说明链接。
- 触发点：只读检查第一步 `src/a6700win/dump.py:175` 的 `backend._file(0x4010, 0, config)`；全仓发 `0x4010` 的只有 `dump.py:175` 与 `flash.py:154`，都走 `patches.install()`（`src/a6700win/patches.py:430`）换上的 `backend.UsbBackend._file`，没有绕过口。

**D. 全站界面文案口语化（8 个文件，461+/229-）**
- 口径：界面解释、卡片正文、按钮、状态标签给外行看，技术细节砍掉（bank 编号、`0x` 地址、字节数、RMS、`/usr`）；**报错与进度日志可以继续技术**（远程判读要用）；**声明/警示必须严谨**（事故、版本、日期、「还原也要先能认成海量存储器（MSC）」这一层不能弱化）；胶片名保留英文 CC / NC / PF / NF；只做中文。
- 涉及 `notices.py`、`gui/looks_page.py`、`gui/pages.py`、`gui/driver_page.py`、`gui/about_page.py`、`bundle.py`、`gui/widgets.py`，测试断言同步改 `tests/test_gui.py` / `tests/test_bundle.py`。写法参考 `refs/a7c2-fl23`（一句一个事实，先说会发生什么再说限制，界面元素名用「」包起来，按钮一律动词短语）。

**E. 功能管理页（`src/a6700win/gui/pages.py`）**
- 「功能状态备份」卡右下角新增「打开备份目录」按钮（Ghost）：先 `mkdir` 再 `window.open_url(QUrl.fromLocalFile(...).toString())`，日志写完整路径，失败弹通知。

**F. 版本**
- `src/a6700win/version.py`：`APP_VERSION = "0.3.8"`（只在工作树，未提交）。

**G. 「重复重启变砖」措辞 + 上游硬件救砖链接（四个入口）**
- `src/a6700win/notices.py`：`internal-storage` 的 body 讲「可能连不上电脑，或者重复重启变砖……只能用硬件办法：拿一块 RP2040 Pico 和一块 USB-C 测试板，按上游接线图接好」，并给该 section 加 `source_url: HARDWARE_RECOVERY_URL` / `link_text: 硬件恢复说明（救砖）↗`。
- `src/a6700win/gui/widgets.py:287`：`DocLink(str(section.get("link_text") or "查看官方说明 ↗"))`——每条风险/范围都能自带链接文字。
- `src/a6700win/gui/about_page.py:33`：关于页「硬件说明（救砖）↗」→ `self.app.open_url(HARDWARE_RECOVERY_URL)`。
- `src/a6700win/patches.py:279`：写配置仍被拒的报错尾部同样挂这个链接。
- 测试坑：**PySide6 的 `QToolButton.clicked` 不带参数**，`clicked.emit(False)` 会 `TypeError: clicked() only accepts 0 argument(s)`；`tests/test_patches.py:260` 的断言由「反复重启」改成「变砖」，并新增 `test_notice_links_the_upstream_hardware_recovery_guide`。
- 上游内容（只读 curl 核实）：Pico 用数据线接电脑，既做串口又供 5V；`VBUS`（物理 40 脚）→ 测试板 VBUS；`VBUS` 各串 56kΩ → A5/CC1、B5/CC2；`GND` → 信号 GND；`GP28` 串 470Ω → A 侧 `D−`；加载完先拔测试板再移数据线到相机；**不含 Pico 2 的验证记录**。

**H. 写入前确认框摊开「分区／字节／回滚方式」（`gui/looks_page.py`，P0-A）**
- 常量 `looks_page.py:37-41`：`COLOR_RECORDS = 4`（只改 bank 1/4/6/14 各一条）、`COLOR_RECORD_BYTES = looks_mod.STRIDE`（64）、`COLOR_UNIT_BYTES = cp.CP_KEYS[cp.CHROMA_UNIT]`（0x2000 = 8,192）、`COLOR_PERSIST = "/setting/BACKUP.BIN"`。
- `def _write_targets(self, action: str) -> list[str]`（`looks_page.py:497`）：`both = action.startswith("一次做完")`；`wants_color = both or action == "写入颜色"`；名字字节数取 `int((self.names_report or {}).get("bytes") or 0)`，取不到写「整份约 14.5 万字节」。
- `_confirm_write`（`looks_page.py:518`）正文 = 动作名 + `targets` 三行（前缀「· 」）+ 空行 +「中断后果：写到一半被打断，相机可能连不上电脑、重复重启变砖，只能拔电池等满 1 分钟再试；仍然黑屏就只剩硬件恢复。」+「写入过程中绝对不能做：{WRITE_RULES}。」+「准备好了再点「知道了，开始」。」；调用点 `looks_page.py:583` / `:624` / `:681`；默认按钮是「先不写」，取消只 log「先不写：这次什么都没动。」。`WRITE_RULES = "拔数据线、关相机、拔电池或断电、让电脑睡眠 / 休眠 / 关机、切走 USB 模式"`。
- 实测文案：颜色 →「写哪里：相机机身里的颜色参数区，不是 SD 卡；关机时相机自己把它写进 /setting/BACKUP.BIN」「多少字节：改 4 条记录、共 256 字节，整块 8,192 字节一起重写」「怎么回滚：同一页「还原颜色」把这 4 个外观逐字节写回出厂值，前提是相机还能开机、插上数据线还能被认成海量存储器（MSC）」；名字 →「写哪里：机身固件分区里的简体中文文字包 /usr/share/app/string_simplifiedchinese_f.uxc，不是 SD 卡」「多少字节：整份 145,612 字节，分块写入，写完逐块读回来核对」「怎么回滚：同一页「把名字改回去」，按本地存的出厂底稿整份写回，前提是底稿还在、相机还能开机、插上数据线还能被认成海量存储器（MSC）」；「一次做完」= 两套全列。
- **还原路径（还原颜色 / 把名字改回去 / 一次还原）故意不加弹窗**，只留这个事实，不写理由。

**I. 失败结果页三步自救（`gui/pages.py`，P0-B）**
- `ResultPage` 新增 `self.rescue_card = Card("先别急着重试")`（`pages.py:656-661`，紧跟 headline card，默认隐藏）；`render()` 空结果时隐藏（`pages.py:712`），正常结果在 `_render_issues` 之前调 `self._render_rescue(result)`（`pages.py:737`）。
- `RESCUE_STEPS`（`pages.py:741`）：拔掉数据线先别再插回去 / 取出电池等满 1 分钟以上再装回去 / 只装电池开机（别插线），能进菜单就说明救回来了，一直黑屏或反复重启就只剩硬件恢复。
- `_render_rescue`（`pages.py:747`）成功即隐藏；开头句按 `write_attempted` / `device_access` / 两者都没有分三种；`pages.py:764` 加粗「不要连续重试、不要反复插拔数据线——那会让相机更久连不上电脑，连海量存储器（MSC）都不出现。」；`self.rescue_link = DocLink("硬件说明（救砖）↗")`（`pages.py:769`）→ `lambda: self.app.open_url(HARDWARE_RECOVERY_URL)`。
- 测试：`tests/test_gui.py:193` `test_confirm_write_states_target_bytes_and_rollback`、`tests/test_gui.py:217` `test_failed_result_gives_three_step_rescue`；`_StubApp`（`tests/test_gui.py:93`）加 `confirm_texts` 记录每次弹窗正文，`confirm_write` 在 `:106`。

**J. README / 必读 / 免责声明（对外文案都在这两块）**
- README 已整篇换版并按 `refs/a7c2-fl23/README.zh-CN.md` 的章节与口吻重排（只有中文版）：顶部 `> [!WARNING]` 五段免责（免费开源的独立研究项目 / 免费提供·不收费，没有付费版、激活码或加密狗 / 严禁冒充官方或作者授权 / 风险自担·不保证恢复成功 / GPL-3.0-only 许可），`:62` 起是「FL2 与 FL3 为什么没有」独立章节，`:112`「还在做」列 FL2/FL3、电子快门自定义声音、CC 强度、蓝端颜色，`:114`「不做」只留机内 LUT 与已撤回的卡速/动态防抖。
- **许可段没有照抄 A7C2 的 PolyForm 非商用**：本项目 `LICENSE` 是 GNU GPL v3、`NOTICE` 首行 `SPDX-License-Identifier: GPL-3.0-only`，GPL 允许再分发，写「禁止商用」会自相矛盾。
- `docs/README-0.3.8.md` 是 README 的同源稿，必须与 `README.md` 逐字节一致（目前都是 37,079 B）。`packaging/必读.txt` 10,777 B / 144 行（LF）：免责与防骗段逐字保留，其余压缩成短句，免责下面有「手把手安装教程」小节——**它在压缩包里，改它就等于改包，必须重打包并换 sha256**。
- **口径沿革（一句话版，别退回旧写法）**：m00581 一次写入不用再提实验性 → m00658「真机未跑先不提」→ m00683「但这个版本得提一下，确实没在本机跑」→ m00743 / m00753「基于稳定版与既有检验，只改软件侧，写进相机的东西没动」→ m00790 / m00817 验证状态一律不写（只留操作提醒）→ m01311「说清楚本次改动与上一版在相机内文件上没有差别，已有多位机友刷机成功，只改界面可见文字与声明」。
- **这样写是有据的**：`git diff HEAD -- src/ third_party/` 只有 9 个 tracked 文件 + 2 个新文件（`notices.py`、`diagnostics.py`）；`looks.py` / `looknames.py` / `flash.py` / `cp.py` / `uxc.py` / `backup.py` 全部 UNCHANGED，`third_party/` 干净；`diagnostics.py` 里没有任何 `write_unit` / `write_block` / `_command(`；`patches.py` 只多了清 `/tmp/jiritsu` 残留再重发；`bundle.py` 纯文案。旧 `.a6700backup` 仍有效：`third_party/a6700_unlock/backup.py:257` 的 required 含 `tool_version`，但 `:288` 只比对 `profile_sha256` / `catalog_sha256`，`tool_version` 记录不比较。

### 0.4 工作树里混着的四批改动（提交时必须分开）

`git status` 现状（`HEAD = 4a3e30c`，未 commit、未 push）：

| 批次 | 文件 | 说明 |
|---|---|---|
| ① 文档批（另一批，`docs/` 下 13 篇） | `docs/AI-HANDOFF.md`、`ANNOUNCEMENT.md`、`BREAKTHROUGHS.md`、`CALIBRATION.md`、`CC-CN-PLAYBOOK.md`、`FEASIBILITY-FL23.md`、`FEATURES.md`、`FL2-ROUTE.md`、`LOOKS.md`、`PROGRESS.md`、`RELEASE-NOTES.md`、`ROADMAP.md`、`VALIDATION.md` | 只是文档；`README.md` 本地那一行（§0.8）可单独提交 |
| ② 诊断层批（另一个会话） | 新增 `src/a6700win/diagnostics.py`、`tests/test_diagnostics.py`；改 `gui/pages.py`（blocked 提示 + 结果页差异明细）、`gui/about_page.py`（导出诊断包）、`inspect_once.py` | 与 ③ **在 `gui/pages.py` / `about_page.py` 上交叉**，不能按文件挑，要 `git add -p` |
| ③ 本批（0.3.8） | 新增 `src/a6700win/notices.py`；改 `gui/looks_page.py`、`gui/pages.py`、`gui/driver_page.py`、`bundle.py`、`patches.py`、`version.py`、`gui/widgets.py`、`tests/test_gui.py`、`tests/test_bundle.py`、`tests/test_patches.py`、`tests/test_config_selfheal.py` | `notices.py` 与 `diagnostics.py` 都是**未跟踪的新文件**，别漏 `git add` |
| ④ 取证批（0.3.9-probe1，2026-10-26 晚） | 新增 `src/a6700win/runlog.py`、`tests/test_runlog.py`；改 `__main__.py`、`dump.py`、`patches.py`、`diagnostics.py`、`gui/widgets.py`、`version.py`、`tests/test_patches.py`、`tests/test_config_selfheal.py` | 只动读侧与日志，不碰 `0x4010` 写入语义；`version.py` 现在是 `0.3.9-probe1`（临时） |

- ` M README.md`：只有 §0.8 第 1 条那一行，未提交未 push。
- ` M packaging/必读.txt`：**是 tracked 文件**（0.3.2 那版就在库里），现在这份 0.3.8 的重写版未提交；它只随 zip 发给用户，是否单独提交看用户，不提交也能发布。
- `src/a6700win/version.py` 目前是 `0.3.9-probe1`（取证版专号）。下次正式发版要先改成正式版本号，再重打包 zip 并重算 sha256。
- 未跟踪的文档：`docs/PUBLISH-RISK-REVIEW.md`（本轮依据）、`docs/README-0.3.8.md`（README 同源稿）、`docs/DIAGNOSTICS.md`、`docs/FTP-KNOWN-ISSUE.md`、`docs/FL23-FULL-RECORD.md`。
- 未跟踪的工具：`tools/` 下 `cp_*` / `fl23_*` / `uxc_audit.py` / `uxc_restore_factory.py` 一批写机脚本（0.3.8 不发，P1）。
- **不要提交的垃圾**：`GitHub端下载/`（下载的发布包）、`.local/`、`README.md.fmt`、`README.md.new`。

### 0.5 验收怎么跑（照抄）

```powershell
cd '<repo>'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='<repo>\src'
$env:QT_QPA_FONTDIR='C:/Windows/Fonts'
$env:TMP='<repo>\.data\tmp\p'; $env:TEMP=$env:TMP; $env:TMPDIR=$env:TMP   # 目录必须先存在
.\venv\Scripts\python.exe .data\tmp\run_pytest.py                     # 124 passed / 1 skipped
.\venv\Scripts\python.exe -m a6700win --render-pages .data\tmp\shots     # 7 张 PNG，phase=notice、ready=true
.\venv\Scripts\python.exe tools\check_publish.py                        # 干净（注意：version.py 现为 0.3.9-probe1，会报版本不一致，属预期）
```

坑（都踩过）：
1. 不设 `TMP` 会直接报 `FileNotFoundError: [Errno 2] No usable temporary directory found`——这台机器默认临时目录不可用；`TMP` 指向的目录**本身要先建好**（跑冻结包的 exe 也一样）。
2. 不设 `PYTHONIOENCODING=utf-8`，中文日志在 GBK 控制台是乱码。
3. `--render-pages` 必须带目录参数，且要 `PYTHONPATH=src`。
4. 测试里凡会弹 `QMessageBox` 的路径，靠 `_StubApp.confirm_write` 拦（`tests/test_gui.py`），别在用例里真弹窗。
5. **`pytest` 会在全部通过后卡在解释器退出**（Qt teardown，本机稳定复现）：直接 `python -m pytest` 会被外层 timeout 杀掉（exit 124），屏幕全绿也不算数。用 `.data/tmp/run_pytest.py` 包装才拿得到真实结果——内容是 `pytest.main(["-q","-p","no:cacheprovider"] + sys.argv[1:])` → `faulthandler.cancel_dump_traceback_later()` → `os._exit(code)`。别为让它自己退出去改产品代码。
6. 改 `README.md` 只能用系统 `python`（`C:\SoftWare\Python`）：`.venv` 的 python 对该文件稳定 `PermissionError: [Errno 13] Permission denied`；脚本用 `open(p,"r+b")` + `truncate()` + 重试。判断换行只读二进制（`open(p,"rb")` 数 `\r\n` 与裸 `\n`），CRLF 文件插行必须 `chr(13)+chr(10)`。

### 0.6 `PUBLISH-RISK-REVIEW` 的 P0 逐项状态

| P0 项 | 状态 |
|---|---|
| README「不做」列表事实错误（FL2/FL3） | ✅ 已整篇换版：`:62` 起独立章节讲「A7C2 固件里自带、只是锁着；A6700 固件里没有这一层」，`:114`「不做」里已删掉 FL2/FL3 |
| README「开始前必读」变砖披露 + 「还原要先能认成 MSC」 | ✅ `README.md:130` 起整节 + `README.md:41` 那句「还原这条路，本身要先连得上相机——插上数据线，电脑得能认出它是海量存储器（MSC）」 |
| README「验证状态」写「一次写入未真机验收」 | ✅ 0.3.8 起按 m00581 / m00790 / m00817 收敛：既不标「实验性／未在真机验收」，也不写验证状态，只提醒「中途不能拔线、断电、关相机」（`README.md:107` 功能表、`:315` 验证状态表） |
| 「一次写入」按钮加锁或移除 | ✅ Ghost + 默认禁用 + 确认勾选 + 写入前弹窗 + 每次写完重新上锁（§0.3-B / H） |
| `notices.py` 两条常驻提示 + `widgets.py` + `docs/FTP-KNOWN-ISSUE.md` 一起发 | ✅ 前两件已在工作树并随 0.3.8 二进制发布；`docs/FTP-KNOWN-ISSUE.md` 仍是未跟踪文档，下次提交文档批时带上（二进制已发，不影响用户） |
| 首屏「操作前须知」增两条 | ✅ §0.3-A |
| 每次写入前弹确认框，列出「写哪个分区 / 多少字节 / 回滚方式 / 中断后果」 | ✅ `gui/looks_page.py:518` `_confirm_write` + `:497` `_write_targets`；默认「先不写」；还原类故意不加（§0.3-H） |
| 失败结果页给三步自救 | ✅ `gui/pages.py:747` `_render_rescue`：卡片「先别急着重试」+ 拔线 / 取电池等满 1 分钟 / 只装电池开机 + 加粗「不要连续重试」+ 硬件说明链接（§0.3-I） |

P0-C 的「`tools/experimental/` + CI」两条仍是 P1，0.3.8 没做。

### 0.7 群里那个 `0x10000004` 到底解决没有

- 现场：0.3.7 只读检查走到「已具备管理员权限，直接安装驱动…」停住，结果页 `error / 未能完成检查`，正文「相机拒绝了配置写入（SET_FILE2）（file_id=0，状态 0x10000004…）」，之后相机「请检查所连接的设备」→ 开机循环。
- 链条：服务模式 `0x0336` 出现 → 现场装 WinUSB 驱动（`wdi-simple` 会重启该 PnP 设备）→ 紧接着第一条 `0x4010` 配置写入被拒 `0x10000004` → 相机留在服务模式 → 用户重插重试后进入重启循环。
- 0.3.7 为什么没兜住：旧逻辑 `removed = _clear_stale_temp(...)`，`if removed:` 才重试；那次 `remove()` 对不存在的文件返回 `False`，一条都没删 → 一次都没重试。现在改成「先清一次再写 + 被拒后无条件清一次并重发一次」（§0.3-C）。
- 给用户的判读口径：修好了 → 进度框出现「相机拒绝了第一次配置写入，清掉临时文件后重试成功，继续。」或先出现「已清掉相机上一次会话留下的临时文件：…」；没修好 → 首句「…清理临时文件后仍被拒，这次会话本身没恢复干净；」，说明不是残留文件，下一步要改成「退出服务模式 → 重新认证 → 再写」。
- 有没有真机验过：**没有**（相机是砖）。这是「针对性修复 + 逻辑自审」，不是「已验证」。
- **2026-10-26 晚：发了取证版去抓现场**（`v0.3.9-probe1-win.1`）。它把界面日志落盘（`data_root()/logs/run-*.log`）并把清理结果逐条打印，所以接下来的反馈可以分辨四件事：
  - 一句 `清理临时文件` 都没有 → 用户跑的不是这一版（看日志头有没有 `Powerful6700Win 0.3.9-probe1`），或日志没导出；
  - `清理临时文件失败：libJit.so：Jiritsu 状态 0x10000006` → 相机上本来没有这个文件，「残留」假设不成立；
  - `清理临时文件失败：tmmc.jit：Jiritsu 状态 0x10000004` → 连删都不让删，服务会话本身是脏的，该往「重新认证」方向查；
  - `已清掉相机上一次会话留下的临时文件：libJit.so` → 真删掉过，看这次有没有因此通过。
- **libJit.so 是推断，不是结论**：`/tmp/jiritsu` 在独立 flash 分区、断电不消失（§11）；遗留的 `libJit.so` 会被固件重放（文档第 844 行），而 0.3.8 的清理名单 `dump.TEMP_PATHS` 只有 `tmmc.jit` / `tmmc.dat`，从来没删过它。0.3.9-probe1 起名单在 `patches._stale_paths()`，多它一个。
- 判读顺序：先找 `清理临时文件` 开头的行，再看是哪一句；细节与未验证项见 §22。

### 0.8 下一步顺序

0. **最要紧：等 0.3.9-probe1 的现场日志**（2026-10-26 晚已发，Pre-release，单 exe）。让报 `0x10000004` 的人用那一版跑一次，导出诊断包（「关于与诊断」→「导出诊断包」），或把日志框 Ctrl+A 复制（重点是最后几行）。拿到后按 §0.7 的四句判定。**在那之前不要再凭猜测改清理逻辑**——这轮已经改过两轮（0.3.7 的 `if removed:` 兜不住、0.3.8 无条件重试）都没解决。
1. **README 本地那一行还没提交**：`README.md:39` 已由「写进相机的东西，这一版和 0.3.7 完全一样…」改成 `◆ **写进相机的东西，和 0.3.7 一个字节都没差**——分区、字节数、校验方式都没变：颜色还是那 4 条记录（256 字节），名字还是那份文字包（145,612 字节）。这版的写入风险和 0.3.7 完全同级，不会比它更容易写坏；也已经在多位机友的机器上刷机成功。`（`docs/README-0.3.8.md` 已同步，两份逐字节一致）。★ 那行**故意没加**：`:33` 已有「这一版没有在本机真机上跑过」，位置更靠前。要不要提交、push，等用户点名。
2. 用户点名后，把三批改动分批提交（§0.4）：① 文档批（`docs/` 下 13 篇）② 诊断层批（`git add -p` 挑 `gui/pages.py` / `about_page.py`）③ 0.3.8 代码批。**不要一次 `git add -A`**；`packaging/必读.txt` 的 0.3.8 重写版是否提交看用户（不提交也能发布），未跟踪垃圾一律不进库。
3. 群公告照 `docs/ANNOUNCEMENT.md`（定稿，不点名按钮，用「把外观颜色和菜单字串成两段连着做」指代）——由用户自己发，不需要 agent。
4. **明确不做**：给 0.3.7 Release 正文加提醒、发置顶 issue、回 issue #1、隐藏仓库（用户 m01524 / m01566 之后已定）。

### 0.9 接手硬约束

- **不碰相机**（用户明确：相机是砖，等硬件恢复）。
- **不提交、不 push**，除非用户点名；已授权的 push 都只针对 `README.md`（`3845574` / `cd09525` / `4a3e30c`）。
- 改文案守 §0.3-D 的口径；声明可以换说法，一个字都不能弱化。
- `third_party/a6700_unlock/` 只读，不改源；壳层需求放 `src/a6700win/`。
- 改 `packaging/必读.txt` = 改发布包：必须重打包 `dist/Powerful6700-Windows-x64.zip`、重算 sha256，并同步 `README.md` 校验值行与 `docs/PROGRESS.md` / `docs/AI-HANDOFF.md` / `docs/RELEASE-NOTES.md`。
- **发布动作要逐个点名**：建 Release、传资产、删 tag 都算发布，只在用户明确说「发」时做；本轮 `v0.3.9-probe1-win.1` 的依据是 m00356（上一版无数人成功、无变砖报告、错误集中在两类）。撤稿命令 `gh release delete v0.3.9-probe1-win.1 --repo wanghm105/Powerful6700-Windows --yes --cleanup-tag`。
- **取证版只有一个 exe**，不要再往那条 Release 上加 zip；要改就发新的 Pre-release，别动 0.3.8。

---

## 1. 项目是什么

把上游 **`xyzhangxin/sony-a6700-powerful`**（A6700 固件 2.00 的非官方解锁工具，GPL-3.0，**只支持 macOS arm64**）做成一个 **Windows 桌面工具**，完整度对齐 **`QAQLeonard/a7c2-fl23`**（A7C2 的逆向研究工程：能读能写、有 GUI、有备份还原、有文档）。

产物：`Powerful6700 · Windows`（PySide6 GUI + PyInstaller 单目录包），不是「脚本合集」。

功能面：只读兼容性检查 → 功能解锁/关闭 → 功能状态备份还原 → 自定义外观（颜色 + 菜单文字）→ 操作结果 → 驱动准备 → 关于与诊断。

许可：GPL-3.0，随包带 `NOTICE` / `THIRD_PARTY_NOTICES`（从上游复制）。

---

## 2. 一句话现状

> 0.3.8 之后的当前状态以 **§0** 为准（本节写于 0.3.7 发布当天，不重复维护）。

**主链路全部真机打通**：只读检查、功能解锁关闭、功能状态备份还原、CP 外观色度写入与逐字节还原、菜单文字改写与还原（英文名 / 中文名两套，都验过）。
**0.3.7 给只读检查加了自愈：相机回 `0x10000004`（界面上的「状态：04000010」）时，先清 `/tmp/jiritsu` 残留再发一次配置写入**；0.3.6 把写入链路改成「一帧发完」，并记下了一条真机结论：相机可能进入「一次上电只给一个服务会话」——0.3.5 的一次写入在这个状态下第二段必失败，绕开办法是把动作压进单个会话，彻底恢复要拔线 + 关机 + 取电池 1 分钟。颜色 + 名字的一次写入本身（`src/a6700win/bundle.py`、`tools/bundle_apply.py`，两段会话 + 冷却）界面与 CLI 都已就位；颜色与文字两条链路已分别用单会话在真机跑通。
**发布状态**：0.3.8 已发 Release（tag `v0.3.8-win.1` → `4a3e30c`，资产 47,983,337 B / sha256 `e1f6449f…`；标题 `0.3.8 · 软件界面修复`）。git 里只提交了 README（`3845574` / `cd09525` / `4a3e30c`），0.3.8 的代码与其余文档仍在工作树里，所以源码包的 `version.py` 还是 0.3.7——详见 §0.1 / §0.2。此前做过一轮「不上传」审计（固件 / 私人备份 / 密钥 / ProductInfo / 照片 / 原始抓包 / 完整日志）：仓库 248 个跟踪文件、701 个历史路径、5 个 Release 资产（逐个读中央目录）全部干净，规则固化成 `tools/check_publish.py`；Release 标题与正文的写法见 §12.4。

**仍在做的**：外观颜色对 A7C2 直出的**定量拟合**——蓝端压不下去（旋钮在矩阵单元 `0x02A4000D` block 4，未标定），CC 定稿强度也还要用实拍确认（当前 RAM 是 pair2×0.60 + pair6=0，离线 RMS 0.164）。
**2026-10-25 晚新增（重要）**：同机型项目 `Himpq/FireHydrant` 已在 A6700 2.00 上**真机做成 FL2/FL3 与 Cine EI**（§18）。我们的「FL2/FL3 不可行」结论作废，路线重排为「离线演练 → 真机 A/B/C 三层」，蓝端标定降为并行项。

---

## 3. 工程结构与环境

### 3.1 路径

下表用 `<repo>` 表示本仓库根目录，`<workspace>` 表示它在磁盘上的上级目录。

| 用途 | 路径 |
|---|---|
| 工程（写） | `<repo>` |
| 上游只读参考 | `<workspace>/refs/a6700-powerful` |
| A7C2 只读参考 | `<workspace>/refs/a7c2-fl23` |
| 固件/素材/备份 | `<workspace>/firmware`（`cp/` `uxc/` `lut/` `photos/`） |
| 运行时数据 | `.data`（可用 `POWERFUL6700_DATA` 覆盖） |
| 基线与日志 | `.data/looknames/`、`.data/backups/`、`.data/run/`、`.data/flash-log/` |
| 冻结包 | `dist/Powerful6700/Powerful6700.exe` |

上游 vendored 代码在 `third_party/a6700_unlock`（不改源，靠 `src/a6700win/patches.py` 打补丁）。

### 3.2 Python 环境

- `.venv`（Python **3.12.3**）：`pyusb 1.3.1`、`libusb-package 1.0.30.0`、`PySide6-Essentials 6.8.3`、`pytest 8.3.5`、`numpy`、`rawpy`
- **没有** PIL / cv2 / imageio → 读 JPEG 一律 `PySide6.QtGui.QImage`（`convertToFormat(Format_RGB888)` + `constBits()` + `bytesPerLine` 切片）
- 安装坑：pip 走阿里云镜像会挂、pypi 建索引也卡 → 用 urllib 直连 `files.pythonhosted.org` 下 wheel 再 `--no-index` 装

### 3.3 每次跑命令的前置

```powershell
cd '<repo>'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='<repo>\src'
$env:POWERFUL6700_DATA='<repo>\.data'
.\.venv\Scripts\python.exe <脚本>
```

- 不设 `PYTHONPATH` → `ModuleNotFoundError: No module named 'a6700win'`
- 不设 `PYTHONIOENCODING` → GBK 控制台把中文日志打成乱码/抛异常
- GUI 渲染（`--render-pages`）还需要 `QT_QPA_FONTDIR=C:/Windows/Fonts`，否则中文全是方块

### 3.4 测试与构建

```powershell
# 测试（最近一次：116 passed / 1 skipped）
# 本机必须走包装：直接 pytest 会在全绿后卡在 Qt teardown（§0.5 坑 5）
.\venv\Scripts\python.exe .data\tmp\run_pytest.py

# 打包（内部先 pytest，再 PyInstaller，再 --offline-self-test）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

构建注意：
1. `build.ps1` **会清空 dist** → 重建后必须重新 seed 基线库（§9.4）。
2. pwsh 退出码常是 **1**（CLIXML/stderr 噪音），成败看末尾「完成…（自检通过，x.y.z）」那行。
3. PyInstaller 的 `pefile` 必须显式钉 **2023.2.7**（新版被它排除）。
4. 冻结包自检九项：python / platform / vendor `a6700_unlock` / files / data-dir / libusb / setupapi / wdi / controller。
5. 窗口化 exe 无 tty 时用 `AttachConsole(-1)` 取回 stdout。

---

## 4. 已验证能力清单

| 能力 | 入口 | 真机证据 |
|---|---|---|
| 只读兼容性检查（260 扇区 / 133,120 字节） | GUI 相机准备 | 多轮通过，`docs/VALIDATION.md` |
| 功能解锁 / 关闭（FTP、快门声、灵活曝光…） | GUI 功能管理 | 实拍验证，`docs/VALIDATION.md` |
| 功能状态备份 / 恢复 | GUI 功能管理 | 备份文件 SHA-256 记录在案；恢复曾需两个补丁（隐藏门闸 + 选择面扩到全部） |
| CP 外观色度写入 / 逐字节还原 | GUI 自定义外观 / `tools/looks_apply.py` | 回读一致 + `/setting/BACKUP.BIN` 三方比对 |
| 菜单文字改写 / 还原（official / zh 两套） | GUI 自定义外观 → 菜单文字卡片 | 英文名 145,708 B、中文名 145,692 B 都在相机菜单里显示正确；还原回出厂 145,612 B |
| 一次写入 / 一次还原（颜色 + 名字） | GUI 自定义外观 → 「一次写入：颜色 + 名字」/ `tools/bundle_apply.py` | `tests/test_bundle.py` 覆盖顺序、两段会话、失败分支与报告 |
| 写 `/usr` 文件 | `src/a6700win/flash.py` + `native/flash_write.elf` | 已真机写、断电持久 |
| 写 `/cp`、`/setting` 文件 | 同上（`WRITABLE_ROOTS`） | 代码已完成并重编，**`/setting` 分支尚未真机跑过** |
| 载荷自检 / 零变化写探测 | `tools/flash_write.py --probe` | 通过 |
| 离线自检、页面离屏渲染 | `Powerful6700.exe --offline-self-test / --render-pages` | 通过（九项 + 7 张 PNG） |

**结果类别**（GUI 与日志统一用这套词）：`completed` / `no-op` / `blocked` / `rolled-back` / `uncertain` / `verification-failed` / `recovery-required`。

---

## 5. Windows 侧技术路线（为什么这么写）

- **USB 绑定**：SetupAPI 枚举 PnP → 用 libwdi 的 `wdi-simple.exe` 把相机接口绑到 **WinUSB** → `pyusb` + `libusb-package` 自带的 `libusb-1.0.dll`。纯 MTP/HID 驱动下 pyusb 拿不到 bulk 端点。
- **提权**：`ShellExecuteExW` + `runas`（绑驱动需要管理员）；提权与非提权进程**必须落到同一个数据目录**，否则状态读写分裂。
- **上游移植**：上游对 `sys.platform` 硬编码 darwin/linux，Windows 上 doctor 恒 False → `src/a6700win/patches.py` 统一补丁（`patches.install()` 实测 **30 项**：applied 28 + already 2），覆盖 legacy 的 libusb 路径/backend/auth、doctor、preparation、usb.backend.payloads、operations 的锁与目录、`planner.os.O_NONBLOCK`、`backup.os.O_BINARY`、`controller.run_reserved` 等。
- **为什么用属性替换**：vendored 的 bridge 不传 `backend_factory`，只能替换模块属性。
- **POSIX 语义**：`src/a6700win/windows_shim.py` 提供 `host_lock_path` / `default_state_dir` / `make_directory` / `sync_file` / `save_json`（`O_BINARY` 防 `0x0A`→`0x0D0A` 损坏稀疏备份）、`device_lock`（`msvcrt.locking` 锁首字节）、`OsProxy`（给 `planner.os` 补 `O_NONBLOCK=0`、给 `backup.os` 补 `O_BINARY`）、`wrap_run_reserved`（异常时清 busy/回 phase）。

### 5.1 相机侧 PID 与驱动状态

| PID | 含义 | 驱动 |
|---|---|---|
| `0x0E76` | 海量存储 MSC（正常操作入口） | `USBSTOR` / 绑 WinUSB 后 `winusb` |
| `0x0E8A` / `0x0336` | 服务模式（认证后切过来） | **无驱动**（`CM_PROB_FAILED_INSTALL`）→ 需 `wdi` 绑 WinUSB |
| `0x096F` | HID / HidUsb（掉线后常见落点） | `HidUsb`，**不是 MSC，救不回来** |

`src/a6700win/usb/windows_auth.py` 里 `_wait_service()` 会在认证后先轮询 SetupAPI 等 `0x0336`、用 wdi 绑 WinUSB，再交给 libusb；`_recover_service_mode()` 处理相机卡在 `0x0336` 的情况（认证 + vendored `STOP_SENSER` 退出）。

---

## 6. 相机侧协议与物理基础

### 6.1 基本帧与命令

- Senser 头 12 字节：`'<IHHBBBB'`
- `0x10` ProductInfo、`0x40` 命令通道
- 命令流程：`0x4010` config → `0x4007` ident2 + ELF 载荷 → `0x4008` 执行
- 固定读写窗口：**260 扇区 / 133,120 字节**（只读检查、功能状态备份都在这个窗口内）
- 文件访问走 **Jiritsu 文件命令**（A7C2 的 cmd 15/16/17/18）：open/read/write/close，路径 + 偏移 + 长度

### 6.2 挂载表（从 initrd 的 fstab 挖出）

| 分区 | 挂载点 |
|---|---|
| nflasha2 | `/setting` |
| nflasha3 | `/system` |
| nflasha8 | `/cp` |
| nflasha10 | `/tmp` |
| nflasha11 | `/log` |
| nflasha12 | `/cert` |
| nflasha15 | `/usr`（ext2，ro 挂载但可写） |
| nflasha18 | `/lens` |

### 6.3 写入载荷（自研）

- 源码 `native/flash_write.c`，交叉编译：`zig cc -target aarch64-freestanding -fPIC -O2 -ffreestanding -fno-builtin -fno-stack-protector -c` + `zig ld.lld -shared -Bsymbolic -z noexecstack`
- 编译前必须把 `ZIG_GLOBAL_CACHE_DIR` / `ZIG_LOCAL_CACHE_DIR` 指到 `.data/zig-cache`（否则 AccessDenied）
- 内联 `svc #0` 必须声明 `"cc"` clobber
- 当前产物：`native/flash_write.elf` **74,040 B**，sha256 `94b45897f48b26d606cc41d2b3fee3e74bd1c767a3eef0553c57df246d022c6c`（带 `/setting` 支持，**未跑过真机**）
- 只读版 `native/dump_range.elf` 18,528 B（模式 2 = `getdents64` 目录列举）
- 载荷模式：0 读 / 1 长度 / 2 列目录 / 3 写 / 4 零变 probe / 5 顺序 probe / 6 顺序写 / 9 临时目录自测 / 10 截断；状态码 0..14（12 = 范围超出文件长度，6 = 路径不在白名单）
- 可写白名单：`/usr/`、`/cp/`、`/setting/`；拒绝 `/../` 与 `/dev/`
- 写大文件流程：先 `truncate` 到目标长度（`SYS_FTRUNCATE=46`，可扩零延长）→ 按 `WRITE_BLOCK`（0x20000）分块 `write_block` → 每块由相机侧载荷 pwrite + fsync 后回读比对，主机侧复核长度
- 硬教训：**fsync 后 close，再用独立 O_RDONLY 句柄回读**（拿 `O_WRONLY` 句柄 `pread` 必然 EBADF / -9）

---

## 7. 颜色子系统（CP 单元）

### 7.1 单元布局（A6700）

| 单元 | 大小 | 结构 |
|---|---|---|
| `0x02A40001`（色度） | 8,192 B | 参数表 @`0x1200`（`0x1200 + N*2`，N=40..49 是外观 profile 号）；色度记录 @`0x1250 + bank*64`，每条 **64 B = 12 组 `(Cb,Cr)` int16 + 尾 8 个 0** |
| `0x02A4000D`（矩阵） | 28,672 B | 参数 @`0x196`；矩阵 @`0x1e0 + slot*768` |

出厂 profile 号：`[16, 8, 14, 10, 12, 9, 15, 11, 13, 19]`（外观 0..9）。

### 7.2 外观 ↔ bank（实测，通道置换验证过）

| 外观 | 菜单 | 色度 bank |
|---|---|---|
| ST 标准 | ST | 0 |
| VV 鲜艳 | VV | 1 |
| NT 中性 | NT | 4 |
| PT 人像 | PT | 6 |
| FL 影视 | FL | 8 |
| SE 棕褐 | SE | 9 |
| VV2 鲜艳2 | VV2 | 14 |
| BW 黑白 | BW | 无独立色度 |

- 菜单 16 项顺序：`ST, PT, NT, VV, VV2, FL, IN, SH, BW, SE, 1ST, 2FL, 3IN, 4SH, 5VV2, 6BW`
- 后 6 个「自定义外观」**是内建外观的别名**，没有独立颜色 bank（bank0 改粉 → ST 与 1ST 同时变）
- 色度 bank 由**外观序号**决定，与 profile 号无关
- 出厂副本：`.data/../firmware/cp/unit-02a40001.backup-def.bin`（sha `72d3da868cc0`）、`unit-02a4000d.backup-def.bin`（sha `59aed2edd1b0`）

### 7.3 持久化语义（关键）

- CP 单元是 **RAM**；**正常关机时相机把它写进 `/setting/BACKUP.BIN`**（色度 @`0x1B2140` 8192 B、矩阵 @`0x1B6870` 28672 B），开机读回。
- **关机后立刻开机 → 改动丢**；**正常关机等满 1 分钟再开机 → 稳定落盘**（2026-10-25 实测：内存与 BACKUP 都是 `72d3da868cc0`，0 字节差异）。
- 只还原 RAM 不还原 BACKUP → 「当场对、重启又变」。
- 复位到出厂的正确顺序：逐单元比对出厂副本 → 写回 RAM → **正常关机再开机**让相机覆盖 BACKUP。

### 7.4 协议入口

```
cp_read  = (0x603, 0x40, pack('<II', key, 1))   # 读单元，额外要吃 0x200 结束包
cp_write = (0x603, 0x41, ...)                   # 写单元
```

`src/a6700win/cp.py` 的 `CpChannel` 提供 `read_unit` / `write_unit`；`session(progress)` 带**会话冷却**（见 §11.1）。

---

## 8. 颜色拟合现状（正在做的事）

### 8.1 目标向量（A7C2 直出，19 张对照图 × 72 样本中位色度比）

```
CC：0.77 0.81 0.74 0.48 0.61 0.62 0.69 0.83 0.99 1.06 0.76 0.53
NC：0.63 0.79 0.34 0.58 0.67 0.74 0.91 0.77 0.91 0.85 0.63 0.44
PF：0.86 0.88 1.16 0.63 0.66 1.03 1.18 0.79 0.62 0.75 0.69 0.64
NF：1.46 1.10 0.58 0.38 0.71 0.83 0.87 0.86 0.97 0.72 0.35 0.23
```

12 档 = 每 30° 一段：`0-30` 蓝 / `30-60` 蓝紫 / `60-90` 紫红 / `90-120` 红 / `120-150` 橙 / `150-180` 黄 / `180-210` 黄绿 / `210-240` 绿 / `240-270` 绿青 / `270-300` 青 / `300-330` 青蓝 / `330-360` 蓝。

### 8.2 指标口径

```
s   = Σ(m·t) / Σ(m·m)          # 最优整体缩放
RMS = √(mean((s·m − t)²))      # 逐档误差
矫正率 = 1 − RMS
```

`docs/LOOKS.md` §9 记录值 → 矫正率：CC **81.7%**、NC **82.7%**、PF **81.1%**、NF **67.0%**（见 `docs/CALIBRATION.md`）。

### 8.3 已测配方（单场景，CC）

| 配方 | 写入指令 | RMS |
|---|---|---|
| pair2×0.35 | `--look "CC=6:6:1.00@2*0.35"` | 0.259 |
| **pair2×0.52**（旧定稿） | `--look "CC=6:6:1.00@2*0.52"` | 0.194 |
| **pair2×0.60 + pair6=0**（现用） | `--look "CC=6:6:1.00@2*0.60,6*0.00"` | **0.164** |
| pair2×0.56 + pair7/10/11×0.40 | 卷4 | 0.178 |
| pair2×0.70 / 0.85 | `@2*0.70` / `@2*0.85` | 未测（观感更浓，中段更低于目标） |

工具：`tools/look_write.py`，语法 `菜单名=目标bank:基底bank:系数[@pair*系数,...]`，必须 `--confirm yes-write`。
其它配方（定稿）：NT bank4 `1.00@2*0.62`、PF bank1 `1.00@2*0.75`、NF bank14 `1.00@2*0.85`（PF/NF 只做低饱和版）。

### 8.4 蓝端结论（别再重复试错）

- **色度记录这层压不动**：`pair1×0.40` 把青蓝从 1.07 推到 **1.37**（方向反）；`pair7/10/11×0.40` 只到 1.08（组效应、边际）；同参数不同轮次蓝端自己在 0.95–1.20 晃。
- **旋钮在矩阵单元 `0x02A4000D` 的 block 4**：整块填 20000 时，PT 蓝 0–30° 档到 **6.20 倍**，其余档 ≤1.68 → 有把手，但只做过粗暴整块填充，**没做块内二分/线性范围标定**。
- CC 实测 `0.95 / 1.06` vs 目标 `0.77 / 0.53` 是 RMS 的大头；中段（60–270°）在 0.52 时误差只有 0.03–0.09。
- **下一步别再调色度层**：矩阵单元前 576 B 是 3 平面 × 16 selector × 6 个 s16，A7C2 用同一结构做 405×405 正规方程 + IRLS 拟合（§17.2 ④⑤、§17.5 路线 A）。

---

## 9. 菜单文字子系统（已完成）

### 9.1 资源格式（UXC v7）

- 路径：`/usr/share/app/string_simplifiedchinese_f.uxc`
- 出厂：**145,612 B**，sha256 `fe263360c15b5530508bf7b098c96ec39cd4c38536b23653d15e6ea977b80e42`，**4,785 条**记录，`base = 0x2574`
- 结构：
  ```
  magic  b'uxc\x07\0\0\0\0'
  u16    kind = 8
  u16    group
  u32    descriptor = count | (((count+1) & ~1) << 12)
  [16]   count 个 u16 索引（0xFFFF = 空槽）
  base   (16 + count*2 + 3) & ~3，记录区
  记录   u32(0x1E000000 | rid & 0xFFFFFF) + UTF-8 + NUL + 补齐到 4
  rid    0x02000000 | ((group << 13) + index)
  ```
- 记录可用容量 = 下一条记录起始 − 本记录 − 4（**按 NUL 算会低估**）

### 9.2 外观文字的两条记录（改名必须一起改）

| 外观 | rid |
|---|---|
| ST | `0x021C658E` |
| PT | `0x021C6654`、`0x021C6F8B` |
| NT | `0x021C6434`、`0x021C7002` |
| VV | `0x021C687B`、`0x021C6F80` |
| VV2 | `0x021C689A`、`0x021C6F4D` |
| FL | `0x021C6CC9` |
| IN | `0x021C6857` |
| SH | `0x021C6961` |
| BW | `0x021C65F8` |
| SE | `0x021C658A` |

出厂文字就是槽位缩写（`PT` / `NT` / `VV` / `VV2` …）。

### 9.3 两套命名

| 预设 | key | 文字 |
|---|---|---|
| 官方原名 | `official`（默认） | Classic Chrome / Classic Neg. / Positive Film / Negative Film |
| 中文简称 | `zh` | 富士CC / 富士NC / 理光正片 / 理光负片 |

- 存在 `docs/looks-profile.json` 的 `menu_names`，界面下拉切换、**切换只改显示不写盘**；预设持久化在 `.data/looknames/settings.json`
- 实测字节：official → **145,708 B**（sha `9fd0bb497171…`）；zh → **145,692 B**（sha `4a2a05e814a0…`）
- 改回短名 → 与出厂**逐字节相同**（145,612 / `fe263360…`）。这是实测行为，**不当承诺**；无损仍靠基线

### 9.4 写入与还原

- 写入：`uxc.rename_all` 整块后移 + 重写索引表 → `flash.truncate` 到新长度 → `WRITE_BLOCK`（0x20000）分块写 → 复核长度（每块由载荷回读校验）
- 还原三档：① 有出厂基线 → 逐字节写回（`mode="baseline"`）；② 无基线 → 把记录改回短名（`mode="labels"`），若回写后哈希恰与出厂一致则自动登记为基线（`mode="labels-factory"`）；③ 拒绝写入
- 基线库 `.data/looknames/`（6 份，best = 出厂 145,612 / `fe263360…`，source `string_simplifiedchinese_f.uxc.20261023T233448Z.bin`）；source 目录 `<workspace>/firmware/uxc`
- **`build.ps1` 清 dist 后必须重新 seed**：
  ```powershell
  $env:POWERFUL6700_DATA='<repo>\dist\Powerful6700\.data'
  .\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'src');from a6700win import looknames;print(looknames.auto_import())"
  ```
- 恢复手法（掉线撕裂时）：`live_repair.py` 只重写差异块（先读全 5 块 → 逐块比 → 只写不同的块 → 只回读这些块）

### 9.5 一次写入（颜色 + 名字，0.3.5）

用户要求（m09376）：软件里的选择必须成对生效——「选中文富士就写中文名 + 富士滤镜」。
这不是新协议，只是把两件已验过的事按顺序排好：

```python
# src/a6700win/bundle.py
colors_wrote = _colors(progress, report, restoring)   # looks.apply / looks.restore（会话 1）
_names(progress, report, restoring, colors_wrote)     # looknames.apply / looknames.restore（会话 2）
```

- 两段各自 `cp.session`，**中间的空档由 `cp._cooldown` 兜**（`SESSION_GAP` 默认 50 s，进度条每 10 s 报一次，末尾报「冷却结束，重新连接相机…」）。
- 前一段失败 → `BundleError` 直接抛出，文字一个字都不动；后一段失败 → 不抛，写进 `report["error"]`，并说明颜色已写入、可单独回滚（GUI 显示「停在这里：…」，CLI 退出码 1）。
- 报告结构：`{preset, label, steps, colors, names, wrote, error, seconds}`；`bundle.summary()` 负责把两段压成人话（GUI 与 CLI 共用）。
- 真机验收要点（还没做）：① 一次写入后关机重启，颜色与名字都要对；② 二次点同一个按钮应报「已是目标状态，没有写入」；③ 一次还原后颜色回 `72d3da86…`、文字回 145,612 / `fe263360…`；④ 中途拔线应停在第 4 条那种可解释的失败上。

---

## 10. 当前真机状态（接手先复核）

> ⚠️ **相机目前是砖（2026-10-26 写坏，等硬件恢复），下表是最后一次实测值，别为了「复核」去连相机。** 等相机修好后再按下面的做。

复核（**一次会话读全，别连两次**）：

```powershell
.\.venv\Scripts\python.exe .data\scratch\live_check_units.py
```

按最后一次**实测**记录（不是推测；每次断电重开后再动相机都要重新读一遍）：

| 项 | 状态 |
|---|---|
| 菜单文字 | **英文原名**，145,708 B，sha `9fd0bb497171…`（单会话 `repair_oneshot.py official` 修复后登记为基线） |
| CP 色度单元 | 配方版，整单元 sha `b0cab23b623c…`；PT(bank 6) = **pair2×0.60 + pair6=0**，NC/PF/NF 为定稿配方 |
| `/setting/BACKUP.BIN` 色度副本 | 曾复核为与 RAM **逐字节相同**（`b0cab23b623c…`，正常关机等待 1 分钟后落盘） |
| 矩阵单元 `0x02A4000D` | 与出厂逐字节相同（`59aed2edd1b0…`，未动） |
| FL | 偏橙是**原厂 FL 本来的样子**（bank 8 与出厂逐字节相同） |
| 相机最近一次枚举 | **0x096F（HidUsb，非 MSC）**，服务模式下若端点卡住要拔线 + 关机 + 取电池 1 分钟 |

- **固件镜像仍是出厂态**（2026-10-25 复核）：`firmware/nflasha5-2.00.bin` 与 `nflasha5-after.bin` 各 314,572,800 B、sha256 同为 `56e0e220…`，WBI 头 `WBI2` / `sections=1314` / `resume_vector 0x4004A67F0` 有效；`firmware/appFw-2.00.so`、`firmware/cp/cpapp-b.bin` 未被改过（§18.4）。
复核脚本（都在 `.data/scratch/`）：`verify_flush.py`（RAM 与 BACKUP 与配方三方比对）、`live_check_units.py`（CP/矩阵/BACKUP）、`bundle_status.py`（一个会话内同时读颜色与文字）。

⚠️ **不要在一个会话里既写 CP 单元又写 145 KB 文字**（实测 3 次，第 5～13 次传输必崩）。

---

## 11. 踩过的坑（照抄，别重犯）

### 11.1 会话与掉线（最贵的五条）
1. **同一会话混写 CP 单元 + 145 KB 文件 → 必掉线**；拆两个会话 + 冷却 **50–60 s**（`cp.SESSION_GAP`，环境变量 `POWERFUL6700_SESSION_GAP`）。
2. **`/tmp/jiritsu` 的残留会让下一次配置写入被拒（`0x10000004`）**。0x4010 配置写入与我们的载荷共用 `tmmc.jit` / `tmmc.dat`，上一次会话没干净结束时残留会连锁到下一次。清理用相机自己的删除命令，报文必须「先 select 目标路径，再发 `CMD_REMOVE`（18）且正文只有 `\0\xff`」——把路径直接塞进 `CMD_REMOVE` 会被拒成 `0x10000201`。0.3.7 已做成自愈：`patches._windows_backend_file` 重试一次，`cp._clear_temp` 在会话开头清一次。
3. **2026-10-25 实测：相机可能进入「一次上电只给一个服务会话」的状态**。表现是第一个会话正常（认证、读写都通），结束后相机在 `0x0336` / `0x096F` / `0x0E76` 之间来回跳几下再回到 MSC；此后再连，第二个认证包写 `0x0336` 的 bulk 端点立刻 `[Errno 32] Pipe error`，等 60 s 也不恢复，只有**取电池断电重开**才恢复。所以排查/修复时要把动作压进**单个会话**（读状态 → 写 → 回读都在一个会话里）。
4. **掉线后普通「关机再开」无效**：要拔线 + 关机 + **取电池约 1 分钟**（A7C2 文档原话：只关机再开机不算断电重开），否则第一个块就崩。
5. **USB 3 高速口时相机不进服务模式**（认证后跳回放画面、`0x0336` 不出现）→ 换 USB 2.0 口/线。端点坏掉的唯一恢复是**物理拔插**。

### 11.2 写入器
1. 先 `truncate` 再写：grow 场景（145,612→145,708）最后一块落在原长度之外 → 状态码 12「范围超出文件长度」。
2. 加「载荷缓存」或改分包大小 → 读到陈旧数据（`flash.stat` 返回 225 其实是路径字符串长度、`read_range` 返回路径文本）。已回滚，**别再加**。
3. 回读必须用新的 `O_RDONLY` 句柄，且要 `fsync` + `close` 之后。

### 11.3 基线
1. 整单元写入**必须以当前实时单元为基线**，不能用历史快照（曾把 ST/VV 写黑白）。
2. `restore()` 的基线来自本地 store；`apply()` 前若无同 sha 基线会自动 capture（事故就是这么救回来的）。
3. 曾用被污染的「出厂快照」当基线 → 每轮「还原」都写回旧数据；`BASELINE` 一律用 `unit-02a40001.backup-def.bin`。

### 11.4 环境
1. GBK 控制台必须 `PYTHONIOENCODING=utf-8`。
2. 每轮写入结束要让相机退出服务模式（发 `STOP_SENSER`），否则停在 `0x0336`。
3. bash heredoc 里 `'\\n'` 会被吞成真换行 → 用数值 10 / `chr(10)`；绝对 POSIX 路径要 `MSYS_NO_PATHCONV=1`。
4. exe 运行时不能删除/改名 `dist` 目录（`base_library.zip` 被占用）。

---

## 12. 待办与下一步的具体做法

### 12.1 矩阵层标定（并行项，不再是优先级 1）
```powershell
# 自由度：矩阵 @0x1e0 + slot*768 的前 576 B（3 平面 × 16 selector × 6 个 s16）
# 已封的做法：整块填 2000/5000、block 4 盲试（背景噪声太大，见 §8.4）
```
做法改成**拟合**而不是盲试：拿 §8.1 的 12 档目标，用正规方程 + 平滑正则 + IRLS（±64、300 epoch、1e-4）解出 576 个 s16，一次写入、一次实拍验证。每轮写前存当前单元、写后回读，**随时能一键写回出厂**。优先级降为并行项的理由：FL2/FL3 通了以后，「像不像富士」不再只靠色度层（§18.6）。

### 12.2 客观验收（优先级 2）
```powershell
# 拍一帧 RAW+JPEG（PT 槽位），然后把卡插上直接读
.\.venv\Scripts\python.exe tools\look_loop.py measure --raw <ARW> --jpeg <jpg>
```
把 0.164 从「历史最优」变成「当前实测」；同一场景重拍还能对比 0.52 / 0.60 / 0.70 / 0.85。

### 12.3 一键写入（0.3.5 已实现）
用户原话（m09376）：「软件里的所有更改都要对应，比如我要中文的富士或者英语版的富士滤镜，就要写入富士滤镜和对应名字」。
代码已完成：`src/a6700win/bundle.py`（`apply` / `restore` / `summary`）+ GUI 的「一次写入：颜色 + 名字」卡片 + `tools/bundle_apply.py`。约束都照实落进去了：
- 两段连续会话（会话 1 写 CP 色度 → 冷却 50–60 s → 会话 2 写文字文件），不合并成一个会话
- 界面写明约 2 分钟、中途不要拔线；冷却期间进度条报剩余秒数
- 失败分支：颜色段失败不动文字；文字段失败保留颜色并提示可单独回滚
- 还原同理：颜色回出厂记录、文字回基线（或短名回写），也拆两段

验收清单见 §9.5 末尾四条；跑完把结果补进 `docs/VALIDATION.md`。

### 12.4 版本与发布
- `src/a6700win/version.py` 工作树里是 `0.3.8`（未提交；tag `v0.3.8-win.1` 指向的 `4a3e30c` 里仍是 `0.3.7`）；已发 Release：`v0.2.0-win.1`、`v0.3.1-win.1`、`v0.3.2-win.1`、`v0.3.4-win.1`、`v0.3.7-win.1`、`v0.3.8-win.1`（0.3.3 / 0.3.5 / 0.3.6 只在仓库记录里，没有单独发）
- 发布流程：`packaging\build.ps1` → 重建后 **seed 基线库**（build 会删 `dist\.data`）→ `--offline-self-test` 九项 → `--render-pages` 七页 → `tools\make_release.ps1` 出 zip → `tools\check_publish.py --zip` 扫描 → `gh release create`
- **不上传清单**（用户要求，2026-10-25）：固件、私人备份、密钥、ProductInfo、照片、原始抓包、完整日志。`tools/check_publish.py` 把这条变成可执行检查（扩展名 / 文件名 / 目录 / 体积 / zip 内容），干净时 exit 0
- **标题写法**：`版本号 · 一句话说清解决了什么问题`，**不写 v 前缀**，例如「0.3.7 · 修好只读检查中途报错的问题」。不写内部实现（「配置写入自愈」这种不行）
- **正文写法**：先一句现象，再 3–5 条改动，最后一句适用范围；状态码推导、测试数字留在 `docs/RELEASE-NOTES.md`
- **0.3.8 的例外（用户改的，别「修回去」）**：标题 `0.3.8 · 软件界面修复` 是用户定的九个字，比上面的规范更口语；正文也按用户的群公告口吻改过，没有状态码推导那类内容，最终稿在 `.data/tmp/release-0.3.8-final.md`。
- 以上两条 2026-10-25 被用户连续纠正三次才定下来，改标题时别退回旧写法

### 12.5 同代项目给出的新路（路线表已被 §18.6 取代，原三条保留作历史）

- **路线 A（先做）**：把外观从色度一层扩到「色度 + 矩阵」两层 —— `0x1e0 + slot*768` 的前 576 B（3 平面 × 16 selector × 6 个 s16）当拟合自由度，搬 A7C2 `native.py` 的正规方程 + 平滑正则 + IRLS（±64、300 epoch、1e-4），目标仍是 §8.1 的 12 档向量。**这条取代 §12.1 的盲试整块填充**。
- **路线 B（第二步）**：六槽自定义外观，前置是静态定位三件事 —— ① `firmware/appFw-2.00.so`（89,027,992 B）里的 look→CP converter 模板（候选起点 `0x34e5604`）；② 名称 label id 的写点；③ CP 里 1215 B 表的实际地址与 stride。判据：找到与 A7C2 那 132 B 模板同构的序列（原厂首字节 `1f 40 00 71 81 00 00 54`）。
- **路线 C（不做）**：整包重签 —— 容器解不开且需要签名身份。

### 12.6 FL2/FL3 三层移植（新，优先级 1；细节见 §18）

- **离线演练（先做）**：把 `cp.delta`（33 窗 / 4,456 B）与 appFw `0x34E5604` 的 112 B 在本机镜像副本上 apply → verify → restore，产出逐窗口 patch table（`before` 与 `after` 都留档）。
- **真机顺序 C → B → A**：`tools/cp_write.py` 写两个 CP 单元的空槽（71 B + 840 B）→ `saveBackup(0x02a4)` → `flash.write_windows("/cp/cpapp-b.bin", 33 窗)` → `flash.write_block("/usr/lib/appFw.so", 0x34E5604, 112 B)`。
- **每层都必须有的三件**：写前 `flash.read_range()` 比对 before（不符即中止）、写后 `O_DIRECT` 复核、失败反向写回。A 层写坏只有官方恢复包，所以放最后。

---

## 13. 已知限制与能力边界

- **只能从机身 dump 取明文**：官方固件 `BODYDATA-2.00.dat`（1,024,017,848 B）是加密容器（DATV/PROV/UDID/FDAT/DEND），12 种 Sony-PMCA-RE crypter 全解不开。
- **固定窗口只有 260 扇区 / 133,120 字节**：`.text` / `.data.rel.ro` 不在窗口内，改判定逻辑（如卡速）需要新的写窗口，风险高。
- **影调层：有载体，没标定**（2026-10-25 修订）。CP 里**有**矩阵单元（`0x02A4000D`，每槽 768 B，A7C2 只写前 576 B），我们一直没动用；cpapp 里还有「42 项 CP 候选模式表 + 当前生效参数」两份数据（§18），FL2/FL3 的观感就是靠这两份加 CP 空槽参数表达出来的，**不经过 gamma 斜坡**。所以「矩阵+曲线拟合残差 0.148 已是模型极限」作废：**0.148 只是色度一层的极限**。仍然没找到的是 gamma 曲线记录（§14 那 9 条 1024 B 斜坡确为死数据），`.cube` 那种 33³ 曲线+LUT 依旧表达不进来。
- **完整备份未实现**（只有功能状态的稀疏备份 254 个固定扇区）。
- **整机验证**仍记 `pending-unified-selection`。
- **payload-integrity 降级**：上游 `manifest.json` 的 `source_sha256` 与自身的 `transaction.c` 不符（全仓库无该哈希），已降级为溯源信息（记录 expected/actual），**实际送相机的字节仍严格校验**。
- **PF/NF 只是低饱和版**：目标里「压红抬黄绿」「压红压蓝抬正蓝」是局部反向，pair 基函数叠加不出来。
- **卡速（V90 判定）没改**：速率等级是固件真实枚举，caution 文案表在 `.data.rel.ro 0x4958148` 起每项 16 B `{name, u32 id, u32 len}`，共 1981 条；属性 id `0x97e` / `0x98c` / `0x19f`。用户卡是 V60，4K120 被速率门挡住 → 要改需新写窗口，已搁置。
- **REA 无可用 provider**（只支持 Linux x64），Windows 上不能用它做运行时逆向。

---

## 14. 历史调查结论（省得重做）

- **外观↔CP 映射工具**：A6700 的 look→CP mode 转换器在 `0x34e5604`（A7C2 是 `0x3528804`）；索引表 `0x40b6024`；两机同一套 look/mode 编号体系。
- **A7C2 的 patches.json**（`list[2]`：appFw 8 处 + cpapp 32 处）：`0x20140` 初始化长度 `0x141B80 → 0x142AA0`（差 `0xF20` = 3872，即 `0x1100B80` 追加的曲线记录）；FL2/FL3 参数 55/56 → CP 槽 23/25；gamma 上界 `0x2f → 0x32`；菜单 product flag。A7C2 的 CP 布局与 A6700 同构（8192 / 28672，参数 @`0x1200`，矩阵 @`0x1e0 + slot*768`）。
- **cpapp 静态镜像**：`/cp/cpapp-b.bin` 17,892,024 B，ARM32 Thumb 裸镜像，60,408 条字符串，含 `SET_LOOKNAME` / `SET_LUT` / `init_cc_3DLUT` / `CheckSetPictureProfile`；但**单元 RAM 地址只在单元目录里**，运行时快照与静态字节几乎不匹配 → 矩阵/色度是运行时算出或主机下发，静态里挖不到现成表。
- **cpapp 里 9 条 1024 B 恒等斜坡（`0xFE0B50` 起，长 `0x400`）是死数据**：改成 gamma 2.2 后实拍三张差异 <2.7/255，屏幕无变化（已写回恒等）。
- **外观八参数（对比度/高光/阴影/褪色/饱和度/锐度/范围/清晰度）按槽存在 CP 单元里，具体字节未定位**（2026-10-25 修订，原结论「不在 CP 单元」作废）：`0x1200`（chroma）/ `0x196`（matrix）里有「槽被引用」的字节串，FireHydrant 的 C 层就是往**未被引用的空槽**写 71 B / 840 B 再 `saveBackup(0x02a4)`。仍成立的部分：`/setting/BACKUP.BIN`、PSD/DEFDET 里没有元组命中。
- **自定义外观是内建别名**（见 §7.2），bank 22–31 / 40–53 涂色无任何变化。
- **官方富士 3D LUT 包（x-h2s / x-pro3 / x-t4）接不上**：19 张表全是 F-Log / F-Log2 / F-Log2C（F-Gamut）→ ETERNA / ETERNA-BB / WDR 的**录制域→显示域**转换，**没有任何胶片模拟**；A6700 只有 S-Log3/HLG。
- **达芬奇导出的 `Fuji_CC.cube` / `Fuji_CN.cube` 不能当参照**：灰阶被烤成强 S 曲线（0.25→0.083、0.5→0.690、0.75→0.937，与恒等偏差 −0.167/+0.190/+0.187），四种域解释应用到实拍帧后与相机 CC 的 12 档 RMS 0.53–1.19。干净 CST cube 的自检标准：灰阶与恒等偏差 <0.02、色相旋转 <3°。
- **tint 被证伪**：蓝基座 `v6` 两个方向都降饱和且偏暖（1.00/0.80→0.763、1.00/1.20→0.658），它只是白点配平项，不是色相旋钮。
- **CC/NC 定稿写法的由来**：`pair2` 是「暖区抑制」基函数，`pair6` 是「绿区抬升」，`pair1` 会把青蓝推向错方向。

---

## 15. 文件地图

### 15.1 源码（`src/a6700win/`）

| 文件 | 职责 |
|---|---|
| `paths.py` | 数据目录解析（`POWERFUL6700_DATA` → `project_root()/.data` → `LOCALAPPDATA` → temp）、`bundled_root()`、`state_dir()`、`backup_dir()` |
| `patches.py` | 上游 30 项补丁（`install()`） |
| `windows_shim.py` | POSIX 语义垫片（锁、目录、`O_BINARY`、`O_NONBLOCK`） |
| `usb/setupapi.py` | PnP 枚举（`present_pids()`） |
| `usb/driver.py` | `wdi-simple.exe` 下载与绑定 |
| `usb/windows_auth.py` | `_wait_service()` / `_recover_service_mode()` |
| `cp.py` | `CpChannel`（`read_unit` / `write_unit`）、`session()` + **会话冷却** |
| `flash.py` | 文件读写（`stat` / `read_range` / `write_block` / `truncate`）、`WRITABLE_ROOTS`、`TARGETS` |
| `looks.py` | CP 色度配方（`profile` / `read_state` / `apply` / `restore`，均支持 `channel=`） |
| `uxc.py` | UXC v7 格式（`decode` / `patch_text` / `grow` / `rename_all` / `texts`） |
| `looknames.py` | 菜单文字（`PRESETS` / `targets` / `read` / `apply` / `restore` / `capture` / `auto_import` / `_write_blob`） |
| `bundle.py` | 一次写入 / 还原（颜色 + 名字）：两段会话编排、部分失败的报告、`summary()` 人话摘要 |
| `app.py` / `controller.py` | 状态机与主控 |
| `selftest.py` | 离线自检九项 |
| `gui/` | `window` / `pages` / `render`（`settle()` 处理 `deleteLater`）/ `looks_page` 等 |
| `diagnostics.py` | 差异翻译与取证：`describe` / `issue_lines` / `issue_hint` / `read_interrupted` / `environment` / `report` / `export_bundle`（环境探针逐项 `_safe`，自身不抛） |
| `version.py` | `APP_NAME="Powerful6700Win"`、`APP_TITLE="Powerful6700 · Windows"`、`APP_VERSION="0.3.8"` |

### 15.2 工具（`tools/`）

| 工具 | 用途 |
|---|---|
| `look_write.py` | 写色度配方（支持 pair 系数） |
| `look_loop.py` | `pairs` / `measure`（`--raw <ARW> --jpeg <jpg>`）/ `simulate` / `solve` |
| `look_diff.py` / `look_calibrate.py` | 差异与标定 |
| `looks_apply.py` | 按配方一次性写四条 |
| `bundle_apply.py` | 一次写入 / 还原（颜色 + 菜单文字），两段会话；`--apply` / `--restore` / `--preset` / `--confirm yes-write` |
| `cp_read.py` / `cp_write.py` / `cp_patch.py` / `cp_probe_unit.py` | CP 单元读写与探测（写前自动存 `<file>.orig`） |
| `cp_verify_factory.py` | 14 个单元与出厂副本比对（**直接 `run_authentication`，无冷却/无锁**） |
| `uxc_grow.py` | 菜单文字改名（离线预览 / 真机写） |
| `flash_write.py` | 载荷读写（`--probe` / `--stat` / `--verify` / `--write-hex` / `--write-file`，写要 `--confirm yes-write`） |
| `dump_camera.py` / `ls_camera.py` | 机身 dump 与目录列举 |
| `build_write_payload.py` | 重编 `flash_write.elf` 并更新 manifest |
| `check_publish.py` | 发布前扫描：仓库与 zip 里有没有固件/备份/密钥/ProductInfo/照片/抓包/日志（`--zip` 连带检查发布包） |
| `make_release.ps1` | 打发布 zip（剔除 `.data`、自检 json） |

### 15.3 诊断脚本（`.data/scratch/`，不进仓库）

`live_dev.py`（枚举 PID）、`live_check_units.py`（CP/矩阵/BACKUP 三方比对）、`live_repair.py`（块级修复）、`live_diff.py`（逐字节比对）、`live_cc085.py`（识别当前 CC 系数并写新档）、`live_state.py`、`cube_*.py`（.cube 解析/域解释/色相统计）、`rate_*.py` / `verify_rate*.py`（矫正率复算）。

### 15.4 文档（`docs/`）

| 文档 | 内容 |
|---|---|
| `AI-HANDOFF.md` | **本文**（接手第一站） |
| `LOOK-COLOR.md` | 颜色机制、pair 基函数、四卷实验、能力边界 |
| `LOOKS.md` | 配方、§9 验收表、§7.1 菜单文字 |
| `CALIBRATION.md` | 矫正率口径、官方 LUT 审计、样本量与分带误差 |
| `VALIDATION.md` | 真机验收记录（含 USB 掉线、冷启动、关机等待） |
| `CC-CN-PLAYBOOK.md` | 操作手册（怎么拍、怎么还原） |
| `ARCHITECTURE.md` | 分层与模块表 |
| `FEATURES.md` | 现有功能逐条说明（对应 README 功能状态表） |
| `PROGRESS.md` | 开发进展速览（新功能 / 优化 / 可行性不通过） |
| `BUILD.md` / `PUBLISHING.md` / `RELEASE-NOTES.md` | 构建、发布（含不上传清单与标题规范）、版本记录 |
| `UI.md` | 界面排版规则 |
| `DIAGNOSTICS.md` | blocked 诊断与取证（0.3.8）：issues 五个 kind 的字段、界面落点、诊断包结构、验证与缺口、以后怎么扩 |
| `KNOWN-AND-GUESSES.md` | 2026-10-27 的全量「已知 / 猜想」：0x10000004 六条假设与 probe5 日志解码表、相机侧机制、变砖与恢复素材、已证伪清单、红线、证据索引（换对话先读这一份） |
| `CP-PARTITION.md` / `FIRMWARE-MAP.md` / `PERSIST-STORE.md` / `FLASH-WRITE.md` | 底层调查 |
| `FL23-INVESTIGATION.md` / `FL2-ROUTE.md` / `FEASIBILITY-FL23.md` / `CPAPP-STATIC.md` | FL2/FL3 与 cpapp 静态分析 |
| `CARD-SPEED.md` | 卡速等级与 caution 表 |
| `BREAKTHROUGHS.md` / `ROADMAP.md` | 结论与路线 |

---

## 16. 未提交改动

> 工作树的当前分堆见 **§0.4**（权威）。本节只留索引，别再按这里的旧数字判断。

- `HEAD = 4a3e30c`，与 `origin/main` 同步；已 push 的三个提交全是 README（`3845574` / `cd09525` / `4a3e30c`）。
- 本地还有 ` M README.md` 一行（§0.8 第 1 条）、` M packaging/必读.txt`（只进 zip），以及 §0.4 表里的三批代码/文档改动，全部未提交。
- 0.3.8 的诊断层（另一个会话）：新增 `src/a6700win/diagnostics.py`、`tests/test_diagnostics.py`；改 `gui/pages.py`、`gui/about_page.py`、`inspect_once.py`；细节见 §21。
- 0.3.8 本批：见 §0.3 A–J。
- 0.3.9-probe1 取证批（2026-10-26 晚）：新增 `src/a6700win/runlog.py`、`tests/test_runlog.py`；改 `__main__.py`（`runlog.start`）、`dump.py`（`select` 支持 `missing`）、`patches.py`（`_stale_paths()` 含 `/tmp/jiritsu/libJit.so`、`_clear_stale_temp` 逐条上报）、`diagnostics.py`（「运行日志：」行、`_recent_logs` 截尾不丢弃）、`gui/widgets.py`（`LogBox.log` 同步落盘）、`version.py`（`0.3.9-probe1`）、`tests/test_patches.py` / `tests/test_config_selfheal.py`。验收 `124 passed / 1 skipped`。详见 §22。
- 0.3.7 的内容（配置写入自愈 + `--inspect-once`）在 `3e3e676`；发布守卫在 `77be7be`；Release 标题与正文的三轮改写在 `454a62f` / `60a4ba3` / `98a01ed` / `1b1352b` / `0d7d3de`。
- 未跟踪垃圾别提交：`GitHub端下载/`、`.local/`、`README.md.fmt`、`README.md.new`。

---

## 17. 同代项目调研（A7C2 / A7R5）

> 目的：看同代另外两个机型已经做到什么程度、走哪条通道，判断哪些结构能搬到 6700、哪些是死路。
> **结论先说**：A7C2 和我们走同一条 USB 服务会话通道（054C:0E8A → 054C:0336），但在「机内色表的层数」与「程序身份 + 原厂区域还原」上比我们成熟，结构可搬；A7R5 走的是整包重签 + SD 升级，**不可搬**。
> 本地副本：`refs/a7c2-fl23` = QAQLeonard/a7c2-fl23-research v3.0.3 全仓（HEAD `7827856`，2026-10-23）；`.data/research/r5` = Hearts-Ace/sony-a7r5-custom-firmware 稀疏克隆（只取 analysis / publication / filters / tools）。`refs/` 是只读上游，**不要改**。

### 17.1 两个项目现在到哪了

| | QAQLeonard/a7c2-fl23-research | Hearts-Ace/sony-a7r5-custom-firmware |
|---|---|---|
| 体量 | 630★ / 91 fork，仓库 139 MB，526 blob（381 个 py） | 42★ / 5 fork，仓库 5.8 MB |
| 版本 | v3.0.3（2026-10-23；v3.0.0–3.0.2、v2.2-preview.1、v2.1 均已发） | v4.28（2026-10-24；按用户要求回退 4.25 并移除更新操作） |
| 支持 | **只认 ILCE-7CM2 固件 2.01**，其它机型拒绝连接 | ILCE-7RM5 |
| 通道 | USB 服务会话：MSC `054C:0E8A` → 认证 → 等 `054C:0336` → 再认证 → 读写 `/usr/lib/appFw.so` / `/cp/cpapp-b.bin` | RP2040 `uart_boot` → fastboot → 刷 partition1（verifykey skip）→ 整包重签 `BODYDATA.DAT` → SD 卡升级 |
| 已做出来的功能 | FL2/FL3 加入/移除；六个自订外观（`.a7look`，含机内名称）；DCP/CUBE 离线转 `.a7look`；Lightroom 插件按槽自动套 DCP；电子快门声（音频/视频片段 0.01–2 s）；竖屏显示；恢复原厂 | 富士九款滤镜（原厂基底不动、自定义滤镜独立选择）；129 点 gamma；5×9×9 网格；菜单项；R5ColorLab 拟合工作台 |
| 自述边界 | 只在一台机上验过；macOS 真机 USB 未验证；65 点 LUT ≠ 机内 65³ 精度 | 公开源码不自足（缺原机镜像、签名身份/私钥、部分依赖）；拟合覆盖 42/256、留出 RMSE 3.696，外推不等于原厂 ISP |

同代机型各自独立成项目（A7C2 README 的「支持的机型」表）：A7CR `lzh2016zzz/a7cr-fl23-research`、A7CR `injectiver/a7cr-creative-look-tools`、A7 IV `DavidBuchanan314/ILCE-7M4-RE`（固件逆向笔记）、A6700 `xyzhangxin/sony-a6700-powerful`（我们）、A7 V `751K/sony-a7m5-looks`（只做 LR/C1 配置文件，不改相机）。**没有跨机型的通用工具**——每家都在自己机型的固件上重新定位偏移。

### 17.2 A7C2 的底层逻辑（同一条路，走得比我们远）

**① 会话与机身绑定。** 普通 MSC 进去后认证，等到 `054C:0336` 再认证一次，然后用属性 `0x00e70003`（十六进制文本的序列号摘要）把会话绑到具体机身；0336 不出现就冷却 30 s 重试、最多 3 次；认证没到 0336 之后**不再发任何命令**。`src/looks/looktool/checkpoint.py` 的 `same_body()` 比对 `serial_sha256` / `usb_serial_sha256`，不符即 raise `'Checkpoint belongs to a different body, or body identity is missing'`。
对照我们：`cp.session()` 直接 `run_authentication(0x0336)`，**没有任何机身绑定**（多设备唯一性至今是未验项，见 §13）。

**② 载荷形态：补丁字节编译进 ELF，不落数据文件。** `src/camera_runtime/native/installer.c` 头注释原文：`'Fixed-window, inode-preserving installer/restore worker. No raw flash, arbitrary files, process memory writes, shell, Backup settings or WBI. Mode0 only checks originals; mode1 installs; mode2 restores originals.'` —— `#include PATCH_MANIFEST` 把 `patch_manifest.h` 里的 `old_0[]/new_0[]` 编进 `.rodata`，结构 `struct Window {u64 offset;u32 length,chip;const u8 *before,*after;};`，`path(i)` 返回 `i ? '/cp/cpapp-b.bin' : '/usr/lib/appFw.so'`，用 syscall 67 `exact_read` / 64 `exact_write`（68 pwrite、EINTR 重试 3 次）、自算 SHA256、`mount_state()` 校验 `/proc/mounts` 里唯一条目前缀 `'/dev/nflasha15 /usr ext2 '` 与 ro/rw，结果写 `/tmp/jiritsu/a7c2.install.result`。
→ 跨 USB 只传这个 `.so`。我们的 `flash_write.elf` 相反：ELF 只带逻辑，145 KB 的 UXC 必须当数据从 `/tmp/jiritsu/tmmc.dat` 送（见 §9、§11.4）。两条都成立，差别是「.so 体积换数据文件」。

**③ 还原不靠用户备份：原厂区域随程序身份一起发布。** `src/looks/assets/factory-regions-2.01.json`（schema `a7c2-factory-regions/1`，model `ILCE-7CM2` / `2.01`，scope 自述「只含本项目会改的区域，不是整份固件或机身标定」）：`appFw.so` **99,960,744 B / 24 个区域**、`cpapp-b.bin` **18,090,880 B / 39 个区域**，每个区域是 `{offset, bytes, zlib_base64}`。身份门是 sha：`replace_tables()` 要求 `sha(ap)==AP_SHA` 且 `sha(cp)==CP_SHA`，否则 raise `'Six-table adapter requires the exact documented full7-v4 AP/CP pair'`；`identify_ap()/structural_ap()` 不匹配即 raise `'Unsupported AP identity; no firmware/settings writes performed'`。
→ 我们目前靠 `.orig` 备份 + 出厂 profile 表，缺「程序身份」这一步；好处是写错机型的概率比我们低。

**④ 机内色表是四层，我们只用了最浅一层。** 尺寸（`src/looks/looktool/photoformat.py` / `native.py`）：

| 层 | 字节 | 结构 | 6700 是否有对应物 |
|---|---|---|---|
| gamma | 576 | 129 个节点（`WIDTHS=(32,32,64,128,256,512,1024,2048,4096,8192,16384,32768)` + 12 个分段 shift，`0x204..0x210`），端点元数据 `0x220` | 未找到（§14 的 9 条 1024 B 斜坡是死数据） |
| 矩阵 | 576 | 16 selector × 6 个 s16 + `row_sums` 展开 3×3 | **有**：`0x02A4000D` `0x1e0 + slot*768` |
| 色度 | 64 | 12 组 (Cb,Cr) int16 + 8 个调整值（`expand_chroma(record, adjustment=(0,)*8)`） | **有**：`0x02A40001` `0x1250 + slot*64` |
| 网格 | 1215 | 405 节点（5×9×9）× 3 平面 signed 7-bit，BT.601 limited-range YCbCr 坐标 | 静态没找到（§17.4） |

`CHROMA_BYTES=64` 与我们 CP 里「12 组 (Cb,Cr) + 8 个 0」同尺寸 → **两机色度记录同构**，这是最硬的一条对齐证据。

**⑤ 写入偏移（CP 内部相对位置，可直接照抄）。** `src/looks/looktool/direct.py` 的 `color_regions()` 原文：

```python
for parameter, slot in ((55, 23), (56, 25)):
    result[checkpoint.CP_KEYS[0]] += [(0x1200 + parameter, 1), (0x1250 + slot * 64, 64)]
    result[checkpoint.CP_KEYS[1]] += [(0x196 + parameter, 1), (0x1e0 + slot * 768, 576)]
```

即：色度参数 `0x1200+55` / `0x1200+56` 各 1 B，记录 `0x1250+23*64=0x1810` / `0x1250+25*64=0x1890` 各 64 B；矩阵参数 `0x196+55` / `0x196+56` 各 1 B，记录 `0x1e0+23*768=0x46e0` / `0x1e0+25*768=0x4ce0` 各 **576 B（768 只写前 576）**。与我们笔记里的布局逐字一致 → §14 的「同构」得到独立确认。
**推论（未验证）**：矩阵 768 = 576 + 192，尾 192 很可能是 16 selector × 3 通道 × 4 B 的 row_sum，这正是 §12.1「block 4 整块填 20000 只影响蓝端」的机制来源。

**⑥ 六槽自定义外观 = 数据区 + 三处 AP 补丁点。** `src/looks/looktool/six.py`：
- 数据：`TABLE_FILE=0x8000`、`PREFIX_VA=0x110000`、`TABLE_VA=0x110020`、`TABLE_BYTES=1215`、`MAGIC=0x364c3741`（字节 `'A7L6'`）、`VERSION=0x10006`，头 32 B = magic + version + 6 个 FNV-1a 校验，紧接 6 × 1215 B；`ORDER=['Classic Neg.','Classic Chrome','Nostalgic Neg.','Eterna','GR Positive Film','GR Negative Film']`。工厂状态这片区域全是零。
- AP 侧（`device_layout.py`）：converter 模板 `0x35287f0`（132 B，原厂首字节 `1f 40 00 71 81 00 00 54`）、title_branch `0x1b5cd7c`（4 B，原厂 `fd 03 00 91`）、map `0x4c7cf7c`（12 B，原厂 `12 00 02 04 06 08 0a 0c`）、label id `0x59896f0 + i*0xb8`（i<6，原厂都是 `u32 0x0200A302` → 改成 `0x0200AB2C+i`）；另有 `0x48cfa83`(38 B) 是 `/usr/sha…` 路径串、`0x3060a24`(16 B) 等。
- 身份与自检：`AP_SHA=690b5f17f21cba5c7cd937e6feb0f6967ea2793c0b4ca6fc1fffdcaa1ed0d761`、`CP_SHA=90d1ed6d47df21c881936816647973b1562764458122eb72869e60b1a624900b`、`CP_SWITCH_SHA=100e286f…`；写后 `read_tables()` 复核 FNV 校验，并做 `apply(apply(before,fwd),rev)==before` 的互逆检查。
- cpapp 侧 39 个区域里值得记的：`0x8000`(7,322 = 32+6×1215)、`0x20140`(4 B，原厂 `80 1b 14 00` = 长度 `0x141B80`)、`0xb27490`(2,844 全零)、`0x1100b80`(3,872 全零)、`0x1101ae0`(1,216 全零) —— 后三个是运行时填的数据区。

### 17.3 A7R5 的底层逻辑（完全不同的一条路，别照抄）

- **入口是硬件**：RP2040 `uart_boot` 固件（GPIO28→相机 RX、GPIO29→TX、GPIO27→复位、OPEN_DRAIN、48000 波特）→ 相机复位 → 发临时 SRAM 载荷（sha256 `330ac322bd0e40a7bb4974f69a2667e7d59a25e59c1322339690f30a3ceadbdc`）→ 切 115200 收输出 → 进 **fastboot**（判据 `usb_transport_verified=true` 且协议 `OKAY0.5`）。
- **然后改信任链**：刷改过的 **partition1（verifykey skip）**，再**重签整包** `BODYDATA.DAT`（754,525,608 B，sha256 `dd64c0d26cf71d3b595dcf20cf11d39abdff8f78eadd7241a833182d28e03816`）走官方 SD 升级。滤镜 BIN 22,196 B，sha256 `5700b9dd8c1390ac851528f01be1776034d6b8fb66287cfffb3600351af38a93`。四个核心脚本：`run_r5_m4strict_personal.py` `658afda1…`、`deploy_r5_m4strict_personal.py` `e189cda6…`、`r5_settings_ram_boot.py` `80b79977…`、`build_r5_m4strict_personal.py` `a95187c2…`。
- **滤镜 BIN v4**：magic `R5CUST4` + 零尾，128 B 头、2,452 B 记录、最多 12 条 / 29,552 B；每条含完整 CC1 + block13 + 129 点 Gamma + 1215 B 强制网格；名称简写 24 B / 全称 64 B；选择存独立的 **24 B `R5FILTER.BIN`**（0 = 关闭）。Gamma 原记录 576 B，**只替换前 516 B（129 点），尾 60 B 原样保留**。
- **1215 与 1620 是同一张表**：405 节点 × 3 通道；1215 是有符号字节（−64..63），1620 是打包成 405 个 32 位 word。项目自己的自纠表里专门记了这条 —— 别再当两个东西。
- **代际生命周期**：暂存 NEW → fsync → 读回 → rename → 目录 fsync → SEAL → SELECT；CP 每代 522,152 B，16 代 ≈ 7.967 MiB；AP 最多 16 个不可变名称代际；controller 边界 `0x719F16` 捕获 generation/slot/level；每代 32 物理项、最多 31 个 READY。
- **菜单项**：自定义滤镜 MID `0x635`（原表 1589 项、键 0…1588 不含 1589，4.23 的 CA4 回退就是这个 bug）；4.24 在 `0x1BD9B9C`（经 facade+0x748 调 `0x1BD2020`）加 24 字节 wrapper，RX 尾扩 24 B，不改文件大小、不动动态重定位。
- **为什么 6700 学不了**：这条路的前提是「能重签整包」= 原始 DAT + verifykey 分区补丁 + 签名身份；我们的 `BODYDATA-2.00.dat` 是加密容器（12 种 Sony-PMCA-RE crypter 全解不开，§13），也没有对应硬件入口。**路线 C 直接划掉。**

### 17.4 本机实测（2026-10-25 复核，A6700 侧）

- `firmware/cp/cpapp-b.bin` 与 `firmware/cp/cpapp-live.bin` 完全同一份：**17,892,024 B**、sha256 `43c5d056ed935795…`；前 8 字节 `04 10 9f e5 04 10 81 e2`（= `ldr r1,[pc,#4]` / `add r1,r1,#4`，不是 `\x7fELF`）→ 裸 ARM32 镜像，**文件偏移 ≠ VA 直接映射**。
- `0x8000` 起 **98,304 B 全零**，`0x20000` 才开始有内容（`d4 da 60 00 00 10 ae 01`）→ 六槽所需的 7,322 B 空间绰绰有余，**但空间存在 ≠ 机制存在**。
- `A7L6`（`0x364c3741`）在 cpapp 与 appFw 里都是 **0 命中**；`SET_LUT` 出现 8 次、`init_cc_3DLUT` 1 次 → 机内 LUT 机制在，但没有 1215 B 网格数据被加载。
- `firmware/appFw-2.00.so` = **89,027,992 B**、sha256 `721fceae…`（与 `flash.TARGETS` 的 appfw 一致）；A7C2 是 99,960,744 B → A7C2 的 `0x57c6710` / `0x59896f0` / `0x1100b80` 等地址**越过 A6700 文件末尾，绝对偏移一律不可平移**，只有结构可搬。
- 旧笔记里 A7C2→A6700 的差值 `−0x3E200`（`0x3528804 → 0x34e5604`）只在局部成立，**不能当全局基址**（按 A7C2 `0x57c6710` 直接反推会 struct.error）。

### 17.5 三条路（选哪条、怎么起）

> **本节已被 §18.6 取代**（2026-10-25 晚）：同机型项目 `Himpq/FireHydrant` 已在固件 2.00 上真机做出 FL2/FL3，路线 A / B 的措辞与前置条件作废。保留本节作为当天白天的判断过程，别照着它开工。

- **路线 A（推荐先做，最小代价）**：把外观从「色度一层」扩到「色度 + 矩阵两层」。做法：沿用 `0x1e0 + slot*768` 的前 576 B（3 平面 × 16 selector × 6 个 s16）当拟合自由度，把 A7C2 `native.py` 的方法搬过来——`equations()` 组正规方程、`smoothness()` 加相邻节点差分正则、`constrained_fit()` 做 IRLS 投影到 ±64（300 epoch、收敛 1e-4），目标仍是 §8.1 的 12 档向量。**蓝端从此有解**：不用再赌色度层（§8.4 已封）。
- **路线 B（第二步，收益最大）**：六槽自定义外观。第一步不是写代码，是**静态定位三件事**：① A6700 appFw 里 look→CP converter 模板（候选起点 `0x34e5604`）；② 名称 label id 的写点（A7C2 是 `0x59896f0 + i*0xb8`，值 `0x0200AB2C+i`）；③ CP 里 1215 B 表的实际地址与 stride。判据：在 89 MB 的 `appFw-2.00.so` 里找与 A7C2 那 132 B 模板同构的序列（原厂首字节 `1f 40 00 71 81 00 00 54`），再用 §6 的固定窗口读回比对。
- **路线 C（不做）**：整机重签，见 §17.3 末段。

### 17.6 明确不要做的（省得再试一遍）

- 不要照抄 A7C2 的任何绝对偏移到 A6700（`0x57c6710` / `0x59896f0` / `0x1100b80` / `0x1101ae0` 全都不成立）。
- 不要以为 `0x8000` 那片零空洞本身就能启用六槽（缺的是代码路径与 label id，不是空间）。
- 不要用 A7R5 的「整包重签」思路（容器解不开，且需要改装线与签名身份）。
- 不要重复测「色度层压蓝端」（§8.4 已封；`pair1` 会把青蓝推向 1.37）。
- 不要把 A7C2 的 checkpoint 还原机制硬搬（它靠整份程序身份 + 完整性比对，我们只有 260 扇区 / 133,120 B 的固定窗口，没有对应通道）。

---

## 18. 同机型项目：Himpq/FireHydrant（A6700 侧）

> 这是目前**唯一在同机型（ILCE-6700 / 固件 2.00）上真机做成 FL2/FL3 与 Cine EI** 的公开项目。凡它和我们的旧结论冲突，以它为准——每条我们都在本机复核过（§18.4）。
> 仓：`Himpq/FireHydrant`「a6700 firmware research」· Python/C · 5★ · **无 LICENSE**（引用结论注明出处，别整段抄代码）· 仓 111 KB · 2026-10-20 建，最后 push 2026-10-25。
> 本地副本：`.data/research/firehydrant`（54 文件 / 196,782 B；从旧盘 `D:\DSH Desktop\Project\.data\research\firehydrant` 搬入）。
> 文件：`README.md`、`DEVICE_CHANNEL.md`、`fl2_fl3/`（`README.md`、`FL23_DETAILS_2026-10-25.md`、`delta/{cp.delta,cpdelta.py,cpdelta.c,build.py}`）、`cine_ei/`（`README.md` + 3 篇 doc）、`wbi/`（5 个 native 模块 + `host/{jiritsu.py,wbi.py,apfl23.py}`）。

### 18.1 它做到哪一步（两件，都真机验过）

1. **FL2/FL3 移植**：三层同时改（appFw 112 B 转换窗口 + cpapp 33 窗口 delta + CP 单元两个空槽），之后在菜单里选中那两个**自定义位**，像素上就是 FL2 / FL3。菜单文字仍是旧名——它也主张接受旧名，不重做文字资源。
2. **Cine EI / Cine EI Quick 固化（V3）**：211 段 / 827 B 写进 `appFw.so`，往 RX 段尾追加代码并改 ELF 程序头；**必须先清 WBI 快照头再断电**，否则启动快照按旧段布局恢复（v1 就崩在这）。

### 18.2 通道层新增事实（`DEVICE_CHANNEL.md`）

- 往 `/tmp/jiritsu/libJit.so` 写文件即触发固件 `dlopen` 执行入口；模块 aarch64、`-shared -nostdlib`、入口 `_init`、只走裸 syscall（`svc #0`）。它把单次上传保守限制在 65,536 B（`MAX_TEMP`），**但我们真机单帧写过 145,708 B 成功**（§11.1）——那是它工具的上限，不是相机上限，别把我们的 `WRITE_BLOCK = 0x20000` 改小。
- **`/tmp/jiritsu` 在独立 flash 分区，断电不消失**。我们一直把它当内存临时目录；所以「会话开头清 `tmmc.jit` / `tmmc.dat`」不只是卫生习惯，遗留的 `libJit.so` 会被固件重放，必须当注入面处理。
- `appFw.so` 是私有映射：内存补丁触发 COW，**只改进程私有副本、断电即消失**——不是能力不足，是映射语义决定的。
- Jiritsu 的路径前缀检查在**主机侧客户端**完成，相机端不做规范化；通道不支持目录枚举，只能按已知文件名读。
- 状态码：`0x10000006` = 目标不存在；`CMD_REMOVE(18)` 的正文只能是 `\0\xff`（必须先 select 路径）；select 是 `\0` + 路径 + `\0`。

### 18.3 FL2/FL3 的三层（全表）

| 层 | 载体 | 落点 | 改动 | 生效条件 |
|---|---|---|---:|---|
| A 应用层映射 | `/usr/lib/appFw.so`（89,027,992 B） | `0x34E5604`（函数入口 `0x34E55F0`） | 112 B | 冷启动 |
| B 成像处理数据 | `/cp/cpapp-b.bin`（17,892,024 B） | 33 个窗口，最小 `0x135F0A`，最大 `0x10D02B8` | delta 9,536 B／实写 4,456 B／实变 2,080 B | 完整断电 |
| C 色彩参数单元 | `0x02A40001` / `0x02A4000D` | chroma 槽 23、matrix 槽 25 | 71 B + 840 B | 下次启动（`saveBackup(0x02a4)` 落盘） |

**A 层怎么改**：原实现是「索引表查表 + `ldrb` + 算跳转」（表基址 `0x40B6024`，正是 §14 记的那个地址）。改成前 8 条不动、加 `cbnz w1` 分流，然后 `cmp w0,#0xe` → `b.eq` → `mov w0,#0x13`（19 = FL2），`cmp w0,#0xf` → `b.eq` → `mov w0,#0x14`（20 = FL3）；`0x3c` 处放 12 B 表 `.byte 0x00,0x03,0x02,0x01,0x10,0x0f,0x11,0x12,0x05,0x0d,0x00,0x00`，其余 NOP 填满 112 B。语义：`selected = 14/15`（两个自定义位）+ `base = 0` → 走 CP mode 19/20。

**B 层 delta 格式**：`0x00 "A6700D01" | u32 version=1 | u32 count=33 | u64 原长 17,892,024 | u64 载荷长`，`0x60` 起 33 × 16 B 表（u64 偏移 / u32 长度 / u32 载荷内相对位置），之后每窗 before 接 after。相机内写入器 `cpdelta.c`：先**全量校验 before（一个字节都不写）**，再写 after、逐窗 `pread` 回读、fsync；七道自洽校验（magic / 版本 / count≤64 / 原长 / 布局 / 不越界 / 不重叠）。

**C 层**：目标槽必须**空且未被引用**。本机实测 `0x02A40001` 槽 22–27、30、31 全零，`0x02A4000D` 槽 20–31 全零 → 它选的 chroma 槽 23（`0x1810`）/ matrix 槽 25（`0x4CE0`）确为空槽。参数表在 `0x1200`（chroma）与 `0x196`（matrix），里头是「哪个槽被引用」的字节串。

**写序**：C → B → A（越难恢复的越晚写）。

### 18.4 本机复核（2026-10-25，全部对上）

- `firmware/appFw-2.00.so` 的 `0x34E5604` 起 112 B 反汇编**逐条等于**它记录的「原实现」（`cmp w1,#9` / `b.hi #0x34E5674` / `adrp+add #0x24` / `ldrb` / `adr` / `add sxtb#2` / `br`，随后 `mov w0,#3/#2/#1/#0x10/#0xf/#0x11/#0x12/#5/#0xd` 各接 `b #0x34E55FC`，末尾 `strb wzr,[x2]; ret`）→ A 层窗口可照写。
- ELF 头：`e_phnum=6`、`e_phentsize=56`、`phdr[0]`（PT_LOAD, flags `0x5`）`p_filesz=p_memsz=0x4488EED`（在 `0x60/0x68`）；`phdr[1]` 起点 `0x4489AA0` → **`0x4488EED` 后有 `0xBB3` 字节空洞**，Cine EI 那种「尾段追加 160 B」不用挪数据。
- `cp.delta` 解出 33 窗，**33/33 窗口 before 与本机 `firmware/cp/cpapp-b.bin`（sha256 `43c5d056…`）逐字节相同，after 命中 0** → 本机 cpapp 是干净出厂态，delta 可直接用（若 after 全中，说明已经打过）。
- 空槽与参数区：见 §18.3 C 层（由本机两个单元的字节确认）。
- WBI：`firmware/nflasha5-2.00.bin` 与 `nflasha5-after.bin` 各 314,572,800 B、sha256 同为 `56e0e220…`；头部 `WBI2`、sections 1314、`resume_vector 0x4004A67F0`、`dVersion 0x20060224`、`sector_size 512`、`r_data_size 248,291,328`、`o_data_size 273,801,216`、`kern_cksum 0x0F0F0F0F`（填充）→ **快照头仍是原厂有效态，没人清过**。

### 18.5 我们已有的写入能力 vs 还缺的

读完 `native/flash_write.c` 后修正一条旧判断：**remount 与窗口回读我们早就有了**，缺的是另外三点。

| 能力 | 状态 |
|---|---|
| 只读挂载下自动 remount rw（失败报 11，收尾 remount 回 ro） | **已有**：`open_writable()` 在 `EROFS(-30)` 时 `remount(where, 0)`，`write_and_verify()` 结束 `remount(where, 1)` |
| 任意偏移窗口写（非整文件） | **已有**：mode 3 = `pwrite64(offset + done)`；mode 6 = 顺序 `write`（某些文件系统拒绝随机偏移时用） |
| fsync + 独立只读句柄回读比对 | **已有**：`fsync` → `close` → 新 `O_RDONLY` 句柄 `compare_file()`，不一致返回 13 |
| 写前 before 全量校验 | **缺**：写入器直接写；需在 Python 侧 `flash.read_range()` 先比对，不符即中止 |
| `O_DIRECT` 复核 | **缺**：现在普通 `pread` 可能命中页缓存（FireHydrant 明确「普通读会看到旧值」） |
| 结构身份判据 | **缺**：我们比 sha256，它用 `p_filesz`（原厂 `0x4488EED` / V3 `0x4489230`）与 WBI `WBI2` + `sections=1314`，跨版本更稳 |
| 多窗口写序 + 整份回滚演练 | **缺**：A 层一处 112 B 好回滚；B 层 33 窗、C 层两单元要写「反向写回」，回滚后必须重跑 before 校验 |
| 模块注入（`libJit.so`） | **不需要**：我们的 `0x4010 / 0x4007 / 0x4008` ELF 通道干的是同一件事 |

### 18.6 修正后的路线（取代 §12.5 原三条与 §17.5）

1. **离线演练（零风险，先做）**：用 `cp.delta` + 112 B 在本机镜像副本上 apply → verify → restore，产出逐窗口 patch table，固化成我们自己的 `tools/` 脚本。
2. **真机 A 层**：`flash.write_block("/usr/lib/appFw.so", 0x34E5604, 112 B)`；写前 before 校验、写后 `O_DIRECT` 复核，失败即反向写回 112 B。
3. **真机 B 层**：`flash.write_windows("/cp/cpapp-b.bin", 33 窗)`（4,456 B，单会话够）；写完必须完整断电再验。
4. **真机 C 层**：`cp.write_unit` 写两个单元（splice 槽 23 / 25）→ `saveBackup(0x02a4)` → 断电重启验证。
5. **蓝端标定（§12.1）降为并行项**：FL2/FL3 通了之后「像不像富士」不再只靠色度层；蓝端改用矩阵层 `0x1e0 + slot*768` 前 576 B 做拟合，不再盲试 block 4。
6. **Cine EI 暂缓**：它要改 ELF 程序头 + 清 WBI 头（失去快照保护），风险比 FL2/FL3 高一个量级。

### 18.7 禁区（照抄，别试）

- 别把「清 WBI 头」当常规步骤：清了就失去快照保护，之后只有 USB 通道或官方恢复包；`nflasha5` 那两份 dump 是底牌。
- BIS / 固件更新走 `warm` 可能**重建 WBI**；正常关机是 `mem`。
- `--probe` 会把 C6 送进 BW mode 5，制造「C6 黑白」假象；A 层已 patched 后不要再跑 RAM 补丁。
- B 层回滚：当前是 selector0 时整文件回滚会 `before_mismatch`，必须先 revert 回 42 项候选。
- A 层写坏 = 主程序起不来、运行时通道同时失效，只有官方恢复包 → 所以写序是 C → B → A。

---

## 19. 更新记录

- **2026-10-25 17:47** · 建立本文件：真机状态（文字=英文 145,708/9fd0bb49；PT=pair2×0.60+pair6=0 仅在 RAM；BACKUP 仍 0.70）、蓝端结论、8 条踩坑、待办 6 项。
- **2026-10-25 17:55** · 扩写成完整交接：补 §1 项目背景、§5 Windows 路线与 PID 表、§6 协议/挂载/载荷细节、§7 单元布局与持久化语义、§9 UXC 格式与 rid 全表、§13 能力边界、§14 历史调查结论（LUT/cube/cpapp/卡速）、§15 文件地图。
- **2026-10-25 18:2x** · 查「只读检查 状态：04000010」：从源码复现不出来（三步探针全 OK，同会话连读 3 次 + 闲置 90 s 再读全 OK，GUI 全路径 headless 跑通得到「预计修改 0 字节」）。判断是一次性设备侧拒绝，与同日多次掉线同源。0.3.4 只做「下次能看懂」：`_windows_backend_file` 报出是哪一步（`配置写入（SET_FILE2）` / `载荷写入（SET_FILE）`）、file_id、状态字含义与恢复步骤（拔线 → 关机 → 取电池 1 分钟 → 装回 → 重连 MSC）。诊断脚本：`.data/scratch/live_inspect_steps.py`、`live_session_reuse.py`、`live_gui_inspect.py`、`live_inspect_plan.py`。同时版本 0.3.3 → 0.3.4（两套命名 + `/setting/` 白名单 + 状态码可读化）。
- **2026-10-25 18:5x** · 0.3.4 发布（Release `v0.3.4-win.1`，zip 45.7 MB / sha256 `93761bfc…`）+ README 顶部「功能状态」表与 `docs/PROGRESS.md`。随后用户要求「按开发进度表写下现有功能」→ 新增 **`docs/FEATURES.md`**（七节：机身功能 / 连接与驱动 / 外观与菜单文字 / 诊断自检 / 数据目录 / 命令行工具 / 明确没有的能力），并补一个真正的 CLI `tools/looknames_apply.py`（`--status` / `--apply --preset official|zh` / `--restore`，写入要 `--confirm yes-write`），README 的目录、功能明细、文档表三处加上 FEATURES.md 入口。`looknames._rows()` 现在把 profile 的 `label` 也带进报告，CLI 能显示「PT（人像）」。真机 `--status` 实测：145,708 / `9fd0bb49…` / renamed / 四条 installed / 基线 factory 145,612（8 份）。`pytest tests -q` → 86 passed / 1 skipped。
- **2026-10-25 19:0x** · 用户 m10336「颜色和名字一次写入继续做」→ 新增 **`src/a6700win/bundle.py`**（两段会话编排 `apply` / `restore`、部分失败报告、`summary()`）、GUI「一次写入：颜色 + 名字」卡片（两按钮 + 结果日志 + 预设联动）、CLI `tools/bundle_apply.py`、`tests/test_bundle.py` 7 个用例；`cp._cooldown` 改成每 10 秒报剩余秒数、末尾报「冷却结束，重新连接相机…」。版本 0.3.4 → **0.3.5**。`pytest tests -q` → **93 passed / 1 skipped**。README / FEATURES / 本文同步；真机验收未做（清单在 §9.5）。
- **2026-10-25 19:4x** · 真机事故收尾：0.3.5 的一次写入把语言资源写成半截（145,692 B，前 131,072 字节新版、尾巴旧版），之后连接一律在认证第一个包挂掉（`[Errno 32] Pipe error`），60 s 冷却无效 → 结论是相机进入了「一次上电只给一个服务会话」，绕开的办法是把动作压进单个会话，彻底恢复要拔线 + 关机 + 取电池 1 分钟。修复与验证：`.data/scratch/repair_oneshot.py official` 单会话内 `truncate` 145,692 → 145,708 + 一帧写完 145,708 字节（约 13 次往返）+ 整份回读，结果 `145708 B 9fd0bb497171 一致` 并登记基线（kind=renamed）→ **145,708 单帧可写，旧笔记的「Jiritsu 64 KiB 上限」被推翻**；随后 `.data/scratch/color_fix.py` 单会话把四条外观颜色写回配方，读回全部「配方在位」，名字仍是英文原名（CC=Classic Chrome / NC=Classic Neg. / PF=Positive Film / NF=Negative Film）。代码：`flash.WRITE_BLOCK = 0x20000`（`BLOCK = 0x8000` 只留给读）、`looknames._write_blob()` 改成 truncate → 分块写（载荷侧 pwrite/fsync/回读）→ 长度复核、`tests/test_flash.py::test_block_limit` 改用 `WRITE_BLOCK + 1`。文档：本文 §11.1 扩成四条、`docs/VALIDATION.md` 新增整节、`docs/FLASH-WRITE.md` 块上限改写、`docs/RELEASE-NOTES.md` 新增 0.3.6 节。版本 0.3.5 → **0.3.6**。`pytest tests -q` → 93 passed / 1 skipped。
- **2026-10-25 20:0x** · 0.3.6 发布后用户在界面点只读检查，报「配置写入（SET_FILE2）」被拒（`0x10000004`）。这次定位到机理：`0x4010` 配置写入与我们的载荷共用 `/tmp/jiritsu/tmmc.jit`、`tmmc.dat`，上一次会话没干净结束时残留会让下一次被拒。删除命令的正确报文（A7C2 同款）是「先 select 目标路径，再发 `CMD_REMOVE`（18）且正文只有 `\0\xff`」——直接把路径塞进 `CMD_REMOVE` 会被拒成 `0x10000201`（真机实测）。做成自愈：`patches._windows_backend_file` 遇到 `0x10000004` 清一遍再重试一次；`cp._clear_temp` 在每个相机会话开头清一次；新增隐藏参数 `--inspect-once`（`src/a6700win/inspect_once.py`），用与界面相同的 controller 路径跑一次只读检查并把结论落 JSON，源码与冻结包都能用。真机复验：两个临时文件删除均 `True`、同会话整份只读读取 `260 块 / 133,120 字节`、`--inspect-once` 输出 `status: inspected` / `compatible: true` / `write_attempted: false`。新增 `tests/test_config_selfheal.py`（3 个用例），`pytest tests -q` → **96 passed / 1 skipped**。版本 0.3.6 → **0.3.7**。
- **2026-10-25 20:1x** · 0.3.7 发布（`v0.3.7-win.1`，zip 47.9 MB / `6dd1c13b…`，唯一资产）；README 下载区对齐。随后用户要求「不上传固件、私人备份、密钥、ProductInfo、照片、原始抓包、完整日志」→ 全仓库审计（248 个跟踪文件、701 个历史路径、超长十六进制 0 命中、本机路径 0 命中）+ 5 个 Release 资产逐个读中央目录（264 / 291 / 291 / 291 / 291 条目，违规 0）；规则固化为 `tools/check_publish.py`（干净时 exit 0）、`.gitignore` 补 16 类路径、`docs/PUBLISHING.md` 新增硬规则第 4 条。提交 `77be7be`。
- **2026-10-25 21:0x–22:1x** · 用户连续三轮纠正 Release 标题写法：①「按照功能来写」②「根据改动内容简洁写」③「写版本号加解决问题的简述，过一遍 humanlizer」④「不写 V 了或者大写 V 都行」。最终规范：**`版本号 · 一句话说清解决了什么问题`，不写 v 前缀，正文 = 现象 + 3–5 条改动 + 适用范围**（`docs/PUBLISHING.md` 第 7、8 条，`docs/RELEASE-NOTES.md` 开头也有同一段）。五个 Release 的标题与正文都按这套重写（`gh release edit`，tag 不动）。标题示例：「0.3.7 · 修好只读检查中途报错的问题」。提交 `454a62f` / `60a4ba3` / `98a01ed` / `1b1352b` / `0d7d3de`。
- **2026-10-25 22:2x** · 交接检查：工作区干净、`main` == `origin/main`（`0d7d3de`）、五个 Release 标题符合新规范、`tools/check_publish.py --zip` 输出「干净：…」、`pytest tests -q` → 96 passed / 1 skipped、`dist\Powerful6700-Windows-x64.zip` 47,925,929 B / sha256 `6dd1c13b…` 与 Release 资产一致、`version.py` = 0.3.7。本文 §2 / §10 / §12.4 / §15.2 / §15.4 / §16 按当前真实状态更新（§10 把「pair2×0.60 只在 RAM」那条旧结论改成实测过的「RAM == BACKUP == `b0cab23b…`」，并补上「相机最近一次枚举 0x096F」）。
- **2026-10-25 22:35** · 新增 §17「同代项目调研（A7C2 / A7R5）」与 §12.5 两条新路。A7C2（630★ / v3.0.3 / 2026-10-23，只认 ILCE-7CM2 2.01）走的是和我们同一条通道（MSC 054C:0E8A → 054C:0336），可搬的四件：机内色表四层尺寸（gamma 576 / 矩阵 576 / 色度 64 / 网格 1215）、CP 写入相对偏移（色度 `0x1200+55/56` 与 `0x1250+23*64`、矩阵 `0x196+55/56` 与 `0x1e0+23*768` **只写前 576**）、六槽存储 `0x8000` 起 7,322 B = 32 + 6×1215 与 AP 三处补丁点（`0x35287f0` converter、`0x1b5cd7c` title_branch、`0x4c7cf7c` map、`0x59896f0+i*0xb8` label id）、factory-regions 原厂区域还原 + 机身绑定（属性 `0x00e70003`）。A7R5（42★ / v4.28 / 2026-10-24）确认是 RP2040 `uart_boot` → fastboot → partition1 verifykey skip → 整包重签 `BODYDATA.DAT`（754,525,608 B），**不可搬**。本机复核 A6700 侧：`firmware/cp/cpapp-b.bin` 17,892,024 B / sha256 `43c5d056ed935795…`（前 8 字节 `04 10 9f e5 04 10 81 e2` = ARM 指令，不是 ELF）、`0x8000` 起 98,304 B 全零、`A7L6`（`0x364c3741`）在 cpapp 与 appFw 中均 0 命中、`SET_LUT`×8 / `init_cc_3DLUT`×1、`appFw-2.00.so` 89,027,992 B（A7C2 为 99,960,744）→ **A7C2 绝对偏移一律不可平移，只有结构可搬**。
- **2026-10-25 23:10** · 研读同机型项目 `Himpq/FireHydrant`（已克隆到 `.data/research/firehydrant`），新增 §18 并**直接改写被推翻的结论**：①「FL2/FL3 不可行」作废（A 层 appFw `0x34E5604` 112 B 把 `selected=14/15` 映射到 CP mode 19/20；B 层 `/cp/cpapp-b.bin` 33 窗 delta；C 层 CP 单元空槽 71 B + 840 B）；②「没有影调层 / 0.148 是模型极限」作废（0.148 只是色度一层的极限，影调靠 cpapp 42 项模式表 + 槽参数）；③「外观八参数不在 CP 单元」作废（按槽存在单元里，具体字节未定位）；④「需要新写窗口」不成立（文件走 `/usr/`、`/cp/`、`/setting/` 白名单，不受 260 扇区限制，`flash_write.c` 已能任意偏移写 + 自动 remount + 回读）。本机复核全通过：112 B 反汇编逐条相符、`cp.delta` 33/33 窗口 before 相同、空槽确认、WBI 头仍原厂态（`WBI2` / 1314 / `resume_vector 0x4004A67F0`）。同步修订 `docs/FL2-ROUTE.md`、`docs/ROADMAP.md`、`docs/FEASIBILITY-FL23.md`、`docs/LOOKS.md`、`docs/CALIBRATION.md`、`docs/PROGRESS.md`、`docs/ANNOUNCEMENT.md`；路线重排见 §18.6，新待办 §12.6。 另：§17.5 顶部加「已被 §18.6 取代」指路，§10 补一条「固件镜像仍是出厂态」的复核行；`FL2-ROUTE.md` §5 的「没有落点」加修订注（donor 数据落在 CP 空槽）、§9 标题标注已被 §18.6 取代，并修掉旧的 `（`+小节号 断排版。
- **2026-10-26 深夜** · FL2/FL3 移植在本机做成了（B 层 33 窗 1.3 秒 + A 层 112 B → 外观菜单 14 → 16 项，新增项显示名 `5VV2` / `6BW`），但静拍路径不成立、FireHydrant 的 `+55`/`+56` 说法未能复现；随后把 cpapp `0x10D02B8` 归零导致相机黑屏无限重启。新增 §20 记录全过程、恢复素材与接手步骤；完整细节见 `docs/FL23-FULL-RECORD.md`（492 行）。

---

- **2026-10-26 08:05** · 0.3.8 现阶段交接：新增 §0（一句话现状 / 仓库与发布面 / 这批改了什么 A–F / 工作树三批改动怎么分 / 验收命令与坑 / PUBLISH-RISK-REVIEW 的 P0 逐项状态 / `0x10000004` 判读口径 / 下一步顺序 / 接手硬约束）。代码侧：`notices.py` 两条风险 section + 首屏须知合并、`looks_page.py` 一次做完加锁（Ghost + 默认禁用 + 确认勾选 + 写入前弹窗默认「先不写」+ 每次写完重锁）、`patches.py` `0x10000004` 自愈（先清 `/tmp/jiritsu` + 被拒后无条件清一次并重发一次）、8 个文件界面文案口语化、`gui/pages.py` 功能状态备份卡加「打开备份目录」、`version.py` → 0.3.8。验收：pytest 113 passed / 1 skipped、`--render-pages` 7 张 PNG（phase=notice、ready=true）、`tools/check_publish.py` 干净。**未提交、未 push、未打包；全程没碰相机。** README 三处 P0 仍未落树（改写稿是 `docs/README-0.3.8.md`）。

- **2026-10-26 08:25** · 0.3.8 文案收口：界面里「自己反复重启」全部改成「重复重启变砖」（`gui/looks_page.py:107`/`:494`、`notices.py:37`、`patches.py:279`）；把上游 `硬件说明.md`（RP2040 Pico + USB-C 24P 测试板冷启动注入，不用拆机）接成四个入口——首屏第 1 条风险的 `source_url`/`link_text`、`gui/about_page.py` 的「硬件说明（救砖）↗」、`patches.py` 报错尾部、`docs/README-0.3.8.md` 四处；`gui/widgets.py` 的 `DocLink` 改成优先读 `link_text`。测试：`tests/test_patches.py` 断言改 `"变砖"`，新增 `test_notice_links_the_upstream_hardware_recovery_guide`（`QToolButton.clicked` 在 PySide6 里不带参数，要 `clicked.emit()`）。验收：`pytest` **114 passed / 1 skipped**、`--render-pages .data/tmp/shots10` 7 张 PNG（phase=notice、ready=true）、`check_publish.py` 干净。坑：这台机器上 `python -m pytest` 现在稳定在全部通过后卡住解释器退出，用 `.data/tmp/run_pytest.py`（`pytest.main` → `os._exit`）才拿得到结果。未提交、未 push、没碰相机。
- **2026-10-26 09:xx · 用户 m00391 三条收口** · ①「前提是相机还能进服务模式」对外行是术语外泄：`服务模式` 是认证后的 USB 会话（PID `0x0336`，程序自己切，用户不用手动进，见 `usb/driver.py:45`、`research.py:49`），机制没错但要换人话——用户可见文案先改成「前提是相机还能开机、还能用数据线连上电脑」（`gui/looks_page.py:507-508` / `:514-515`、`gui/pages.py:764`、`notices.py:40`），没有弱化成「一定能还原」；随即用户 m00488 指出准数词是 **MSC**——所有写入的第一道门都是「找到唯一的 MSC 相机」（`usb/windows_auth.py:228-242` 两段式认证 MSC → `0x0336`；`gui/looks_page.py:67`/`:403`、`gui/driver_page.py:121` 早就这么写），于是四处文案再改成「插上数据线还能被认成海量存储器（MSC）」。②删掉「还原是退路…不该再添摩擦」这类理由句（本文件 §0.3-H、`docs/RELEASE-NOTES.md`、`docs/PROGRESS.md`），只留「还原路径不加弹窗」这个事实。③`README.md` 按 `refs/a7c2-fl23/README.zh-CN.md` 的格式口吻整篇重排、只留中文版：去掉顶部四个 `###` 子标题与 shields，`冷重载`→「断电重开」，`/usr`→「固件分区」，`约 140 KB`→「约 142 KB」，新增常见问题表与「还原也要先连得上相机」一行；新稿先落 `.data/tmp/README-new.md` 再覆盖两个文件（34,888 B / 366 行，逐字节一致）。验收：`pytest` 116 passed / 1 skipped。**包需重打。**
- **2026-10-26 白天 · 0.3.8 收尾到发布** · 两处 P0（写入前确认框摊开分区/字节/回滚、失败页三步自救）落地并补两条 GUI 用例（`pytest` 116 passed）；README 按 A7C2 模板重排并加五段免责（GPL 版，不抄 PolyForm 非商用）；`packaging/必读.txt` 从 0.3.2 那份重写成 0.3.8、压缩到 10,777 B / 144 行；包重打为 47,983,337 B / `e1f6449f…`，解压到别处九项自检全过。
- **2026-10-26 00:39 · 0.3.8 发布** · README 三次提交并 push（`3845574` / `cd09525` / `4a3e30c`）；Release `v0.3.8-win.1`（id `423755708`，标题 `0.3.8 · 软件界面修复`，正文改六轮，末段写明源码包 `version.py` 仍是 0.3.7），资产 sha256 与本地一致。issue #1 我发的两次回复都被删了，用户自己回了「新版本已修复」；**不要再回该 issue**。0.3.7 Release 加提醒、置顶 issue 两项用户已明确不做。
- **2026-10-26 · 交接整理** · §0 重写为「0.3.8 已发布」版（发布面、工作树三批、验收、P0 状态、`0x10000004`、下一步、硬约束），删掉「未发 Release / 包已在本地产出（未上传）/ `HEAD = 73e36a3`」等过期表述；§2 发布状态、§3.4 测试数与包装、§12.3 标题、§12.4 版本与 0.3.8 例外、§16 未提交改动都同步到今天。
- **2026-10-26 晚 · 0.3.9-probe1 取证版发布**：用户 m00183「让软件记录日志呢？直接让他们发日志过来」→ 新增 `runlog.py`（界面日志同时写 `logs/run-*.log`，保留最近 10 份，任何失败都不抛）、`LogBox.log` 同步落盘、`_clear_stale_temp` 逐条上报（删掉 / 本来不在 / 失败+状态码，不再 `except Exception: continue` 静默）、清理名单加 `/tmp/jiritsu/libJit.so`、`dump.select` 支持 `missing`、诊断包 `logs/` 改成截尾保留、诊断报告加「运行日志：」行。用户 m00356 放行。打包走 onefile（`.data/tmp/probe.spec`，48,066,148 B，`1919ab5e…`），冻结自检九项全过；发 `v0.3.9-probe1-win.1`（Pre-release，0.3.8 仍是 Latest）。验收 `124 passed / 1 skipped` + `--render-pages` 七页。

## 20. 2026-10-26 · FL2/FL3 真机战役与炸机

细节全表见 `docs/FL23-FULL-RECORD.md`（492 行：八阶段目标演变、E1–E18 实验表、照片量化、§12 对话索引、§13 存疑 9 条）。

### 20.1 两层写入都成功了（菜单 14 → 16 项）
- B 层：`tools/fl23_write.py b` 写 `/cp/cpapp-b.bin` 的 33 个窗口，**33/33 全 ok、用时 1.3 秒**，实写 4,456 B、实际变化 2,080 B；日志 `.data/writes/fl23-b-20261025T233917.json`。
- 写前 `tools/fl23_preflight.py` 只读核对：cpapp 17,892,024 B、appFw 89,027,992 B、A 层 112 B 原厂 sha256 `93ad5e98ba69b284…`、B 层 before 33/33。
- A 层：`tools/fl23_write.py a` 写 `/usr/lib/appFw.so` 的 `0x34E5604` 共 112 B，回读一致；日志 `.data/writes/fl23-a-20261025T234441.json`。
- 用户冷启动后菜单从 14 项变 16 项（m00714）。这 112 B 的作用 = 把「选中第 15/16 项」映射到 CP mode 19/20，菜单不再把选择归一化回 mode 0。
- 新增两项的显示名是 **`5VV2`、`6BW`**：名字 =「序号 + 基底外观名」，运行时拼出来，不是 UXC 里的字符串（用户 16 项全名：ST PT NT VV VV2 FL IN SH BW SE 1ST 2FL 3IN 4SH 5VV2 6BW）。
- 稳态核对：`tools/fl23_write.py verify` 报 `B 层 before 0/33, after 33/33`、`A 层 FL23（sha256 554d823659ef4fdb…）`。

### 20.2 改名字走错的一步（留给后面的人）
- appFw `0x04b597ac` 有 16 条 **160 B 外观记录表**（`+0x00` 名字 rid、`+0x08` 引导语 rid、`+0x10`=0x42b、`+0x44`=序号、`+0x7c` 16 个 getter 桩）；把两条记录的名字/引导语改掉、回读一致，**菜单毫无变化** → 这张表是「外观参数页」的条目，不是列表名来源。已用 `tools/fl23_names.py --restore` 写回 `CUSTOM_NAME=0x021C6C81` / `CUSTOM_GUIDE=0x021C634A`。
- **命令默认值坑**：`tools/fl23_names.py` 不带参数 = apply，只读必须 `--dry-run`（按错过一次，误写两条记录后已还原）。
- UXC 侧已查清：`/usr/share/app/string_simplifiedchinese_f.uxc` **出厂 145,612 B / sha256 `fe263360c15b5530…` 本来就是短名**（PT/NT/VV/VV2）；`145,708 / 9fd0bb49…` 是我们 official 预设写的长名，`145,692 / 4a2a05e8…` 是 zh 预设。已用 `tools/uxc_restore_factory.py --yes` 写回出厂，核对 `与出厂基线逐字节相同 = True`。

### 20.3 别名机制与 A 层的真实闸门（本轮最重要的机理）
- A 层 112 B 只在 **`w1 == 0`（基底外观 = ST）** 时接管自定义槽的 override；`w1` 是基底外观编号。六个自定义槽基底依次 ST / FL / IN / SH / VV2 / BW，所以 `5VV2`（基底 VV2，`w1 = 4`）**从来没走过 override**。
- 三组配对照片证实 5VV2 与 VV2 逐像素几乎相同（WHM00153/154、157/158、159/160，ΔY 0.2–0.4%、通道差 <1%）→ 5VV2 只是 VV2 的别名。
- 早期「5VV2 变绿」（m00969）的真因：当时把 VV2 自己的色度记录 14 涂成 `(0,300)`，别名跟着变。
- 把 override 表改成 `w0 = 10 → mode 19`（当时以为槽 1 是 ST 基底）后：**选中 ST 立刻闪屏重启，且该槽从菜单消失**（m01459）→ mode 19 在静拍路径上数据不成立（B 层 33 窗只够 movie 用）。回滚后该槽显示为 `1FL`（m01486），说明槽 1 的基底是 FL，不是 ST。

### 20.4 `+55` / `+56` 与色度记录布局
- FireHydrant 文档称「CP 参数 `+55` → 色度槽 23、`+56` → 矩阵槽 25」。我们独立复现失败：把记录 23 涂成 `(400,400)×12` 并设 `+55 = 23`，两次冷启动都没在画面里出现；矩阵侧 `+55 = 6` / `+56 = 4` 也看不出变化。**结论：`+55/+56` 至今未被独立证实。**
- 色度记录布局订正：64 B = 12 组 (Cb,Cr) int16（48 B）+ **8 个 int16 的尾巴（16 B）**；尾巴不是纯填充——记录 16 的尾 `f6fff3ff95ff3100` 是唯一非零样本，把记录 8 整条覆盖成纯色后 FL 变黑白（m01080），说明尾部带「单色/饱和度」类标志位。
- 探针工具与实跑记录：`tools/cp_color_probe.py`（bank 10–15、22–27 上色）、`tools/cp_slot_map.py`（`PARAM_EDITS = {55: 23, 56: 25}`）、`tools/cp_custom_probe.py`、`tools/cp_extra_slots.py`、`tools/cp_cleanup_probes.py`、`tools/cp_bank_diff.py`。**`+51..+54` 完全无效（m00993）；`+57..+60` 会让 ST 闪屏重启（m01047）。**

### 20.5 四条配方回出厂（已完成）
- `tools/fl23_install_looks.py`（`status` / `restore-factory --yes` / `install --yes`）：`install` 把 `BUILTIN_BANKS = (0, 1, 4, 6, 8, 9, 10, 11, 14)` 全写出厂字节，再把 CC 写进记录 23（`+55 = 23`）、NC 写进记录 25（`+56 = 25`）。
- 最终态：`.data/tmp/factory_restore.py` 一个会话写两个单元 → 色度与 `firmware/cp/unit-02a40001.backup-def.bin` 差异 **72 → 0 字节**，矩阵本来 0（跳过写入）；快照 `.data/cp/before-restore-02a40001-20261026T020659.bin`。A/B 层按用户要求保留，菜单仍 16 项。

### 20.6 FL 偏粉：量化了，根因没定位
- FL / 1FL / 2FL 三张彼此相同，`B/G` = 0.966–0.982，其它外观 0.883–0.907；`Y` = 144–146，ST/PT 只有 117 左右（亮度高约 25%）。最新一组：WHM00169 FL Y144.0 / B/G0.974、WHM00171 ST 117.6/0.895、WHM00172 PT 117.1/0.907、WHM00173 FL 146.5/0.982。
- 已排除：把 cpapp 的 168 B 模式表 `0x10D11D8` 归零（备份 `.data/writes/modetable-before-20261026T035230.bin`）→ FL 仍偏粉。
- 未得结论：再把 3,872 B 曲线区 `0x10D02B8` 归零（备份 `.data/writes/ramp-before-20261026T035953.bin`）→ **当场炸机**。

### 20.7 炸机与恢复素材
- 触发：`/cp/cpapp-b.bin` 的 `0x10D02B8` 3,872 B 写成全零（原 1,682 个非零字节），回读一致后黑屏无限重启。
- USB 现象：只有 PID `0x0D68`（service `HidUsb`，USB 输入设备），每约 3 秒出现 1.5 秒；**从不出现 `0x0E76`（MSC）或 `0x0336`（服务）** → 应用层起不来，Jiritsu / MSC 全部无用，只能走 RP2040 冷启动注入（`refs/a6700-powerful/硬件说明.md`）。
- 离线算清的落点：`/cp` = `nflasha8`，FAT12、32 扇区/簇、数据区 `0x10000`；`CPAPP-B.BIN` 首簇 145、1,093 簇连续；文件偏移 `0x10D02B8` → 绝对扇区 **39,137**、簇内偏移 184。必须写 **9 个扇区 39,137…39,145（4,608 B）** 才能连模式表尾部一起覆盖（8 个不够，§18 里那个数字是错的）。
- 恢复镜像（离线造好、结构已校验）：`.data/recovery/ramp.img` 4,608 B sha256 `f3078dd214972e04d4f45ee137dc905720d8bd94457224738fe5dcc895e7159d`、`ramp.sparse` 4,660 B `591f89a9…`、`restore-b.sparse` 12,556 B `afdd68ac…`（33 窗全部回出厂，24 块 / 10 段）。
- 未完成的一环：**可写入版 RAM payload 还没编出来**（上游只读 payload 把 `cmd_flash`/`cmd_download`/`mmc_write_blocks` 剔掉了）。源码与工具链已就位（`refs/ILCE-7M4-RE` commit `2328d18ce640e6c8cd9341efcf0043ce9042a135`、`.venv/Lib/site-packages/ziglang/zig.exe` 0.13.0），卡在 `构建相机引导.py` 输出的解码：`UnicodeDecodeError: 'gbk' codec can't decode byte 0xaf in position 126` → 给 `subprocess.run` 加 `encoding=utf-8, errors=replace`。

### 20.8 接手立刻要做的
1. 等 Pico 套装到货（清单见 `docs/FL23-FULL-RECORD.md` §8.3）→ 按 §8.5 操作手册：先 `oem partition dump nflasha8 98E1 9` 只读对照 `ramp.img` 前 184 字节，再 `download:` + `flash:nflasha8` 推 `ramp.sparse`（只动 9 个扇区，比 `restore-b.sparse` 风险小）。
2. 相机起来后先 `tools/fl23_write.py restore-b` 把 B 层整段回出厂，再决定要不要重做。
3. 「内置 10 项回原厂 + CC/NC 住独立槽」这条路已证伪（§20.3）；四条配方的落点仍只有内建记录：CC → 记录 6、NC → 记录 4、PF → 记录 1、NF → 记录 14。

---

## 21. 2026-10-26 · 0.3.8 诊断层（blocked 为什么只有一句话）· 另一个会话的改动，未提交

> 完整记录见 `docs/DIAGNOSTICS.md`（字段表、界面落点、诊断包结构、验证与缺口、以后怎么扩）；本节只留结论。

issue #1 的根因不在协议，在展示：上游 `operations.py:288` 在 `plan["compatible"]` 为 False 时只 `progress("内容或布局不匹配，已停止；没有写入功能目标。")`，而 `device_profile.inspect_sectors()` 算好的 `plan["issues"]`（`kind`/`index`/`device`/`offset`/`actual`）界面一个字段都没读，`cli.py:83` 也只打一句「N 处内容／结构不匹配，具体位置见操作记录」。

这一版把差异摊开到界面上，并且给一条取证通道——全部离线，没碰相机：

- `src/a6700win/diagnostics.py`：`describe(issue)`（5 类 kind → 中文短句，未知 kind 原样带出）、`issue_lines(issues, limit=12)`（超出补「…还有 N 处，完整列表在运行目录的 plan.json 里」）、`issue_hint(issues)`（结构守卫 / 取值未知 / 前置条件三类各一句）、`read_interrupted(message)`（9 种掉线字样）、`environment()`（版本 / Python / 平台 / 数据目录 / `patches.status()` / `setupapi.summary()`，逐项 `_safe`）、`report(result, env, limit=20)`、`export_bundle(result, target, env)`。
- `gui/pages.py`：`HomePage.blocked_hint`（摘要下一行「被结构守卫拦下：N 处差异…」+ 前 3 条）；`ResultPage.issues_card`（「差异明细 · N 处」+ hint + 前 10 条 + 运行目录 + 「复制诊断信息」「导出诊断包」），`render()` 在 `_render_aftercare()` 之前调 `_render_issues()`。
- 诊断包 zip：`diagnostics.txt`、`result.json`（剔除 sectors/blob）、`environment.json`、`run/{plan,result,native-result}.json`（≤2 MB）、`logs/`（最近 3 个 ≤300 KB）。
- `--inspect-once` 输出新增 `run_directory` / `issues` / `issues_text`。
- `README.md`：「一次写入」从「已经能用的」删掉，只在「还在做」保留并写明按钮默认锁着、勾一行确认才解锁、一次还原不受限。

验证：`pytest tests -q` → **108 passed / 1 skipped**（新增 `tests/test_diagnostics.py` 10 例；`tests/test_gui.py` 加 1 例，用合成 issues 校验两页都真的显示了偏移与运行目录）。`--render-pages .data/tmp/render` 七页正常、`tools/check_publish.py` 干净。

**没验证的**：诊断包没在冻结包里点过；真实 blocked 现场（别人的机器）没复现，只用合成 issues；相机自 2026-10-26 起在等硬件修复，本版没有任何真机操作。



---

## 22. 2026-10-26 晚 · 0.3.9-probe1 取证版（单文件 exe，已发布）

> 目的只有一个：让报 `0x10000004` 的人把现场交上来。它**不是修复**——读取、写入、备份、还原的行为与 0.3.8 完全一样，只多记录了两件事。

### 22.1 为什么发它

用户 m00183「让软件记录日志呢？直接让他们发日志过来」。之前拿不到证据有两个硬原因：

1. 界面日志只活在内存里（`gui/widgets.py` 的 `LogBox`），用户只能截图，而截图常常停在最想知道的那一行之后（m00174 纠正过我一次：他们贴的日志正好停在「正在读取补丁目标和结构守卫…」，而清理进度打印在它之后）。
2. `_clear_stale_temp` 只在真删掉时打一行字，失败被 `except Exception: continue` 静默吞掉 ⇒ 同一段日志分不清「文件不存在 / 存在但删不掉 / 日志被截断」三种情况。

所以这一版的第一价值是**让删除开口**，不是修好。

### 22.2 加了什么（按文件）

- 新增 `src/a6700win/runlog.py`（110 行，CRLF）：`start(tag, directory=None)` / `write(message)` / `path()` / `close()` / `_trim(folder)`；文件名 `run-<yyyymmdd-HHMMSS>-<tag>.log`，落 `paths.log_dir()`（即 `data_root()/logs`），头两行是版本与文件路径，只保留最近 `MAX_FILES = 10` 份。全部 best-effort：`start()` 失败返回 `None`，`write()` 不抛（日志坏掉不能带崩主流程），实测不设 TMP 时 `paths.data_root()` 抛 `FileNotFoundError: [Errno 2] No usable temporary directory found`，`start()` 照样安全返回。
- `src/a6700win/gui/widgets.py`：`LogBox.log()` 里加 `runlog.write(message)`，界面日志与文件是同一份。
- `src/a6700win/__main__.py`：`render_pages` 分支之后 `runlog.start("cli" if (args.dump or args.inspect_once or args.diagnose) else "gui")`。
- `src/a6700win/dump.py`：`select(channel, path, missing=False)` 新增 `missing` 并透传给 `jiritsu`；`remove()` 把它传下去 ⇒ 「文件本来就不在」不再当异常。`read_file` 那条路径**没改**。
- `src/a6700win/patches.py`：`_stale_paths()` 返回 `tuple(dump.TEMP_PATHS) + ("/tmp/jiritsu/libJit.so",)`（依据 §11 第 844 行那句「遗留的 `libJit.so` 会被固件重放」）；`_clear_stale_temp` 逐条上报三句：`已清掉相机上一次会话留下的临时文件：…` / `清理临时文件失败：<名字>：<状态>` / `相机上没有上次会话留下的临时文件：…。`
- `src/a6700win/diagnostics.py`：报告多一行 `运行日志：<路径>`；诊断包 `logs/` 从「超过 300 KB 整份丢掉」改成**截尾保留**（前面加 `……（前面省略）……`）；`_recent_logs()` 返回 `(Path, bytes)`。
- `src/a6700win/version.py`：`APP_VERSION = "0.3.9-probe1"`（临时；README / 必读 / zip 仍是 0.3.8）。
- 测试：新增 `tests/test_runlog.py`（4 例：落盘、`close` 后不写、只留 MAX_FILES 份、目录不可用不抛）；`tests/test_patches.py` 加 3 例（名单含 libJit.so、删除失败要上报、删干净要上报）+ import 改成 `from a6700win import dump, patches`；`tests/test_config_selfheal.py` 的基准全部换成 `patches._stale_paths()`。

### 22.3 怎么打的包（onefile，不是原来的 zip）

- `packaging/Powerful6700.spec` 是 **onedir**（`COLLECT` 到 `dist/Powerful6700/`），单独一个 exe 跑不起来（要旁边的 `_internal`）。取证版另写 `.data/tmp/probe.spec`：datas 照旧，去掉 `COLLECT`、把 `a.binaries` / `a.datas` 塞进 `EXE`。
- 命令：`.venv/Scripts/python.exe -m PyInstaller .data/tmp/probe.spec --noconfirm --clean --distpath .data/tmp/dist-probe --workpath .data/tmp/build-probe`（约 41 秒）。
- 产物 **48,066,148 B / sha256 `1919ab5e373b01dc4fdbbe9ab11f3b53dfbd969fe5b8c907c1c0c49f7cecc013`**，改名为 `Powerful6700-0.3.9-probe1.exe` 上传。
- 冻结自检九项全过（`--offline-self-test --json .data/tmp/probe-selftest2.json`；注意 `--json` 必须带路径，否则 argparse 报 `argument --json: expected one argument`）：python 3.12.3 / win32 / vendor 0.2.0 / files 完整 / data-dir / libusb（`_MEIPASS/libusb-1.0.dll`）/ setupapi / wdi / controller。
- onefile 下的路径语义：`paths.project_root()` 冻结时 = **exe 所在目录**（`paths.py:38-41`），所以 `.data` 与 `logs/` 落在 exe 旁边，不进临时目录；只有 `paths.bundled_root()` 用 `_MEIPASS`。⇒ 用户在 exe 同级的 `.data/logs` 里能找到日志。

### 22.4 怎么发的

- `gh auth status` 是 `You are not logged into any GitHub hosts`；于是向 Git Credential Manager 要已存凭据（`git credential fill`，喂两行 `protocol=https` / `host=github.com` 加一个空行，配 `GIT_TERMINAL_PROMPT=0`、`GCM_INTERACTIVE=never`），把返回的 password 直接放进 `GH_TOKEN`（**全程没打印过凭据**）。
- `gh release create v0.3.9-probe1-win.1 .data/tmp/dist-probe/Powerful6700-0.3.9-probe1.exe --repo wanghm105/Powerful6700-Windows --title "0.3.9-probe1 · 报错的请下这版" --notes-file .data/release-body-039-probe1.md --prerelease`
- 核对：Pre-release true / draft false / tag → `4a3e30c` / 唯一资产 48,066,148 B、GitHub digest 与本地一致；`gh api repos/wanghm105/Powerful6700-Windows/releases/latest` 仍是 `v0.3.8-win.1`（资产 47,983,337 B 没动）。
- 脚本与文案：`.data/tmp/pre_publish2.sh`、`.data/tmp/publish_probe.sh`、`.data/tmp/verify_publish.sh`、`.data/release-body-039-probe1.md`、`.data/announcement-039-probe1.md`。
- `gh` 1.x 的 `release view --json` **没有 `isLatest` 字段**（会报 `Unknown JSON field: "isLatest"`），判「谁是 Latest」用 `gh api repos/<repo>/releases/latest`。
- 撤稿：`gh release delete v0.3.9-probe1-win.1 --repo wanghm105/Powerful6700-Windows --yes --cleanup-tag`。

### 22.5 日志回来怎么判

先找有没有 `清理临时文件` 开头的行，再看是哪一句（§0.7 有同样的表）：

| 日志行 | 含义 | 下一步 |
| --- | --- | --- |
| 一句都没有 | 不是这一版（看日志头 `Powerful6700Win 0.3.9-probe1`），或日志没导出 | 让他重跑/重新导出 |
| `清理临时文件失败：libJit.so：Jiritsu 状态 0x10000006` | 相机上没有这个文件 | 「残留」假设不成立，往「服务会话本身脏」查 |
| `清理临时文件失败：tmmc.jit：Jiritsu 状态 0x10000004` | 连删都被拒 | 会话已不可用：先退服务模式、重新认证，再写 |
| `已清掉相机上一次会话留下的临时文件：libJit.so` | 真删掉过 | 看这次有没有因此通过；通过则残留假设成立 |

### 22.6 未验证 / 风险（交接时先看这一段）

- **onefile 是第一次发**（此前都是 onedir + zip）。自检九项、七页 `--render-pages` 都过，但**没在别人的机器上双击跑过**，更没在真机上跑过（相机自 2026-10-26 起是砖，等 RP2040 硬件恢复）。
- 代码只动读侧与日志：`0x4010` 的写入语义、分块、`truncate` 顺序一个字节没改；`cp.py` 的 `_clear_temp` **没动**（CP 会话对 `SESSION_GAP` 冷却敏感，无真机可验，不在这一轮加命令）。
- `version.py` 现在是 `0.3.9-probe1`，而 README / `packaging/必读.txt` / zip 仍是 0.3.8 ⇒ `tools/check_publish.py` 会报版本不一致，**属预期**。下次正式发版先改回正式版本号，再重打包、重算 sha256、同步 README 校验值行。
- 现场反馈汇总（三条 issue / 群报告的归类）记在 `docs/DIAGNOSTICS.md` §8。

## 23. 0.3.9-probe2：一次会话试完三种可能（**未发布**，截至本文件写入时）

### 23.1 为什么还有 probe2

probe1 只干两件事：把日志写进文件、把清理失败说出来。issue #3（机友 E，2026-10-26T11:16:06Z）的日志到了以后，证据翻了一次盘：

- `tmmc.jit` / `tmmc.dat` / `libJit.so` **三个名字、连续两轮、全部回 `0x10000004`**，而「文件不存在」本该回 `0x10000006`。
- `libJit.so` 从来没被这个工具写过，所以**「残留的 libJit.so 被固件重放」这条假设被证伪**——它不成立。
- 结论改成：这台相机**整段会话的所有文件操作都被拒**，不是某个文件残留。

所以 probe2 不再只取证：让程序在**同一条会话**里把三种可能都试一遍，能救就继续跑，救不了就把每一步的状态写进日志。

### 23.2 改了什么（只在 `src/a6700win/patches.py`）

Windows 后端那条文件写入包装 `_windows_backend_file` 的失败分支，从「再清一次、重发一次」升级成三层阶梯，**只在 `command == 0x4010` 且状态正好是 `0x10000004` 时**才升级：

| 层 | 动作 | 成功的日志 |
|---|---|---|
| 1 | 清掉 `/tmp/jiritsu` 下的临时文件后重写一次 | 清完临时文件后写入成功，继续。 |
| 2 | 分别等 0.5 / 1.5 / 3.0 秒后各重写一次 | 等了 1.5 秒后写入成功，继续。 |
| 3 | 先读一次 `/setting/BACKUP.BIN`（SELECT + READ，纯读），再重写一次 | 同层 1 / 2 |

三层都失败时抛一条带 `trace` 的 DeviceError：逐条列出每次尝试的状态行，并按探测结果给**描述性**结论（四选一：普通文件读得出来 / 回 0x10000006 / 没拿到通道 / 连普通文件都没读出来——最后一种不下结论）。

配套常量与函数：`_PROBE_PATH`、`_RETRY_DELAYS = (0.5, 1.5, 3.0)`、`_TEMP_STATUS = 0x10000004`、`_sleep(seconds)`、`_status_line(status)`、`_attempt(backend, command, ident, data)`、`_probe_file_service(channel)`。

命令数：健康相机与 0.3.8 完全一致（写一次就成）；持续被拒时 `0x4010` 一共发 6 次（1 首次 + 1 清后 + 3 延迟 + 1 探测后），累计等待 5 秒。**这 6 次全在固件写入之前**（上游顺序 `0x4010 → 0x4007 → 0x4008`）。

### 23.3 安全审计的三条硬结论（用户问过「会不会更危险」）

1. `third_party/a6700_unlock/` 与 `native/` **零改动**（`git status -- third_party native` 为空）；两个 native 载荷与 HEAD、与 0.3.8 发布 zip 里的**逐字节相同**。
2. 新代码对相机的动作只有三类：`dump.remove()`（SELECT + REMOVE）、`_attempt → backend._command()`（0x4010 / 0x4007，命令、file_id、内容都与 0.3.8 相同）、`dump.camera_file()`（SELECT + READ）。`CMD_WRITE` 在 patches.py 里零命中。
3. 已知的炸机触发是往 `/cp/cpapp-b.bin` 写全零，与本路径无关；文档里记的重启循环由**反复拔插**驱动，不是会话内重试。

### 23.4 构建与验收

- `127 passed, 1 skipped`（新增 3 个 `_probe_file_service` 用例；两个测试文件加了 autouse fixture 把 `patches._sleep` 换成空函数，否则失败用例真等 4 秒多）。
- `--render-pages` 七张图正常。
- onefile exe：`.data/tmp/dist-probe2/Powerful6700.exe` **48,068,000 B**，sha256 `17d442d83f9976542644ef731727f46e85ba358bd7ee9f827210a75b8e4a97b9`；`--offline-self-test` 九项全 ok、`version 0.3.9-probe2`。
- `src/a6700win/version.py` = `0.3.9-probe2`；**未重打包**，README / 必读 / 0.3.8 zip 仍是 0.3.8。

### 23.5 样本：6 份，含第一份健康对照（2026-10-27 凌晨）

明细表在 `docs/DIAGNOSTICS.md` §8.5。要点：

- 4 份失败样本（issue #3、机友 A、机友 C、机友 D）全部卡在同一位置——会话里**第一条**文件操作就被拒，三个临时文件名连续两轮的 `REMOVE` 都回 `0x10000004`；其中 机友 A 那份 `cleanup_warning` 为空，说明会话正常退出、相机没被卡住。
- 1 份**健康样本**（用户目录 `D:\迅雷下载`，Win11 26200，PID `0x0e76`，用 probe2）：同一步打印的是「已清掉相机上一次会话留下的临时文件：tmmc.jit、tmmc.dat、libJit.so」，随后「检查完成：预计修改 0 字节／0 个扇区」「只读检查完成，可以管理功能」⇒ `0x10000004` 属异常状态，我们的清理链路本身是对的，三层阶梯压根没触发（第一次写入即成功，命令数与 0.3.8 相同）。
- 同一台健康机还复现过一次「内容或布局不匹配，已停止；没有写入功能目标。」和一次「USB 认证失败…Operation not supported or unimplemented on this platform」，重跑都通过 ⇒ 结构守卫不匹配与认证失败**至少有一部分是暂时性的**，和 §8.2 那个「260 块里只 1 块不符」是同一类信号。

仍然不能证明的：是不是所有报错机都长这样（可能几种成因混在一起）；与固件批次 / USB 连接模式 / 机器来源的关系；连续六次被拒会不会推进重启循环。

现在最缺的**不是对照，而是卡住那几台的 probe2 日志**：看阶梯停在第几层、每层状态码是什么，就能把三种可能分开。
### 23.6 未验证 / 待办

- **没有真机**：连健康路径「命令数不变」也只是读代码 + 单测，不是实测（相机自 2026-10-26 起是砖）。
- `_attempt()` 直接调 `backend._command()`，**没有 try/except**：阶梯中途掉线（`[Errno 32] Pipe error` 之类）会立刻穿透，前面累积的 trace 不打印。修法约五行——**未获点名，未动**。
- 探测读的是整份 `/setting/BACKUP.BIN`（约 1.8 MB），故障机上很可能超时；所以结论文字只描述、不下断言。
- 发布状态：**已发布** `0.3.9-probe2`（tag `v0.3.9-probe2-win.1`，2026-10-26 夜，勾了 Pre-release，单一资产 `Powerful6700-0.3.9-probe2.exe` 48,068,000 B / sha256 `17d442d8…`）；`0.3.8` 仍是 Latest。


## 24. 0.3.9-probe5：GET_VERSION（0x400D）与 MOUNT（0x4002）两个新旋钮（未发布，2026-10-27）

### 24.1 现场：probe3 / probe4r 与 机友 C 的两份新包

- probe3：只改了失败正文的排版（按层编号换行）。probe4r：多一层「把会话整个关掉、重新认证一次」。
- **probe4r 的那一层是错的**：它唯一的增量结果是相机从 0x0E76（MSC）被推到 0x096F（HidUsb，即 §6 里写「救不回」的落点），写入一次都没成。probe5 已把整段代码连同 POWERFUL6700_RESTART_SESSION 一起删掉，代码里留了注释「别再放回来」。
- 2026-10-27 17:20：`v0.3.9-probe4r-win.1` 的 release 与 tag 已从 GitHub 删除（`gh release delete --yes --cleanup-tag`），probe4r 的 exe 不再可下载。probe1–probe3 仍在线上。
- 机友 C 的两份新包（报错/Powerful6700-诊断-20261027-112337.zip 与 …111626.zip，probe4r）：
  - 认证、二次认证、服务响应全部通过；/tmp/jiritsu 的三条 REMOVE 与随后的 0x4010 file_id=0 全部回 `Jiritsu 状态 0x10000004`；连读 /setting/BACKUP.BIN 也回 0x10000004；三个路径的 select 都不报错。
  - 与 20261026-204503 那份不同：这次**重开会话也成功了**，相机仍是 pid 3702 = 0x0E76 / winusb / supported，但「关掉会话再认证」并没有让文件服务活过来。
  - 结论：不是「相机被卡在服务模式」，也不是「临时文件残留」，而是**会话建立之后文件服务整体不可用**。

### 24.2 新线索：nflasha6 可能被我们自己卸掉了

来自同族机器 FX30 6.00 的 Jiritsu 笔记（t2r05/fx30-senser-map，docs/07-jiritsu-breakthrough.md §3.3）：

- 删掉 /tmp/jiritsu/libJit.so 会让 Jiritsu **卸载整个 nflasha6**（libJit 所在的分区），此后所有文件操作一律被拒；读 /tmp/jiritsu 直接回 **130 = 分区已卸载**（不是文件不存在）。
- 补救只有一条：发 **0x4002（MOUNT）** 重挂，之后文件操作恢复正常。正确清理顺序是 FILE_DELETE → 读回（可能 130）→ 0x4002 重挂 → 再读回确认。
- FX30 6.00 的 category 0x1001 有 0x4001–0x4012 共 18 条命令；其中 **0x400D（GET_VERSION）** 实测回 res=0 len=4 `06 00 00 10`（= 6.00）。
- 我方 grep：0x4002 / 0x400D 在 Powerful6700Win 与 refs 里**零命中** —— 我们从来没发过 MOUNT，也从来没读过固件版本。
- 与现场吻合之处：不存在的路径 select 也返回成功、普通文件读也 0x10000004、第一条 REMOVE 就过不去 —— 全是「分区已卸载」的形状；而 0.3.9 的清理名单里正好有 libJit.so。**这是我们自己的候选成因**，probe5 就是去证伪它的。

### 24.3 改了什么（按文件）

- src/a6700win/dump.py：新增 CMD_VERSION = 0x400D、CMD_MOUNT = 0x4002；新增 `service(channel, command, data=b"")` → `channel.send(0x40, struct.pack("<HH", 0x1001, command) + data)`（文件命令仍走带白名单的 jiritsu()）。
- src/a6700win/patches.py：
  - 删掉 `_restart_session()` 与 `POWERFUL6700_RESTART_SESSION` 分支（probe4r 的错误尝试）。
  - 新增 `_version_text(body)`（4 字节且 body[3]==0x10 → 「固件版本 2.00（原始字节 02000010）」；同一串字节若落在 _KNOWN_STATUS 里，追加「按状态读是 0x10000004」）、`_probe_version(channel)`、`_remount_jiritsu(channel)`。
  - `_windows_backend_file` 在第一次 `_clear_stale_temp` 之前只读地问一次版本（每个 backend 实例只问一次，打 _a6700win_version_read 标记）。
  - `_clear_stale_temp`：某个路径报 0x10000004 且还没重挂过 → 调 `_remount_jiritsu`，**重试同一条 remove**，再失败就写「重挂分区后仍然失败」。
  - `_clear_stale_temp` 第二处：**删掉 libJit.so 的成功分支里立刻调 `_remount_jiritsu`**（`path.endswith("/libJit.so")`），日志写「libJit.so 已清掉，顺便把相机的临时目录重新挂上：成功」；重挂没成功时补一句「没挂上也不要紧，等下写入时会再试一次」，不抛异常。（对机友的界面文案刻意不提「卸载分区」，只写「清理 + 重新挂上」。）原因：名单里 libJit.so 排最后，删它必然卸载分区，不重挂的话同一会话第一条配置写入一定 0x10000004。
  - 阶梯新增第 5 种「重挂 nflasha6（0x4002）后再写」，原第 6/7 顺延；原第 7 种（重开会话）整块删除。
- src/a6700win/guards.py：`guards.install()` 返回名去掉 `a6700_unlock.` 前缀（改成 `device_profile.inspect_sectors`），与 `_PATCH_NAMES`、界面清单一致——之前 install() 会把两条带前缀的名字塞进 applied，导致 test_install_is_idempotent 断言「applied 必须 ∈ EXPECTED」失败。
- tests/test_patches.py：删 3 例（重启会话），新增 8 例；tests/test_config_selfheal.py：加 `_file_commands(channel)` 过滤掉会话开头那条 0x400D，再数文件命令。

### 24.4 坑：pytest 静默卡死原来是「测试文件被写成二进制」

- 现象：`pytest tests/test_patches.py -q` 连续超时（EXIT=124），日志 **0 字节**；`--collect-only -q` 也 0 字节。看起来像「测试太慢」或「导入卡住」，其实文件根本不可解析。
- 判据：`grep -n "^[^ #]" tests/test_patches.py` 报 **Binary file tests/test_patches.py matches** → 源码里有控制字节（这次 26 个：b"\x02\x00\x00\x10" 之类被写成真实 NUL/0x02/0x04/CR 而不是转义文本）。
- 修法：正则 `b"([\x00-\x1f]+)"` 把控制字节逐个转成 `\xNN`；注意别多写一层反斜杠（我第一次修成了 `\x02`，测试拿到 16 字节 ASCII）、也别漏掉含真实 CR 的字面量（`b"\x01\x10\r@"` 因为 \r 不在匹配类里被跳过，要单独替换）。
- 另一个坑：这台机上 pytest **跑完不出摘要**（Qt/Defender 让进程在点号之后不退出），`timeout` 杀掉时 summary 还没写。可靠做法是加 `--junitxml=.data/tmp/x.xml`，事后解析 XML 读 tests/failures 与失败正文；终端点号只当辅助。
- TEMP/TMP 必须给**绝对路径且目录已存在**，否则 pytest 启动即 `FileNotFoundError: [Errno 2] No usable temporary directory found`。

### 24.5 验收

- `pytest tests -q`（QT_QPA_PLATFORM=offscreen）→ **141 passed / 1 skipped**（0.3.8 时是 109）。
- 单文件 exe 已构建（未发布）：.data/tmp/dist-probe5/Powerful6700-0.3.9-probe5.exe， **48,075,450 B / sha256 3e92fa9b3425356a4c60c6e4401e6cc5ab89dea27e1f87e17bb2e8d89811c05d**；冻结自检九项全过、`version 0.3.9-probe5`。
- `pytest tests -q`（junit 读数为准）→ **144 passed / 1 skipped**（含 libJit.so 重挂那一版；0.3.8 时是 109）。
- 单文件 exe（含 libJit.so 重挂修复 + 文案软化）：.data/tmp/dist-probe5c/Powerful6700-0.3.9-probe5.exe， **48,074,201 B / sha256 4e8232965a5eb4245e9d77c0eb76a1bf750450f3ea6f5cac647a53988cde8c04**；冻结自检九项全过、`version 0.3.9-probe5`；拆 PYZ 复核过 `_probe_version`/`_remount_jiritsu`/0x400D/0x4002 与新文案都在包里、旧的「会因此卸载」「马上重挂」已不在包里（更早的 3e92fa9b…、1c2347… 两个包全部作废，都没发布过）。
- 发布侧：`v0.3.9-probe4r-win.1` 的 release 与 tag 已于 2026-10-27 17:20 删除（`gh release delete --yes --cleanup-tag`）；probe1–probe3 仍在线上。
- `src/a6700win/version.py` = 0.3.9-probe5；**未发布、未提交**（工作树里所有改动都还没 commit）。

### 24.6 未验证 / 待办

- 0x4002 与 0x400D **从未在真机上发过**（相机自 2026-10-26 起是砖，等 RP2040 Pico）。它们是同族机器验证过的命令，但对 A6700 2.00 属未实测：返回码、副作用（重挂是否影响正在进行的写）都只有推断。
- 「nflasha6 被卸载」仍是假设：probe5 只有拿到失败机的日志才能证实/证伪。判读：先看「先只读地问一句相机固件版本…」那行回什么；再看第 5 种「重挂 /tmp/jiritsu：成功」之后写入是否还回 0x10000004。
- 若 probe5 仍全灭，下一步才是真机刷回官方 2.00 固件 / 相机内初始化（机友侧），以及我们自己等待 Pico 硬件恢复。
- 打包 probe5 单文件 exe 的步骤照 §22.3 / §23.4；构建后必须 `looknames.auto_import()` 重新 seed 基线库。
