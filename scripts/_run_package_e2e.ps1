# ============================================================================
#  _run_package_e2e.ps1 - drive the packaged copy end to end
#
#  1. rebuild the school package with the current launcher scripts
#  2. copy it to a scratch folder (no .venv, no node_modules)
#  3. run the packaged SETUP.bat  (real first-run: creates venv, installs deps)
#  4. run the packaged START.bat (one-click start)
#  5. probe health / model info / one real inference
#  6. run the packaged STOP.bat
#
#  ASCII-only on purpose (Windows PowerShell 5.1 misreads UTF-8 without BOM);
#  the Chinese package folder name is built from code points.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Scratch = 'E:\Ataidi\_pkgtest',
    [string]$Package = '',
    [string]$Log = 'E:\Ataidi\_pkg_e2e.log'
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot

if (-not $Package) {
    $name = [string]([char]0x76AE + [char]0x80A4 + [char]0x764C + [char]0x56FE + [char]0x50CF + [char]0x68C0 + [char]0x6D4B + [char]0x7CFB + [char]0x7EDF) +
            '_' + [string]([char]0x5B66 + [char]0x6821 + [char]0x63D0 + [char]0x4EA4 + [char]0x7248)
    $Package = Join-Path (Split-Path -Parent $repo) $name
}

function Say([string]$Message) {
    $stamp = (Get-Date).ToString('HH:mm:ss')
    Write-Output "[$stamp] $Message"
}

Set-Content -LiteralPath $Log -Value "package e2e run started $(Get-Date -Format s)" -Encoding UTF8

Say 'step 1/6: rebuild the package'
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $repo 'scripts\build_school_package.ps1') *>&1 |
    Tee-Object -FilePath $Log -Append |
    Select-String -Pattern 'VALIDATION|zip size|zip SHA256|ZIP:|PROBLEMS|ZIP CHECK' |
    ForEach-Object { Say $_.Line }

Say 'step 2/6: copy to scratch (excluding .venv and node_modules)'
if (Test-Path -LiteralPath $Scratch) { Remove-Item -LiteralPath $Scratch -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null
& robocopy $Package $Scratch /E /NFL /NDL /NJH /NJS /NC /NS /XD .venv node_modules /R:1 /W:1 | Out-Null
Say ("copied {0} files; .venv present = {1}" -f (Get-ChildItem -LiteralPath $Scratch -Recurse -File).Count, (Test-Path -LiteralPath "$Scratch\.venv"))

Say 'step 3/6: packaged SETUP.bat (first run)'
& cmd.exe /c "`"$Scratch\SETUP.bat`" < nul" *>&1 |
    Tee-Object -FilePath $Log -Append |
    Select-String -Pattern '^\[|^--|SETUP|Next|last output' |
    ForEach-Object { Say $_.Line }
$setupExit = $LASTEXITCODE
Say "SETUP exit code: $setupExit"

Say 'step 4/6: packaged START.bat (one click)'
& cmd.exe /c "`"$Scratch\START.bat`" -NoBrowser < nul" *>&1 |
    Tee-Object -FilePath $Log -Append |
    Select-String -Pattern '^\[|^--|Status      |ERROR' |
    ForEach-Object { Say $_.Line }
$startExit = $LASTEXITCODE
Say "START exit code: $startExit"

Say 'step 5/6: health / model / real inference'
$probe = Join-Path $repo 'scripts\package_smoke_inference.py'
$venvPython = Join-Path $Scratch '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -X utf8 $probe *>&1 |
        Tee-Object -FilePath $Log -Append |
        ForEach-Object { Say $_ }
} else {
    Say 'no venv in the scratch copy - inference probe skipped'
}

Say 'step 6/6: packaged STOP.bat'
& cmd.exe /c "`"$Scratch\STOP.bat`" < nul" *>&1 |
    Tee-Object -FilePath $Log -Append |
    Select-String -Pattern 'OK\]|STOPPED|WARN|System is not' |
    ForEach-Object { Say $_.Line }

Add-Content -LiteralPath $Log -Encoding UTF8 -Value "SETUP exit=$setupExit START exit=$startExit"
Say "log: $Log"
