# A6700 CP 分区（nflasha8）只读勘察

日期：2026-10-24　相机：ILCE-6700 / 固件 2.00　方式：WinUSB + dump_range.elf，全程只读（openat O_RDONLY）

## 1. 已取到的镜像

| 文件 | 大小 | sha256 |
| --- | --- | --- |
| `D:\DSH Desktop\Project\firmware\appFw-2.00.so` | 89,027,992 | 721fceaef26a46dabd538c4729b8c5a937b51887d4b127ba2832959b03c1144d |
| `D:\DSH Desktop\Project\firmware\nflasha8-2.00.bin` | 67,108,864 | 3bddcce378438423617a7c647ab862e5fd4ee6d0d4f627b769b4b08007457dcc |
| `D:\DSH Desktop\Project\firmware\cp\cpapp-b.bin` | 17,892,024 | 43c5d056ed935795…（完整值见 sidecar） |

dump 命令（无需管理员，0x0E76 已绑 WinUSB）：

```
cd Powerful6700Win
MSYS_NO_PATHCONV=1 ./.venv/Scripts/python.exe tools/dump_camera.py --path /dev/nflasha8 --out ../firmware/nflasha8-2.00.bin
```

67 MB 用时 17 s，≈3.8 MB/s。

## 2. nflasha8 是 FAT12 卷，不是裸程序

- 扇区 0 是 mkfs.fat 引导扇区：bps 512 / spc 32 / rsvd 32 / nfats 2 / rootent 512 / fatsz16 32。
- 根目录在 `0xC000`，数据区从 `0x10000` 开始，簇 16 KiB。
- 目录项（12 个文件，全部 chain 校验通过）：

| 文件 | 字节 | 说明 |
| --- | --- | --- |
| cpapp-b.bin | 17,892,024 | CP 应用（ARM32 Thumb，非 ELF，入口前 4 字节 e59f1004） |
| cpImg.dat | 1,885,696 | |
| nor_ldr.img | 417,792 | |
| OldAmtCL.bin | 161,766 | |
| MIS.bin | 119,296 | |
| DmmCfg.bin | 43,972 | |
| SysSound.bin | 41,792 | |
| mini_ldr.bin | 40,752 | |
| loader_spi.bin | 39,184 | |
| DGU.bin | 24,336 | |
| pcie_phy_fw.bin | 16,384 | |
| tomco.txt | 741 | |

提取结果在 `firmware/cp/`。

> 注：`third_party/a6700_unlock/data/a6700-2.00.json` 的 `images.cpapp` 声明 25,008,128 字节、
> sha256 f12fa369…，与本次真机 dump 出来的分区对不上（该清单来自上游作者的另一种提取路径）。
> 因此现有 260 扇区写窗口里那一条 cpapp 编辑（0x5d3900）不能直接套用到本机 dump，
> 只要动 CP 就必须重新做“结构守卫”。

## 3. cpapp-b.bin 里的 look / LUT 机制（字符串证据）

cpapp-b.bin 是 ARM32 Thumb 裸镜像，60,408 条 ≥6 字节 ASCII 串，其中与画面处理相关的关键串：

- `SET_LOOKNAME` / `SET_LOOKNAME PARAM_ERR: LookCategory %d` / `SET_LOOKNAME PARAM_ERR: LookName %d` / `SET_LOOKNAME_DMM_OPEN_ERR` / `SendVEF_PathSetLookname`
- `SET_LUT` / `SET_LUT PARAM_ERR: InternalRec %d` / `SET_LUT PARAM_ERR: PanelEvf %d` / `SET_LUT PARAM_ERR: MainOutput %d` / `SET_MONITOR_LUT_ERR`
- `init_cc_3DLUT` / `CC: LUT Write Cnt:%d %d %d` / `CC: Copy2DLUT 0x%X > 0x%X` / `CC: Copy2DLUT uc_SRAM=[%d], SRAM addr=0x[%X]`
- `EC: Invalid Value baseLook -> %x`
- `CheckSetPictureProfile` / `CheckSetColorMode` / `CheckSetMovieColorSpace` / `CheckSetStillColorSpace`

结论：Creative Look 的“名字 → 类别 → LUT/矩阵”这条路走在 CP 侧（cpapp-b.bin），
而 appFw.so 里只有 12 处 UI 资源 id（`No88_CreativeLookOptionVlue` 等），不含系数表。

## 4. 卡速限制的落点在 appFw.so（主控侧）

appFw.so 的 .rodata 里有一整族判定文案（0x4315ac0–0x4317f06）：

- `CAUTION_ID_XAVC_TRANSFER_RATE_DISABLE_UNDER_{100,200,400,600,1350}MBPS_MEDIA_SLOT{1,2}[_SECONDARY_SLOTn][_FILE_FORMAT]_MSG`
- `CAUTION_ID_SLOW_AND_QUICK_XAVC_TRANSFER_RATE_DISABLE_UNDER_{80,100,200,400,600,1350}MBPS_*`
- `CAUTION_ID_PROXY_*` 变体

也就是说 4K120p / S&Q 的门是“介质传输速率档位（MB/s）”，不是 V30/V60/V90 枚举；
另有独立的一层 `T_CONFIRMED_LICENSE_TYPE_4K120P_NOT_AVAILABLE_FILE_FOMRAT_XAVC_*`。
串搜索：`FL2`/`FL3`/`V90`/`SpeedClass`/`SDR104` 在 appFw.so 中 0 命中。

## 5. 下一步（按风险从低到高）

1. 在 cpapp-b.bin 里定位 `SET_LOOKNAME` / `SET_LUT` 的调用点（ARM32 字面量池反查），
   确认 look 表的数据布局（类别、名字、LUT/矩阵指针），再判断 A6700 是否已存在被隐藏的 FL2/FL3 槽。
2. 在 appFw.so 里用 `CAUTION_ID_*TRANSFER_RATE*` 的字符串地址反查 `.data.rel.ro` 指针表，
   再反查代码，找到“介质速率 → 允许的录制格式”判定函数。
3. 只有在 1/2 都定位清楚、且能给出**结构守卫**（不认识的字节一律阻断）之后，才考虑新的写窗口。
   现有 260 扇区窗口不覆盖这两处，绝不能拿它硬写。
