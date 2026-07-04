# Capture the primary screen and save a timestamped PNG into .tmp/
$ErrorActionPreference = "Stop"
$dir = Join-Path (Get-Location) ".tmp"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $dir "ui_$ts.png"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()

Write-Host $out
