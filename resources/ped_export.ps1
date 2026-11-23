param(
    [Parameter(Mandatory = $true)][string]$Ydd,
    [Parameter(Mandatory = $true)][string]$Ymt,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$CoreDir = '',
    [switch]$Legacy
)
# Export a ped's .ydd and .ymt to CodeWalker XML. Needs a CodeWalker build that
# ships MetaXml (the dev48 build cannot read CPedVariationInfo at all).
$ErrorActionPreference = 'Stop'
if ($CoreDir -eq '') { $CoreDir = $env:GTA_TOOLS_CW }
if (-not $CoreDir -or -not (Test-Path (Join-Path $CoreDir 'CodeWalker.Core.dll'))) {
    throw "CodeWalker.Core.dll not found in '$CoreDir'"
}
Get-ChildItem (Join-Path $CoreDir '*.dll') | Sort-Object Name | ForEach-Object {
    try { [void][Reflection.Assembly]::UnsafeLoadFrom($_.FullName) } catch { }
}
[CodeWalker.GameFiles.RpfManager].GetField('<IsGen9>k__BackingField', [Reflection.BindingFlags]'NonPublic,Static').SetValue($null, (-not $Legacy))

New-Item -ItemType Directory -Force $OutDir | Out-Null
$stem = [IO.Path]::GetFileNameWithoutExtension($Ymt)

$yddFile = New-Object CodeWalker.GameFiles.YddFile
$yddFile.Load([IO.File]::ReadAllBytes($Ydd))
$warn1 = ''
$yddXml = [CodeWalker.GameFiles.MetaXml]::GetXml($yddFile, [ref]$warn1, '')
[IO.File]::WriteAllText((Join-Path $OutDir ($stem + '.ydd.xml')), $yddXml, (New-Object Text.UTF8Encoding($false)))

$ymtFile = New-Object CodeWalker.GameFiles.YmtFile
$ymtFile.Load([IO.File]::ReadAllBytes($Ymt))
$warn2 = ''
$ymtXml = [CodeWalker.GameFiles.MetaXml]::GetXml($ymtFile, [ref]$warn2)
if (-not $ymtXml) { throw "could not read $Ymt as CPedVariationInfo (CodeWalker build too old?)" }
[IO.File]::WriteAllText((Join-Path $OutDir ($stem + '.ymt.xml')), $ymtXml, (New-Object Text.UTF8Encoding($false)))

Write-Output ("exported {0}: ydd {1} chars, ymt {2} chars" -f $stem, $yddXml.Length, $ymtXml.Length)
