param(
    [Parameter(Mandatory)] [string] $Installer,
    [Parameter(Mandatory)] [string] $Application
)

Add-Type -AssemblyName System.Drawing
$asset = Join-Path $PSScriptRoot 'assets/vydra.ico'
foreach ($executable in @($Installer, $Application)) {
    $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($executable)
    if (!$icon) { throw "No icon found in $executable" }
    $reference = [System.Drawing.Icon]::new($asset, $icon.Size)
    $actual = $icon.ToBitmap()
    $expected = $reference.ToBitmap()
    try {
        $different = 0
        for ($x = 0; $x -lt $actual.Width; $x++) {
            for ($y = 0; $y -lt $actual.Height; $y++) {
                $left = $actual.GetPixel($x, $y)
                $right = $expected.GetPixel($x, $y)
                if ($left.A -lt 16 -and $right.A -lt 16) { continue }
                $difference = [Math]::Abs([int]$left.A - $right.A) + [Math]::Abs([int]$left.R - $right.R) +
                    [Math]::Abs([int]$left.G - $right.G) + [Math]::Abs([int]$left.B - $right.B)
                if ($difference -gt 40) { $different++ }
            }
        }
        if ($different -gt ($actual.Width * $actual.Height * 0.12)) {
            throw "The icon in $executable does not match Vydra."
        }
        Write-Output "Verified Vydra icon in $executable"
    } finally {
        foreach ($image in @($actual, $expected, $icon, $reference)) { $image.Dispose() }
    }
}
