# ============================================================================
#  render_docx_page.ps1 - export one page range of a DOCX to PDF, then rasterise
#  it to PNG with headless Chrome and report pixel statistics.
#
#  Used for the visual review of the final report: it verifies that specific
#  pages really contain rendered content (cover, first content pages, figure
#  pages) instead of being blank or mispaginated.
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\render_docx_page.ps1 `
#         -Path deliverables\docs\皮肤癌图像检测系统_实习项目综合报告_V1.0.docx `
#         -From 6 -To 7 -Tag report_p6
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$From = 1,
    [int]$To = 1,
    [string]$Tag = 'page'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$full = (Resolve-Path -LiteralPath $Path).Path
$tmp = Join-Path $root 'artifacts\_page_render'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$pdf = Join-Path $tmp "$Tag.pdf"
$png = Join-Path $tmp "$Tag.png"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($full, $false, $true)
    $doc.ExportAsFixedFormat($pdf, 17, $false, 0, 0, $From, $To)   # wdExportFormatPDF
    $doc.Close(0)
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}

$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $chrome) {
    Write-Output "RENDER: chrome not found - PDF exported only: $pdf"
    exit 0
}

$uri = ([System.Uri]$pdf).AbsoluteUri
& $chrome --headless=new --disable-gpu --hide-scrollbars --window-size=1240,1754 `
    "--screenshot=$png" $uri 2>$null | Out-Null
Start-Sleep -Seconds 2

if (-not (Test-Path -LiteralPath $png)) {
    Write-Output "RENDER: screenshot failed - PDF kept at $pdf"
    exit 0
}

$stats = & (Join-Path $root '.venv\Scripts\python.exe') -X utf8 -c @"
from PIL import Image
import sys
im = Image.open(r'$png').convert('L')
w, h = im.size
px = list(im.getdata())
dark = sum(1 for v in px if v < 200)
print(f'size={w}x{h} dark_pixel_ratio={dark/len(px):.4f} min={min(px)} max={max(px)}')
"@
Write-Output "RENDER: pages $From-$To -> $png"
Write-Output "RENDER: $stats"
