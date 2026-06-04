# 一键拉取/更新 ref/ 目录下的所有外部参考仓库 (PowerShell)
# 用法: .\ref\pull-all.ps1

$repos = @(
    @("GESim", "https://github.com/LazyShion/GESim.git"),
    @("chematic", "https://github.com/kent-tokyo/chematic.git"),
    @("paddleocr-vl-local", "https://github.com/CHEN010325/paddleocr-vl-local"),
    @("MoleCode", "https://github.com/AtomFlow-AI/MoleCode.git")
)

$base = Split-Path -Parent $MyInvocation.MyCommand.Definition
Write-Host "Working directory: $base`n"

foreach ($item in $repos) {
    $name = $item[0]
    $url  = $item[1]
    $path = Join-Path $base $name

    Write-Host "[$name]"

    if (Test-Path (Join-Path $path ".git")) {
        Write-Host "  Existing repo found at $path, pulling..."
        $oldPwd = Get-Location
        Set-Location $path
        git pull
        Set-Location $oldPwd
    } else {
        Write-Host "  Cloning from $url..."
        git clone $url $path
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠️  Exit code $LASTEXITCODE`n" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ OK`n" -ForegroundColor Green
    }
}

Write-Host "Done."
