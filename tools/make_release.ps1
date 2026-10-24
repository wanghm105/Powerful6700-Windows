param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$src = Join-Path $Root 'dist\Powerful6700'
$stage = Join-Path $Root '.data\zip_stage'
$zip = Join-Path $Root 'dist\Powerful6700-Windows-x64.zip'
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Path $stage | Out-Null
# self-test json carries the build machine's absolute paths; keep it out of the release.
$excluded = @('.data', 'offline-self-test.json', 'selftest.json', 'selftest2.json')
Get-ChildItem -Force $src | Where-Object { $_.Name -notin $excluded } |
    Copy-Item -Destination $stage -Recurse -Force
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
Remove-Item -Recurse -Force $stage
"zip: $zip ($((Get-Item $zip).Length) bytes)"
