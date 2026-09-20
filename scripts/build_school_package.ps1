# ============================================================================
#  build_school_package.ps1 - build the clean school submission package
#
#  copy -> sanitize -> validate -> zip
#
#  The source repository is never modified: everything happens on a copy in the
#  output folder.  Secrets, runtime data, virtual environments, node_modules and
#  the development database are excluded, and the result is scanned and
#  validated before zipping.
#
#  This script is deliberately ASCII-only (Windows PowerShell 5.1 would misread
#  a UTF-8 file without BOM); the Chinese delivery notice is read from
#  docs/archive/project-origin/delivery_notice.txt.
#
#  Usage:
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_school_package.ps1
#     powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_school_package.ps1 -SkipZip
#     $env:DSH_PACKAGE_SMOKE=1; powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_school_package.ps1
# ============================================================================
[CmdletBinding()]
param(
    [string]$OutRoot = 'E:\Ataidi',
    [switch]$SkipZip,
    [string]$SmokePythonHome = '',
    [string]$SmokeNodeModules = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$packageName = [string]([char]0x76AE + [char]0x80A4 + [char]0x764C + [char]0x56FE + [char]0x50CF + [char]0x68C0 + [char]0x6D4B + [char]0x7CFB + [char]0x7EDF) + '_' + [string]([char]0x5B66 + [char]0x6821 + [char]0x63D0 + [char]0x4EA4 + [char]0x7248)
$noticeSource = Join-Path $repo 'docs\archive\project-origin\delivery_notice.txt'
$dest = Join-Path $OutRoot $packageName
$zip = Join-Path $OutRoot ($packageName + '.zip')

Write-Output "repo    : $repo"
Write-Output "package : $dest"
Write-Output "zip     : $zip"

if (-not (Test-Path -LiteralPath $OutRoot)) { throw "output root not found: $OutRoot" }
if (-not (Test-Path -LiteralPath $noticeSource)) { throw "delivery notice not found: $noticeSource" }
if ($dest -notlike "$OutRoot*") { throw "refusing to clean a path outside $OutRoot" }

# ---------------------------------------------------------------- 1. copy
if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$dirs = @('backend', 'frontend', 'ml', 'scripts', 'skills', 'docs', 'deliverables', 'launcher',
          'models', 'artifacts', 'data')
$excludeDirs = @('.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
                 '.mypy_cache', '.ruff_cache', 'htmlcov', 'coverage', 'dist', '.vite',
                 'playwright-report', 'test-results', 'logs', '.runtime', 'tmp', 'temp',
                 'staging', 'encrypted_uploads', '.idea', '.vscode')
$excludeFiles = @('*.log', '*.sqlite3', '*.sqlite3-shm', '*.sqlite3-wal', '*.sqlite', '*.db',
                  '*.pyc', '*.pyo', '.env', '.env.*', '*.tsbuildinfo', '.DS_Store',
                  'Thumbs.db', 'desktop.ini', '.eslintcache', '.coverage')

foreach ($dir in $dirs) {
    $source = Join-Path $repo $dir
    if (-not (Test-Path -LiteralPath $source)) { Write-Output "skip (missing): $dir"; continue }
    $target = Join-Path $dest $dir
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $arguments = @($source, $target, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/R:1', '/W:1')
    foreach ($name in $excludeDirs) { $arguments += @('/XD', $name) }
    foreach ($pattern in $excludeFiles) { $arguments += @('/XF', $pattern) }
    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $dir (exit $LASTEXITCODE)" }
}

$rootFiles = @('README.md', 'SETUP.bat', 'START.bat', 'STOP.bat', 'STATUS.bat',
               'docker-compose.yml', '.env.example', '.gitignore')
foreach ($file in $rootFiles) {
    $source = Join-Path $repo $file
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $dest -Force }
}
foreach ($pattern in @('*.cfg', '*.toml', '*.ini')) {
    Get-ChildItem -LiteralPath $repo -Filter $pattern -File -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dest -Force }
}

# no compiled Python bytecode inside the submission
foreach ($leftover in Get-ChildItem -LiteralPath $dest -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue) {
    Remove-Item -LiteralPath $leftover.FullName -Recurse -Force
}

