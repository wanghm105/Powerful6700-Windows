# blocked 诊断与取证（0.3.8）

只读检查不通过时，界面原来只有一句「内容或布局不匹配」。差异其实早就算好了，只是没有一个字段被显示。这一篇记录 2026-10-26 那轮离线整改：问题出在哪、加了什么、怎么验的、还差什么。

> 范围：纯离线改动，没有新增任何写入路径，也没有碰过相机（相机自 2026-10-26 起在等硬件修复，见 `docs/FL23-FULL-RECORD.md` §8）。

## 1. 问题：issue #1 为什么问不出东西

上游有两处都只给人一句话：

- `third_party/a6700_unlock/operations.py:288`：`if not plan["compatible"]:` → `result["status"] = "blocked"`，`progress("内容或布局不匹配，已停止；没有写入功能目标。")`。
- `third_party/a6700_unlock/cli.py:83`：只印 `N 处内容／结构不匹配；具体位置见操作记录。`

而 `third_party/a6700_unlock/device_profile.py:143` 的 `inspect_sectors()` 早就把每一处不一致写进 `plan["issues"]`，`compatible = not issues`。字段：

| kind | 带的信息 |
|---|---|
| `sector-guard-mismatch` | `index` / `device` / `offset` / `role` |
| `unknown-field` | `edit_id` / `image` / `offset` / `actual` |
| `unknown-value` | `image` / `offset` / `value` |
| `feature-requirement` | `feature` / `detail` |
| `identity-mismatch` | `image` / `sha256` |

`result["plan"]` 与 `result["run_directory"]` 都在 `result` 里，`plan` 也会写进 `runs/<run_id>/plan.json`。也就是说：**信息一直都在，只是没人读。** 2026-10-25 的 issue #1 因此卡住——用户拿不到偏移，我们只能反问固件版本。

## 2. 这一版加了什么

### 2.1 `src/a6700win/diagnostics.py`（新文件，只依赖标准库）

| API | 作用 |
|---|---|
| `describe(issue)` | 一条 issue → 一句中文；不认识的 kind 原样带出并附其余字段 |
| `issue_lines(issues, limit=12)` | 批量成行；超出补「…还有 N 处，完整列表在运行目录的 plan.json 里」 |
| `issue_hint(issues)` | 一句「最可能的原因 + 下一步」；无话可说返回空串 |
| `read_interrupted(message)` | 这句报错更像「读到一半相机没了」而不是「内容不符」 |
| `environment()` | 版本 / Python / 平台 / 机器 / 数据目录 / `patches.status()` / `setupapi.summary()`，**逐项 `_safe`，诊断自己绝不抛** |
| `report(result, env=None, limit=20)` | 一段可直接粘进 issue 的纯文本（结论 + 只读检查行 + 错误 + 运行目录 + 差异列表 + 环境） |
| `export_bundle(result, target, env=None)` | 打成 zip：`diagnostics.txt`、`result.json`（剔除 sectors/blob 等大字段）、`environment.json`、`run/{plan,result,native-result}.json`（≤2 MB）、`logs/`（最近 3 个 ≤300 KB） |

`describe()` 的实际输出（就是测试里的断言）：

```
结构守卫不匹配：#9 · 0 偏移 0x02844000（role=guard）
字段取值未知：ftp · appFw 偏移 0x00100004 · 实际 ff
```

### 2.2 界面落点

- **「功能管理」页**：被拦下时摘要下面多一行 `被结构守卫拦下：N 处差异，完整原因在「操作结果」页，那里可以复制诊断信息。` + 前 3 条差异（`HomePage.blocked_hint`，默认隐藏）。
- **「操作结果」页**：新增「差异明细 · N 处」卡片（`ResultPage.issues_card`）——hint、前 10 条差异、运行目录，末尾两个按钮：「复制诊断信息」（写剪贴板）、「导出诊断包」（`QFileDialog` → `diagnostics.export_bundle`）。`render()` 里在 `_render_aftercare()` 之前调 `_render_issues()`，没有结果时两块一起隐藏。
- **「关于与诊断」页**：新增「导出诊断包」，还没有结论时至少能把环境与补丁状态带走。

默认文件名：`paths.documents_dir() / "Powerful6700-诊断-%Y%m%d-%H%M%S.zip"`。

