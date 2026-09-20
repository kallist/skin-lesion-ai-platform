# ============================================================================
#  start.ps1 - one-click startup for the Skin Cancer Detection System
#
#  Called by START.bat.  Nothing in this file changes application code.
#
#  Flow: already-running check -> environment -> venv/node_modules -> model
#        -> storage dirs -> backend -> backend readiness (real HTTP)
#        -> frontend -> frontend readiness (real HTTP) -> browser -> summary
# ============================================================================
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$ShowServiceWindows,
    [int]$BackendTimeoutSeconds = 90,
    [int]$FrontendTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

$RepoRoot = Get-RepoRoot
$Paths    = Get-LauncherPaths -RepoRoot $RepoRoot
Initialize-LauncherDirs -Paths $Paths
# rotate the launcher log once per start so it cannot grow without bound
Reset-ServiceLog -Path $Paths.LauncherLog
$Config   = Get-EffectiveConfig -Paths $Paths

$script:StartedBackend  = $null
$script:StartedFrontend = $null
$exitCode = 0

function Fail {
    param([Parameter(Mandatory = $true)][string]$Message, [string[]]$Hints = @())

    Write-Err $Message
    Write-LauncherLog $Message 'ERROR'
    foreach ($hint in $Hints) { Write-Host ("        " + $hint) -ForegroundColor Yellow }
    return 1
}

function Undo-PartialStart {
    <#
      Never leave an orphan backend/frontend behind after a failure - but also
      never delete the record of a service this launch did not start.
    #>
    if ($script:StartedFrontend) {
        Write-Info "rolling back frontend PID $($script:StartedFrontend)"
        Stop-OwnedProcessTree -Paths $Paths -ProcessId $script:StartedFrontend -Role 'frontend' | Out-Null
        $script:StartedFrontend = $null
        Clear-LauncherStateEntry -Paths $Paths -Role 'frontend'
    }
    if ($script:StartedBackend) {
        Write-Info "rolling back backend PID $($script:StartedBackend)"
        Stop-OwnedProcessTree -Paths $Paths -ProcessId $script:StartedBackend -Role 'backend' | Out-Null
        $script:StartedBackend = $null
        Clear-LauncherStateEntry -Paths $Paths -Role 'backend'
    }
}

Write-Banner 'Skin Lesion AI Platform - starting'
Write-Info "repository : $RepoRoot"
Write-Info "logs       : $($Paths.LogsDir)"

# ---------------------------------------------------------------- launch lock
# A repository-scoped named mutex serialises concurrent launches.  Without it,
# two simultaneous START.bat invocations could both pass the "already running"
# check, race on the port bind and leave a corrupt .runtime\launcher.json.
# The mutex is released in the finally block below (verified to run on exit).
$launchLock = Get-LaunchLock -Paths $Paths
if (-not (Enter-LaunchLock -Mutex $launchLock -TimeoutSeconds 45)) {
    Write-Warn 'another START.bat is already starting the system - not launching a second copy.'
    Write-Info 'wait a few seconds, then run STATUS.bat to see the state.'
    Write-LauncherLog 'START refused: launch lock is held by another launcher' 'WARN'
    Wait-ForUser
    exit 1
}