# the packaging script itself does not belong inside the submission
foreach ($internal in @('build_school_package.ps1', 'make_training_data_zip.ps1',
                        'audit_school_test_data.py', '_run_package_e2e.ps1',
                        'package_smoke_inference.py')) {
    $path = Join-Path $dest ('scripts\' + $internal)
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

# keep one copy of the production model only
foreach ($extra in @('models\best_model_torchscript.pt', 'models\best_model_int8_dynamic.pt',
                     'deliverables\models\best_model_torchscript.pt',
                     'deliverables\models\best_model.pt')) {
    $path = Join-Path $dest $extra
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force; Write-Output "removed duplicate weight: $extra" }
}

# ---------------------------------------------------------------- 2. delivery notice
$noticeName = [string]([char]0x63D0 + [char]0x4EA4 + [char]0x8BF4 + [char]0x660E) + '.txt'
$notice = Get-Content -LiteralPath $noticeSource -Raw -Encoding UTF8
Set-Content -LiteralPath (Join-Path $dest $noticeName) -Value $notice -Encoding UTF8
Write-Output "wrote $noticeName"

# ---------------------------------------------------------------- 3. optional smoke test on the copy
if ($env:DSH_PACKAGE_SMOKE -eq '1') {
    Write-Output ''
    Write-Output '=== smoke test on the package copy ==='
    if ($SmokePythonHome) {
        # verify the packaged scripts and configuration against a Python
        # installation that already has the dependencies.  The package itself must
        # not ship a venv, so a junction is created for the smoke test only and
        # removed again before validation and zipping.
        $venvLink = Join-Path $dest '.venv'
        if (Test-Path -LiteralPath $venvLink) { Remove-Item -LiteralPath $venvLink -Recurse -Force }
        $venvParent = Split-Path -Parent $SmokePythonHome
        & cmd.exe /c "mklink /J `"$venvLink`" `"$venvParent`"" | Out-Null
        Write-Output "temporary .venv junction for the smoke test -> $venvParent"
    }
    if ($SmokeNodeModules) {
        # same idea for the frontend dependencies: the package never ships
        # node_modules, so the smoke test links the development copy temporarily
        $modulesLink = Join-Path $dest 'frontend\node_modules'
        if (Test-Path -LiteralPath $modulesLink) { Remove-Item -LiteralPath $modulesLink -Recurse -Force }
        & cmd.exe /c "mklink /J `"$modulesLink`" `"$SmokeNodeModules`"" | Out-Null
        Write-Output "temporary node_modules junction for the smoke test -> $SmokeNodeModules"
    }
    # NOTE: the launcher output is written to a temporary file and read back
    # afterwards.  Piping a child process straight into Select-String can hang in
    # non-interactive hosts, so the file round-trip is used instead.
    $logFile = Join-Path $env:TEMP ("pkg_smoke_" + [guid]::NewGuid().ToString('N') + ".txt")
    $envFile = "`"$($env:DSH_PACKAGE_ROOT)`""
    & cmd.exe /c "`"$(Join-Path $dest 'STOP.bat')`" < nul > `"$logFile`" 2>&1"
    & cmd.exe /c "`"$(Join-Path $dest 'START.bat')`" -NoBrowser < nul >> `"$logFile`" 2>&1"
    & cmd.exe /c "`"$(Join-Path $dest 'STATUS.bat')`" < nul >> `"$logFile`" 2>&1"
    Get-Content -LiteralPath $logFile -Encoding UTF8 |
        Select-String -Pattern 'Backend ready|Frontend ready|Status      |Backend  |Frontend |Backend health|Model loaded|OK\]|ERROR' |
        ForEach-Object { $_.Line }

    Write-Output ''
    Write-Output '=== inference check on the packaged copy ==='
    $python = Join-Path $dest '.venv\Scripts\python.exe'
    $smokeScript = Join-Path $dest 'scripts\package_smoke_inference.py'
    if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $smokeScript)) {
        & $python -X utf8 $smokeScript
    } else {
        Write-Output 'inference check skipped (no python or smoke script in the copy)'
    }

    # stop whatever the smoke test left running, then clean its artefacts
    & cmd.exe /c "`"$(Join-Path $dest 'STOP.bat')`" < nul >> `"$logFile`" 2>&1"
    Write-Output 'launcher log (package smoke test):'
    Get-Content -LiteralPath $logFile -Encoding UTF8 |
        Select-String -Pattern 'Backend ready|Frontend ready|Backend  |Frontend |Backend health|Model loaded|OK\]|ERROR' |
        ForEach-Object { '  ' + $_.Line }
    Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue

    # remove everything the smoke test created so the package stays clean
    foreach ($junk in @('backend\data\app.sqlite3', 'backend\data\app.sqlite3-shm',
                        'backend\data\app.sqlite3-wal', 'logs', '.runtime')) {
        $path = Join-Path $dest $junk
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force; Write-Output "cleaned after smoke test: $junk" }
    }
    $uploads = Join-Path $dest 'backend\data\encrypted_uploads'
    if (Test-Path -LiteralPath $uploads) {
        Get-ChildItem -LiteralPath $uploads -File | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Output 'cleaned encrypted uploads after smoke test'
    }
    $smokeScriptCopy = Join-Path $dest 'scripts\package_smoke_inference.py'
    if (Test-Path -LiteralPath $smokeScriptCopy) { Remove-Item -LiteralPath $smokeScriptCopy -Force }

    # the temporary junctions must never reach the submission
    $venvLink = Join-Path $dest '.venv'
    if (Test-Path -LiteralPath $venvLink) {
        & cmd.exe /c "rmdir `"$venvLink`"" | Out-Null
        if (Test-Path -LiteralPath $venvLink) { Remove-Item -LiteralPath $venvLink -Recurse -Force }
        Write-Output 'removed the temporary .venv junction'
    }
    $modulesLink = Join-Path $dest 'frontend\node_modules'
    if (Test-Path -LiteralPath $modulesLink) {
        & cmd.exe /c "rmdir `"$modulesLink`"" | Out-Null
        if (Test-Path -LiteralPath $modulesLink) { Remove-Item -LiteralPath $modulesLink -Recurse -Force }
        Write-Output 'removed the temporary node_modules junction'
    }
}

