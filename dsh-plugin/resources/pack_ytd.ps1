param(
    [Parameter(Mandatory = $true)][string]$Xml,
    [Parameter(Mandatory = $true)][string]$Build,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$CoreDir = 'C:\Users\calvi\Desktop\GTA\_cw',
    [switch]$Legacy,
    [string]$Original = ''
)
# Pack a texture dictionary from a CodeWalker YTD XML + a folder of DDS files.
# When -Original is given, per-texture descriptor fields that the XML cannot carry
# (G9_UsageData / G9_Flags / UsageData / UsageFlags / ExtraFlags) are copied back
# from that archive; skipping this is what breaks script render targets.
$ErrorActionPreference = 'Stop'
Get-ChildItem (Join-Path $CoreDir '*.dll') | Sort-Object Name | ForEach-Object {
    try { [void][Reflection.Assembly]::UnsafeLoadFrom($_.FullName) } catch { }
}
[CodeWalker.GameFiles.RpfManager].GetField('<IsGen9>k__BackingField', [Reflection.BindingFlags]'NonPublic,Static').SetValue($null, (-not $Legacy))

$text = [IO.File]::ReadAllText($Xml)
$ytd = [CodeWalker.GameFiles.XmlYtd]::GetYtd($text, $Build)
$bytes = $ytd.Save()

if ($Original -ne '') {
    $orig = New-Object CodeWalker.GameFiles.YtdFile
    $orig.Load([IO.File]::ReadAllBytes($Original))
    $byName = @{}
    foreach ($t in $orig.TextureDict.Textures.data_items) { $byName[$t.Name] = $t }

    $fresh = New-Object CodeWalker.GameFiles.YtdFile
    $fresh.Load($bytes)
    $missing = 0
    foreach ($t in $fresh.TextureDict.Textures.data_items) {
        if (-not $byName.ContainsKey($t.Name)) { $missing++; continue }
        $s = $byName[$t.Name]
        $t.G9_UsageData = $s.G9_UsageData
        $t.G9_Flags = $s.G9_Flags
        $t.UsageData = $s.UsageData
        $t.UsageFlags = $s.UsageFlags
        $t.ExtraFlags = $s.ExtraFlags
    }
    $bytes = $fresh.Save()
    Write-Host ("descriptors copied, unmatched textures: " + $missing)
}

[IO.File]::WriteAllBytes($Out, $bytes)
$check = New-Object CodeWalker.GameFiles.YtdFile
$check.Load($bytes)
$ver = if ($bytes.Length -ge 8) { [BitConverter]::ToInt32($bytes, 4) } else { -1 }
Write-Host ("{0}: {1} bytes, {2} textures, rsc7 version {3}" -f (Split-Path -Leaf $Out), $bytes.Length, $check.TextureDict.Textures.data_items.Count, $ver)