### 2.3 命令行

`--inspect-once` 的 JSON 多了三个字段：`run_directory`、`issues`（原始结构）、`issues_text`（中文短句）。冻结包里也能用，排障不必手点界面。

### 2.4 文案口径

`issue_hint()` 三类各一句，原则是**先给最可能的原因，再给一个安全的下一步**：

- 结构守卫不匹配：「机身里的内容和登记的基线不一样。常见的三种原因：相机不是 A6700 固件 2.00；这台相机被别的工具改过；出厂批次的内容本来就不同。**只读检查不写任何东西**，可以放心把诊断信息贴到 issue，我们按偏移对一遍。」
- 取值未知：「某个功能当前的取值不在已知取值表里。最常见的是 FTP 队列有残留（传过一张没传完），或者这个功能被别的工具调过。先在相机菜单里把对应功能关掉、断线重连再试一次。」
- 前置条件：「这次操作有前置条件没满足，按提示把前置功能开到目标状态再重试。」

`read_interrupted()` 认这九种字样：`pipe error` / `errno 32` / `timed out` / `timeout` / `no such device` / `libusb_error` / `broken pipe` / `device disconnected` / `input/output error`。目的只有一个：别把「掉线」说成「内容不符」，免得用户去查固件版本。

## 3. 同批的三处文档/提示修正

| 项 | 状态 |
|---|---|
| README 里「颜色和名字一次写完」同时列在「已经能用的」和「还在做」 | 已删掉「已经能用的」那条；「还在做」写成「按钮默认锁着，要勾一行确认才解锁；一次还原不受限制，那是退路」 |
| `README.md:57` 说 FL2/FL3「不可行」 | 早前已改为「机身里确实有，但静拍路径上没有可用的模式数据，暂停」；本轮核对无需再动 |
| FTP 第 2 张卡死、快门音长期可靠性没有任何提示 | `src/a6700win/notices.py` 的 `FEATURE_NOTICES` 常驻在功能行下方；`NOTICE_SECTIONS` 另有「内置存储」「关机等 60 秒」两条风险 |

`FEATURE_NOTICES` 原文：

- ftp：「跨关机队列未验证：连续传第 2 张可能卡住。卡住后先取出电池 10 秒再开机，或删除存储卡上 PRIVATE/SONY/FTPNSEND.DAT。」
- shutter：「长期可靠性与取出电池后是否保持未验证；升级固件前先备份功能状态。」

## 4. 验证

- `pytest tests -q` → **108 passed / 1 skipped**（原 96+1）。新增 `tests/test_diagnostics.py` 10 例：describe 带偏移、未知 kind 原样带出、截断行数与「还有 N 处」、空列表、hint 文案、掉线识别、report 可粘贴、`export_bundle` 含 `run/plan.json` 且 `result.json` 不含 `sectors`、`environment()` 在探针全炸时仍返回版本号。
- `tests/test_gui.py` 加 1 例：合成两条 issues 后 `ResultPage.issues_card` 可见、标题含「2 处」、正文含 `0x02844000` 与运行目录；`HomePage.blocked_hint` 含「2 处差异」。
- `--render-pages .data/tmp/render` → 七页 PNG 正常（`phase: notice`、`ready: true`）。
- `tools/check_publish.py` → 「干净：仓库与发布包都没有固件、私人备份、密钥、ProductInfo、照片、抓包或日志。」

## 5. 没验证的（别当成已完成）

- 诊断包**没在冻结包里点过**：`.venv` 里跑的是同一份代码，但 PyInstaller 打包后的 `QFileDialog` 与 zip 写入路径没实点。
- **真实 blocked 现场没复现**：只用了合成 issues（真机自 2026-10-26 起在等硬件修复），别人的机器上会不会出现别的 kind 还不知道。
- 掉线识别的字样表是从我们自己的日志里抄的，陌生人报的错可能是别的写法。

## 6. 以后怎么扩

