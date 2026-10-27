# 发布风险复盘与整改清单（GitHub 现状）

> 时点：2026-10-26 深夜。审计对象：本地 `HEAD 73e36a3`（与 `origin/main` 同步，ahead 0）与 tag `v0.3.7-win.1` 的发布物。
> 后注（2026-10-26 发布后）：0.3.8 已发布（tag `v0.3.8-win.1`），本文件里的 P0/P1 清单与「未发布」判断都已过时，现状只看 `docs/AI-HANDOFF.md` §0。
> 未复核：GitHub Release 页面正文、Issues（当时离线）。

> **相机现状：砖。** 黑屏无限重启，USB 只在每次循环里出现约 1.5 秒的 HID 设备（PID `0x0D68`），从不出现 MSC `0x0E76` 或服务模式 `0x0336`。恢复路线是 RP2040 冷启动注入 + sparse 写回扇区 39,137…39,145，素材已备好在 `.data/recovery/`（见 `docs/FL23-FULL-RECORD.md` §8.5）。
> **本文件里的所有整改都不需要碰相机**，全部是文档、目录与 GUI 文案级别的改动。

---

## 一句话结论

代码质量不是短板（96 个测试、逐字节回读、无强制写入开关）；短板是**对外承诺**和**危险面收口**：

1. 一个从未真机验收的功能（一次写入）以主按钮发布；
2. README 里一句「机身里没有那一层」把已经证实的风险说成了不存在；
3. 二十多个能写相机内部存储的脚本裸奔在 `tools/` 里，仓库零 CI、零警告。

三件都能在不动相机的前提下改完。

---

## 三个大问题

### P0-A｜「一次写入：颜色 + 名字」是主按钮，但完整流程从未真机验收

证据：

- `src/a6700win/gui/looks_page.py:90` — `QPushButton("一次写入（颜色 + 名字）")`，`setObjectName("Primary")`，tooltip 只写「分两次连接，约 2 分钟」。
- `src/a6700win/bundle.py` — 两段会话（颜色段 → 文字段），文字段失败只写进 `report["error"]` 并 return，不抛异常。设计克制，但**没有界面层面的门**。
- `docs/VALIDATION.md` 的未验清单里包含「一次写入完整流程」；README 的「验证状态」一节也没提它——**发布物里没有任何地方告诉用户这是未验收的**。

为什么这条最重：同类「两段写大文件」的路径在真机上已经出过事。

- 0.3.5 真机把 `/usr/share/app/string_simplifiedchinese_f.uxc` 写成了**半截**（前 131,072 B 新版 + 残尾），之后相机进入「一次上电只给一个服务会话」的状态，靠 0.3.7 的自愈补丁才绕出来。
- 2026-10-26 把 `/cp/cpapp-b.bin` 的 3,872 B 曲线区误写全零 → 相机**黑屏无限重启**，回滚代码一行都执行不到。

也就是说：**回滚的前提是相机还能开机、插上数据线还能被认成海量存储器（MSC）**。而 README「开始前必读」写的是「失败时程序会尽力回滚并如实告诉你结果」——这句在关键处给了错误的安全感。

### P0-B｜`README.md:57` 是错的，而且是最危险的那种错

现状原文：

```text
**不做**：整盘固件备份、FL2／FL3 原生外观、机内 3D LUT、录像卡速档位、像素位移、动态防抖。前几项是机身里没有那一层，后两项是上游试过但没稳住，已经撤回。
```

事实：

- FL2/FL3 的两层**都在机身里**。2026-10-25 真机复刻成功，菜单从 14 项变 16 项（用户亲眼确认，显示为 `5VV2` / `6BW`）。
- 真正的结论是：**做出来了，但静拍路径上没有可用的 mode 数据**，继续往 `cpapp-b.bin` 造数据会写砖。这是风险披露，不是「不存在」。
- 机内 3D LUT 同理：槽位存在（CP 单元空槽与 `init_cc_3DLUT` 符号都在），未知的是接线方式。

### P0-C｜写机脚本裸奔 + 零 CI

- `tools/` 下 20 多个能直接写机的脚本：`cp_*.py`、`fl23_*.py`、`firehydrant_drill.py`、`fl23_write.py`、`fl23_slot_map.py`… 有的还带 `--yes`。
- 仓库根**没有 `.github/`**（零 CI），没人拦住顶层 import，也没有任何脚本头上写「这会写相机」。
- `src/` 里 0 个 TODO/FIXME —— 说明问题不是「遗留标记被忽略」，而是危险脚本从上线第一天起就没被标注过。

