# 第三方代码与归属

项目自有代码采用 GPL-3.0-only。以下第三方文件保留原作者和 MIT 许可；不得删除其声明。GPL 选择不改变上游文件自身的许可声明。

| 来源 | 分发文件 | 许可及版权 |
|---|---|---|
| [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)，固定提交 `a82f5baaa8e9c3d9f28f94699e860fb2e48cc8e0` | `usb/reference/sony_pmca/constants.py`、`crypto.py`，源码包另含 `verified/usb/reference/sony_pmca/` 原件 | MIT，Copyright (c) 2015 ma1co |
| [ajalt/python-sha1](https://github.com/ajalt/python-sha1) | 上述 `crypto.py` 内的兼容 SHA-1 实现 | MIT，Copyright (c) 2013-2015 AJ Alt |
| [pbatard/libwdi](https://github.com/pbatard/libwdi) v1.0 x64 发布包 | `third_party/libwdi/wdi-simple.exe` 与同目录 `amd64/`、`x86/` 下的驱动载荷（libusb0、libusbK、WinUSB 协装器） | libwdi 本体为 LGPL-3.0，Copyright (c) 2010-2024 Pete Batard；其中的驱动载荷沿用各自上游许可，原始归属见 libwdi 发布包。随包分发是为了让「驱动准备」页完全离线 |

完整许可在对应目录的 `LICENSE.txt` 和 `LICENSE-python-sha1.txt`，运行包与源码包都必须保留。归集文件的来源与逐文件哈希见源码包 `verified/SOURCES.json`；运行版本适配差异见 `docs/PROVENANCE.md` 与 `CHANGELOG.md`。

wheel 中 PyUSB 是单独安装的可选依赖，libusb 为外部运行依赖。macOS 内置环境应用另包含固定版本 CPython／python-build-standalone、PyUSB 和 libusb：来源及哈希在 `desktop/runtime-*.json`，许可与 Python 运行环境元数据位于应用 `Contents/Resources/runtime-licenses/`。libusb 从固定源包构建，对应源包随应用保留在 `dependency-sources/`，可由构建脚本重建替换；这些组件不进入工具 wheel。Unicorn、pyelftools 是可选开发测试依赖，也不随运行包分发。各依赖使用各自的许可。

本项目许可覆盖工具自有代码，不代表取得 Sony 商标或相机固件的所有权，也不将外部固件及用户备份改为 GPL。源码包只收录工具所需的修改字段、校验及归集代码样例，不包含完整固件、个人镜像或机身密钥。

GPL 正文来自 [SPDX license-list-data 的 GPL-3.0-only 文本](https://github.com/spdx/license-list-data/blob/main/text/GPL-3.0-only.txt)；原文版权属于 Free Software Foundation，按其允许逐字复制的声明保留。
