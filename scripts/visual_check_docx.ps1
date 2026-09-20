# ============================================================================
#  visual_check_docx.ps1 - visual/DOCX validation of the school deliverables
#
#  Opens every .docx with Microsoft Word through COM automation (Word fails
#  loudly on a corrupt package), reports the page/word/paragraph/table/image
#  counts Word itself computed, and optionally exports a PDF for layout review.
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\visual_check_docx.ps1
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\visual_check_docx.ps1 -Pdf
# ============================================================================
[CmdletBinding()]
param(
    [string]$Folder = 'deliverables\docs',
    [switch]$Pdf
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root $Folder

if (-not (Test-Path -LiteralPath $target)) {
    Write-Output "FAIL: folder not found: $target"
    exit 1
}

$files = @(Get-ChildItem -LiteralPath $target -Filter '*.docx' | Sort-Object Name)
if ($files.Count -eq 0) {
    Write-Output 'FAIL: no .docx files found'
    exit 1
}

try {
    $word = New-Object -ComObject Word.Application
} catch {
    Write-Output "VISUAL DOCX REVIEW: NOT TESTED (Word COM automation unavailable: $($_.Exception.Message))"
    exit 2
}

$word.Visible = $false
$word.DisplayAlerts = 0
$failures = 0

try {
    foreach ($file in $files) {
        try {
            $doc = $word.Documents.Open($file.FullName, $false, $true)   # ConfirmConversions=false, ReadOnly=true
            $pages      = $doc.ComputeStatistics(2)   # wdStatisticPages
            $words      = $doc.ComputeStatistics(0)   # wdStatisticWords
            $paragraphs = $doc.Paragraphs.Count
            $tables     = $doc.Tables.Count
            $images     = $doc.InlineShapes.Count
            $note = ''
            if ($Pdf) {
                $pdfPath = [System.IO.Path]::ChangeExtension($file.FullName, '.pdf')
                # ExportAsFixedFormat is a true export: it does not touch the
                # source document.  SaveAs2 with the PDF format can remove the
                # original file for some Word builds, so it is not used here.
                $doc.ExportAsFixedFormat($pdfPath, 17)   # wdExportFormatPDF
                if (-not (Test-Path -LiteralPath $pdfPath)) {
                    throw "PDF export produced no file at $pdfPath"
                }
                $note = " pdf=$([math]::Round((Get-Item -LiteralPath $pdfPath).Length / 1KB)) KB"
            }
            Write-Output ("[OK]   {0}: pages={1} words={2} paragraphs={3} tables={4} images={5}{6}" -f `
                $file.Name, $pages, $words, $paragraphs, $tables, $images, $note)
            $doc.Close(0)                             # wdDoNotSaveChanges
        } catch {
            $failures++
            Write-Output ("[FAIL] {0}: Word could not open/render it - {1}" -f $file.Name, $_.Exception.Message)
        }
    }
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}

Write-Output ''
Write-Output ("VISUAL DOCX REVIEW: " + $(if ($failures -eq 0) { 'PASS' } else { 'FAIL' }))
exit $(if ($failures -eq 0) { 0 } else { 1 })