---

## 功能取舍

| 功能 | 现状 | 建议 |
| --- | --- | --- |
| 一次写入（颜色 + 名字） | `Primary` 主按钮，未真机验收 | **撤回/降级**：0.3.8 先移除按钮，或收进「实验」折叠区并默认禁用；真机复验通过后再放回 |
| 菜单文字批量写（145 KB） | 已验证、可逐字节还原，但历史事故源 | **保留**，加三重门：写前必须导出基线、写入前列出分区与字节数、失败后给「拔电池」指引 |
| 外观颜色写入 | 多次真机、逐字节可逆 | **保留**，这是招牌功能 |
| 解锁 / 关闭、备份 / 恢复、只读检查、驱动准备 | 已验证 | **保留** |
| FL2/FL3 | 从未进过 GUI | 不涉及下架；文档里「P1 技术路径已通」必须撤回到「实验性、暂停、有变砖记录」 |

---

## 整改清单

### P0（做完就能发 0.3.8）

- [ ] `README.md:57` 的「不做」列表改写（文案见下）
- [ ] `README.md:129` 的「开始前必读」加黑屏变砖披露 + 「回滚依赖相机能进服务模式」
- [ ] `README.md:205` 的「验证状态」明确列出「一次写入：未真机验收」
- [ ] 「一次写入」按钮加锁或移除（`src/a6700win/gui/looks_page.py:67-92`）
- [ ] 把工作树里已写好的 `src/a6700win/notices.py`（FTP 第 2 张卡死、快门音两条常驻提示）+ `src/a6700win/gui/widgets.py` 的 20 行改动 + `docs/FTP-KNOWN-ISSUE.md` 一起发版
- [ ] 首屏「操作前须知」增两条（文案见下）
- [ ] 每次写入前弹确认框，列出「写哪个分区 / 多少字节 / 回滚方式 / 中断后果」
- [ ] 失败结果页给三步自救（文案见下）

### P1

- [ ] `tools/experimental/`：搬走写机脚本 + 红头 README + CI 禁止顶层 import
- [ ] 接 CI：`pytest`（`QT_QPA_PLATFORM=offscreen`）+ `tools/check_publish.py` + `--render-pages` 七页回归
- [ ] 关于页「导出诊断包」：脱敏 zip（诊断 JSON + 最近日志 + 版本 + 枚举到的 PID 与驱动）
- [ ] 离线 `.a6700backup` 查看器（状态表 + JSON 导出 + 两份 diff）
- [ ] 结果页 7 种状态分级（completed / no-op / blocked / rolled-back / uncertain / verification-failed / recovery-required，现在只有 success/danger 两色）

### P2

- [ ] 只读检查前的「环境体检卡」（型号 / 固件 / PID / 驱动 / 管理员 / 服务模式逐项 ✓✗）
- [ ] 灰按钮必须带 tooltip 解释原因
- [ ] `--render-pages` 自动产出 `docs/images/*.png`
- [ ] 配方编辑器（离线编辑 `docs/looks-profile.json` + 复算 12 档 RMS / 矫正率）
- [ ] UXC 只读页（把 `looknames --status` 搬进 GUI）
- [ ] `docs/README.md` 索引 + 权威表；`docs/FL23-FULL-RECORD.md` 标为历史档案
- [ ] ruff + mypy、requirements lock、Inno Setup 安装包、代码签名、更新提示（只提示不下载）

---

## 警告文案（可直接抄）

### 1. 首屏「操作前须知」增两条

```text
- 这个工具写的是相机内部存储，不是 SD 卡。写入过程被打断，相机可能进入无法连接、反复重启的状态；
  那种情况本程序救不回来，需要硬件级别的恢复手段。
- 写完必须拔线、关机、等满 60 秒再开机，设置才会落盘；立刻开机会丢。
```

### 2. 每次写入前确认框

```text
即将写入：/cp/cpapp-b.bin   4,456 字节 / 33 段
回滚方式：同一界面「还原」，前提是相机还能开机、插上数据线还能被认成海量存储器（MSC）
中断后果：可能需要拔电池等待 1 分钟再重试；若仍黑屏，只能硬件恢复
```

### 3. 失败结果页三步自救

```text
1) 拔掉数据线；
2) 取出电池，等满 1 分钟以上；
3) 只用电池开机。
不要连续重试、不要反复插拔数据线——那会让相机更久连不上电脑。
```

### 4. README 顶部 banner（徽章下面第一屏）

