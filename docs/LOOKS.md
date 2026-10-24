# 自定义外观（Classic Chrome / Classic Negative / 理光正片负片）

适用：Sony A6700（ILCE-6700）+ 固件 **2.00**，Windows 端工具 Powerful6700。
本文是最终状态说明；调查过程、失败路径与全部实测数据在 [LOOK-COLOR.md](LOOK-COLOR.md)。

## 1. 现在能做什么

| 菜单项 | 名称（已改写） | 内容来源 | 验收 |
| --- | --- | --- | --- |
| PT（第 2 项） | Classic Chrome | 出厂 bank6 × 1.00，pair2 × 0.52 | 逐色相 RMS **0.194** |
| NT（第 3 项） | Classic Negative | 出厂 bank4 × 1.00，pair2 × 0.62 | 逐色相 RMS **0.190** |
| VV（第 4 项） | Positive Film | 出厂 bank1 × 1.05，pair2 × 0.75 | 轻量版（低饱和） |
| VV2（第 5 项） | Negative Film | 出厂 bank14 × 0.62，pair2 × 0.85 | 轻量版（低饱和） |

CC / NC 的验收口径：同一场景内与 ST 基准帧比，12 个 30° 色相档的
「实测 / A7C2 参考目标」RMS。CC 目标向量
`0.77 0.81 0.74 0.48 0.61 0.62 0.69 0.83 0.99 1.06 0.76 0.53`，
NC 目标向量 `0.63 0.79 0.34 0.58 0.67 0.74 0.91 0.77 0.91 0.85 0.63 0.44`（来自 A7C2 项目的 19 张真实直出对照图）。

## 2. 原理（三行）

- 外观颜色存在 CP 单元 `0x02A40001` 的色度表里：`0x1250 + bank*64`，每条 64 B = **12 组 (Cb,Cr)**（24 个 int16）。
- 菜单里的每个外观按固定 bank 读色度（ST=0、VV=1、NT=4、PT=6、FL=8、SE=9、VV2=**14**）。
- 12 组里只有 **第 2 组（pair2）** 是有用的宽把手：压它 ≈ 把 60–180° 的暖区整体下压（宽约 90°），其余 11 组叠不出局部形状。

名称走 `/usr/share/app/string_simplifiedchinese_f.uxc`（UXC 资源，改记录文本 + 重排索引表），断电保留。

## 3. 一键写入

```powershell
# 相机切到「USB 存储 / MSC」，先干跑确认计划
python tools/looks_apply.py --dry-run
# 真正写入（整单元读基线 → 写 → 回读校验）
python tools/looks_apply.py --confirm yes-write
```

配方在 [looks-profile.json](looks-profile.json)，改配方改这个 JSON 即可；
单条也可用 `tools/look_write.py --look "CC=6:6:1.00@2*0.52"` 直接写。

改名（一次性，写前自动备份到 `firmware/uxc/`）：

```powershell
python tools/uxc_grow.py --set 0x021c6654/0x021c6f8b="Classic Chrome" `
    --set 0x021c6434/0x021c7002="Classic Negative" `
    --set 0x021c687b="Positive Film" --set 0x021c689a="Negative Film" --confirm yes-write
```

## 4. 验收方法（可复现）

```powershell
# 同一场景、同一机位，先拍 ST，再依次拍四个外观，各带 .ARW
python .data/hue_eval.py <ST.jpg> <LOOK.jpg>     # 输出 12 档比值、最优整体缩放 s、RMS
```

注意事项（踩过的坑）：
- **MSC 模式下不能拍照**，拍完必须切回拍照模式，写之前再切回 MSC。
- 每轮场景/光线不同，**跨轮的绝对比值不可比**，只能比同一轮里的「外观 vs ST」。
- 判读顺序时先确认文件顺序（第一张必须是 ST），否则 RMS 会算反。

## 5. 边界（明确做不到的）

| 想要 | 现实 |
| --- | --- |
| 富士的 S 形影调 | **做不到**。A6700 无可用伽马层：cpapp 里 9 条 1024 B 恒等斜坡（`0xfe0b50` 起）改成 gamma 2.2 后实拍与屏幕均无变化，是死数据。 |
| NC 的窄带品红缺口（0.34） | **只能近似**。目标形状靠 pair2 的宽下压逼近到 RMS 0.190；真正的窄带需要逐色相权威，而 `0x02A4000D` 做不到（见下）。 |
| 理光正片的「压红抬黄绿」、负片的「压红压蓝但抬正蓝」 | **做不到**，停在低饱和轻量版。 |
| `.cube` 直接导入 | **做不到**。相机只吃自己的色度表；A7C2 的 `.a7look`（缺 curve/matrix/chroma 三层）与 `.dcp`（Adobe PCS 线性 RGB 的 HSV 空间）都无法搬到 12 组 (Cb,Cr) 模型。 |

## 6. `0x02A4000D` 的 16 个块（已探明，但不是解法）

- 单块整填 +20000 可定位归属：**block2 = VV 主表**、**block3 = NT(NC) 主表**、**block4 = 仅 PT 的蓝端**。
- 填 1–8 时 PT/NT/VV/FL/IN 五个一起爆；VV2/SH/SE 从不响应，它们的表在 9–15。
- 但**基线量级的修改测不出来**：整块 × 0.6 后平均色度 0.0620（基线 0.0621）；只有灌 +20000 这类超载才显形，
  且响应与"填了几个值"近似线性（16/8/4 个值 → 蓝 7.67/4.58/2.98×）。
- 结论：它是**细调增量表**，不是颜色曲线的权威，做不出逐色相性格。数值饱和，也不能用幅度排序区分归属。

## 7. 还原到出厂

1. `python tools/cp_verify_factory.py` —— 逐单元与 `/setting/def/BACKUP.BIN` 的出厂副本比对；
2. `python tools/restore_units.py` —— 把出厂值写回 CP RAM；
3. **正常关机再开机** —— 相机才会把 RAM 覆盖进 `/setting/BACKUP.BIN`（少了这步会出现"当场对、重启又变"）；
4. 名称还原用 `firmware/uxc/` 里的时间戳备份。

## 8. 工具索引

| 工具 | 用途 |
| --- | --- |
| `tools/looks_apply.py` | 按 `docs/looks-profile.json` 一键写四个外观（幂等） |
| `tools/look_write.py` | 单条写入，支持 `base`、系数、pair 覆写（`@2*0.52`） |
| `tools/uxc_grow.py` | UXC 改名 / 加长（自动重排索引表） |
| `tools/look_loop.py` / `.data/hue_eval.py` | RAW+JPEG 标定、逐色相验收 |
| `tools/cp_read.py` / `cp_write.py` | CP 单元读写原语 |