try {
Write-LauncherLog "START requested (repo=$RepoRoot)"

# ---------------------------------------------------------------- 1. already running
Write-Step '1/9  Checking whether the system is already running'

$state         = Read-LauncherState -Paths $Paths
$startedAt     = [string]$state.started_at
$backendPid    = Get-RecordedPid -Paths $Paths -Role 'backend'
$frontendPid   = Get-RecordedPid -Paths $Paths -Role 'frontend'
$backendPortOwner  = Get-PortOwnerPid -Port $Config.BackendPort
$frontendPortOwner = Get-PortOwnerPid -Port $Config.FrontendPort
$backendOwned  = ($backendPid -and (Test-ServiceAlive -Paths $Paths -ProcessId $backendPid -Role 'backend' `
    -Port $Config.BackendPort -NotBefore $startedAt -PortOwnerPid $backendPortOwner))
$frontendOwned = ($frontendPid -and (Test-ServiceAlive -Paths $Paths -ProcessId $frontendPid -Role 'frontend' `
    -Port $Config.FrontendPort -NotBefore $startedAt -PortOwnerPid $frontendPortOwner))

if ($backendPid -and -not $backendOwned) {
    Write-Warn "stale backend PID $backendPid (process gone, reused or port taken over) - cleaning up"
    Write-LauncherLog "stale backend pid $backendPid removed" 'WARN'
    $backendPid = $null
}
if ($frontendPid -and -not $frontendOwned) {
    Write-Warn "stale frontend PID $frontendPid (process gone, reused or port taken over) - cleaning up"
    Write-LauncherLog "stale frontend pid $frontendPid removed" 'WARN'
    $frontendPid = $null
}

$backendHealthy  = $false
$frontendHealthy = $false
if ($backendOwned) {
    $probe = Invoke-HttpProbe -Url $Config.HealthUrl -TimeoutSeconds 10
    if ($probe.Ok -and $probe.Status -eq 200) {
        try {
            $payload = $probe.Body | ConvertFrom-Json
            if ([bool]$payload.model -and [bool]$payload.database) { $backendHealthy = $true }
        } catch { }
    }
}
if ($frontendOwned) {
    $probe = Invoke-HttpProbe -Url $Config.FrontendProbeUrl -TimeoutSeconds 10
    if ($probe.Ok -and $probe.Status -eq 200 -and $probe.Body -match 'id="root"') { $frontendHealthy = $true }
}

if ($backendOwned -and $frontendOwned -and $backendHealthy -and $frontendHealthy) {
    Write-Ok 'Skin Lesion AI Platform is already running.'
    $modelInfo = Get-ModelSummaryFromApi -Config $Config
    Show-FinalScreen -Config $Config -ModelInfo $modelInfo -Paths $Paths
    if (-not $NoBrowser) { Open-Browser -Url $Config.FrontendUrl | Out-Null }
    Write-LauncherLog 'duplicate START detected: services already running, browser reopened'
    exit 0
}

# Partially running: keep the healthy half, restart only what is missing.
$keepBackend = ($backendOwned -and $backendHealthy)
if ($backendOwned -and -not $backendHealthy) {
    Write-Warn "backend PID $backendPid is alive but not answering $($Config.HealthUrl) - restarting it"
    Stop-OwnedProcessTree -Paths $Paths -ProcessId $backendPid -Role 'backend' | Out-Null
    $backendPid = $null
}
if ($frontendOwned -and -not $frontendHealthy) {
    Write-Warn "frontend PID $frontendPid is alive but not serving $($Config.FrontendUrl) - restarting it"
    Stop-OwnedProcessTree -Paths $Paths -ProcessId $frontendPid -Role 'frontend' | Out-Null
    $frontendPid = $null
}
if ($keepBackend) { Write-Info "backend already running (PID $backendPid) - reusing it" }
if ($frontendOwned -and $frontendHealthy) { Write-Info "frontend already running (PID $frontendPid) - reusing it" }

# ---------------------------------------------------------------- 2. environment
Write-Step '2/9  Checking Python and Node.js'

# Same discovery order as SETUP.bat: .venv -> python on PATH -> py -3
$Python = Find-UsablePython -Paths $Paths -MinimumVersion '3.10'

$blocked = $false
if (-not $Python.Found) {
    $exitCode = Fail 'Python was not found on this machine.' @(
        'Checked the project virtual environment, python.exe on PATH and the py launcher.',
        'Run SETUP.bat once, or install Python 3.10+ from https://www.python.org/downloads/'
    )
    $blocked = $true
} elseif ($Python.Source -eq 'venv') {
    Write-Ok "Python $($Python.Version) (project virtual environment)"
} elseif ($Python.Source -eq 'py') {
    Write-Warn "python.exe is not on PATH; the Windows launcher will be used for diagnostics: $($Python.Display)"
    Write-Warn 'the launcher itself always starts the backend with the project virtual environment.'
} else {
    Write-Ok "Python $($Python.Version) ($($Python.Display))"
}

$nodeVersion = Get-NodeVersion
$npmPath     = Get-ExecutablePath -Name 'npm.cmd'
if (-not $npmPath) { $npmPath = Get-ExecutablePath -Name 'npm' }

if (-not $blocked) {
    if (-not $nodeVersion) {
        $exitCode = Fail 'Node.js was not found on this machine.' @(
            'Install Node.js 18 or newer from https://nodejs.org/ (LTS).',
            'Then run SETUP.bat once.'
        )
        $blocked = $true
    } else {
        Write-Ok "Node.js $nodeVersion"
    }
}
if (-not $blocked) {
    if (-not $npmPath) {
        $exitCode = Fail 'npm was not found (it ships with Node.js).' @(
            'Reinstall Node.js 18+ from https://nodejs.org/ and run SETUP.bat.'
        )
        $blocked = $true
    } else {
        Write-Ok "npm $npmPath"
    }
}
if ($blocked) { Wait-ForUser; exit $exitCode }

# ---------------------------------------------------------------- 3. python env
Write-Step '3/9  Checking the Python virtual environment'

if (-not (Test-Path -LiteralPath $Paths.VenvPython)) {
    $exitCode = Fail 'The project virtual environment was not found.' @(
        "Expected: $($Paths.VenvPython)",
        'Run SETUP.bat once to create it and install the dependencies.'
    )
    Wait-ForUser
    exit $exitCode
}
Write-Ok "virtual environment: $($Paths.VenvPython)"

$venvProbe = & $Paths.VenvPython -c "import sys, fastapi, uvicorn, torch; sys.stdout.write('ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or ($venvProbe -join ' ') -notmatch 'ok') {
    $exitCode = Fail 'The virtual environment exists but the backend dependencies are not usable.' @(
        'Run SETUP.bat to repair the environment.',
        ("Details: " + (($venvProbe | Select-Object -First 3) -join ' '))
    )
    Wait-ForUser
    exit $exitCode
}
Write-Ok 'backend dependencies importable (fastapi, uvicorn, torch)'

