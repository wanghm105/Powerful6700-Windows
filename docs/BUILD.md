# 构建与依赖

> 依赖已固化为仓库根目录的 [`requirements.txt`](../requirements.txt)，可用 `--no-index --find-links wheelhouse -r requirements.txt` 一次装齐。

## 为什么不用 pip 装依赖

本机 `pip` 走配置里的阿里云镜像时会长时间挂住（`global.index-url = https://mirrors.aliyun.com/pypi/simple/`），
换成官方索引同样卡在建索引阶段；而直接对 `files.pythonhosted.org` 取 wheel 是秒级的。
因此依赖准备走「先下 wheel，再离线安装」：

```bash
./.venv/Scripts/python.exe tools/fetch_wheels.py pyinstaller==6.16.0 altgraph pefile==2023.2.7 \
    pywin32-ctypes pyinstaller-hooks-contrib
PIP_DISABLE_PIP_VERSION_CHECK=1 ./.venv/Scripts/python.exe -m pip install \
    --no-index --find-links wheelhouse --no-input pyinstaller
```

- `tools/fetch_wheels.py` 按 `cp312-win_amd64 → py3-none-any → 其它` 的优先级选文件，缓存到 `wheelhouse/`；
- PyInstaller 的依赖声明是 `pefile!=2024.8.26,>=2022.5.30`，而 PyPI 最新正好是 2024.8.26，
  必须显式取 `pefile==2023.2.7` 并删掉缓存的 2024.8.26，否则离线安装报
  `No matching distribution found for pefile!=2024.8.26`。

运行时依赖（已锁版本）：`pyusb 1.3.1`、`libusb-package 1.0.30.0`、`PySide6-Essentials 6.8.3`、
`shiboken6 6.8.3`、`importlib_resources 7.1.0`（libusb-package 的必需依赖，冻结包必须带上）；
开发依赖：`pytest 8.3.5`、`PyInstaller 6.16.0`。

## 测试

```bash
./.venv/Scripts/python.exe -m pytest tests -q      # 37 passed, 1 skipped
```

界面用例走无头渲染，必须同时设置字体目录，否则 Qt 找不到中文字体会整体退化成方框：

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts ./.venv/Scripts/python.exe -m pytest tests -q
```

## 打包

```bash
./.venv/Scripts/python.exe -m PyInstaller packaging/Powerful6700.spec --noconfirm --clean \
    --distpath dist --workpath build
./dist/Powerful6700/Powerful6700.exe --offline-self-test --json dist/Powerful6700/selftest.json
```

或直接 `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`（先跑测试，再打包，再自检）。

- 产物是 onedir：`dist/Powerful6700/`（约 98 MB，主要是 Qt），exe 4 MB 左右；
- `packaging/Powerful6700.spec` 显式带上 `third_party/a6700_unlock`（→ `_internal/third_party/a6700_unlock`）、
  `libusb_package` 的 `libusb-1.0.dll`（→ `_internal/`）以及可选的 `third_party/libwdi/`；
- exe 是 windowed 的，从终端调用时靠 `AttachConsole` 借用父控制台；从资源管理器直接跑
  `--offline-self-test` 会把结果写到数据目录的 `logs/offline-self-test.json`。

## 发布

```bash
cd dist && powershell Compress-Archive -Path Powerful6700 -DestinationPath Powerful6700-Windows-x64.zip
```