# nothing below counts as submission content any more: the validation and the zip
# run on this exact state

# ---------------------------------------------------------------- 4. validate
Write-Output ''
Write-Output '=== validation ==='
$problems = @()

$reportMarkdown = 'docs\archive\project-origin\' + [string]([char]0x76AE + [char]0x80A4 + [char]0x764C + [char]0x56FE + [char]0x50CF + [char]0x68C0 + [char]0x6D4B + [char]0x7CFB + [char]0x7EDF) + '_' + [string]([char]0x5B9E + [char]0x4E60 + [char]0x9879 + [char]0x76EE + [char]0x7EFC + [char]0x5408 + [char]0x62A5 + [char]0x544A) + '.md'
$reportDocx = 'deliverables\docs\' + [string]([char]0x76AE + [char]0x80A4 + [char]0x764C + [char]0x56FE + [char]0x50CF + [char]0x68C0 + [char]0x6D4B + [char]0x7CFB + [char]0x7EDF) + '_' + [string]([char]0x5B9E + [char]0x4E60 + [char]0x9879 + [char]0x76EE + [char]0x7EFC + [char]0x5408 + [char]0x62A5 + [char]0x544A) + '_V1.0.docx'
$reportPdf = [System.IO.Path]::ChangeExtension($reportDocx, '.pdf')

$mustExist = @(
    'README.md', $noticeName, 'SETUP.bat', 'START.bat', 'STOP.bat', 'STATUS.bat',
    'docker-compose.yml', '.env.example',
    'models\best_model.pt', 'models\model_meta.json', 'models\class_mapping.json',
    'backend\requirements.txt', 'backend\app\main.py',
    'frontend\package.json', 'frontend\package-lock.json', 'frontend\src\main.tsx',
    'ml\train.py', 'ml\evaluate_external.py', 'ml\infer.py',
    'scripts\start.ps1', 'scripts\stop.ps1', 'scripts\status.ps1', 'scripts\setup.ps1',
    'scripts\launcher-common.ps1',
    $reportMarkdown, $reportDocx, $reportPdf,
    'docs\archive\project-origin\EXTERNAL_TEST_REPORT.md', 'docs\archive\project-origin\METRICS_SOURCE.md',
    'artifacts\metrics.json',
    'artifacts\external_test\external_metrics.json',
    'artifacts\external_test\external_predictions.csv',
    'artifacts\external_test\external_errors.csv',
    'artifacts\external_test\confusion_matrix.png',
    'artifacts\external_test\roc_curve.png',
    'artifacts\external_test\pr_curve.png',
    'artifacts\external_test\verification.json',
    'artifacts\external_test\threshold_sweep.json',
    'data\manifests\train.csv', 'data\manifests\val.csv', 'data\manifests\test.csv'
)
foreach ($relative in $mustExist) {
    if (-not (Test-Path -LiteralPath (Join-Path $dest $relative))) { $problems += "missing: $relative" }
}