# ---------------------------------------------------------------- 4. frontend deps
Write-Step '4/9  Checking the frontend dependencies'

if (-not (Test-Path -LiteralPath $Paths.NodeModules)) {
    $exitCode = Fail 'frontend\node_modules was not found.' @(
        "Expected: $($Paths.NodeModules)",
        'Run SETUP.bat once (it uses npm ci).',
        'START.bat never installs dependencies.'
    )
    Wait-ForUser
    exit $exitCode
}
if (-not (Test-Path -LiteralPath (Join-Path $Paths.NodeModules 'vite'))) {
    $exitCode = Fail 'frontend\node_modules looks incomplete (vite is missing).' @(
        'Run SETUP.bat to reinstall the frontend dependencies.'
    )
    Wait-ForUser
    exit $exitCode
}
Write-Ok 'frontend node_modules present'

# ---------------------------------------------------------------- 5. model
Write-Step '5/9  Checking the trained model'

$model = Test-ModelFile -Paths $Paths -Config $Config
if (-not $model.Found) {
    $exitCode = Fail 'The trained model file was not found. Refusing to start.' @(
        "Expected: $($model.Path)",
        'The model is a training artefact (about 90 MB) and is not committed to Git.',
        'Restore models\best_model.pt or run the training pipeline - SETUP.bat cannot create it.'
    )
    Wait-ForUser
    exit $exitCode
}
$sizeMb = [math]::Round($model.Size / 1MB, 1)
Write-Ok "model found: $($model.Path) ($sizeMb MB)"

if ($Config.ModelBackend -eq 'stub') {
    $exitCode = Fail 'MODEL_BACKEND=stub is set: the backend would serve the deterministic test double instead of the trained model.' @(
        'This is only meant for UI/E2E tests, so START.bat refuses to launch it.',
        'Set MODEL_BACKEND=auto (or real) in backend\.env and run START.bat again.'
    )
    Wait-ForUser
    exit $exitCode
}
if ($Config.ModelBackend -notin @('auto', 'real')) {
    Write-Warn "unexpected MODEL_BACKEND=$($Config.ModelBackend) in .env (expected auto or real)."
}

# ---------------------------------------------------------------- 6. config + dirs
Write-Step '6/9  Checking configuration and storage directories'

