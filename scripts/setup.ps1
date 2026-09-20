# ============================================================================
#  setup.ps1 - first-time configuration for the Skin Lesion AI Platform
#
#  Called by SETUP.bat.  Run this once per machine, then use START.bat.
#
#  What it does:
#    1. audits Python / Node.js versions (never installs system software)
#    2. creates .venv and installs backend requirements (+ PyTorch if missing)
#    3. installs frontend dependencies with npm ci (falls back to npm install)
#    4. creates backend\.env from .env.example and generates random secrets
#    5. checks the trained model (cannot be created here - it is a training artefact)
#    6. creates the runtime/storage directories and reports the database status
#
#  It never overwrites an existing .env, never deletes the database and never
#  re-trains or replaces models\best_model.pt.
# ============================================================================
[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

$RepoRoot = Get-RepoRoot
$Paths    = Get-LauncherPaths -RepoRoot $RepoRoot
Initialize-LauncherDirs -Paths $Paths
$Config   = Get-EffectiveConfig -Paths $Paths

$MinPython = '3.10'
$MinNode   = '18'
$failures  = @()
$warnings  = @()

Write-Banner 'Skin Cancer Detection System - first-time setup'
Write-Info "repository : $RepoRoot"
if ($DryRun) { Write-Warn 'DRY RUN: no dependency will be installed and no file will be written.' }
Write-LauncherLog "SETUP requested (dryRun=$DryRun)"

# ---------------------------------------------------------------- 1. audit
Write-Step '1/6  Auditing Python and Node.js'

# Python discovery is shared with start.ps1 / status.ps1 so all launchers agree:
# existing .venv first, then python/python3 on PATH (Store aliases rejected),
# then the Windows launcher `py -3`.
$Python = Find-UsablePython -Paths $Paths -MinimumVersion $MinPython

if (-not $Python.Found) {
    $failures += 'Python was not found (checked .venv, python on PATH and the py launcher).'
    Show-PythonMissingHelp -MinimumVersion $MinPython
} else {
    Write-LauncherLog "python source=$($Python.Source) version=$($Python.Version) exe=$($Python.Display)"
}

$nodeVersion = Get-NodeVersion
$npmPath = Get-ExecutablePath -Name 'npm.cmd'
if (-not $npmPath) { $npmPath = Get-ExecutablePath -Name 'npm' }

if (-not $nodeVersion) {
    $failures += 'Node.js was not found on PATH.'
    Write-Err 'Node.js was not found.'
    Write-Host '        Install the Node.js 18+ LTS build from https://nodejs.org/' -ForegroundColor Yellow
} else {
    $minimumNode = [version]($MinNode + '.0.0')
    if ($nodeVersion -ge $minimumNode) {
        Write-Ok "Node.js $nodeVersion"
    } else {
        $failures += "Node.js $nodeVersion is older than the required $MinNode."
        Write-Err "Node.js $nodeVersion found, but the project requires $MinNode or newer."
    }
}
if (-not $npmPath) {
    $failures += 'npm was not found (it ships with Node.js).'
    Write-Err 'npm was not found - reinstall Node.js 18+ from https://nodejs.org/'
} else {
    Write-Ok "npm $npmPath"
}

if ($failures.Count -gt 0) {
    Write-Host ''
    Write-Err 'SETUP CANNOT CONTINUE: install the missing software above, then run SETUP.bat again.'
    Write-Host '  This script never installs system-level software for you.' -ForegroundColor Yellow
    Write-LauncherLog ("setup aborted: " + ($failures -join ' | ')) 'ERROR'
    Wait-ForUser
    exit 2
}

# ---------------------------------------------------------------- 2. python env
Write-Step '2/6  Backend Python environment'

$venvPython = $Paths.VenvPython
if ($SkipBackend) {
    Write-Info 'skipped (-SkipBackend)'
} else {
    $venvCreated = $false
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if ($DryRun) {
            Write-Info "DRY RUN: would create the virtual environment at $($Paths.VenvDir)"
            Write-Info "DRY RUN: would use $($Python.Display) to create it"
        } else {
            if (-not $Python.Found) {
                Write-Err 'cannot create the virtual environment: no usable Python was found.'
                Show-PythonMissingHelp -MinimumVersion $MinPython
                Wait-ForUser
                exit 3
            }
            if (-not (New-ProjectVirtualEnv -Paths $Paths -Python $Python)) {
                Write-Err 'could not create the virtual environment.'
                Write-Host "        interpreter: $($Python.Display)" -ForegroundColor Yellow
                Write-LauncherLog 'venv creation failed' 'ERROR'
                Wait-ForUser
                exit 3
            }
            $venvCreated = $true
            Write-Ok 'virtual environment created'
        }
    } else {
        Write-Ok "virtual environment already present: $venvPython"
    }

    # Is the existing environment already usable?  This keeps a second SETUP run
    # cheap and avoids touching a working (possibly CUDA) environment.
    $venvReady = $false
    if (-not $venvCreated -and -not $DryRun -and (Test-Path -LiteralPath $venvPython)) {
        $probe = Invoke-NativeCapture -FilePath $venvPython -Arguments @(
            '-c', 'import fastapi, uvicorn, torch, sys; sys.stdout.write("ready")')
        if (-not $probe.Failed -and $probe.Text -match 'ready') { $venvReady = $true }
    }

    if ($DryRun) {
        Write-Info "DRY RUN: would run 'python -m pip install --upgrade pip'"
        Write-Info "DRY RUN: would run 'python -m pip install -r $($Paths.Requirements)'"
        Write-Info 'DRY RUN: would check/install PyTorch'
    } elseif ($venvReady) {
        Write-Ok 'backend dependencies already importable - nothing to install'
    } else {
        Write-Info 'upgrading pip'
        # NOTE: no -Echo here.  The Echo path pipes through cmd.exe, which mangles
        # non-ASCII project paths; the direct call handles them correctly.
        $pipUpgrade = Invoke-NativeCapture -FilePath $venvPython -Arguments @(
            '-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check', '--quiet')
        if ($pipUpgrade.Failed) { $warnings += 'pip upgrade reported an error (continuing).' }

        if (-not (Test-Path -LiteralPath $Paths.Requirements)) {
            $failures += "requirements file missing: $($Paths.Requirements)"
            Write-Err "requirements file missing: $($Paths.Requirements)"
        } else {
            Write-Info 'installing backend requirements (this can take several minutes)'
            $pipInstall = Invoke-NativeCapture -FilePath $venvPython -Arguments @(
                '-m', 'pip', 'install', '-r', $Paths.Requirements, '--disable-pip-version-check')
            if ($pipInstall.Failed) {
                $failures += 'pip install -r backend\requirements.txt failed.'
                Write-Err 'backend dependency installation failed. Last pip output:'
                Write-Host ('        ' + (($pipInstall.Text -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 4) -join "`n        ")) -ForegroundColor DarkGray
                Write-LauncherLog "pip install failed: $($pipInstall.Text)" 'ERROR'
            } else {
                Write-Ok 'backend requirements installed'
            }
        }

        # PyTorch is installed separately (CPU vs CUDA wheel), see README.
        # A failing import writes a traceback to stderr, which must be treated as
        # a normal negative result and not abort the whole setup.
        $torchCheck = Invoke-NativeCapture -FilePath $venvPython -Arguments @(
            '-c', 'import torch, sys; sys.stdout.write(torch.__version__)')
        if ($torchCheck.Failed) {
            Write-Warn 'PyTorch is not installed in the virtual environment.'
            Write-Info 'installing the CPU wheel torch==2.5.1 / torchvision==0.20.1'
            $torchInstall = Invoke-NativeCapture -FilePath $venvPython -Arguments @(
                '-m', 'pip', 'install', 'torch==2.5.1', 'torchvision==0.20.1',
                '--index-url', 'https://download.pytorch.org/whl/cpu', '--disable-pip-version-check')
            if ($torchInstall.Failed) {
                $failures += 'PyTorch installation failed.'
                Write-Err 'PyTorch installation failed. Last pip output:'
                Write-Host ('        ' + (($torchInstall.Text -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 4) -join "`n        ")) -ForegroundColor DarkGray
                Write-Host '        See README for the CUDA wheel alternative; if this was a network' -ForegroundColor Yellow
                Write-Host '        timeout, run SETUP.bat again - pip resumes from its cache.' -ForegroundColor Yellow
                Write-LauncherLog "torch install failed: $($torchInstall.Text)" 'ERROR'
            } else {
                Write-Ok 'PyTorch installed'
            }
        } else {
            Write-Ok "PyTorch already installed: $($torchCheck.Text)"
        }
    }
}

