param(
    [Parameter(Mandatory = $true)][string[]]$Ytd,
    [string]$CoreDir = '',
    [switch]$Legacy
)
# Dump a YTD's texture list as JSON lines: name, width, height, format, mips, bytes.
# Read-only: nothing is written next to the archive.
$ErrorActionPreference = 'Stop'
if (-not $CoreDir -or -not (Test-Path (Join-Path $CoreDir 'CodeWalker.Core.dll'))) {
    throw "CodeWalker.Core.dll not found in '$CoreDir' (pass -CoreDir or set GTA_TOOLS_CW)"
}
Get-ChildItem (Join-Path $CoreDir '*.dll') | Sort-Object Name | ForEach-Object {
    try { [void][Reflection.Assembly]::UnsafeLoadFrom($_.FullName) } catch { }
}
[CodeWalker.GameFiles.RpfManager].GetField('<IsGen9>k__BackingField', [Reflection.BindingFlags]'NonPublic,Static').SetValue($null, (-not $Legacy))

foreach ($path in $Ytd) {
    $entry = [ordered]@{ ytd = (Split-Path -Leaf $path); path = $path; textures = @(); error = '' }
    try {
        $y = New-Object CodeWalker.GameFiles.YtdFile
        $y.Load([IO.File]::ReadAllBytes($path))
        $list = @()
        foreach ($t in $y.TextureDict.Textures.data_items) {
            $len = 0
            try { $len = $t.Data.FullData.Length } catch { }
            $list += [ordered]@{
                name   = [string]$t.Name
                width  = [int]$t.Width
                height = [int]$t.Height
                format = ([string]$t.Format) -replace '^D3DFMT_', ''
                mips   = [int]$t.Levels
                bytes  = $len
            }
        }
        $entry.textures = $list
    } catch {
        $msg = $_.Exception.Message
        if ($_.Exception.InnerException) { $msg = $_.Exception.InnerException.Message }
        $entry.error = $msg
    }
    Write-Output ($entry | ConvertTo-Json -Compress -Depth 6)
}