$secrets = Test-SecretPresence -Paths $Paths
if (-not $secrets.Complete) {
    Write-Warn ("missing secret(s): " + ($secrets.Missing -join ', '))
    Write-Warn 'development defaults are used, but run SETUP.bat to generate real random secrets.'
    Write-LauncherLog ("missing secrets: " + ($secrets.Missing -join ',')) 'WARN'
} else {
    Write-Ok 'SESSION_SECRET and IMAGE_ENCRYPTION_KEY are configured (values never printed)'
}

$createdDirs = @(Initialize-StorageDirs -Paths $Paths)
if ($createdDirs.Count -gt 0) {
    foreach ($dir in $createdDirs) { Write-Ok "created directory: $dir" }
} else {
    Write-Ok 'storage directories present'
}
if (Test-Path -LiteralPath $Paths.DatabaseFile) {
    $dbSize = [math]::Round((Get-Item -LiteralPath $Paths.DatabaseFile).Length / 1KB, 1)
    Write-Ok "database kept: $($Paths.DatabaseFile) ($dbSize KB) - never reset by the launcher"
} else {
    Write-Info 'no database yet; the backend will create it on first start (no history to lose)'
}

# ---------------------------------------------------------------- 7. backend
Write-Step '7/9  Starting the backend'

if (-not $keepBackend) {
    $portOwner = Get-PortOwnerPid -Port $Config.BackendPort
    if ($portOwner) {
        $ours = (Test-PidOwnership -ProcessId $portOwner -Paths $Paths -Role 'backend')
        if ($ours.Owned) {
            Write-Warn "port $($Config.BackendPort) is held by a leftover backend from this project (PID $portOwner) - reclaiming it"
            Stop-OwnedProcessTree -Paths $Paths -ProcessId $portOwner -Role 'backend' | Out-Null
            Wait-PortReleased -Port $Config.BackendPort -TimeoutSeconds 15 | Out-Null
            $portOwner = Get-PortOwnerPid -Port $Config.BackendPort
        }
        if ($portOwner) {
            $owner = Get-ProcessInfo -ProcessId $portOwner
            $exitCode = Fail "Port $($Config.BackendPort) is already in use by another process (PID $portOwner, $($owner.Name))." @(
                'This launcher will NOT kill that process.',
                'Close the program using the port, or change PORT in backend\.env.',
                ("Inspect it with: Get-Process -Id " + $portOwner)
            )
            Wait-ForUser
            exit $exitCode
        }
    }

    Reset-ServiceLog -Path $Paths.BackendLog
    Write-LauncherLog "starting backend: $($Paths.VenvPython) -m uvicorn app.main:app --host $($Config.BackendHost) --port $($Config.BackendPort)"

    $backendArgs = @('-m', 'uvicorn', 'app.main:app',
                     '--host', $Config.BackendHost,
                     '--port', [string]$Config.BackendPort)
    if ($ShowServiceWindows) {
        $backendProc = Start-Process -FilePath $Paths.VenvPython -ArgumentList $backendArgs `
            -WorkingDirectory $Paths.BackendDir -PassThru `
            -RedirectStandardOutput $Paths.BackendLog -RedirectStandardError $Paths.BackendErrorLog
    } else {
        $backendProc = Start-Process -FilePath $Paths.VenvPython -ArgumentList $backendArgs `
            -WorkingDirectory $Paths.BackendDir -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $Paths.BackendLog -RedirectStandardError $Paths.BackendErrorLog
    }
    if (-not $backendProc) {
        $exitCode = Fail 'could not spawn the backend process.'
        Wait-ForUser
        exit $exitCode
    }
    $script:StartedBackend = [int]$backendProc.Id
    $backendPid = $script:StartedBackend

    $state = Read-LauncherState -Paths $Paths
    $state.repo_root     = $Paths.RepoRoot
    $state.started_at    = (Get-Date).ToString('s')
    $state.backend_pid   = $backendPid
    $state.backend_port  = $Config.BackendPort
    $state.backend_url   = $Config.BackendUrl
    $state.frontend_port = $Config.FrontendPort
    $state.frontend_url  = $Config.FrontendUrl
    $state.model_path    = $Config.ModelPath
    Save-LauncherState -Paths $Paths -State $state
    Write-Ok "backend process started (PID $backendPid), log: $($Paths.BackendLog)"
} else {
    Write-Ok "reusing the running backend (PID $backendPid)"
}

Write-Info "waiting for $($Config.HealthUrl) (model load can take a while on CPU)"
$ready = Wait-BackendReady -HealthUrl $Config.HealthUrl -TimeoutSeconds $BackendTimeoutSeconds `
    -ProcessId $backendPid -LogPath $Paths.BackendErrorLog

if (-not $ready.Ready) {
    $exitCode = Fail ("Backend failed to start (waited {0:N1}s). {1}" -f $ready.ElapsedSeconds, $ready.Error) @(
        "See $($Paths.BackendLog) and $($Paths.BackendErrorLog)"
    )
    Undo-PartialStart
    Wait-ForUser
    exit $exitCode
}
Write-Ok ("Backend ready in {0:N1}s (database + trained model loaded)" -f $ready.ElapsedSeconds)

# The health endpoint could also have been answered by a foreign instance of the
# project that grabbed the port first.  Only accept the start when the process
# that owns the port is inside our own process tree.
$listenerPid = Get-PortOwnerPid -Port $Config.BackendPort
$ourTree = @(Get-ProcessTreeIds -RootId $backendPid)
if ($listenerPid -and ($ourTree -notcontains $listenerPid)) {
    $listenerInfo = Get-ProcessInfo -ProcessId $listenerPid
    $exitCode = Fail "Port $($Config.BackendPort) is served by PID $listenerPid ($($listenerInfo.Name)), which is NOT the process this launcher started." @(
        'Another copy of the backend is already running - this launcher will not kill it.',
        'Run STOP.bat, or stop that process manually, then run START.bat again.'
    )
    Undo-PartialStart
    Wait-ForUser
    exit $exitCode
}
Write-Info "backend port $($Config.BackendPort) owned by our process tree (listener PID $listenerPid)"

# record the listener PID so STOP/STATUS can cross-check the port owner later
$state = Read-LauncherState -Paths $Paths
$state.backend_listener_pid = $listenerPid
Save-LauncherState -Paths $Paths -State $state

# ---------------------------------------------------------------- 8. frontend
Write-Step '8/9  Starting the frontend'

if (-not ($frontendOwned -and $frontendHealthy)) {
    $portOwner = Get-PortOwnerPid -Port $Config.FrontendPort
    if ($portOwner) {
        $ours = (Test-PidOwnership -ProcessId $portOwner -Paths $Paths -Role 'frontend')
        if ($ours.Owned) {
            Write-Warn "port $($Config.FrontendPort) is held by a leftover frontend from this project (PID $portOwner) - reclaiming it"
            Stop-OwnedProcessTree -Paths $Paths -ProcessId $portOwner -Role 'frontend' | Out-Null
            Wait-PortReleased -Port $Config.FrontendPort -TimeoutSeconds 15 | Out-Null
            $portOwner = Get-PortOwnerPid -Port $Config.FrontendPort
        }
        if ($portOwner) {
            $owner = Get-ProcessInfo -ProcessId $portOwner
            $exitCode = Fail "Port $($Config.FrontendPort) is already in use by another process (PID $portOwner, $($owner.Name))." @(
                'This launcher will NOT kill that process.',
                'Close the program using the port, or change the dev-server port in frontend\vite.config.ts.',
                ("Inspect it with: Get-Process -Id " + $portOwner)
            )
            Undo-PartialStart
            Wait-ForUser
            exit $exitCode
        }
    }

    Reset-ServiceLog -Path $Paths.FrontendLog
    Write-LauncherLog "starting frontend: $npmPath run dev (cwd=$($Paths.FrontendDir))"

    $npmArgs = @('run', 'dev')
    # The child process inherits this, so the Vite dev proxy always targets the
    # backend the launcher actually started (PORT may differ from 8000).
    $env:VITE_API_TARGET = $Config.BackendUrl
    if ($ShowServiceWindows) {
        $frontendProc = Start-Process -FilePath $npmPath -ArgumentList $npmArgs `
            -WorkingDirectory $Paths.FrontendDir -PassThru `
            -RedirectStandardOutput $Paths.FrontendLog -RedirectStandardError $Paths.FrontendErrorLog
    } else {
        $frontendProc = Start-Process -FilePath $npmPath -ArgumentList $npmArgs `
            -WorkingDirectory $Paths.FrontendDir -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $Paths.FrontendLog -RedirectStandardError $Paths.FrontendErrorLog
    }
    if (-not $frontendProc) {
        $exitCode = Fail 'could not spawn the frontend process.'
        Undo-PartialStart
        Wait-ForUser
        exit $exitCode
    }
    $script:StartedFrontend = [int]$frontendProc.Id
    $frontendPid = $script:StartedFrontend

    $state = Read-LauncherState -Paths $Paths
    $state.frontend_pid   = $frontendPid
    $state.frontend_port  = $Config.FrontendPort
    $state.frontend_url   = $Config.FrontendUrl
    Save-LauncherState -Paths $Paths -State $state
    Write-Ok "frontend process started (PID $frontendPid), log: $($Paths.FrontendLog)"
} else {
    Write-Ok "reusing the running frontend (PID $frontendPid)"
}

Write-Info "waiting for $($Config.FrontendProbeUrl)"
$frontReady = Wait-FrontendReady -Url $Config.FrontendProbeUrl -TimeoutSeconds $FrontendTimeoutSeconds `
    -ProcessId $frontendPid -LogPath $Paths.FrontendErrorLog

if (-not $frontReady.Ready) {
    $exitCode = Fail ("Frontend failed to start (waited {0:N1}s). {1}" -f $frontReady.ElapsedSeconds, $frontReady.Error) @(
        "See $($Paths.FrontendLog) and $($Paths.FrontendErrorLog)"
    )
    Undo-PartialStart
    Wait-ForUser
    exit $exitCode
}
Write-Ok ("Frontend ready in {0:N1}s" -f $frontReady.ElapsedSeconds)

# the dev server is served by a child of npm.cmd; remember the real listener
$frontListenerPid = Get-PortOwnerPid -Port $Config.FrontendPort
$frontTree = @(Get-ProcessTreeIds -RootId $frontendPid)
if ($frontListenerPid -and ($frontTree -notcontains $frontListenerPid)) {
    $listenerInfo = Get-ProcessInfo -ProcessId $frontListenerPid
    $exitCode = Fail "Port $($Config.FrontendPort) is served by PID $frontListenerPid ($($listenerInfo.Name)), which is NOT the process this launcher started." @(
        'Another dev server is already running - this launcher will not kill it.',
        'Run STOP.bat, or stop that process manually, then run START.bat again.'
    )
    Undo-PartialStart
    Wait-ForUser
    exit $exitCode
}
$state = Read-LauncherState -Paths $Paths
$state.frontend_listener_pid = $frontListenerPid
Save-LauncherState -Paths $Paths -State $state
Write-Info "frontend port $($Config.FrontendPort) owned by our process tree (listener PID $frontListenerPid)"

# ---------------------------------------------------------------- 9. browser + summary
Write-Step '9/9  Opening the browser'

$modelInfo = Get-ModelSummaryFromApi -Config $Config
if ($modelInfo.Available) {
    Write-Ok "served model: $($modelInfo.Architecture) $($modelInfo.Version) on $($modelInfo.Device)"
} else {
    Write-Warn 'the API did not report the model as available - check logs\backend.log'
}

if (-not $NoBrowser) {
    if (Open-Browser -Url $Config.FrontendUrl) { Write-Ok "browser opened: $($Config.FrontendUrl)" }
    else { Write-Warn "could not open the browser automatically - open $($Config.FrontendUrl) manually" }
}

Show-FinalScreen -Config $Config -ModelInfo $modelInfo -Paths $Paths
Write-LauncherLog 'START completed successfully'
Write-Host '  Services keep running after this window is closed.' -ForegroundColor Gray
Write-Host '  Use STOP.bat to shut them down.' -ForegroundColor Gray
exit 0
} finally {
    Exit-LaunchLock -Mutex $launchLock
}
