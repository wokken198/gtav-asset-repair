param(
    [Parameter(Mandatory = $true)][string]$Xml,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$CoreDir = '',
    [switch]$Legacy
)
# Compile a CPedVariationInfo XML back into a binary .ymt.
$ErrorActionPreference = 'Stop'
if ($CoreDir -eq '') { $CoreDir = $env:GTA_TOOLS_CW }
if (-not $CoreDir -or -not (Test-Path (Join-Path $CoreDir 'CodeWalker.Core.dll'))) {
    throw "CodeWalker.Core.dll not found in '$CoreDir'"
}
Get-ChildItem (Join-Path $CoreDir '*.dll') | Sort-Object Name | ForEach-Object {
    try { [void][Reflection.Assembly]::UnsafeLoadFrom($_.FullName) } catch { }
}
[CodeWalker.GameFiles.RpfManager].GetField('<IsGen9>k__BackingField', [Reflection.BindingFlags]'NonPublic,Static').SetValue($null, (-not $Legacy))

$doc = New-Object System.Xml.XmlDocument
$doc.PreserveWhitespace = $true
$doc.Load($Xml)
$name = [IO.Path]::GetFileNameWithoutExtension($Out)
$bytes = [CodeWalker.GameFiles.XmlMeta]::GetData($doc, [CodeWalker.GameFiles.MetaFormat]::RSC, $name)
if (-not $bytes -or $bytes.Length -lt 16) { throw "packing produced no data for $Xml" }
[IO.File]::WriteAllBytes($Out, $bytes)
Write-Output ("packed {0}: {1} bytes" -f $name, $bytes.Length)
