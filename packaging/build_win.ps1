# Build the Windows portable distribution.
#
#   pwsh -File packaging/build_win.ps1 -Texconv D:\tools\texconv.exe
#
# Steps: PyInstaller onedir -> prune unused bytes -> drop README/LICENSE next to
# the exe -> zip. The README ships inside the archive on purpose: people who
# unzip the folder should find the instructions without going back to GitHub.

param(
    [string]$Py = "python",
    [string]$Name = "gtav-asset-repair",
    [string]$Texconv = "",
    [switch]$KeepBuildDir
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not $Texconv) {
        $cand = @("texconv.exe", "..\texconv.exe", "..\..\texconv.exe") |
            ForEach-Object { if (Test-Path $_) { (Resolve-Path $_).Path } } | Select-Object -First 1
        if (-not $cand) { throw "texconv.exe not found; pass -Texconv <path>" }
        $Texconv = $cand
    }

    Write-Host "==> PyInstaller ($Name)"
    & $Py -m PyInstaller --noconfirm --clean --onedir --windowed --name $Name `
        --icon resources/gtatools.ico `
        --add-binary "$Texconv;." `
        --add-data "resources;resources" `
        --paths src `
        --hidden-import PIL.ImageTk `
        packaging/gui_entry.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

    $out = Join-Path $root "dist\$Name"
    $internal = Join-Path $out "_internal"

    Write-Host "==> prune"
    foreach ($junk in @("_tcl_data\tzdata", "libssl-3-x64.dll", "libcrypto-3-x64.dll", "_ssl.pyd", "_hashlib.pyd")) {
        $p = Join-Path $internal $junk
        if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
    $msgs = Join-Path $internal "_tcl_data\msgs"
    if (Test-Path $msgs) {
        Get-ChildItem $msgs -Directory |
            Where-Object { $_.Name -notin @("en", "en_gb", "zh_cn", "zh_tw") } |
            Remove-Item -Recurse -Force
    }

    Write-Host "==> ship docs next to the exe"
    # The GitHub README is written for people browsing the repo; the zip gets the
    # user guide instead, renamed to README.md so it is the first thing people open.
    $guide = "packaging\README-portable.md"
    if (-not (Test-Path $guide)) { throw "missing $guide" }
    Copy-Item $guide (Join-Path $out "README.md") -Force
    foreach ($doc in @("CHANGELOG.md", "LICENSE")) {
        if (Test-Path $doc) { Copy-Item $doc (Join-Path $out $doc) -Force }
    }

    $zip = Join-Path $root "dist\$Name-portable.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Write-Host "==> zip"
    Compress-Archive -Path "$out\*" -DestinationPath $zip -CompressionLevel Optimal

    $exe = Join-Path $out "$Name.exe"
    $size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    $payload = [math]::Round(((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
    Write-Host ("done: {0} ({1} MB zip, {2} MB unpacked)" -f $exe, $size, $payload)
}
finally {
    Pop-Location
}
