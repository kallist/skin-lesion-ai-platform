# ============================================================================
#  stop.ps1 - stop ONLY the backend/frontend started by this project's launcher
#
#  Called by STOP.bat.  It never runs taskkill /IM python.exe or /IM node.exe:
#  every PID is validated (command line / executable + recorded port) before it
#  is touched, so VS Code, other Python projects and other Node projects are safe.
# ============================================================================
[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'launcher-common.ps1')

$RepoRoot = Get-RepoRoot
$Paths    = Get-LauncherPaths -RepoRoot $RepoRoot
Initialize-LauncherDirs -Paths $Paths
$Config   = Get-EffectiveConfig -Paths $Paths

Write-Banner 'Skin Lesion AI Platform - stopping'
Write-LauncherLog "STOP requested (repo=$RepoRoot)"

$state = Read-LauncherState -Paths $Paths
$stale = @()
# capture what was recorded before the state file is removed at the end
$recordedBackendPid  = Get-RecordedPid -Paths $Paths -Role 'backend'
$recordedFrontendPid = Get-RecordedPid -Paths $Paths -Role 'frontend'

function Stop-Role {
    param(
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $recordedPid = Get-RecordedPid -Paths $Paths -Role $Role
    $label = $Role.Substring(0, 1).ToUpper() + $Role.Substring(1)
    $startedAt = [string]$state.started_at

    if (-not $recordedPid) {
        Write-Info "$label was not started by this launcher (no recorded PID)."
        return $false
    }

    $portOwner = Get-PortOwnerPid -Port $Port
    $check = Test-PidOwnership -ProcessId $recordedPid -Paths $Paths -Role $Role `
        -Port $Port -NotBefore $startedAt -PortOwnerPid $portOwner

    if (-not $check.Owned) {
        # The recorded PID is gone/reused - but the service may still be running
        # as a child whose PID we never recorded.  Fall back to the port owner.
        if ($portOwner) {
            $ownerCheck = Test-PidOwnership -ProcessId $portOwner -Paths $Paths -Role $Role
            if ($ownerCheck.Owned) {
                Write-Info "$label recorded PID $recordedPid is stale, but port $Port is served by our PID $portOwner - stopping that tree"
                if (Stop-OwnedProcessTree -Paths $Paths -ProcessId $portOwner -Role $Role -NotBefore $startedAt) {
                    if (Wait-PortReleased -Port $Port -TimeoutSeconds $TimeoutSeconds) { Write-Ok "port $Port released." }
                    Write-Ok "$label stopped."
                    return $true
                }
                Write-Warn "$label PID $portOwner did not exit within the timeout."
                return $false
            }
            Write-Warn "$label recorded PID $recordedPid is stale and port $Port is held by PID $portOwner, which is NOT ours - left alone."
            return $false
        }
        Write-Warn "$label PID $recordedPid is not running or no longer belongs to this project - stale PID entry removed."
        Write-LauncherLog "$Role pid $recordedPid stale/foreign" 'WARN'
        return $false
    }

    Write-Info "$label PID $recordedPid verified as this project's process - stopping the whole process tree"
    $stopped = Stop-OwnedProcessTree -Paths $Paths -ProcessId $recordedPid -Role $Role -NotBefore $startedAt

    if (-not $stopped) {
        Write-Warn "$label PID $recordedPid did not exit within the timeout."
        Write-LauncherLog "$Role pid $recordedPid did not exit" 'WARN'
        return $false
    }
    Write-Ok "$label stopped."

    $released = Wait-PortReleased -Port $Port -TimeoutSeconds $TimeoutSeconds
    if ($released) {
        Write-Ok "port $Port released."
    } else {
        $owner = Get-PortOwnerPid -Port $Port
        Write-Warn "port $Port is still held (PID $owner) - it is NOT ours, so it was left alone."
    }
    return $true
}

$backendStopped  = Stop-Role -Role 'backend'  -Port $Config.BackendPort
$frontendStopped = Stop-Role -Role 'frontend' -Port $Config.FrontendPort

# ---------------------------------------------------------------- safety net
# The PID file can be stale (crashed launcher, overwritten state).  Any process
# whose command line still proves it belongs to THIS repository is stopped, so a
# second STOP run can never leave an orphan backend/frontend behind.
$orphans = @(Get-ProjectProcesses -Paths $Paths -NotBefore ([string]$state.started_at))
if ($orphans.Count -gt 0) {
    Write-Info ("found $($orphans.Count) leftover project process(es) not covered by the PID file")
    foreach ($orphan in $orphans) {
        Write-Info ("  PID $($orphan.Pid) [$($orphan.Role)] $($orphan.CommandLine)")
    }
    foreach ($orphan in $orphans) {
        if (Stop-OwnedProcessTree -Paths $Paths -ProcessId $orphan.Pid -Role $orphan.Role -NotBefore ([string]$state.started_at)) {
            if ($orphan.Role -eq 'backend') { $backendStopped = $true } else { $frontendStopped = $true }
        }
    }
    foreach ($port in @($Config.BackendPort, $Config.FrontendPort)) {
        Wait-PortReleased -Port $port -TimeoutSeconds 10 | Out-Null
    }
    Write-Ok 'leftover project processes stopped.'
}

# ---------------------------------------------------------------- stale cleanup
foreach ($role in @('backend', 'frontend')) {
    $recordedPid = Get-RecordedPid -Paths $Paths -Role $role
    if ($recordedPid -and -not (Test-ServiceAlive -Paths $Paths -ProcessId $recordedPid -Role $role -NotBefore ([string]$state.started_at))) {
        $stale += $role
    }
}
if ($stale.Count -gt 0) {
    Write-Info ("stale PID file(s) cleaned: " + ($stale -join ', '))
}

# Which ports are still held by our own services (a foreign holder is reported
# separately and never touched).
$stillListening = @()
$heldByOthers = @()
foreach ($port in @($Config.BackendPort, $Config.FrontendPort)) {
    $owner = Get-PortOwnerPid -Port $port
    if (-not $owner) { continue }
    $stillListening += $port
    $role = if ($port -eq $Config.BackendPort) { 'backend' } else { 'frontend' }
    if (-not (Test-PidOwnership -ProcessId $owner -Paths $Paths -Role $role).Owned) { $heldByOthers += $port }
}

Remove-LauncherState -Paths $Paths
Write-LauncherLog 'state + PID files removed'

if ($backendStopped -or $frontendStopped) {
    Write-Ok 'Skin Cancer Detection System stopped.'
} else {
    Write-Info 'System is not running.'
}

if ($heldByOthers.Count -gt 0) {
    Write-Warn ("port(s) still in use by other programs: " + ($heldByOthers -join ', ') + ' (left untouched).')
}

$exitCode = 0
if ($stillListening.Count -gt 0 -and $heldByOthers.Count -eq 0) {
    Write-Err ("could not release port(s) " + ($stillListening -join ', ') + " - the services may still be running.")
    $exitCode = 1
}

function Get-RoleSummary {
    param([string]$Role, [int]$Port, [bool]$Stopped, [bool]$WasRunning)

    if ($Stopped) { return 'STOPPED' }
    $owner = Get-PortOwnerPid -Port $Port
    if (-not $owner) {
        if ($WasRunning) { return 'STOPPED' }
        return 'not running'
    }
    if ((Test-PidOwnership -ProcessId $owner -Paths $Paths -Role $Role).Owned) {
        return "STILL RUNNING (PID $owner)"
    }
    return "port $Port held by another program (left alone)"
}

$backendWasRunning = [bool]$recordedBackendPid
$frontendWasRunning = [bool]$recordedFrontendPid

Write-Host ''
Write-Host ("  Backend  : " + (Get-RoleSummary -Role 'backend' -Port $Config.BackendPort -Stopped $backendStopped -WasRunning $backendWasRunning))
Write-Host ("  Frontend : " + (Get-RoleSummary -Role 'frontend' -Port $Config.FrontendPort -Stopped $frontendStopped -WasRunning $frontendWasRunning))
Write-Host ''

exit $exitCode
