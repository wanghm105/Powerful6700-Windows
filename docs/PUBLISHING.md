# 发布到 GitHub

本文件只记录「发布这一步」要满足的条件和命令。功能与验证状态见 [VALIDATION.md](VALIDATION.md)。

## 发布前必须成立的条件

1. **许可证一致**：`third_party/a6700_unlock/` 是 [xyzhangxin/sony-a6700-powerful](https://github.com/xyzhangxin/sony-a6700-powerful)
   0.2.0 的原样副本（GPL-3.0-only）。本项目整体因此按 GPL-3.0-only 发布，仓库里必须带：
   - `LICENSE`（GPL-3.0 全文）
   - `NOTICE`（上游版权与免责声明）
   - `THIRD_PARTY_NOTICES.md`（PyUSB / libusb / PySide6 / libwdi 等）
2. **改动可追溯**：本项目自己的代码全部在 `src/a6700win/`（约 4,000 行），对上游的 22 处
   修改逐条写在 `docs/ARCHITECTURE.md`；与上游的差异说明写在 `docs/UPSTREAM-NOTES.md`。
   GPL-3.0 要求分发二进制时提供对应源码——发布 zip 时把同一提交的源码包一起放出来。
3. **不提交运行期数据**：`.gitignore` 已排除 `.venv/`、`build/`、`dist/`、`.data/`、
   `wheelhouse/`、`__pycache__/`、`*.pyc`、`.pytest_cache/`。`.data/` 里有备份文件
   （含机身状态）、运行日志与下载的 libwdi 组件，**绝不能**进仓库。
4. **不含本机路径**：首次发布前确认 `git grep -nE 'D:.*DSH|C:.*Users'` 为空。
5. **免责声明可读**：README 写明非官方、非 Sony、风险与适用范围（仅 A6700 + 固件 2.00）。

## 首次发布

```bash
cd Powerful6700Win
git init -b main
git add -A
git commit -m "Powerful6700 · Windows 0.2.0：A6700 工具的 Windows 端实现"
git remote add origin https://github.com/<你的账号>/Powerful6700Win.git
git push -u origin main
```

## 发布 zip

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools/make_release.ps1
```

产物 `dist/Powerful6700-Windows-x64.zip`（约 40 MB，已剔除 `.data`）。作为 GitHub Release
资产上传，同时附上该提交的源码 zip（GitHub 的 Source code 自动产物即可）。

## 不建议在仓库里放的东西

- 打包后的 `dist/`（体积 + 每次构建都变）
- `wheelhouse/`（依赖缓存）
- 相机备份 `.a6700backup`（含机身固件状态快照）
- `wdi-simple.exe` / `zadig.exe`（运行时从 libwdi 官方 release 下载即可）
