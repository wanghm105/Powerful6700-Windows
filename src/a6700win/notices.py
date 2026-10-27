"""功能行下方常驻显示的边界提醒。

catalog 里的 ``limits`` 只在鼠标悬停时出现（见 gui/widgets.py 的 tooltip），实测反馈
里 FTP 的跨关机问题会让人以为是自己网络没配好。这里放必须被看见的那一条。

为什么不直接改 vendor 的 limits 文案：``a6700_unlock/backup.py:288`` 用
``manifest["catalog_sha256"] != profile.catalog.digest`` 校验备份，改一个字就让用户手上
已有的 ``.a6700backup`` 全部失效。所以提醒放壳层，vendor 数据一个字节都不动。
"""
from __future__ import annotations

# 相机被写坏到「连电脑都认不出来」时，软件这边没有任何退路，唯一的路是硬件注入。
# 上游把采购清单、接线和步骤写在同仓库的「硬件说明.md」，直接引它，别在这里复述：
# 上游哪天改了接线，本地这份副本一定会忘掉。
HARDWARE_RECOVERY_URL = "https://github.com/xyzhangxin/sony-a6700-powerful/blob/main/硬件说明.md"

# 键是 catalog 里的 feature id；没有条目的功能行不显示灰字。
FEATURE_NOTICES: dict[str, str] = {
    "ftp": (
        "连着传第 2 张可能卡住（跨关机的情况没在真机上验过）。卡住了先取出电池 10 秒再开机，"
        "或者删掉存储卡上的 PRIVATE/SONY/FTPNSEND.DAT。"
    ),
    "shutter": "长期用会不会出问题、取出电池后还保不保持，这两件都没验过；升级相机固件前，先备份一次功能状态。",
}


# 首屏「操作前须知」在 vendor 那 5 条之前追加的两条。vendor 的 device-risk 只说到
# 「恢复不保证成功」，没说透两件事：写的是机身 NAND 而不是 SD 卡；以及回滚本身依赖
# 相机还能进服务模式。同样放壳层，vendor 的 notice.py 一个字节不动。
NOTICE_SECTIONS: tuple[dict, ...] = (
    {
        "id": "internal-storage",
        "level": "risk",
        "title": "改的是相机机身里的东西，不是 SD 卡",
        "body": (
            "颜色和菜单里那几行字都写在机型内部，不在存储卡上。写入时如果被打断——拔线、"
            "断电、程序崩了、相机自己掉线——相机可能连不上电脑，或者重复重启变砖。真到那一步，"
            "本程序救不回来，只能用硬件办法：拿一块 RP2040 Pico 和一块 USB-C 测试板，按上游的接线图接好，"
            "从 USB-C 口给它冷启动注入。采购清单、接线和步骤都在上游的「硬件说明」里，"
            "下面那个链接就是。能不能改回去，取决于相机还能不能开机、插上数据线还能不能被认成海量存储器（MSC）；"
            "连这个都出不来，软件这边就没有退路。"
        ),
        "source_url": HARDWARE_RECOVERY_URL,
        "link_text": "硬件恢复说明（救砖）↗",
    },
    {
        "id": "power-cycle",
        "level": "risk",
        "title": "写完必须断线、关机、等满 60 秒再开机",
        "body": (
            "相机只在正常关机的时候才把当前状态存下来。写完马上关机再开机，这次的改动就丢了；"
            "所以写完先断线、正常关机，等满 60 秒再开机。开机后先确认相机能正常拍照、菜单能进，"
            "再想第二次写入的事，不要连着反复试。"
        ),
    },
)

def notice_for(feature_id: str) -> str:
    """返回该功能行要常驻显示的提醒；没有对应条目时返回空串。"""
    return FEATURE_NOTICES.get(str(feature_id), "")
