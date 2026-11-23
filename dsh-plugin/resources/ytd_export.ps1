param(
    [Parameter(Mandatory = $true)][string]$Ytd,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$CoreDir = '',
    [switch]$Legacy
)
# Export one texture dictionary to a CodeWalker YTD XML plus the DDS files it
# references, so a caller can resize/convert the images and pack them back.
$ErrorActionPreference = 'Stop'
if ($CoreDir -eq '') { $CoreDir = $env:GTA_TOOLS_CW }
if (-not $CoreDir -or -not (Test-Path (Join-Path $CoreDir 'CodeWalker.Core.dll'))) {
    throw "CodeWalker.Core.dll not found in '$CoreDir'"
}
Get-ChildItem (Join-Path $CoreDir '*.dll') | Sort-Object Name | ForEach-Object {
    try { [void][Reflection.Assembly]::UnsafeLoadFrom($_.FullName) } catch { }
}
[CodeWalker.GameFiles.RpfManager].GetField('<IsGen9>k__BackingField', [Reflection.BindingFlags]'NonPublic,Static').SetValue($null, (-not $Legacy))

$bytes = [IO.File]::ReadAllBytes($Ytd)
$ver = if ($bytes.Length -ge 8) { [BitConverter]::ToInt32($bytes, 4) } else { -1 }

$dict = New-Object CodeWalker.GameFiles.YtdFile
$dict.Load($bytes)

New-Item -ItemType Directory -Force $OutDir | Out-Null
$stem = [IO.Path]::GetFileNameWithoutExtension($Ytd)
$xml = [CodeWalker.GameFiles.YtdXml]::GetXml($dict, $OutDir)
$xmlPath = Join-Path $OutDir ($stem + '.ytd.xml')
[IO.File]::WriteAllText($xmlPath, $xml, (New-Object Text.UTF8Encoding($false)))

$count = $dict.TextureDict.Textures.data_items.Count
Write-Host ("exported {0}: {1} textures, rsc7 version {2}, xml {3}" -f $stem, $count, $ver, $xmlPath)