- 上游新增一种 `kind`：只在 `diagnostics._KIND_LABEL` 加一行、`describe()` 加一个分支，界面与 CLI 自动跟着变（`issue_lines()` 是唯一入口）。
- 想给某类差异更具体的下一步：改 `issue_hint()`，不要在页面里拼句子。
- 诊断包要收新文件：改 `export_bundle()` 的 `run/` 白名单；日志仍走 `_recent_logs(limit=3, max_bytes=300_000)`。
- 页面里取结果的写法照抄 `_copy_diagnostics()`：`self.app.snapshot.get("result")`，注意 `ResultPage.render(snapshot)` 收的是**快照**不是 result。

## 7. 相关文件

- 新增：`src/a6700win/diagnostics.py`、`tests/test_diagnostics.py`
- 改动：`src/a6700win/gui/pages.py`（首页 hint + 结果页差异卡）、`src/a6700win/gui/about_page.py`（导出诊断包）、`src/a6700win/inspect_once.py`（三个字段）、`README.md`、`docs/RELEASE-NOTES.md`（0.3.8 小节）、`docs/AI-HANDOFF.md` §16 / §21、`src/a6700win/version.py`（0.3.8）
- 本批全部未提交。


## 8. 现场反馈（2026-10-26 汇总）

到 2026-10-26 晚，「只读检查失败」在群和 issue 上一共三类，证据强度不同，**别混着修**。

### 8.1 `0x10000004`：绝大多数人报的是这一条

- 观测：认证、驱动、二次认证（接口类 `0xff`）、服务响应全部通过，卡在会话里**第一条**文件写入 `0x4010 file_id=0`（`third_party/a6700_unlock/usb/backend.py:188`），返回状态 `0x10000004`（原始字节 `04000010`）。
- 现场的完整日志（用户 m00160）停在「正在读取补丁目标和结构守卫…」（`third_party/a6700_unlock/operations.py:281` 打的），后面的清理进度行不在截图范围里 ⇒ **不能从这段日志判断有没有删掉临时文件**。
- 用户侧已知：换电脑、换线、换口、用上游 Mac 版、相机菜单初始化，都不解决。
- 根因：**未定位**。
  - **已排除「遗留文件」**：`libJit.so` 从没被写过，照样回 `0x10000004`（§8.5 样本 #1）；而健康机在同一步能把三个名字全部删掉（样本 #5）。
  - **首选解释（推断，未证实）**：那台机器的 `/tmp/jiritsu` 整段在会话里不可用（目录或分区不存在、没挂上），于是该区任何路径的 `SELECT` / `REMOVE` / `SET_FILE2` 都回同一个码；0.3.7 / 0.3.8 一直在「清残留」，实际清的是不存在的目录。
  - **次选**：切完模式后发得太早的时间窗——但「换电脑、换 Mac 版、相机菜单初始化都无效」削弱它。
- 取证：`0.3.9-probe1` 把清理结果逐条打印 + 日志落盘，判读见 `docs/AI-HANDOFF.md` §22.5。

### 8.2 结构守卫不匹配：只有一个人（issue #1）

- plan.json 证据（`.data/tmp/issue-at/plan-i1.json`）：`compatible: false`、`read_sectors: 260`、`changed_bytes: 0`、`issues` 只有 1 条 `{"kind":"sector-guard-mismatch","role":"guard","index":0,"device":"/dev/nflasha15","offset":1024}`。
- 也就是 260 块里 259 块与登记基线一致，只有 app 分区字节偏移 `1024`（扇区 2）那块不同。`profile_sha256` / `catalog_sha256` 与本地 `load_device_profile()` / `load_catalog()` 完全一致 ⇒ 用户跑的是同一份 profile，不是版本错配。
- 现有 plan.json **不含 actual / expected 字节或 sha**，所以从证据本身看不出机身里到底是什么。下一步要让 `diagnostics.describe()` 带上 actual 与首个不同字节偏移（**待办，未做**）。
- 只有 yianZHK 一人报（用户 m00168），暂不当主战场。

### 8.3 掉线 / 中断：混在 8.1 里的次生现象

- `[Errno 32] Pipe error`、`0x096F` 非 MSC、连两次认证后不再给服务会话——机理都在 `docs/AI-HANDOFF.md` §11，不是新问题。
- 判读：`read_bytes` 不满 260 块、或 `cleanup_warning` 带掉线字样，才算这一类。

### 8.4 诊断包的两个缺口

