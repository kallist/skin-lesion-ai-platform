# ============================================================================
#  status.ps1 - read-only status report for the Skin Cancer Detection System
#
#  Called by STATUS.bat.  Nothing is started, stopped or modified.
#  Secret values are never read out or printed.
# ============================================================================
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

$RepoRoot = Get-RepoRoot
$Paths    = Get-LauncherPaths -RepoRoot $RepoRoot
Initialize-LauncherDirs -Paths $Paths
$Config   = Get-EffectiveConfig -Paths $Paths

Write-Banner 'Skin Lesion AI Platform - status'
Write-Host ("  Repository : " + $RepoRoot)
# git is optional: the launcher must work on a machine that only has Python/Node
$branch = 'n/a (git not installed)'
$commit = 'n/a'
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null | Select-Object -First 1)
        $commit = (& git -C $RepoRoot rev-parse --short HEAD 2>$null | Select-Object -First 1)
    } catch {
        $branch = 'n/a'
        $commit = 'n/a'
    }
}
Write-Host ("  Branch     : " + $branch)
Write-Host ("  Commit     : " + $commit)
Write-Host ''

# ---------------------------------------------------------------- processes
$backendPid  = Get-RecordedPid -Paths $Paths -Role 'backend'
$frontendPid = Get-RecordedPid -Paths $Paths -Role 'frontend'

$backendAlive  = ($backendPid -and (Test-ServiceAlive -Paths $Paths -ProcessId $backendPid -Role 'backend'))
$frontendAlive = ($frontendPid -and (Test-ServiceAlive -Paths $Paths -ProcessId $frontendPid -Role 'frontend'))

# Fall back to a port lookup when the PID file is gone but a service is listening.
$backendPortOwner  = Get-PortOwnerPid -Port $Config.BackendPort
$frontendPortOwner = Get-PortOwnerPid -Port $Config.FrontendPort

# ---------------------------------------------------------------- health
$backendProbe = Invoke-HttpProbe -Url $Config.HealthUrl -TimeoutSeconds 10
$backendHealthPass = ($backendProbe.Ok -and $backendProbe.Status -eq 200)
$modelLoaded = $false
$dbOk = $false
$healthStatus = ''
$uptime = ''
if ($backendHealthPass) {
    try {
        $payload = $backendProbe.Body | ConvertFrom-Json
        $modelLoaded  = [bool]$payload.model
        $dbOk         = [bool]$payload.database
        $healthStatus = [string]$payload.status
        $uptime       = [string]$payload.uptime_seconds
    } catch { }
}

$frontendProbe = Invoke-HttpProbe -Url $Config.FrontendProbeUrl -TimeoutSeconds 10
$frontendPass = ($frontendProbe.Ok -and $frontendProbe.Status -eq 200 -and $frontendProbe.Body -match 'id="root"')

# ---------------------------------------------------------------- assets
$model = Test-ModelFile -Paths $Paths -Config $Config
$secrets = Test-SecretPresence -Paths $Paths

function Show-Row {
    param([string]$Label, [string]$Value, [string]$Colour = 'Gray')
    Write-Host ("  {0,-18}: " -f $Label) -NoNewline
    Write-Host $Value -ForegroundColor $Colour
}

$backendStateColour  = if ($backendAlive -and $backendHealthPass) { 'Green' } elseif ($backendAlive -or $backendPortOwner) { 'Yellow' } else { 'DarkGray' }
$frontendStateColour = if ($frontendAlive -and $frontendPass) { 'Green' } elseif ($frontendAlive -or $frontendPortOwner) { 'Yellow' } else { 'DarkGray' }

Write-Host '  --- services ---' -ForegroundColor Cyan
Show-Row 'Backend'      $(if ($backendAlive) { 'RUNNING' } elseif ($backendPortOwner) { "PORT HELD by PID $backendPortOwner" } else { 'STOPPED' }) $backendStateColour
Show-Row 'Frontend'     $(if ($frontendAlive) { 'RUNNING' } elseif ($frontendPortOwner) { "PORT HELD by PID $frontendPortOwner" } else { 'STOPPED' }) $frontendStateColour
Show-Row 'Backend PID'  $(if ($backendPid) { [string]$backendPid } else { '-' })
Show-Row 'Frontend PID' $(if ($frontendPid) { [string]$frontendPid } else { '-' })
Show-Row 'Backend URL'  $Config.BackendUrl
Show-Row 'Frontend URL' $Config.FrontendUrl
Show-Row 'API Docs'     ($Config.BackendUrl + '/docs')
Write-Host ''

