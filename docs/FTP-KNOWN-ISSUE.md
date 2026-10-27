# FTP 传输：已知故障、反向取证结论与界面提醒

一句话：**解锁没写错字节**。坏在机身自带的 FTP 传输队列／状态机（证据见第 3、4 节），
本次工具侧只做了「把边界从悬停提示搬到界面上」的呈现层改动，没有改任何一个写入字段。

- 现象：真机复现 3 次，行为稳定可重复
- 原因：定位到相机内 model::sequence_ftp_transfer 的传输完成／恢复路径（**推断，尚未取到运行时日志证实**）
- 工具侧影响：无（工具只在写入瞬间工作，FTP 传输过程不参与）
- 本次改动：新增 1 个模块、改 2 个文件，见第 7 节；验证结果见第 9 节

## 1. 现象（用户原文，m00001）

> 这个 6700 的 ftp 弄好后，连接上，传一张就不能再传了关机，拔电池等一会儿，上电池再开机，直接关机
> 开机后一张也上传不了，关机拔电池等一会再上电池开机，上传一张后就又不行了，这样试了三次都是一样
> 上传一张后就不行了

拆成三句就是：

1. 连上服务器后第 1 张能传，第 2 张卡住；
2. 此时正常关机再开机 → **一张都传不了**；
3. 拔电池等一会儿再开机 → 又能传 1 张，然后重复第 1、2 条。

## 2. 结论先行

| 问题 | 结论 |
| --- | --- |
| 是不是解锁把固件写坏了？ | 不是。242 条 FTP 改动全是 00→01 的静态「本机型支持该参数／菜单里有这一项」标志，没有一条动代码逻辑 |
| 为什么能传第 1 张？ | 机身后台是**原厂完整 FTP 引擎**，解锁只是把入口打开 |
| 为什么关机方式不同，结果不同？ | 正常关机把 RAM 里的传输状态刷回机身；拔电池跳过这次回写。见第 5 节 |
| 是不是服务器／网络问题？ | 不是。断连走 FTP_ERROR_CONNECT_SERVER_DISCONNECTED 一类路径，不会因为关机方式不同而变化 |

## 3. 为什么可以排除「解锁字段写错」

- catalog（third_party/a6700_unlock/data/a6700-2.00.json，355 条 edit）里 ftp 共 242 条：
  image 分布 wbi 152 / app 90；字节量 app 89 B + wbi 151 B + CP 0 B；**全部是 00→01**。
- 涉及的参数 ID：0x5a5 开关、0x5a6 连接方式、0x5a8 服务器、0x5aa 自动传输、0x5ac～0x5b0 照片格式／目标／节能。
- 参数表实测（appFw-2.00.so 偏移 0x3f17524 起，8 字节稀疏记录 {u32 param_id, u32 value}）：
  0x5a5 起依次 0x5a6／0x5a8／0x5aa／0x5ac／0x5ad／0x5ae／0x5af／0x5b0 的值都是 1。
- **0x5a7 / 0x5a9 / 0x5ab 在整张表里没有对应条目**（不是值为 0，是压根不存在）→ 曾经怀疑「catalog 漏改三条」的假设作废，
  不是漏改，是这三条参数本来就不在该机型的参数表里。
- 机身侧的证据：导出符号 _ZN3mpr4file17TransferStillFileERNS0_24transferStillFileInParamEPNS0_25transferStillFileOutParamE
  （mpr::file::TransferStillFile）；mpr 模块共 65 个导出符号；.rodata 里含 "FTP" 的 unique 字符串 1303 条，
  含完整 FTP_ERROR_CONNECT_*／FTP_CONNECTION_ERROR_TYPE_*／FTP_NETWORK_ERROR_TYPE_*／INFRA_NOTIFY_FTP_ERR_* 枚举。
  → 传输功能是原厂实现，所以「能传第一张」是必然结果，问题出在传完之后。

## 4. 反向取证：传输队列是落盘文件，状态机在 model 层

镜像：firmware/appFw-2.00.so（89,027,992 B，sha256 721fceae…c1144d）。ELF64 AArch64、已 strip，
**文件内 addr == 偏移**，所以偏移可直接当 VA 用（catalog 里的「ELF 文件偏移」正是这个原因）。

- 队列文件路径格式串：%c:%s/SONY/FTPNSEND.DAT，.rodata 0x4080245，4 处 xref：
  0x325ee68 / 0x32627a0 / 0x3265384 / 0x32654d0
