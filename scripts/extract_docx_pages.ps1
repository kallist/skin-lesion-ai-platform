# ============================================================================
#  extract_docx_pages.ps1 - print the text of selected pages of a DOCX
#
#  Used for the editorial review of the final report: it shows what a reader
#  actually sees on the opening pages (does the school test result really appear
#  right after the cover and table of contents?).
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\extract_docx_pages.ps1 `
#         -Path deliverables\docs\皮肤癌图像检测系统_实习项目综合报告_V1.0.docx -From 5 -To 8
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$From = 1,
    [int]$To = 3
)

$ErrorActionPreference = 'Stop'
$full = (Resolve-Path -LiteralPath $Path).Path

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    $doc = $word.Documents.Open($full, $false, $true)
    $total = $doc.ComputeStatistics(2)
    Write-Output "file : $([System.IO.Path]::GetFileName($full))"
    Write-Output "pages: $total"
    $to = [Math]::Min($To, $total)

    # Pre-compute the character offset where each page starts.
    $starts = @{}
    for ($page = 1; $page -le $to + 1; $page++) {
        $word.Selection.GoTo(1, 1, $page) | Out-Null   # wdGoToPage, wdGoToAbsolute
        $starts[$page] = $word.Selection.Start
    }

    for ($page = $From; $page -le $to; $page++) {
        $start = $starts[$page]
        $end = if ($starts.ContainsKey($page + 1)) { $starts[$page + 1] } else { $doc.Content.End }
        if ($end -le $start) { continue }
        $text = $doc.Range($start, $end).Text -replace "[\r\a\x07\x0b]", "`n"
        $text = ($text -split "`n" | Where-Object { $_.Trim() -ne '' }) -join "`n"
        Write-Output ""
        Write-Output "========== PAGE $page =========="
        Write-Output $text.Trim()
    }
    $doc.Close(0)
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
