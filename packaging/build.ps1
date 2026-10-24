# Powerful6700 · Windows 打包脚本（PyInstaller onedir）
# 用法：powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-DistPath dist] [-WorkPath build]
param([string]$DistPath = "dist", [string]$WorkPath = "build")
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# 绝对路径直接用；相对路径才拼到仓库根下（Join-Path 遇到绝对子路径会拼坏）。
function Resolve-UnderRoot([string]$Path) {
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return (Join-Path $root $Path)
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "未找到虚拟环境：$python（先按 docs\BUILD.md 准备依赖）"
}

$distRoot = Resolve-UnderRoot $DistPath
$workRoot = Resolve-UnderRoot $WorkPath
$dist = Join-Path $distRoot "Powerful6700"
$exe = Join-Path $dist "Powerful6700.exe"
$selftest = Join-Path $dist "offline-self-test.json"

Write-Host "[1/4] 运行测试" -ForegroundColor Cyan
& $python -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "测试未通过，终止打包" }

Write-Host "[2/4] PyInstaller 打包" -ForegroundColor Cyan
& $python -m PyInstaller "packaging\Powerful6700.spec" --noconfirm --clean `
    --distpath $distRoot --workpath $workRoot
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }
if (-not (Test-Path $exe)) { throw "未生成 $exe" }

Write-Host "[3/4] 复制必读与许可文件" -ForegroundColor Cyan
Copy-Item (Join-Path $root "packaging\必读.txt") $dist -Force
foreach ($name in @("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")) {
    $src = Join-Path $root $name
    if (Test-Path $src) { Copy-Item $src $dist -Force }
}

Write-Host "[4/4] 冻结包离线自检" -ForegroundColor Cyan
if (Test-Path $selftest) { Remove-Item $selftest -Force }
# 窗口化 exe 不会让 PowerShell 等待（退出码也不可靠），用 Process 显式等待并读结果文件。
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.Arguments = "--offline-self-test --json `"$selftest`""
$psi.UseShellExecute = $false
$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc.WaitForExit(180000)) { throw "冻结包自检超过 180 秒没有结束" }
if (-not (Test-Path $selftest)) { throw "冻结包自检没有写出结果（exit $($proc.ExitCode)）：$selftest" }
$payload = Get-Content $selftest -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $payload.ok) {
    $failed = ($payload.checks | Where-Object { -not $_.ok } |
        ForEach-Object { "$($_.id): $($_.detail)" }) -join "; "
    throw "冻结包自检未通过（$($payload.version)）：$failed"
}
Write-Host "完成：$exe（自检通过，$($payload.version)）" -ForegroundColor Green
