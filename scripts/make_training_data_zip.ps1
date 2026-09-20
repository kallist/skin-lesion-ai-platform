# ============================================================================
#  make_training_data_zip.ps1 - package the original training images separately
#
#  The WebApp submission package deliberately excludes the training images (they
#  are not needed to run the app and would make the e-mail attachment much
#  bigger), so this script builds them into a separate ZIP on request.
#
#  The original images are copied, never modified.
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make_training_data_zip.ps1
# ============================================================================
[CmdletBinding()]
param(
    [string]$OutRoot = 'E:\Ataidi'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

# the raw dataset lives in the school data folder inside the repository
$candidates = @(
    (Join-Path $repo ([string]([char]0x6570 + [char]0x636E) + '\' + [char]0x6570 + [char]0x636E + '\' + [char]0x8BAD + [char]0x7EC3 + [char]0x6570 + [char]0x636E)),
    (Join-Path $repo 'data\raw')
)
$source = $null
foreach ($candidate in $candidates) {
    if ((Test-Path -LiteralPath $candidate) -and
        (Test-Path -LiteralPath (Join-Path $candidate 'benign')) -and
        (Test-Path -LiteralPath (Join-Path $candidate 'malignant'))) {
        $source = $candidate
        break
    }
}
if (-not $source) { throw 'training image folder not found (expected a benign/ and malignant/ pair)' }

$benignCount = @(Get-ChildItem -LiteralPath (Join-Path $source 'benign') -File).Count
$malignantCount = @(Get-ChildItem -LiteralPath (Join-Path $source 'malignant') -File).Count
Write-Output "source     : $source"
Write-Output "benign     : $benignCount"
Write-Output "malignant  : $malignantCount"

$nameSystem = [string]([char]0x76AE + [char]0x80A4 + [char]0x764C + [char]0x56FE + [char]0x50CF + [char]0x68C0 + [char]0x6D4B + [char]0x7CFB + [char]0x7EDF)
$nameTraining = [string]([char]0x8BAD + [char]0x7EC3 + [char]0x6570 + [char]0x636E)
$zipName = $nameSystem + '_' + $nameTraining + '.zip'
$zip = Join-Path $OutRoot $zipName
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

# stage the images plus a short readme, then zip the staged folder
$staging = Join-Path $env:TEMP ('training_data_' + [guid]::NewGuid().ToString('N'))
$inner = Join-Path $staging $nameTraining
New-Item -ItemType Directory -Force -Path $inner | Out-Null

foreach ($class in @('benign', 'malignant')) {
    $target = Join-Path $inner $class
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $arguments = @((Join-Path $source $class), $target, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/R:1', '/W:1')
    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $class (exit $LASTEXITCODE)" }
}

# the Chinese readme lives in its own UTF-8 file (this script stays ASCII-only)
$readmeSource = Join-Path $repo ('docs\archive\project-origin\training_data_readme.txt')
if (-not (Test-Path -LiteralPath $readmeSource)) { throw "readme not found: $readmeSource" }
$readmeName = [string]([char]0x8BF4 + [char]0x660E) + '.txt'
$readme = Get-Content -LiteralPath $readmeSource -Raw -Encoding UTF8
Set-Content -LiteralPath (Join-Path $inner $readmeName) -Value $readme -Encoding UTF8

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $staging, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $false,
    [System.Text.Encoding]::UTF8)
Remove-Item -LiteralPath $staging -Recurse -Force

$item = Get-Item -LiteralPath $zip
Write-Output "zip        : $zip"
Write-Output "zip size   : $([math]::Round($item.Length / 1MB, 1)) MB"
Write-Output "zip SHA256 : $((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash)"

$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    # entry names on Windows use backslashes; normalise before matching
    $names = @($archive.Entries | ForEach-Object { $_.FullName -replace '\\', '/' })
    $perClass = @{}
    foreach ($class in @('benign', 'malignant')) {
        $perClass[$class] = @($names | Where-Object { $_ -like "*/$class/*.jpg" }).Count
    }
    Write-Output "entries    : $($names.Count)"
    Write-Output "benign     : $($perClass['benign']) images in zip"
    Write-Output "malignant  : $($perClass['malignant']) images in zip"
    if ($perClass['benign'] -ne $benignCount -or $perClass['malignant'] -ne $malignantCount) {
        Write-Output 'TRAINING ZIP: FAIL (image count mismatch)'
        exit 1
    }
} finally {
    $archive.Dispose()
}
Write-Output 'TRAINING ZIP: OK'