- 路径构造函数 0x325edbc：ldr w20,[x0,#0x28] 为 0 则整段跳过（媒体未就绪）；ldrb w3,[x0,#0x19] 取槽位号；
  媒体类型 == 3 时前缀取 /PRIVATE（.rodata 0x406fd2），否则取另一串。
- load_ftp_transfer_list_from_media（0x32627a0 一带）：读缓冲 0xC3500 = 800,000 字节，按 8 字节记录遍历、
  逐条 add；失败重试 3 次后打 "$s() FTP Transfer file is Not found."；成功打
  [ftp_transfer]added ftp_transfer_list size: %d（0x408025d，xref 0x3262960）。
- save_ftp_transfer_list_to_media（0x3265384 一带）：日志
  [ftp_transfer]save to media size = %d, slot1 = %s, slot2 = %s（0x4080207，xref 0x32653cc）。
- 同一段 .rodata（0x407f000–0x4083000）里的方法／类型／枚举：
  - 方法：exec_transfer()、write_to_file、read_from_file、remove_from_media、start_ftp_transfer()、
    resume_ftp_transfer()、set_reconnect_timer(model::ds_ftp_transfer_cmp_info_t)、
    schedule_transfer_contents()、do_event(model::ds_ftp_transfer_event_t)、pop_event()
  - 类型：N5model20ftp_transfer_state_tE、N5model21sequence_ftp_transferE、
    N5model42sequence_acquire_ftp_transfer_confirmationE、N5model14release_lock_tE
  - 枚举：FTP_TRANSFER_LIST_ADD_STATE_ADD_PROCESSING / NOT_ADD_PROCESSING；
    FTP_TRANSFER_CONDITION_RESULT_EXCEED_MAX / FAILED / NOT_SUPPORT / NO_CONTENTS / OK / RESTRICTION；
    FTP_PAUSE_FACTOR_RATING_* / PROTECT_SINGLE / NONE；
    INFRA_NOTIFY_FTP_TRANSFER_CMP / _FTP_TRANSFER_PROGRESS / _FTP_TRANSFER_PROGRESS_TIMER_EXPIRED /
    _FTP_RETRANSFER_TIMER_EXPIRED / _FTP_CONNECTION_RETRY_DELAY_TIMER_EXPIRED / _FTP_POWER_SAVE_TIMER_EXPIRED；
    MODEL_FTP_TRANSFER_COMP / TRANSFER_STOP_CMP / TRANSFERRING_CONTENTS_ADDED / SERVER_CONNECTION_COMP /
    TRANSFER_PAUSE_COMP
  - 其他：Wait for Slot1 Initialize... / Wait for Slot2 Initialize... / [ftp_transfer]off factor is not suspend
- FTP 内部状态 DB 列名（.rodata 0x43944b2–0x4394710，连续一段），与本次故障最相关的六个：
  ftp_function_internal_state、is_transferring_infra_ftp、is_ftp_stopped_proc_waiting、
  ftp_connection_error_count、is_ftp_connect_wait_comp、ftp_disconnecting_state

## 5. 推断的故障链（标注了哪一段是推断）

1. 第 1 张传输结束，INFRA_NOTIFY_FTP_TRANSFER_CMP 到达 model::sequence_ftp_transfer，但内部状态没有回到 idle，
   于是队列第 2 条不会被调度 —— **推断**，未见日志。
2. 正常关机时，机身把 RAM 中的状态／队列写回 flash（docs/PERSIST-STORE.md:82 「相机自己会把 CP 单元状态写回
   nflasha2:BACKUP.BIN」、:169 「最可能是关机时从 RAM 刷入」、:181 「要么写 /setting/BACKUP.BIN（boot 时被读入）」）
   —— **借 CP 单元机制外推，FTP 状态本身未单独证实**。
3. 开机读到「传输中／未完成」，于是第 1 张就被判为不可调度 → 一张都传不了。
4. 拔电池跳过回写 → 读回干净值 → 恰好能传 1 张，然后回到第 1 步。

附带发现（取证用得上）：firmware/nflasha5-2.00.bin 偏移 0x1d6e3xx 一带存在 appFw .rodata 的原样 4 KB 页拷贝
（含 FTPNSEND.DAT 与整段 [ftp_transfer] 日志串，最长一致段恰为 4096 B），nflasha5-after.bin 同位置相同 →
这块 WBI 区会落运行时／镜像痕迹，失败后优先 dump 这一段。

## 5.1 追加观测：取消传输后「FTP功能」整项变灰（用户实测，m00357）

> 传完第一张，之后的图片一直显示传输中，取消传输后，那个 ftp 功能的选项就直接暗了，选不了了，提示该功能已被禁用

这条把故障分成了两段，而且给出了「变灰」这个可搜索的现象：

- 相机菜单里的这一项叫 **FTP功能**（f-entries.txt：`021c6a6d` / `021c7147`「FTP功能」），
  灰掉时的提示是「**此功能当前被禁止。**」（string_simplifiedchinese.txt：`0204e377`、`0204e45e` 等 20 余处，
  同一句被多个菜单项复用，所以不能靠提示文案定位到具体判断点）。
- 对应到 model 层的参数（`PRM_*` / `VAL_*` 字符串表）：
  - `PRM_setting_ftp_function`（0x40f2c05）取值 `FTP_FUNCTION_ON` / `FTP_FUNCTION_OFF`（0x425bf79 / 0x425bfa2）
  - `PRM_ftp_transfer_state`（0x40f2c1e）取值：`FTP_TRANSFER_STATE_STANDBY_CONNECTED` / `STANDBY_SEARCHING_AP` /
    `STANDBY_CONNECTING` / `STANDBY_CONNECTION_ERROR` / `STANDBY_CONNECTED_CERTIFICATION_ERROR` /
    `TRANSFERRING_CONNECTED` / `TRANSFERRING_CONNECTING` / `TRANSFERRING_SEARCHING_AP` /
    `TRANSFERRING_CONNECTION_ERROR` / `TRANSFERRING_CONNECTED_CERTIFICATION_ERROR` / `INVALID`
    （0x425bfed–0x425c29c）→「一直显示传输中」就是状态停在 `TRANSFERRING_*`
  - `PRM_ftp_transfer_canceling`（0x40f3333）取值 `FTP_TRANSFER_NOT_CANCELING` / `FTP_TRANSFER_CANCELING`
  - `PRM_ftp_stopping`（0x40f2bf4）、`PRM_ftp_transfer_re_throwing`（0x40f2837）、
    `PRM_ftp_transfer_for_exclusion`（0x40f2ff5，每张影像的传输态：`NOT_TARGET` / `RESERVED` / `COMPLETE` / `FAILED`）
- 运行时状态列（都在同一张 model 参数/列名表里）：`is_ftp_func_temporary_off`、`ftp_function_internal_state`、
  `is_ftp_stopped_proc_waiting`、`is_ftp_restart`、`ftp_transfer_list_add_state`、`is_ftp_transfer_list_full`、
  `is_ftp_transfer_content_add_processing`、`ftp_setting_save_read_state`、`is_ftp_func_temporary_off`。
  **注意**：这张表里还有 `ftp_stop_wait_cv` / `ftp_stop_wait_mutex`（条件变量与互斥量），
  所以它是**内存里的运行时模型库，不是 flash 镜像本身**；能不能跨关机活下来，取决于哪一部分被快照，
  这一点尚未证明（见第 10 节）。
- model 层方法名（0x4367xxx 段）里有 `ftp_function_on`、`ftp_function_off`、`ftp_function_restart`、
  `ftp_update_status`、`ftp_retry_connect`、`ftp_process_event`、`ftp_pause_transfer_by_media_id`、
  `ftp_unpause_transfer_all`、`ftp_transfer_stop_cmp`、`set_setting_ftp_function_by_smartphone_remote`、
  `is_ftp_func_temporary_off`；FUNC 层有 `FUNC_set_setting_ftp_function`、`FUNC_reset_ftp_result`、
  `FUNC_re_throw_ftp_transfer_state`、`FUNC_save_load_ftp_settings_save|load|delete`。

据此把故障链改成两段（前一段仍属推断）：

1. **第 2 张不推进**：传输态停在 `TRANSFERRING_*`，队列里那条记录没有被处理完
   （可能是 `ftp_transfer_list_add_state` 没走完，或 `ftp_transfer_condition_result` 判成
   `RESTRICTION`/`NO_CONTENTS`，两者都还没证明）。
2. **取消 → 整项被禁**：取消走 `PRM_ftp_transfer_canceling` = `CANCELING` 与
   `INFRA_NOTIFY_FTP_ERR_TRANSFER_CANCELED`/`FTP_ERROR_CONNECT_TRANSFER_CANCELED`，
   之后 `setting_ftp_function` 这一项被判为不可用 → 显示「此功能当前被禁止。」，
   候选载体是 `is_ftp_func_temporary_off`（字面意思就是「FTP 功能临时关闭」）。
3. **正常关机 → 状态留存**：如果第 2 步的标记被快照进 flash，开机后 FTP 功能依旧是禁用态，
   这就是「一张都传不了」；拔电池跳过快照 → 读回旧值 → 又能传一张。

**关键判别实验（不用拆电池）**：出现「FTP功能」变灰后，直接把存储卡插到电脑上，看
`PRIVATE/SONY/FTPNSEND.DAT` 是否存在、多大：

- 文件不存在或 0 字节 → 第 2 张根本没进队列，问题在「加入队列」这一段（`ftp_transfer_list_add_state`）。
- 文件里有 8 字节记录（`load_ftp_transfer_list_from_media` 按 8 字节一条遍历）→ 队列有货但引擎不推进，
  问题在调度/条件判断（`ftp_transfer_condition_result`）。
- 删掉这个文件后不拔电池、直接重开机，如果「FTP功能」恢复可选 → 跨关机的载体是**卡上的队列文件**，
  与 flash 无关，那就还有救：清队列即可，不必动写入字节。
- 删文件无效、只有拔电池才恢复 → 载体是 flash 里的状态，需要另找地址（不在 260 扇区窗口内）。


## 6. 用户侧应急与判别（按顺序试）

1. 看相机屏幕文案：「正在通过FTP传输该影像。」/「无法传输到FTP服务器: 正在重新连接...」/「在FTP传输期间无法执行。」
   （string_simplifiedchinese.txt 里都有）能区分是卡在传输还是卡在连接。
2. 删除存储卡上 PRIVATE/SONY/FTPNSEND.DAT 再重试 —— 这是队列文件，删掉等于清空积压。
3. 静置 2–3 分钟，看 reconnect / power-save 定时器能否自己恢复。
4. 关掉 0x5aa 自动传输，改手动逐张传。
5. 关机前先把 FTP 功能关掉（让状态回到 idle 再断电）。
6. 换一张卡（排除卡上队列文件写坏）。

以上都是绕开故障的手段，不修根因。

## 7. 本次改动（3 个文件）

### 7.1 新增 src/a6700win/notices.py

功能行下方常驻灰字的提醒表，只覆盖会让人卡住的功能：

- "ftp"：「跨关机队列未验证：连续传第 2 张可能卡住。卡住后先取出电池 10 秒再开机，或删除存储卡上 PRIVATE/SONY/FTPNSEND.DAT。」
- "shutter"：「长期可靠性与取出电池后是否保持未验证；升级固件前先备份功能状态。」
- def notice_for(feature_id: str) -> str: return FEATURE_NOTICES.get(str(feature_id), "")

### 7.2 src/a6700win/gui/widgets.py（FeatureRow）

- 新增导入：from ..notices import notice_for（放在 from . import theme 之前）
- 外层由水平布局改为竖直布局：outer = QVBoxLayout(self)（margins 14,10,14,10；spacing 4），
  原来那行内容仍放在内部 layout = QHBoxLayout() 里（margins 14,10,14,10；spacing 12）
- self.tag 之后接 outer.addLayout(layout)，然后新增：

  ```python
  # catalog 的 limits 只在悬停时出现；会让用户卡住的边界用常驻灰字放在行下方。
  self.notice = QLabel()
  self.notice.setObjectName("Faint")
  self.notice.setWordWrap(True)
  self.notice.setIndent(2)
  self.notice.setVisible(False)
  outer.addWidget(self.notice)
  ```

- update_feature() 里 setToolTip 之后接：

  ```python
  note = notice_for(self.feature_id)
  if self.notice.text() != note:
      self.notice.setText(note)
  self.notice.setVisible(bool(note))
  ```

- 灰字样式复用现成的 src/a6700win/gui/theme.py:52：QLabel#Faint { color: TEXT_FAINT; font-size: 12px; }
- 回退方式：删掉导入、把 outer 换回 QHBoxLayout(self)、删掉上面两段即可，没有别的耦合。

### 7.3 docs/FEATURES.md

- 功能表 FTP 行的「做到哪一步」列补：（**有已知边界，见本节末**）
- 在 ### 1.3 之前新增 **已知边界（FTP）** 一节：连续传输、跨关机、应急、以及「不是写入字段的问题」
  （0x5a7/0x5a9/0x5ab 不存在；反向取证指向 FTPNSEND.DAT、load/save_ftp_transfer_list_to_media、
  resume_ftp_transfer()、INFRA_NOTIFY_FTP_TRANSFER_CMP）。

## 8. 为什么不改 catalog 的 limits 文案

原本打算直接改 vendor catalog 里 ftp 的 limits，被一处校验挡住了：

- refs/a6700-powerful/应用/src/a6700_unlock/backup.py:288：
  `if manifest["catalog_sha256"] != profile.catalog.digest:` → 拒绝整个备份
- catalog.digest 由 canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
  算出，改一个字符 sha256 就变；device_profile.py:33 也会拿 profile 里的 catalog_sha256 对比。
- 后果：**用户手上已有的 .a6700backup（实测 41,582 字节稀疏快照）会全部失效**。

所以 vendor 的 a6700-2.00.json 一个字节都不动，提醒放壳层（第 7 节）。顺带记录一条事实：
device_profile.py:223-228 会把 feature 里除 id/name 外的键原样透传给 GUI，也就是说壳层本可以往数据里塞自定义键，
但六个功能的 limits 都很长（sound 三条、dynamic_active 四条），全部内联会变成文字墙，因此只给需要的功能写一行短句。

## 9. 验证记录（本机实跑）

- 编译：.venv/Scripts/python.exe -m compileall -q src/a6700win/notices.py src/a6700win/gui/widgets.py → 无输出（通过）
- 离屏渲染（QT_QPA_PLATFORM=offscreen，构造 FeatureRow 后 show + processEvents）：
  - ftp 行：notice.isVisible() True，文本为第 7.1 条那句；tooltip 仍是 catalog 的 limits
  - sound 行：notice.isVisible() False，文本为空（没有条目不占高度）
  - sizeHint 高度：带灰字 102 px，不带 58 px
  - row.update_feature(state="disabled") 后灰字仍在，状态胶囊变成「● 已关闭」
- 测试：pytest tests/test_gui.py → 7 passed；pytest（全量）→ 96 passed, 1 skipped
- **环境陷阱**：本机 venv 里的 python 无法在项目根目录、C:/tmp、临时子目录创建文件（PermissionError），
  只有 src/ 下可写；不处理时 pytest 直接报
  `FileNotFoundError: [Errno 2] No usable temporary directory found in [...]`。
  可用的跑法是：`--basetemp=src/.pytest-tmp` 并把 TMP/TEMP 指到同一目录（跑完删掉这个目录）。

## 10. 未闭环 / 下一步

1. **哪个字段卡住还没证明**。候选：is_transferring_infra_ftp、ftp_function_internal_state、
   is_ftp_stopped_proc_waiting、ftp_connection_error_count。要在故障复现时抓 [ftp_transfer] 运行时日志才能定。
2. "正常关机才刷写 FTP 状态"这条是借 CP 单元机制外推的，未单独验证。
3. 真要修根因，动的是固件里的状态机，不在工具的 260 扇区窗口（133,120 字节）内；
   按 docs/FIRMWARE-MAP.md 末节，必须另做 catalog（新增 target 扇区 + 结构守卫 + 未管理字节哈希）并重走四步验收：
   离线预检 → 只读检查 → dry-run → 真机写入。
4. 仓库里没有 FTP 传输运行时的专题文档（docs/ 全量 340,890 B 中 grep -i ftp 几乎为 0），本文是第一篇。
   catalog 引用的 docs/FTP解锁复盘与后续功能准备.md 在仓库中不存在，只是离线研究工作区的证据路径。

## 11. 环境备忘（下次接着查要用）

- 该机器没有 GNU strings / objdump / readelf / gdb；可用 python + capstone（已装 5.0.7）。
- python 读 JSON 默认按 GBK 解码，读 UTF-8 文本必须显式 encoding='utf-8'；控制台中文需 PYTHONIOENCODING=utf-8。
- 用文件读取工具时 /d/ 开头路径会被错误解析成 D:\d\...，必须写 D:/A6700/... 绝对路径。
- 分析脚本放在仓库外（本次在 C:/tmp/a6，含 elf.py：sections()/off2va()/va2off()/cstr()/find_str()/disas()/
  annotate()/xrefs_to()/func_start()/dump()，xrefs_to 按 ADRP+ADD 扫描 .text）。