$mustNotExist = @('backend\.env', '.env', '.venv', 'node_modules', '.git',
                  'backend\data\app.sqlite3', 'backend\data\encrypted_uploads',
                  'logs', '.runtime', 'artifacts\external_test\staging',
                  'frontend\node_modules', 'frontend\dist')
foreach ($relative in $mustNotExist) {
    if (Test-Path -LiteralPath (Join-Path $dest $relative)) { $problems += "must not exist: $relative" }
}

Write-Output 'scanning for secrets...'
# A real secret needs an actual value: "SESSION_SECRET=" (an empty .env template)
# and documentation that mentions the variable name are not secrets.
$secretValuePatterns = @(
    '(?m)^\s*SESSION_SECRET\s*=\s*\S+',
    '(?m)^\s*IMAGE_ENCRYPTION_KEY\s*=\s*\S+',
    'sk-[A-Za-z0-9]{20,}',
    'AIza[0-9A-Za-z_\-]{30,}',
    'ghp_[A-Za-z0-9]{30,}',
    'BEGIN (RSA|OPENSSH|PRIVATE) KEY',
    '(?m)^\s*[A-Z_]*SECRET\s*=\s*\S+'
)
# files where the variable names legitimately appear (templates, docs, code)
$secretExempt = @(
    '\.env\.example$', 'DEPLOYMENT\.md$', 'generate_secrets\.py$', 'setup\.ps1$',
    'test_security\.py$', 'METRICS_SOURCE\.md$', 'OPERATIONS\.md$', 'README\.md$',
    'start\.ps1$', 'launcher-common\.ps1$', '03_.*\.md$', '02_.*\.md$'
)
$textExtensions = @('.py', '.ps1', '.bat', '.md', '.txt', '.json', '.yml', '.yaml', '.ts',
                    '.tsx', '.js', '.mjs', '.css', '.html', '.example', '.cfg', '.toml', '.ini')
$secretHits = @()
foreach ($file in Get-ChildItem -LiteralPath $dest -Recurse -File) {
    $extension = $file.Extension.ToLower()
    if ($textExtensions -notcontains $extension -and $file.Name -ne '.gitignore') { continue }
    if ($file.Length -gt 2MB) { continue }
    $relative = $file.FullName.Substring($dest.Length + 1)
    $exempt = $false
    foreach ($exemptPattern in $secretExempt) { if ($relative -match $exemptPattern) { $exempt = $true; break } }
    $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    foreach ($pattern in $secretValuePatterns) {
        if ($content -match $pattern) {
            # an empty assignment in a template file is fine; anything else is reported
            $match = [regex]::Match($content, $pattern)
            $isTemplate = $match.Value -match '=\s*$'
            $isGeneratedCode = $match.Value -match '=(\"|'')\s*(\.\.\.|<|\{)' -or $match.Value -match '= *\$'
            if (-not $exempt -and -not $isTemplate -and -not $isGeneratedCode) {
                $secretHits += "$relative -> $pattern :: $($match.Value.Substring(0, [Math]::Min(40, $match.Value.Length)))"
            }
        }
    }
}
foreach ($hit in $secretHits) { $problems += "possible secret: $hit" }

# explicit check: no .env file with a non-empty secret value anywhere
foreach ($envFile in Get-ChildItem -LiteralPath $dest -Recurse -File -Force |
        Where-Object { $_.Name -eq '.env' -or $_.Name -like '.env.*' }) {
    $content = Get-Content -LiteralPath $envFile.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($content -match '(?m)^SESSION_SECRET=[^\r\n]+' -or $content -match '(?m)^IMAGE_ENCRYPTION_KEY=[^\r\n]+') {
        $problems += "real secret in $($envFile.FullName.Substring($dest.Length))"
    }
}

