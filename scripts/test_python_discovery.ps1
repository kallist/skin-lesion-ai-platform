# ============================================================================
#  test_python_discovery.ps1 - unit test for the shared Python discovery
#
#  Verifies that Find-UsablePython resolves an interpreter in the documented
#  order (.venv -> python/python3 on PATH, Store aliases rejected -> py -3) and
#  that it never reports a Microsoft Store alias as a usable Python.
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test_python_discovery.ps1 `
#         -RepoRoot "E:\Ataidi\皮肤癌图像检测系统_学校提交版"
# ============================================================================
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

$paths = Get-LauncherPaths -RepoRoot (Resolve-Path -LiteralPath $RepoRoot).Path
$failures = @()

Write-Output "repo        : $($paths.RepoRoot)"
Write-Output "venv python : $($paths.VenvPython) (exists: $(Test-Path -LiteralPath $paths.VenvPython))"

# --- Store alias detection -------------------------------------------------
$alias = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\python.exe'
$aliasVerdict = Test-StorePythonStub -Path $alias
Write-Output "store alias : $alias -> detected as stub: $aliasVerdict"
if ((Test-Path -LiteralPath $alias) -and -not $aliasVerdict) {
    $failures += 'the Microsoft Store alias was not recognised as a stub'
}
$normalPath = 'C:\Users\someone\AppData\Local\Programs\Python\Python310\python.exe'
if (Test-StorePythonStub -Path $normalPath) {
    $failures += 'a normal Python installation was misdetected as a Store alias'
}

# --- discovery -------------------------------------------------------------
$python = Find-UsablePython -Paths $paths -MinimumVersion '3.10'
Write-Output ''
Write-Output "found       : $($python.Found)"
Write-Output "source      : $($python.Source)"
Write-Output "version     : $($python.Version)"
Write-Output "interpreter : $($python.Display)"
Write-Output "prefix args : $($python.PrefixArgs -join ' ')"

if (-not $python.Found) {
    $failures += "no usable Python was discovered: $($python.Error)"
} else {
    if ($python.Source -notin @('venv', 'python', 'py')) {
        $failures += "unexpected discovery source: $($python.Source)"
    }
    if (-not $python.Version -or $python.Version -lt [version]'3.10') {
        $failures += "discovered Python is too old: $($python.Version)"
    }
    if ($python.Display -and $python.Display.ToLowerInvariant().Contains('windowsapps')) {
        $failures += 'discovery accepted a Microsoft Store alias'
    }
}

# --- the interpreter can actually run Python ------------------------------
if ($python.Found) {
    $probe = Invoke-PythonCommand -Python $python -Arguments @('-c', 'import sys; print(sys.version.split()[0]); print(sys.executable)')
    Write-Output ''
    Write-Output 'probe output:'
    $probe | ForEach-Object { Write-Output "  $_" }
    $joined = ($probe | Out-String)
    if ($joined -notmatch '\d+\.\d+\.\d+') {
        $failures += 'the discovered interpreter could not report its version'
    }
}

Write-Output ''
if ($failures.Count -gt 0) {
    Write-Output 'PYTHON DISCOVERY TEST: FAIL'
    foreach ($failure in $failures) { Write-Output "  - $failure" }
    exit 1
}
Write-Output 'PYTHON DISCOVERY TEST: PASS'