- 已修（0.3.9-probe1）：`logs/` 以前恒为空——因为程序根本不写日志文件；现在 `runlog.py` 每次都写，并进诊断包。
- 已修：`logs/` 里超过 300 KB 的日志以前被整份丢掉，现在截尾保留。
- **未修**：`payload_source.matches: false` 会原样出现在用户导出的诊断包里，看着像「安装包坏了」。它其实是上游 `manifest.json` 的 `source_sha256` 与自身 `transaction.c` 不一致（`docs/UPSTREAM-NOTES.md`），真正硬校验的是 reader / writer 的 `.elf`（`src/a6700win/patches.py:170-174`）。要在 `environment()` 里补一句 note。

### 8.5 样本：8 份，含第一份健康对照（2026-10-27 下午补 #7/#8）

| 样本 | 来源 | 版本 | 结果 | 能说明什么 |
|---|---|---|---|---|
| #1 | issue #3（机友 E 上报）的诊断包 | probe1 | 失败 | 整段会话的文件操作全被拒：三个临时文件名、连续两轮、全是 `0x10000004` |
| #2 | 机友 A 的机器（`.data/tmp/issue-at/i4`） | probe1 | 失败 | 同上；且 `cleanup_warning` 为空 ⇒ 会话正常退出，不是「相机被卡住」 |
| #3 | 机友 C 的机器（`报错/…205618.zip` + `…213350.zip`） | probe1 | 失败 ×2 | 同上；另带一次 `[Errno 32] Pipe error` |
| #4 | 机友 D 的机器 | probe1 | 失败 | 同上（只有日志片段） |
| #5 | **健康机**（用户目录 `D:\迅雷下载`，Win11 26200，PID `0x0e76`） | **probe2** | **通过** | 同一步打印「已清掉相机上一次会话留下的临时文件：tmmc.jit、tmmc.dat、libJit.so」⇒ `0x10000004` 属异常状态；随后「检查完成：预计修改 0 字节／0 个扇区」「只读检查完成，可以管理功能」；阶梯未触发 |
| #6 | 同 #5 的另一段日志 | probe2 | 中途两次失败后通过 | 出现过「内容或布局不匹配，已停止」与「USB 认证失败…Operation not supported or unimplemented on this platform」各一次，重跑均通过 ⇒ 这两类至少有一部分是暂时性的 |
| #7 | 机友 C 的机器（报错/Powerful6700-诊断-20261027-112337.zip） | probe4r | 失败 | 12 步全灭；environment.json 里 pid 3702 = 0x0E76、service winusb、supported true ⇒ 相机没被推到 0x096F，但文件服务整个不可用：连读 /setting/BACKUP.BIN 都回 0x10000004，select 三个临时路径都不报错 |
| #8 | 同 #7 的另一份（…111626.zip） | probe4r | 失败 | 日志与 #7 逐行一致（同一台机、同一次会话结构）；导出时刻 pids 为空（数据线已拔），可见 #7 的 0x0E76 是真实的会话内状态 |

**基线判据（写死）**：同一位置打印「已清掉相机上一次会话留下的临时文件：…」= 健康；打印「清理临时文件失败：…Jiritsu 状态 0x10000004」= 异常。这一条把 §8.1 里「是不是所有相机都这样」直接判死：**不是**。

失败样本的共同点与差异：

- 共同点：认证、驱动、二次认证（`0xff`）、服务响应全部通过，卡在会话里**第一条**文件操作；三个临时文件名的 `REMOVE` 与随后的 `0x4010 file_id=0` 回同一个 `0x10000004`。
- 差异：`cleanup_warning` 有的为空（会话正常退出）、有的是 `[Errno 32] Pipe error` ⇒「相机被留在服务模式」不是这个错误的必要条件。

仍然不能证明的：

- 是不是所有报 `0x10000004` 的机器都同一种成因（可能「整段服务不可用」「只是临时区坏」「只是时间窗」几种混在一起）；
- 与固件批次、USB 连接模式、`PC 遥控` 设置、机器来源有没有关系；
- 连续六次被拒会不会把相机推进重启循环。

现在最缺的：卡住那几台用 probe2 再跑一次的日志（看阶梯停在第几层、每层状态码是什么）。判读表见 `docs/AI-HANDOFF.md` §23.2。
