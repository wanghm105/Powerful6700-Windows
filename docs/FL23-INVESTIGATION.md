# FL2/FL3（自定义外观 / User LUT）调查记录 — A6700 固件 2.00

> **状态：历史记录，已被 `docs/FL2-ROUTE.md` 取代。** 本文件是调查过程中的中间记录（含当时的错误假设）。

调查目标：判断能否在 A6700（ILCE-6700，固件 2.00）上复刻 A7C2 项目的 FL2/FL3
（在「创意外观」里增加两个可导入 LUT/DCP 的自定义外观）。全程离线只读，未接触相机。

素材：
- `firmware/appFw-2.00.so`（机身只读 dump，89,027,992 B = 0x54E7598）
- `firmware/nflasha8-2.00.bin` → `firmware/cp/cpapp-b.bin`（17,892,024 B，CP 侧 ARM/Thumb 裸镜像）

---

## 1. 先例：A7C2 的 FL2/FL3 补丁到底改了什么

从 `refs/a7c2-fl23/src/camera_runtime/assets/patches.json` 与 `src/fl23/core.py` 反推：

- **appFw 侧只有 6 个窗口**，其中最关键的一个是 0x3528804：
  原字节 `3f 24 00 71` = `0x7100243f` = **`cmp w1, #9`**；
  补丁后 `3f 2c 00 71` = `0x71002c3f` = **`cmp w1, #11`**（9 个外观 → 11 个）。
  另一处 0x4B4A5E4 / 0x4B4A5EC 把「普通槽 16 / 17」的初始绑定改成 0x0A / 0x0B。
  再两处 0x59892CA / 0x5989382 是 **菜单产品标志**。
- **cpapp 侧**则是十几处 gamma 上限 0x2f→0x32、chroma 白名单、矩阵上界 0x2b34→0x2b38，
  外加 0x1100b80 写入 3872 字节（四组 adapted curve records）。

结论：A7C2 并不是「发明新外观」，而是**打开同平台代码里已经存在的自定义外观机制**，
再往 CP 的曲线/矩阵表里补两套数据。

## 2. A6700 里同一套机制已经存在

这不是猜测，是字符串与结构表的直接证据（全部在 appFw-2.00.so 内）：

| 证据 | 位置 | 含义 |
|---|---|---|
| `PRM_creative_look_option_look0 … look15` | 参数注册表 | 模型里**有 16 个外观槽**（而菜单只暴露 10 个） |
| `PRM_creative_look_option_fade/highlight/clarity/fineness/contrast/saturation/sharpness/shadow` 各 16 槽 | 同上 | 每个自定义外观的 8 个微调参数都按 16 槽预留 |
| `PRM_is_exist_user_lut0 … 15` / `BKID_APP_is_exist_user_lut0 … 15` | 参数表 + BKID 池 | **16 个用户 LUT 是否存在**的标志 |
| `BKID_APP_is_imported_lut_hq0 … 15` | BKID 池 | 16 个「已导入 LUT」标志 |
| `model::import_lut_hq_conversion_t`、`model::sequence_set_lut_data::run()` | RTTI/日志串 | 导入与下发 LUT 的模型序列都在 |
| `BKID_APP_MR_setting_pplut1..4_link_uset_lut` | BKID 池 | Picture Profile 1–4 可挂用户 LUT |
| `menu::util::util_instance::get_name_resid_select_lut(model::value_id_t, libra::ResID&, dict_t&)` | 符号串 | **存在「选择 LUT」的菜单项代码** |
| `No12_UserLUTSubItems_Background`、`No4_UserLUTSubItems_Title`… | UI 资源名池 | 用户 LUT 子菜单的界面资源齐全 |
| `Custom1:(Not Imported)` … `Custom4:(Not Imported)` | 0x40815d8–0x4081634，紧邻 `[with long unsigned int Num = 16ul]` 与 `sequence_get_display_string_list::write_binary_data` | **自定义外观 1–4 的显示串**（未导入时的占位文案） |
| `asrid_func_select_lut_set_userlut_imported_1` / `_not_imported_1`、`asrid_msg_import_userlut_1` | 资源 id 池 | 已导入/未导入两种图标与提示消息 |
| CP 侧 `ChkSetLooknameParam` / `ChkSetLutParam` / `SET_LOOKNAME PARAM_ERR: LookCategory` / `SET_LUT PARAM_ERR: …` | cpapp-b.bin | CP 本来就接受「外观名 + 类别 + LUT」下发 |

