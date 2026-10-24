# Powerful6700 · Windows 打包脚本（PyInstaller onedir）
# 用法：powershell -ExecutionPolicy Bypass -File packaging\build.ps1
param([string]$DistPath = "dist", [string]$WorkPath = "build")
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "未找到虚拟环境：$python（先按 docs\BUILD.md 准备依赖）"
}

Write-Host "[1/3] 运行测试" -ForegroundColor Cyan
& $python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "测试未通过，终止打包" }

Write-Host "[2/3] PyInstaller 打包" -ForegroundColor Cyan
& $python -m PyInstaller "packaging\Powerful6700.spec" --noconfirm --clean --distpath $DistPath --workpath $WorkPath
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$exe = Join-Path $root (Join-Path $DistPath "Powerful6700\Powerful6700.exe")
if (-not (Test-Path $exe)) { throw "未生成 $exe" }

Write-Host "[3/4] 复制必读与许可文件" -ForegroundColor Cyan
$dist = Join-Path $root (Join-Path $DistPath "Powerful6700")
Copy-Item (Join-Path $root "packaging\必读.txt") $dist -Force
foreach ($name in @("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")) {
    $src = Join-Path $root $name
    if (Test-Path $src) { Copy-Item $src $dist -Force }
}

Write-Host "[4/4] 冻结包离线自检" -ForegroundColor Cyan
& $exe --offline-self-test --json (Join-Path $root (Join-Path $DistPath "Powerful6700\offline-self-test.json"))
Write-Host "完成：$exe" -ForegroundColor Green