# ---------------------------------------------------------------- 3. frontend
Write-Step '3/6  Frontend dependencies'

if ($SkipFrontend) {
    Write-Info 'skipped (-SkipFrontend)'
} elseif ($DryRun) {
    if (Test-Path -LiteralPath $Paths.PackageLock) {
        Write-Info "DRY RUN: would run 'npm ci' in $($Paths.FrontendDir)"
    } else {
        Write-Info "DRY RUN: would run 'npm install' in $($Paths.FrontendDir) (no package-lock.json)"
    }
} else {
    $useCi = Test-Path -LiteralPath $Paths.PackageLock
    if ($useCi) { Write-Info "npm ci (lockfile present, it will not be modified)" }
    else { Write-Warn 'no package-lock.json: falling back to npm install' }

    $npmArgs = if ($useCi) { @('ci', '--no-audit', '--no-fund') } else { @('install', '--no-audit', '--no-fund') }
    Push-Location -LiteralPath $Paths.FrontendDir
    try {
        # npm writes progress and warnings to stderr; captured so that warnings
        # cannot be escalated into a terminating error by $ErrorActionPreference
        $npmResult = Invoke-NativeCapture -FilePath $npmPath -Arguments $npmArgs
        if ($npmResult.Failed) {
            $failures += 'frontend dependency installation failed.'
            Write-Err 'frontend dependency installation failed - see the npm output above.'
            Write-LauncherLog "npm failed: $($npmResult.Text)" 'ERROR'
        } else {
            Write-Ok 'frontend dependencies installed'
        }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------- 4. .env + secrets
Write-Step '4/6  Environment file and secrets'

if ($DryRun) {
    if (Test-Path -LiteralPath $Paths.EnvFile) {
        Write-Info "DRY RUN: $($Paths.EnvFile) already exists - it would be left untouched"
    } else {
        Write-Info "DRY RUN: would create $($Paths.EnvFile) from .env.example and generate random secrets"
    }
} else {
    if (-not (Test-Path -LiteralPath $Paths.EnvFile)) {
        if (Test-Path -LiteralPath $Paths.EnvExample) {
            Copy-Item -LiteralPath $Paths.EnvExample -Destination $Paths.EnvFile -Force
            Write-Ok "created $($Paths.EnvFile) from .env.example"
        } else {
            $failures += '.env.example is missing.'
            Write-Err "could not create backend\.env: $($Paths.EnvExample) is missing."
        }
    } else {
        Write-Ok "existing $($Paths.EnvFile) kept (never overwritten)"
    }

    if (Test-Path -LiteralPath $Paths.EnvFile) {
        $present = Read-EnvFile -Path $Paths.EnvFile
        $missingSecrets = @()
        foreach ($name in @('SESSION_SECRET', 'IMAGE_ENCRYPTION_KEY')) {
            $value = $null
            if ($present.ContainsKey($name)) { $value = $present[$name] }
            if ([string]::IsNullOrWhiteSpace($value)) { $missingSecrets += $name }
        }

        if ($missingSecrets.Count -eq 0) {
            Write-Ok 'SESSION_SECRET and IMAGE_ENCRYPTION_KEY already set (values are never printed)'
        } else {
            Write-Info ("generating random value(s) for: " + ($missingSecrets -join ', '))
            # A temporary helper script is used instead of `python -c "<multi-line>"`,
            # because Windows PowerShell 5.1 mangles embedded newlines in a native
            # command-line argument.  The generated values are written straight to
            # backend\.env and are never echoed to the console or the log.
            $generatorPath = Join-Path $Paths.RuntimeDir 'generate-secrets.tmp.py'
            $generator = @'
import secrets
from cryptography.fernet import Fernet

print("SESSION_SECRET=" + secrets.token_urlsafe(48))
print("IMAGE_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
'@
            Set-Content -LiteralPath $generatorPath -Value $generator -Encoding UTF8
            try {
                $secretRun = Invoke-NativeCapture -FilePath $venvPython -Arguments @($generatorPath)
                $generated = @($secretRun.Output)
                $generatorExit = $secretRun.ExitCode
            } finally {
                Remove-Item -LiteralPath $generatorPath -Force -ErrorAction SilentlyContinue
            }

            if ($generatorExit -ne 0) {
                $failures += 'could not generate the secrets (is cryptography installed?).'
                Write-Err 'secret generation failed - run SETUP.bat again after the dependency step succeeds.'
            } else {
                $lines = @()
                $lines += ''
                $lines += '# --- generated by SETUP.bat (random, local only, never committed) ---'
                $written = @()
                foreach ($name in @('SESSION_SECRET', 'IMAGE_ENCRYPTION_KEY')) {
                    if ($missingSecrets -notcontains $name) { continue }
                    $match = $generated | Where-Object { $_ -like ($name + '=*') } | Select-Object -First 1
                    if ($match) {
                        $lines += $match
                        $written += $name
                    }
                }
                Add-Content -LiteralPath $Paths.EnvFile -Encoding UTF8 -Value $lines

                # verify the write instead of trusting it: a silently missing
                # secret would make the app fall back to the public dev values.
                $verify = Read-EnvFile -Path $Paths.EnvFile
                $stillMissing = @()
                foreach ($name in $missingSecrets) {
                    $value = $null
                    if ($verify.ContainsKey($name)) { $value = $verify[$name] }
                    if ([string]::IsNullOrWhiteSpace($value)) { $stillMissing += $name }
                }
                if ($stillMissing.Count -gt 0) {
                    $failures += ("secrets could not be written to backend\.env: " + ($stillMissing -join ', '))
                    Write-Err ("FAILED to write: " + ($stillMissing -join ', ') + ' - check write permissions on backend\.env')
                } else {
                    Write-Ok ("appended " + ($written -join ', ') + ' to backend\.env (values not shown, verified)')
                    Write-LauncherLog ("generated and verified secrets in backend\.env: " + ($written -join ','))
                }
            }
        }
        Write-Info 'backend\.env is git-ignored by .gitignore (.env) and is never committed'
    }
}

# ---------------------------------------------------------------- 5. model
Write-Step '5/6  Trained model'

$model = Test-ModelFile -Paths $Paths -Config $Config
if ($model.Found) {
    Write-Ok ("model found: {0} ({1} MB)" -f $model.Path, [math]::Round($model.Size / 1MB, 1))
} else {
    $warnings += "model missing: $($model.Path)"
    Write-Err 'The trained model file was NOT found:'
    Write-Host ("        Expected: " + $model.Path) -ForegroundColor Yellow
    Write-Host '        A dependency install cannot create it: best_model.pt is a training' -ForegroundColor Yellow
    Write-Host '        artefact (about 90 MB) and is intentionally not committed to Git.' -ForegroundColor Yellow
    Write-Host '        Restore it from the delivery package (models\best_model.pt) before START.bat.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 6. dirs + db
Write-Step '6/6  Runtime directories and database'

$createdDirs = @(Initialize-StorageDirs -Paths $Paths)
if ($createdDirs.Count -gt 0) {
    foreach ($dir in $createdDirs) { Write-Ok "created: $dir" }
} else {
    Write-Ok 'all runtime directories present'
}
if (Test-Path -LiteralPath $Paths.DatabaseFile) {
    $dbSize = [math]::Round((Get-Item -LiteralPath $Paths.DatabaseFile).Length / 1KB, 1)
    Write-Ok "existing database kept ($dbSize KB): $($Paths.DatabaseFile)"
    Write-Info 'history is preserved; SETUP never resets or migrates the database'
} else {
    Write-Info 'no database yet - the backend creates it on the first start'
}

# ---------------------------------------------------------------- summary
Write-Host ''
if ($failures.Count -gt 0) {
    Write-Banner 'SETUP FAILED'
    foreach ($item in $failures) { Write-Err $item }
    Write-Host ''
    Write-Host '  Fix the items above and run SETUP.bat again.' -ForegroundColor Yellow
    Write-LauncherLog ("setup failed: " + ($failures -join ' | ')) 'ERROR'
    Wait-ForUser
    exit 4
}

Write-Banner 'SETUP COMPLETE'
if ($warnings.Count -gt 0) {
    Write-Warn 'warnings:'
    foreach ($item in $warnings) { Write-Host ("        - " + $item) -ForegroundColor Yellow }
    Write-Host ''
}
Write-Host '  Next:' -ForegroundColor Green
Write-Host '    Double click START.bat'
Write-Host ''
Write-Host '  START.bat never re-installs dependencies and never re-trains the model.'
Write-Host '  It always uses the current models\best_model.pt.'
Write-Host ''
Write-Host '  AI-assisted results are for reference only and are NOT a medical diagnosis.' -ForegroundColor Yellow
Write-Host ''
Write-LauncherLog 'SETUP completed'
exit 0