也就是说：**A6700 固件 2.00 与 A7C2 共享同一套 User LUT / 自定义外观实现**，
A6700 只是被产品配置关掉了入口（菜单不出现、外观列表只有 10 项）。

顺带确认的负面结果：
- `FL2` / `FL3` 这两个名字在 appFw 与 cpapp 里都 **0 次**——它们是 A7C2 项目的叫法，
  固件里叫 `Custom1..4`。
- `baseLook` 在 appFw 里 0 次（CP 里 3 次，但按地址反查 0 命中，见下）。
- `DmmCfg.bin`（43,972 B）是 CP 的寄存器级配置（24 字节记录 + 构建戳
  `for ilc8g8g26m-ipsxcp 2025/01/16 15:20:57`），与产品功能无关。

## 3. 为什么还不能直接动手（两个硬约束）

**约束 A：补丁偏移不可移植。**
A7C2 的 0x3528804 在 A6700 里是 `fd 7b bc a9`（`stp` 函数序言），不是同一条指令；
0x59892CA / 0x5989382 干脆超出 A6700 文件长度。两份固件是同平台**不同构建**，
必须按结构重新定位，不能照抄偏移。

**约束 B：现有写窗口不覆盖这些字节。**
当前 catalog 只允许写 260 个固定扇区（133,120 字节），集中在 FTP / 快门 / 曝光等标志位附近；
外观代码在 .text、外观表在 .data/.data.rel.ro，都**不在**窗口内。要动必须先扩 catalog。
好消息：我们已有 appFw 的完整明文 dump，可以把任意新目标扇区的
「已知字段清零后哈希」结构守卫离线算出来，所以扩窗口在工程上是可控的。

## 4. 定位 CP/appFw 内部的教训（避免重复劳动）

- appFw 与 cpapp 的**日志/文案串都不按地址引用**：文案表是 `{char* name, u32 id, u32 len}`
  16 字节条目，代码只传 id 或档位索引。因此靠「字符串地址 xref」找判定点一定 0 命中。
- cpapp 里对 `SET_LOOKNAME PARAM_ERR: LookCategory` 等四处串，用四种方式反查全部 0 命中：
  精确 u32 指针、掩码 `(w & 0xFFFFFF)`、Thumb `ADR`/`LDR literal` PC 相对、
  未知基址的三串差值指针表（只出 7 个 base 荒谬的假阳性）。
- appFw 的属性/参数 id 是**线性编号**：外观槽 `creative_look_option_look0..15` 对应
  id 0x1953 + i（每个 24 字节记录 `{name_ptr, x, u32 size, u32 id}`，位于 0x49966d0 起）；
  `creative_look_option_fade0..15` 是 0x19b3 + i；`setting_pictureprofile_colormode0..10` 是 0x1672 + i。
  这些 id 在代码里只出现在**注册函数**（0x1a07f00 附近逐条 `mov w1,#id`）与**名称映射**，
  没有判定分支。

## 5. 下一步（按性价比排序）

1. **找门闸**：定位「外观列表要列几项」「菜单是否显示自定义外观」的产品标志。
   A7C2 的对应物是 0x59892CA / 0x5989382 两个菜单产品标志；A6700 需按
   `No88_creative_look_option` / `No12_UserLUTSubItems_` 资源名反查菜单构建代码。
   若能找到且只改 1–2 个字节，FL2/FL3 就会变成「开关级」改动。
2. **找容量**：确认 CP 的 `LookCategory` 校验上界（cpapp 是 ARM/Thumb，需先写 Thumb 反汇编脚本，
   现有工具只处理 AArch64）。
3. **扩窗口**：无论 1/2 结果如何，落地前都要把 catalog 从 260 扇区扩到目标扇区，
   并为新扇区生成结构守卫（可用明文 dump 离线计算）。
4. **只读验证**：扩窗口后先做 dry-run（读 260+N 扇区 + 全字段/守卫校验），确认不写也能通过，
   再谈真实写入。

风险提示：外观链涉及 CP 的 LUT 存取与 gamma 曲线表。改错 CP 侧的判定或表长，
相机可能进入显示异常/取景异常（可恢复），严重时影响启动。每一步都必须先 dry-run。