$modelPath = Join-Path $dest 'models\best_model.pt'
$modelSha = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash
$expectedSha = '9C385625FBA8D297FDFC2808C3504D034EADFCFDFA3182E844D604E4C2D164E8'
if ($modelSha -ne $expectedSha) { $problems += "model SHA mismatch: $modelSha" }

$files = Get-ChildItem -LiteralPath $dest -Recurse -File
$sizeMb = [math]::Round((($files | Measure-Object -Property Length -Sum).Sum / 1MB), 1)
$dbCount = @($files | Where-Object { $_.Extension -in @('.sqlite3', '.db') }).Count
$encCount = @($files | Where-Object { $_.Extension -eq '.enc' }).Count

Write-Output "files          : $($files.Count)"
Write-Output "size on disk   : $sizeMb MB"
Write-Output "sqlite files   : $dbCount"
Write-Output "encrypted files: $encCount"
Write-Output "model SHA256   : $modelSha"

if ($problems.Count -gt 0) {
    Write-Output ''
    Write-Output "PROBLEMS ($($problems.Count)):"
    foreach ($problem in $problems) { Write-Output "  - $problem" }
    Write-Output 'VALIDATION: FAIL'
    exit 1
}
Write-Output 'VALIDATION: PASS'

# ---------------------------------------------------------------- 5. zip
if ($SkipZip) { Write-Output 'skipping zip (-SkipZip)'; exit 0 }

Write-Output ''
Write-Output '=== zipping ==='
Add-Type -AssemblyName System.IO.Compression.FileSystem
# includeBaseDirectory = true: the archive contains the package folder itself, so
# extracting it always yields one clean folder
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $dest, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true,
    [System.Text.Encoding]::UTF8)

$zipItem = Get-Item -LiteralPath $zip
$zipSha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Write-Output "zip            : $zip"
Write-Output "zip size       : $([math]::Round($zipItem.Length / 1MB, 1)) MB"
Write-Output "zip SHA256     : $zipSha"

$archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
try {
    # entry names written on Windows use backslashes; normalise before matching
    $names = @($archive.Entries | ForEach-Object { $_.FullName -replace '\\', '/' })
    Write-Output "zip entries    : $($names.Count)"
    $forbidden = $names | Where-Object {
        $_ -match '(^|/)(\.env$|\.git/|\.venv/|node_modules/|logs/|\.runtime/|staging/)' -or
        $_ -match '\.sqlite3' -or $_ -match '\.enc$'
    }
    if ($forbidden) {
        Write-Output 'ZIP CONTAINS FORBIDDEN ENTRIES:'
        $forbidden | Select-Object -First 10 | ForEach-Object { Write-Output "  - $_" }
        exit 1
    }
    $reportToken = [string]([char]0x7EFC + [char]0x5408 + [char]0x62A5 + [char]0x544A)
    $checks = [ordered]@{
        'best_model.pt' = @($names | Where-Object { $_ -like '*/models/best_model.pt' }).Count
        'report docx'   = @($names | Where-Object { $_ -like '*_V1.0.docx' -and $_ -like "*$reportToken*" }).Count
        'report pdf'    = @($names | Where-Object { $_ -like '*_V1.0.pdf' -and $_ -like "*$reportToken*" }).Count
        'README.md'     = @($names | Where-Object { $_ -like "*/README.md" -and ($_ -split '/').Count -eq 2 }).Count
        'notice txt'    = @($names | Where-Object { $_ -like "*$noticeName" }).Count
        'external test' = @($names | Where-Object { $_ -like '*artifacts/external_test/external_metrics.json' }).Count
        'manifests'     = @($names | Where-Object { $_ -like '*data/manifests/test.csv' }).Count
    }
    foreach ($key in $checks.Keys) {
        Write-Output ("  {0,-16}: {1}" -f $key, $checks[$key])
        if ($checks[$key] -lt 1) { Write-Output "ZIP CHECK FAILED for $key"; exit 1 }
    }
} finally {
    $archive.Dispose()
}
Write-Output 'ZIP: OK'