Write-Host '  --- health probes (real HTTP) ---' -ForegroundColor Cyan
Show-Row 'Backend health' $(if ($backendHealthPass) { "PASS (status=$healthStatus, uptime=${uptime}s)" } elseif ($backendProbe.Status) { "FAIL (HTTP $($backendProbe.Status))" } else { 'FAIL (no response)' }) $(if ($backendHealthPass) { 'Green' } else { 'Red' })
Show-Row 'Database'       $(if ($backendHealthPass) { $(if ($dbOk) { 'PASS' } else { 'FAIL' }) } else { 'unknown (backend down)' }) $(if ($backendHealthPass -and $dbOk) { 'Green' } elseif ($backendHealthPass) { 'Red' } else { 'DarkGray' })
Show-Row 'Model loaded'   $(if ($backendHealthPass) { $(if ($modelLoaded) { 'PASS' } else { 'FAIL' }) } else { 'unknown (backend down)' }) $(if ($backendHealthPass -and $modelLoaded) { 'Green' } elseif ($backendHealthPass) { 'Red' } else { 'DarkGray' })
Show-Row 'Frontend'       $(if ($frontendPass) { 'PASS (HTTP 200, app HTML)' } elseif ($frontendProbe.Status) { "FAIL (HTTP $($frontendProbe.Status))" } else { 'FAIL (no response)' }) $(if ($frontendPass) { 'Green' } else { 'Red' })
Write-Host ''

Write-Host '  --- assets ---' -ForegroundColor Cyan
Show-Row 'Model file'   $(if ($model.Found) { "FOUND ($([math]::Round($model.Size / 1MB, 1)) MB)" } else { 'MISSING' }) $(if ($model.Found) { 'Green' } else { 'Red' })
Show-Row 'Model path'   $model.Path
Show-Row 'Model backend' $Config.ModelBackend
if (Test-Path -LiteralPath $Paths.DatabaseFile) {
    $dbSize = [math]::Round((Get-Item -LiteralPath $Paths.DatabaseFile).Length / 1KB, 1)
    Show-Row 'Database' "FOUND ($dbSize KB)" 'Green'
} else {
    Show-Row 'Database' 'MISSING (created on first backend start)' 'Yellow'
}
Show-Row 'Uploads dir' $(if (Test-Path -LiteralPath $Paths.UploadsDir) { 'FOUND' } else { 'MISSING' }) $(if (Test-Path -LiteralPath $Paths.UploadsDir) { 'Green' } else { 'Yellow' })
Show-Row 'Virtualenv'  $(if (Test-Path -LiteralPath $Paths.VenvPython) { 'FOUND' } else { 'MISSING - run SETUP.bat' }) $(if (Test-Path -LiteralPath $Paths.VenvPython) { 'Green' } else { 'Red' })
# same discovery order as SETUP / START: .venv, then python on PATH, then py -3
$statusPython = Find-UsablePython -Paths $Paths -MinimumVersion '3.10' -Quiet
$pythonText = if ($statusPython.Found) {
    "Python $($statusPython.Version) via $($statusPython.Source) ($($statusPython.Display))"
} else {
    'NOT FOUND - install Python 3.10+ or run SETUP.bat'
}
Show-Row 'Python' $pythonText $(if ($statusPython.Found) { 'Green' } else { 'Red' })
Show-Row 'node_modules' $(if (Test-Path -LiteralPath $Paths.NodeModules) { 'FOUND' } else { 'MISSING - run SETUP.bat' }) $(if (Test-Path -LiteralPath $Paths.NodeModules) { 'Green' } else { 'Red' })
Show-Row 'Secrets'     $(if ($secrets.Complete) { 'CONFIGURED (values not shown)' } else { 'MISSING: ' + ($secrets.Missing -join ', ') + ' - run SETUP.bat' }) $(if ($secrets.Complete) { 'Green' } else { 'Yellow' })
Write-Host ''

Write-Host '  --- logs ---' -ForegroundColor Cyan
foreach ($log in @($Paths.BackendLog, $Paths.BackendErrorLog, $Paths.FrontendLog, $Paths.FrontendErrorLog, $Paths.LauncherLog)) {
    if (Test-Path -LiteralPath $log) {
        $item = Get-Item -LiteralPath $log
        Show-Row (Split-Path -Leaf $log) ("{0} KB, modified {1}" -f [math]::Round($item.Length / 1KB, 1), $item.LastWriteTime.ToString('HH:mm:ss'))
    } else {
        Show-Row (Split-Path -Leaf $log) 'not created yet' 'DarkGray'
    }
}

Write-Host ''
Write-Host '  AI-assisted results are for reference only and are NOT a medical diagnosis.' -ForegroundColor Yellow
Write-Host ''

exit 0