```text
> ⚠️ 这个工具会写相机内部存储。2026-10-26 我们在开发中把测试机写进了黑屏循环，
> 最终靠硬件注入才救回。没有硬件恢复手段的用户，不要做实验性写入。
```

### 5. `README.md:57` 替换建议

```text
**不做**：整盘固件备份、FL2／FL3 原生外观、机内 3D LUT、录像卡速档位、像素位移、动态防抖。
FL2／FL3 与机内 LUT 那两层机身里确实有——2026-10-25 我们把 FL2/FL3 菜单项做了出来，
但它在静拍路径上没有可用的模式数据，继续往下造会把相机写坏，所以暂停，不再对外承诺。
卡速档位与动态防抖是上游试过没稳住，已撤回。
```

### 6. `tools/experimental/README.md` 红头

```text
这些脚本会写相机内部存储，没有回滚保证，可能把相机写砖。仅供研究，不要在能拍片的机器上跑。
```

---

## 改动位置索引

| 位置 | 现在是什么 | 要改成什么 |
| --- | --- | --- |
| `README.md:36` | 功能状态表，把「一次写入」列在已能用 | 移到实验性/未验收 |
| `README.md:57` | 「前几项是机身里没有那一层」 | 见文案 5 |
| `README.md:129` | 「失败时程序会尽力回滚」 | 补「回滚依赖相机还能进服务模式」+ 变砖披露 |
| `README.md:205` | 验证状态未提一次写入 | 明确写「未真机验收」 |
| `src/a6700win/gui/looks_page.py:67-92` | Primary 一次写入按钮 | 加锁 / 收进实验区 / 移除 |
| `src/a6700win/gui/pages.py:167` | 「操作前须知」四项确认 | 增两条风险确认 |
| `src/a6700win/notices.py`（未提交） | FTP、快门音两条只读提示 | 随 0.3.8 一起发 |
| `docs/FTP-KNOWN-ISSUE.md`（未提交） | FTP 第 2 张卡死的取证 | 随 0.3.8 一起发 |
| `tools/*.py` | 写机脚本在顶层 | 搬进 `tools/experimental/` |

---

## 验证方式

本次整改不需要相机，全部可在离线状态验证：

```bash
cd D:/A6700/1.Powerful6700_Project/Powerful6700Win
PYTHONPATH=src PYTHONIOENCODING=utf-8 QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests -q
# 期望：96 passed, 1 skipped（约 1 秒内）
PYTHONPATH=src POWERFUL6700_DATA=".data" PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m a6700win --render-pages
PYTHONPATH=src POWERFUL6700_DATA=".data" PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m a6700win --offline-self-test
PYTHONPATH=src PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe tools/check_publish.py
```

注意：

- 跑 GUI 测试必须带 `QT_QPA_PLATFORM=offscreen`，否则可能挂住。
- `timeout` 不能直接跟在环境变量赋值后面，要用 `env VAR=... timeout ...`。
- 打包后 `dist/` 里的 exe 运行期间不能删改（`base_library.zip` 被占用）；重新打包前先关掉。

---

## 红线（这次不改，也不要顺手做）

- 任何写相机的新功能（CP 单元、`/cp`、`/usr`、UXC、`flash` 通道）。
- FL2/FL3 继续推进、mode 19/20 的任何实验。
- 整盘固件备份、`.cube` 导入。
- 理由：相机是砖；且 mode 19/20 在静拍上为什么不成立还没解。

---

## 交接注意

- 工作树里有 **12 篇 docs 改动未提交**（用户明确要求不提交、也不写进 GitHub 主页，只作跨对话交接）。详见 `docs/AI-HANDOFF.md` §20 与 `docs/FL23-FULL-RECORD.md`。
- 未跟踪文件：`docs/FL23-FULL-RECORD.md`（492 行全量档案）、`docs/FTP-KNOWN-ISSUE.md`、`src/a6700win/notices.py`、多个 `tools/fl23_*.py`、`tools/cp_*.py`、`GitHub端下载/`。
- 相机恢复素材：`.data/recovery/ramp.img`（4,608 B, sha256 `f3078dd214972e04d4f45ee137dc905720d8bd94457224738fe5dcc895e7159d`）、`ramp.sparse`（`591f89a971f0a72133a80a4ce8c762db32e21ecb055a3f254624977ee6f9805a`）、`restore-b.sparse`（`afdd68ac8ce32039e21eec8a4e4ada3b40e12166e5aa7c989e2d3076ed4a7063`）。
- 相机恢复前，**不要**跑 `--inspect-once --probe`（A 层补丁在机上时会返回「C6 黑白」假象）。
