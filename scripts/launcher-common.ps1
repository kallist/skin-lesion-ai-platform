# ============================================================================
#  launcher-common.ps1 - shared helpers for the Windows one-click launcher
#  Skin Lesion AI Platform
#
#  Dot-sourced by start.ps1 / stop.ps1 / status.ps1 / setup.ps1.
#  No project code is modified by anything in this file.
#
#  Rules honoured here:
#    * never hard-code the repository path (always derive from $PSScriptRoot)
#    * never kill a process we cannot prove belongs to this project
#    * never print secret values (SESSION_SECRET / IMAGE_ENCRYPTION_KEY)
#    * work on paths containing spaces or non-ASCII characters
#  Compatible with Windows PowerShell 5.1 and PowerShell 7+.
# ============================================================================

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- constants
$script:LogFile     = $null
$script:SecretNames = @('SESSION_SECRET', 'IMAGE_ENCRYPTION_KEY')

# ---------------------------------------------------------------- paths
function Get-RepoRoot {
    <# Repository root = parent of this script's directory (scripts/). #>
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-LauncherPaths {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    return [ordered]@{
        RepoRoot       = $RepoRoot
        BackendDir     = Join-Path $RepoRoot 'backend'
        FrontendDir    = Join-Path $RepoRoot 'frontend'
        ModelsDir      = Join-Path $RepoRoot 'models'
        ModelFile      = Join-Path $RepoRoot 'models\best_model.pt'
        VenvDir        = Join-Path $RepoRoot '.venv'
        VenvPython     = Join-Path $RepoRoot '.venv\Scripts\python.exe'
        NodeModules    = Join-Path $RepoRoot 'frontend\node_modules'
        PackageLock    = Join-Path $RepoRoot 'frontend\package-lock.json'
        Requirements   = Join-Path $RepoRoot 'backend\requirements.txt'
        EnvExample     = Join-Path $RepoRoot '.env.example'
        EnvFile        = Join-Path $RepoRoot 'backend\.env'
        LogsDir        = Join-Path $RepoRoot 'logs'
        RuntimeDir     = Join-Path $RepoRoot '.runtime'
        StateFile      = Join-Path $RepoRoot '.runtime\launcher.json'
        BackendPidFile = Join-Path $RepoRoot '.runtime\backend.pid'
        FrontPidFile   = Join-Path $RepoRoot '.runtime\frontend.pid'
        BackendLog     = Join-Path $RepoRoot 'logs\backend.log'
        BackendErrorLog = Join-Path $RepoRoot 'logs\backend.error.log'
        FrontendLog    = Join-Path $RepoRoot 'logs\frontend.log'
        FrontendErrorLog = Join-Path $RepoRoot 'logs\frontend.error.log'
        LauncherLog    = Join-Path $RepoRoot 'logs\launcher.log'
        DatabaseFile   = Join-Path $RepoRoot 'backend\data\app.sqlite3'
        UploadsDir     = Join-Path $RepoRoot 'backend\data\encrypted_uploads'
        TempDir        = Join-Path $RepoRoot 'backend\data\tmp'
    }
}

function Initialize-LauncherDirs {
    param([Parameter(Mandatory = $true)]$Paths)

    foreach ($dir in @($Paths.LogsDir, $Paths.RuntimeDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
    }
    # logs/ is git-ignored; keep the placeholder so a fresh clone still has it.
    $keep = Join-Path $Paths.LogsDir '.gitkeep'
    if (-not (Test-Path -LiteralPath $keep)) {
        Set-Content -LiteralPath $keep -Value '' -Encoding ASCII
    }
    $script:LogFile = $Paths.LauncherLog
}

# ---------------------------------------------------------------- output
function Write-Banner {
    param([string]$Title)
    $line = '=' * 56
    Write-Host ''
    Write-Host $line -ForegroundColor DarkCyan
    Write-Host ("  " + $Title) -ForegroundColor Cyan
    Write-Host $line -ForegroundColor DarkCyan
}

function Write-Info {
    param([string]$Message)
    Write-Host ("[INFO]  " + $Message) -ForegroundColor Gray
}

function Write-Ok {
    param([string]$Message)
    Write-Host ("[ OK ]  " + $Message) -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host ("[WARN]  " + $Message) -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host ("[ERROR] " + $Message) -ForegroundColor Red
}

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host ("-- " + $Message) -ForegroundColor Cyan
}

function Write-LauncherLog {
    param([string]$Message, [string]$Level = 'INFO')
    if (-not $script:LogFile) { return }
    try {
        $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        Add-Content -LiteralPath $script:LogFile -Encoding UTF8 -Value ("$stamp [$Level] $Message")
    } catch {
        # logging must never break the launcher
    }
}

# ---------------------------------------------------------------- env file
function Read-EnvFile {
    <# Parse KEY=VALUE lines; blank lines and # comments ignored. #>
    param([Parameter(Mandatory = $true)][string]$Path)

    $result = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $result }

    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ($null -eq $line) { continue }
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $result[$key] = $value
    }
    return $result
}

function Resolve-ProjectPath {
    <# Resolve a possibly relative path against backend/ first, then repo root. #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    $candidate = $Value.Trim()
    if ([System.IO.Path]::IsPathRooted($candidate)) { return $candidate }

    foreach ($base in @($Paths.BackendDir, $Paths.RepoRoot)) {
        $full = [System.IO.Path]::GetFullPath((Join-Path $base $candidate))
        if (Test-Path -LiteralPath $full) { return $full }
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Paths.BackendDir $candidate))
}

function Get-EffectiveConfig {
    <#
      Effective runtime configuration = real environment variables, overlaid by
      the repository .env files (backend/.env wins over the root .env, matching
      the order used by backend/app/core/config.py).
    #>
    param([Parameter(Mandatory = $true)]$Paths)

    $config = @{}
    foreach ($name in @('HOST', 'PORT', 'MODEL_PATH', 'MODEL_BACKEND', 'DATABASE_URL',
                        'ENCRYPTED_IMAGE_DIR', 'TEMP_DIR', 'APP_ENV')) {
        $value = [System.Environment]::GetEnvironmentVariable($name)
        if ($value) { $config[$name] = $value }
    }
    foreach ($file in @((Join-Path $Paths.RepoRoot '.env'), $Paths.EnvFile)) {
        foreach ($entry in (Read-EnvFile -Path $file).GetEnumerator()) {
            if ($entry.Value -ne '') { $config[$entry.Key] = $entry.Value }
        }
    }

    $backendPort = 8000
    if ($config.ContainsKey('PORT')) {
        $parsed = 0
        if ([int]::TryParse([string]$config['PORT'], [ref]$parsed) -and $parsed -gt 0) {
            $backendPort = $parsed
        }
    }
    $backendHost = '127.0.0.1'
    if ($config.ContainsKey('HOST') -and $config['HOST'] -notin @('0.0.0.0', '::', '*')) {
        $backendHost = $config['HOST']
    }

    $modelPath = $null
    if ($config.ContainsKey('MODEL_PATH')) {
        $modelPath = Resolve-ProjectPath -Paths $Paths -Value ([string]$config['MODEL_PATH'])
    }
    if (-not $modelPath) { $modelPath = $Paths.ModelFile }

    $frontendPort = Get-FrontendPort -Paths $Paths
    # Vite's default dev-server host is "localhost", which on Windows resolves to
    # ::1 (IPv6).  Probing 127.0.0.1 would therefore fail, so the probe host is
    # derived from the real config instead of being hard-coded.
    $frontendHost = Get-FrontendHost -ViteConfigPath (Join-Path $Paths.FrontendDir 'vite.config.ts')
    $probeHost = $frontendHost
    if ($probeHost -in @('0.0.0.0', '::', '*', 'true')) { $probeHost = 'localhost' }

    return [pscustomobject]@{
        BackendHost   = $backendHost
        BackendPort   = $backendPort
        FrontendHost  = $frontendHost
        FrontendPort  = $frontendPort
        BackendUrl    = "http://${backendHost}:$backendPort"
        FrontendUrl   = "http://${frontendHost}:$frontendPort"
        FrontendProbeUrl = "http://${probeHost}:$frontendPort"
        HealthUrl     = "http://${backendHost}:$backendPort/api/v1/health"
        ModelInfoUrl  = "http://${backendHost}:$backendPort/api/v1/model/info"
        ModelPath     = $modelPath
        ApiPrefix     = '/api/v1'
        ModelBackend  = if ($config.ContainsKey('MODEL_BACKEND')) { [string]$config['MODEL_BACKEND'] } else { 'auto' }
        AppEnv        = if ($config.ContainsKey('APP_ENV')) { [string]$config['APP_ENV'] } else { 'development' }
    }
}

function Get-FrontendHost {
    <# Dev-server host from frontend/vite.config.ts ("localhost" when unset). #>
    param([Parameter(Mandatory = $true)][string]$ViteConfigPath)

    $default = 'localhost'
    if (-not (Test-Path -LiteralPath $ViteConfigPath)) { return $default }

    $inServerBlock = $false
    $depth = 0
    foreach ($line in (Get-Content -LiteralPath $ViteConfigPath -Encoding UTF8)) {
        if ($inServerBlock) {
            if ($line -match "host\s*:\s*['""]([^'""]+)['""]") { return $matches[1] }
            # host: true binds every interface - "localhost" still reaches it
            if ($line -match 'host\s*:\s*(true|false)') { return $default }
            $depth += ([regex]::Matches($line, '\{')).Count
            $depth -= ([regex]::Matches($line, '\}')).Count
            if ($depth -le 0) { $inServerBlock = $false }
        }
        if ($line -match 'server\s*:\s*\{') {
            $inServerBlock = $true
            $depth = 1
        }
    }
    return $default
}

function Get-FrontendPort {
    <# Read the real dev-server port out of frontend/vite.config.ts. #>
    param([Parameter(Mandatory = $true)]$Paths)

    $default = 5173
    $configPath = Join-Path $Paths.FrontendDir 'vite.config.ts'
    if (-not (Test-Path -LiteralPath $configPath)) { return $default }

    $inServerBlock = $false
    $depth = 0
    foreach ($line in (Get-Content -LiteralPath $configPath -Encoding UTF8)) {
        if ($inServerBlock) {
            if ($line -match 'port\s*:\s*(\d+)') { return [int]$matches[1] }
            $depth += ([regex]::Matches($line, '\{')).Count
            $depth -= ([regex]::Matches($line, '\}')).Count
            if ($depth -le 0) { $inServerBlock = $false }
        }
        if ($line -match 'server\s*:\s*\{') {
            $inServerBlock = $true
            $depth = 1
        }
    }
    return $default
}

# ---------------------------------------------------------------- processes
function Get-PortOwnerPid {
    <# PID currently LISTENING on a local port, or $null. Read-only. #>
    param([Parameter(Mandatory = $true)][int]$Port)

    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
                Select-Object -First 1
        if ($conn) { return [int]$conn.OwningProcess }
    } catch { }

    $lines = @()
    try { $lines = & netstat.exe -ano -p TCP 2>$null } catch { return $null }
    foreach ($line in $lines) {
        if ($line -match "^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            if ([int]$matches[1] -eq $Port) { return [int]$matches[2] }
        }
    }
    return $null
}

function Get-ProcessInfo {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $info = [pscustomobject]@{
        Pid          = $ProcessId
        Alive        = $false
        Name         = ''
        CommandLine  = ''
        Executable   = ''
        CreationTime = $null
    }
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        $info.Alive = $true
        $info.Name = $proc.ProcessName
        try { $info.Executable = $proc.Path } catch { }
        try { $info.CreationTime = $proc.StartTime } catch { }
    } catch {
        return $info
    }
    try {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($cim) {
            if ($cim.CommandLine) { $info.CommandLine = $cim.CommandLine }
            if ($cim.ExecutablePath) { $info.Executable = $cim.ExecutablePath }
            if (-not $info.CreationTime -and $cim.CreationDate) {
                try { $info.CreationTime = [Management.ManagementDateTimeConverter]::ToDateTime($cim.CreationDate) } catch { }
            }
        }
    } catch {
        # Command line unavailable (e.g. elevated process): ownership then falls
        # back to executable path + creation-time + port checks.
    }
    return $info
}

function Get-ChildProcessIds {
    param([Parameter(Mandatory = $true)][int]$ParentId)

    $children = @()
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentId" -ErrorAction Stop)
    } catch {
        return @()
    }
    return @($children | ForEach-Object { [int]$_.ProcessId })
}

function Get-ProcessTreeIds {
    <# Parent PID plus every descendant PID (breadth first, cycle safe). #>
    param([Parameter(Mandatory = $true)][int]$RootId)

    $seen = New-Object System.Collections.Generic.List[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $queue.Enqueue($RootId)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if ($seen.Contains($current)) { continue }
        $seen.Add($current)
        foreach ($child in (Get-ChildProcessIds -ParentId $current)) { $queue.Enqueue($child) }
    }
    return $seen.ToArray()
}

function Test-PidOwnership {
    <#
      True only when the process is alive AND everything known about it agrees
      that it belongs to this repository, so PID reuse can never target an
      unrelated program.  Checks, in order:

        1. liveness
        2. creation time is not older than the recorded launch (reused PID)
        3. a role-specific command-line / executable marker
        4. (when a port is given) the process is inside the recorded port owner

      Returns a hashtable: @{ Owned = $bool; Info = <process info> }
    #>
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)]$Paths,
        [string]$Role = '',
        [int]$Port = 0,
        [string]$NotBefore = '',
        [int]$PortOwnerPid = 0
    )

    $info = Get-ProcessInfo -ProcessId $ProcessId
    if (-not $info.Alive) { return @{ Owned = $false; Info = $info } }

    # ---- 2. PID reuse: a process started before our launch cannot be ours.
    if ($NotBefore) {
        $notBeforeTime = [datetime]::MinValue
        if ([datetime]::TryParse($NotBefore, [ref]$notBeforeTime)) {
            if ($info.CreationTime -and $info.CreationTime -lt $notBeforeTime.AddSeconds(-10)) {
                return @{ Owned = $false; Info = $info }
            }
        }
    }

    # ---- 4. the recorded port must still be served by our own tree.
    #      $ProcessId may be the tree root (npm.cmd) or the listener itself.
    if ($Port -gt 0 -and $PortOwnerPid -gt 0) {
        $tree = @(Get-ProcessTreeIds -RootId $ProcessId)
        if (($tree -notcontains $PortOwnerPid) -and ($PortOwnerPid -ne $ProcessId)) {
            return @{ Owned = $false; Info = $info }
        }
    }

    # ---- 3. command line / executable evidence.
    $evidence = @()
    if ($info.CommandLine) { $evidence += $info.CommandLine }
    if ($info.Executable) { $evidence += $info.Executable }
    if ($evidence.Count -eq 0) { return @{ Owned = $false; Info = $info } }

    $repo = $Paths.RepoRoot.TrimEnd('\').ToLowerInvariant()
    $venv = $Paths.VenvDir.ToLowerInvariant()
    $frontendDir = (Join-Path $repo 'frontend')
    $backendDir = (Join-Path $repo 'backend')

    foreach ($text in $evidence) {
        $lower = $text.ToLowerInvariant()
        if ($Role -eq 'backend') {
            # the venv interpreter (or its real child) running our app module
            if ($lower.Contains($venv) -and $lower.Contains('app.main:app')) {
                return @{ Owned = $true; Info = $info }
            }
            if ($lower.Contains($backendDir) -and $lower.Contains('app.main:app')) {
                return @{ Owned = $true; Info = $info }
            }
        } elseif ($Role -eq 'frontend') {
            # vite must resolve to this repository's node_modules
            if ($lower.Contains('vite') -and $lower.Contains($frontendDir)) {
                return @{ Owned = $true; Info = $info }
            }
        } else {
            # unknown role: the repository root must appear in the command line
            if ($lower.Contains($repo)) { return @{ Owned = $true; Info = $info } }
        }
    }

    # npm.cmd is a batch wrapper: cmd.exe /c "npm.cmd" run dev carries neither
    # the repository path nor "vite".  Such a launcher is ours when a descendant
    # proves it (the node/vite child that actually serves the app).
    if ($Role -eq 'frontend') {
        foreach ($childPid in @(Get-ProcessTreeIds -RootId $ProcessId)) {
            if ($childPid -eq $ProcessId) { continue }
            $child = Get-ProcessInfo -ProcessId $childPid
            $childEvidence = @()
            if ($child.CommandLine) { $childEvidence += $child.CommandLine }
            if ($child.Executable) { $childEvidence += $child.Executable }
            foreach ($text in $childEvidence) {
                $lower = $text.ToLowerInvariant()
                if ($lower.Contains('vite') -and $lower.Contains($frontendDir)) {
                    return @{ Owned = $true; Info = $info }
                }
            }
        }
    }

    # A process whose executable is our venv interpreter and whose role is
    # backend is still ours even if the command line could not be read.
    if ($Role -eq 'backend' -and $info.Executable -and $info.Executable.ToLowerInvariant().Contains($venv)) {
        return @{ Owned = $true; Info = $info }
    }
    if ($Role -eq 'frontend' -and $info.Executable -and $info.Executable.ToLowerInvariant().Contains($frontendDir)) {
        return @{ Owned = $true; Info = $info }
    }
    return @{ Owned = $false; Info = $info }
}

function Test-ServiceAlive {
    <# Is the recorded service still running and still provably ours? #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [string]$Role = '',
        [int]$Port = 0,
        [string]$NotBefore = '',
        [int]$PortOwnerPid = 0
    )

    $check = Test-PidOwnership -ProcessId $ProcessId -Paths $Paths -Role $Role `
        -Port $Port -NotBefore $NotBefore -PortOwnerPid $PortOwnerPid
    return [bool]$check.Owned
}

# ---------------------------------------------------------------- state
function Read-LauncherState {
    param([Parameter(Mandatory = $true)]$Paths)

    $state = [ordered]@{
        repo_root        = $Paths.RepoRoot
        started_at       = $null
        backend_pid      = $null
        frontend_pid     = $null
        backend_listener_pid  = $null
        frontend_listener_pid = $null
        backend_port     = $null
        frontend_port    = $null
        backend_url      = $null
        frontend_url     = $null
        model_path       = $null
        launcher_version = '1.0.0'
    }
    if (-not (Test-Path -LiteralPath $Paths.StateFile)) { return $state }

    try {
        $raw = Get-Content -LiteralPath $Paths.StateFile -Raw -Encoding UTF8
        if (-not $raw) { return $state }
        $json = $raw | ConvertFrom-Json
        # A state file written by a different checkout (or a copied project
        # folder) must never drive process management here.
        $owner = $json.PSObject.Properties['repo_root']
        if ($owner -and $owner.Value) {
            $recorded = ([string]$owner.Value).TrimEnd('\')
            $current = $Paths.RepoRoot.TrimEnd('\')
            if ($recorded.ToLowerInvariant() -ne $current.ToLowerInvariant()) {
                Write-LauncherLog "ignoring state file from another checkout: $recorded" 'WARN'
                return $state
            }
        }
        foreach ($key in @($state.Keys)) {
            $value = $json.PSObject.Properties[$key]
            if ($value -and $null -ne $value.Value) { $state[$key] = $value.Value }
        }
    } catch {
        Write-LauncherLog "state file unreadable, treating as empty: $($_.Exception.Message)" 'WARN'
    }
    return $state
}

function Save-LauncherState {
    <# Atomic write: temp file + move, so a crash cannot leave half a JSON file. #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$State
    )

    $object = [ordered]@{}
    foreach ($key in $State.Keys) { $object[$key] = $State[$key] }
    $json = ($object | ConvertTo-Json -Depth 5)

    $tempFile = $Paths.StateFile + '.tmp'
    Set-Content -LiteralPath $tempFile -Value $json -Encoding UTF8
    Move-Item -LiteralPath $tempFile -Destination $Paths.StateFile -Force

    if ($object.backend_pid) {
        Set-Content -LiteralPath $Paths.BackendPidFile -Value ([string]$object.backend_pid) -Encoding ASCII
    } elseif (Test-Path -LiteralPath $Paths.BackendPidFile) {
        Remove-Item -LiteralPath $Paths.BackendPidFile -Force -ErrorAction SilentlyContinue
    }
    if ($object.frontend_pid) {
        Set-Content -LiteralPath $Paths.FrontPidFile -Value ([string]$object.frontend_pid) -Encoding ASCII
    } elseif (Test-Path -LiteralPath $Paths.FrontPidFile) {
        Remove-Item -LiteralPath $Paths.FrontPidFile -Force -ErrorAction SilentlyContinue
    }
}

function Clear-LauncherStateEntry {
    <#
      Remove one service from the state without touching the other (used when a
      failed launch must not delete a service it did not start).
    #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $state = Read-LauncherState -Paths $Paths
    if ($Role -eq 'backend') {
        $state.backend_pid = $null
        $state.backend_listener_pid = $null
    } else {
        $state.frontend_pid = $null
        $state.frontend_listener_pid = $null
    }
    if (-not $state.backend_pid -and -not $state.frontend_pid) {
        Remove-LauncherState -Paths $Paths
        return
    }
    Save-LauncherState -Paths $Paths -State $state
}

function Remove-LauncherState {
    param([Parameter(Mandatory = $true)]$Paths)

    foreach ($file in @($Paths.StateFile, $Paths.BackendPidFile, $Paths.FrontPidFile)) {
        if (Test-Path -LiteralPath $file) {
            try { Remove-Item -LiteralPath $file -Force } catch { }
        }
    }
}

function Get-RecordedPid {
    <# PID from the state file, falling back to the plain .pid file. #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][string]$Role
    )

    $state = Read-LauncherState -Paths $Paths
    $pidValue = $null
    if ($Role -eq 'backend') { $pidValue = $state.backend_pid } else { $pidValue = $state.frontend_pid }

    if (-not $pidValue) {
        $pidFile = if ($Role -eq 'backend') { $Paths.BackendPidFile } else { $Paths.FrontPidFile }
        if (Test-Path -LiteralPath $pidFile) {
            $text = (Get-Content -LiteralPath $pidFile -Raw -Encoding ASCII).Trim()
            $parsed = 0
            if ([int]::TryParse($text, [ref]$parsed)) { $pidValue = $parsed }
        }
    }

    if (-not $pidValue) { return $null }
    $parsedPid = 0
    if (-not [int]::TryParse([string]$pidValue, [ref]$parsedPid)) { return $null }
    return $parsedPid
}

# ---------------------------------------------------------------- launch lock
function Get-LaunchLock {
    <#
      Repository-scoped named mutex.  Two START.bat invocations for the same
      repository can therefore never both pass the "already running" check and
      race on the port bind (which would corrupt .runtime\launcher.json).
    #>
    param([Parameter(Mandatory = $true)]$Paths)

    $name = 'Global\SkinCancerLauncher_' + (Get-PathHash -Value $Paths.RepoRoot)
    try {
        return New-Object System.Threading.Mutex($false, $name)
    } catch {
        Write-LauncherLog "could not create the launch mutex ($name): $($_.Exception.Message)" 'WARN'
        return $null
    }
}

function Get-PathHash {
    param([Parameter(Mandatory = $true)][string]$Value)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value.ToLowerInvariant())
        $hash = $sha.ComputeHash($bytes)
        return (($hash[0..7] | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha.Dispose()
    }
}

function Enter-LaunchLock {
    <# Returns $true when the lock was acquired (or no mutex is available). #>
    param($Mutex, [int]$TimeoutSeconds = 45)

    if (-not $Mutex) { return $true }
    try {
        return $Mutex.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
    } catch [System.Threading.AbandonedMutexException] {
        # the previous launcher crashed while holding the lock - we own it now
        return $true
    } catch {
        Write-LauncherLog "launch lock wait failed: $($_.Exception.Message)" 'WARN'
        return $true
    }
}

function Exit-LaunchLock {
    param($Mutex)

    if (-not $Mutex) { return }
    try { $Mutex.ReleaseMutex() } catch { }
    try { $Mutex.Dispose() } catch { }
}

# ---------------------------------------------------------------- logging
function Reset-ServiceLog {
    <# Rotate once per launch so logs cannot grow without bound. #>
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return }
    try {
        $item = Get-Item -LiteralPath $Path
        if ($item.Length -eq 0) { return }
        $previous = [System.IO.Path]::ChangeExtension($Path, $null).TrimEnd('.') + '.previous.log'
        if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Force }
        Move-Item -LiteralPath $Path -Destination $previous -Force
    } catch {
        try { Set-Content -LiteralPath $Path -Value '' -Encoding UTF8 } catch { }
    }
}

# ---------------------------------------------------------------- http
function Get-ElapsedSeconds {
    param([Parameter(Mandatory = $true)][datetime]$Since)
    return [math]::Round(((Get-Date) - $Since).TotalSeconds, 1)
}

function Invoke-HttpProbe {
    <# GET a URL; returns @{ Ok; Status; Body; Error }. Never throws. #>
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 5
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return @{ Ok = $true; Status = [int]$response.StatusCode; Body = [string]$response.Content; Error = $null }
    } catch {
        $status = 0
        $body = ''
        $response = $null
        try { $response = $_.Exception.Response } catch { }
        if ($response) {
            try { $status = [int]$response.StatusCode } catch { }
            try {
                $stream = $response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $body = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            } catch { }
        }
        return @{ Ok = $false; Status = $status; Body = $body; Error = $_.Exception.Message }
    }
}

function Wait-BackendReady {
    <#
      Poll the real health endpoint until the API answers AND the trained model
      is loaded.  Never a blind sleep.
      Returns @{ Ready; Status; Body; Error; ElapsedSeconds; LastStatus }.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$HealthUrl,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalMs = 1000,
        [int]$ProcessId = 0,
        [string]$LogPath = ''
    )

    $started = Get-Date
    $lastStatus = 0
    $lastError = ''
    $nextProgress = 10
    while ($true) {
        if ($ProcessId -gt 0) {
            $alive = $false
            try { $alive = [bool](Get-Process -Id $ProcessId -ErrorAction Stop) } catch { $alive = $false }
            if (-not $alive) {
                return @{
                    Ready = $false; Status = 0; Body = ''; ElapsedSeconds = (Get-ElapsedSeconds -Since $started)
                    Error = 'the backend process exited during startup'; LastStatus = $lastStatus
                }
            }
        }

        $probe = Invoke-HttpProbe -Url $HealthUrl -TimeoutSeconds 5
        if ($probe.Ok -and $probe.Status -eq 200) {
            $modelLoaded = $false
            $databaseReady = $false
            try {
                $payload = $probe.Body | ConvertFrom-Json
                $modelLoaded = [bool]$payload.model
                $databaseReady = [bool]$payload.database
            } catch {
                $modelLoaded = ($probe.Body -match '"model"\s*:\s*true')
                $databaseReady = ($probe.Body -match '"database"\s*:\s*true')
            }
            if ($modelLoaded -and $databaseReady) {
                return @{
                    Ready = $true; Status = 200; Body = $probe.Body; Error = $null
                    ElapsedSeconds = (Get-ElapsedSeconds -Since $started); LastStatus = 200
                }
            }
            $lastStatus = 200
            if (-not $modelLoaded) { $lastError = 'API is up but the model is not loaded' }
            elseif (-not $databaseReady) { $lastError = 'API is up but the database is not ready' }
        } else {
            $lastStatus = $probe.Status
            if ($probe.Error) { $lastError = $probe.Error }
        }

        $elapsed = Get-ElapsedSeconds -Since $started
        if ($elapsed -ge $nextProgress) {
            Write-Info ("  ... still waiting for the backend ({0:N0}s/{1}s): {2}" -f $elapsed, $TimeoutSeconds, $lastError)
            $nextProgress = $nextProgress + 10
        }

        if ($elapsed -ge $TimeoutSeconds) {
            if ($LogPath -and (Test-Path -LiteralPath $LogPath)) {
                try {
                    $tail = Get-Content -LiteralPath $LogPath -Tail 15 -Encoding UTF8
                    Write-LauncherLog "backend.log tail: $($tail -join ' | ')" 'ERROR'
                } catch { }
            }
            return @{
                Ready = $false; Status = $lastStatus; Body = ''; Error = $lastError
                ElapsedSeconds = $elapsed; LastStatus = $lastStatus
            }
        }
        Start-Sleep -Milliseconds $IntervalMs
    }
}

function Wait-FrontendReady {
    <# Poll the dev-server URL until it serves the app HTML. #>
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalMs = 1000,
        [int]$ProcessId = 0,
        [string]$LogPath = ''
    )

    $started = Get-Date
    $lastStatus = 0
    $lastError = ''
    while ($true) {
        if ($ProcessId -gt 0) {
            $alive = $false
            try { $alive = [bool](Get-Process -Id $ProcessId -ErrorAction Stop) } catch { $alive = $false }
            if (-not $alive) {
                return @{
                    Ready = $false; Status = 0; ElapsedSeconds = ((Get-Date) - $started).TotalSeconds
                    Error = 'the frontend process exited during startup'; LastStatus = $lastStatus
                }
            }
        }

        $probe = Invoke-HttpProbe -Url $Url -TimeoutSeconds 5
        if ($probe.Ok -and $probe.Status -eq 200 -and $probe.Body -match 'id="root"') {
            return @{
                Ready = $true; Status = 200; Error = $null
                ElapsedSeconds = ((Get-Date) - $started).TotalSeconds; LastStatus = 200
            }
        }
        if ($probe.Ok) {
            $lastStatus = $probe.Status
            $lastError = 'the server answered but did not serve the app HTML'
        } else {
            $lastStatus = $probe.Status
            if ($probe.Error) { $lastError = $probe.Error }
        }

        if ((Get-ElapsedSeconds -Since $started) -ge $TimeoutSeconds) {
            if ($LogPath -and (Test-Path -LiteralPath $LogPath)) {
                try {
                    $tail = Get-Content -LiteralPath $LogPath -Tail 15 -Encoding UTF8
                    Write-LauncherLog "frontend.log tail: $($tail -join ' | ')" 'ERROR'
                } catch { }
            }
            return @{
                Ready = $false; Status = $lastStatus; Error = $lastError
                ElapsedSeconds = ((Get-Date) - $started).TotalSeconds; LastStatus = $lastStatus
            }
        }
        Start-Sleep -Milliseconds $IntervalMs
    }
}

# ---------------------------------------------------------------- stopping
function Get-ProjectProcesses {
    <#
      Every process whose command line proves it belongs to this repository
      (backend uvicorn, npm run dev, vite).  Used as a safety net when the PID
      file is stale or was overwritten, so no orphan is left behind.
    #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [string]$NotBefore = ''
    )

    $result = @()
    $candidates = @()
    try {
        $candidates = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    } catch {
        return @()
    }
    foreach ($candidate in $candidates) {
        $commandLine = $candidate.CommandLine
        if (-not $commandLine) { continue }
        $isBackend = ($commandLine -like '*uvicorn*app.main:app*')
        $isNpmDev = ($commandLine -like '*npm-cli.js*run*dev*')
        $isVite = ($commandLine -like '*node_modules*vite*bin*vite.js*')
        if (-not ($isBackend -or $isNpmDev -or $isVite)) { continue }
        $role = 'backend'
        if ($isNpmDev -or $isVite) { $role = 'frontend' }
        $check = Test-PidOwnership -ProcessId ([int]$candidate.ProcessId) -Paths $Paths -Role $role -NotBefore $NotBefore
        if ($check.Owned) {
            $result += [pscustomobject]@{
                Pid         = [int]$candidate.ProcessId
                ParentId    = [int]$candidate.ParentProcessId
                Role        = $role
                CommandLine = $commandLine
            }
        }
    }
    return @($result)
}

function Stop-OwnedProcessTree {
    <#
      Stop a process tree, but only after proving the root PID belongs to this
      repository.  Returns $true when the process is gone at the end.
      taskkill /T /F is used deliberately: it reaps the npm -> node -> vite
      chain that a plain Stop-Process would leave behind.
    #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [string]$Role = '',
        [string]$NotBefore = ''
    )

    $check = Test-PidOwnership -ProcessId $ProcessId -Paths $Paths -Role $Role -NotBefore $NotBefore
    if (-not $check.Owned) {
        Write-LauncherLog "refusing to stop PID $ProcessId ($Role): not provably ours" 'WARN'
        return $false
    }

    $tree = Get-ProcessTreeIds -RootId $ProcessId
    Write-LauncherLog "stopping $Role tree: $($tree -join ', ')"
    try {
        & taskkill.exe /PID $ProcessId /T /F 2>&1 | Out-Null
    } catch {
        Write-LauncherLog "taskkill failed for PID $ProcessId : $($_.Exception.Message)" 'WARN'
    }

    for ($i = 0; $i -lt 20; $i++) {
        $still = $false
        foreach ($treePid in $tree) {
            try {
                if (Get-Process -Id $treePid -ErrorAction Stop) { $still = $true }
            } catch { }
        }
        if (-not $still) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Wait-PortReleased {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 15
    )

    $started = Get-Date
    while ((Get-ElapsedSeconds -Since $started) -lt $TimeoutSeconds) {
        $owner = Get-PortOwnerPid -Port $Port
        if (-not $owner) { return $true }
        Start-Sleep -Milliseconds 300
    }
    return (-not (Get-PortOwnerPid -Port $Port))
}

# ---------------------------------------------------------------- checks
function Test-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return [bool]$cmd
}

function Get-ExecutablePath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    if ($cmd.Source) { return $cmd.Source }
    return $cmd.Definition
}

function Get-PythonVersion {
    param([Parameter(Mandatory = $true)][string]$PythonExe)

    try {
        $output = & $PythonExe --version 2>&1 | Select-Object -First 1
        if ($output -match '(\d+)\.(\d+)\.(\d+)') {
            return [version]("$($matches[1]).$($matches[2]).$($matches[3])")
        }
    } catch { }
    return $null
}

function Get-VersionFromText {
    <# Pull "x.y.z" out of any version banner text. #>
    param([string]$Text)

    if ($Text -and $Text -match '(\d+)\.(\d+)\.(\d+)') {
        return [version]("$($matches[1]).$($matches[2]).$($matches[3])")
    }
    return $null
}

function Test-StorePythonStub {
    <#
      Windows ships "App execution aliases" for python.exe/python3.exe in
      %LOCALAPPDATA%\Microsoft\WindowsApps.  They are not a Python installation:
      running them opens the Microsoft Store (or fails), so they must never be
      accepted as an interpreter.

      Only the path is inspected on purpose - actually executing the candidate is
      avoided, because invoking a Store alias can pop up the Store window.
    #>
    param([string]$Path)

    if (-not $Path) { return $false }
    $lower = $Path.ToLowerInvariant()
    return ($lower.Contains('\windowsapps\') -or $lower.EndsWith('\windowsapps'))
}

function Invoke-NativeCapture {
    <#
      Run a native command and capture its output without letting it kill the
      script.  Windows PowerShell 5.1 turns stderr written by a native process
      into a terminating error while $ErrorActionPreference is 'Stop' (for
      example `python -c "import torch"` failing with a traceback), which would
      abort the launcher instead of being handled as a normal failure.

      Returns a hashtable: @{ ExitCode; Output; Text; Failed }

      With -Echo the command's output is also streamed to the console, which is
      what long installs (pip, npm) should do so the user sees progress and, if
      something fails, the actual error instead of a bare "installation failed".
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Echo
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $text = ''
    $exitCode = 0
    $raw = @()
    try {
        if ($Echo) {
            # stream through a temp file, printing the tail as new lines arrive
            $tempLog = Join-Path $env:TEMP ('native_' + [guid]::NewGuid().ToString('N') + '.log')
            & cmd.exe /c "`"$FilePath`" $($Arguments -join ' ') > `"$tempLog`" 2>&1"
            $exitCode = $LASTEXITCODE
            if (Test-Path -LiteralPath $tempLog) {
                $raw = @(Get-Content -LiteralPath $tempLog -Encoding UTF8)
                $raw | Select-Object -Last 25 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                $text = ($raw | Select-Object -Last 25) -join [Environment]::NewLine
                Remove-Item -LiteralPath $tempLog -Force -ErrorAction SilentlyContinue
            }
        } else {
            $raw = & $FilePath @Arguments 2>&1
            $exitCode = $LASTEXITCODE
            $text = (($raw | Out-String).Trim())
        }
    } catch {
        $exitCode = 1
        $text = $_.Exception.Message
        if ($Echo) { Write-Host "    $($_.Exception.Message)" -ForegroundColor DarkGray }
    } finally {
        $ErrorActionPreference = $previous
    }
    return @{
        ExitCode = $exitCode
        Output   = $raw
        Text     = $text
        Failed   = ($exitCode -ne 0)
    }
}

function Find-UsablePython {
    <#
      Resolve a Python interpreter for this project.  Search order:

        1. the project virtual environment  <repo>\.venv\Scripts\python.exe
        2. python.exe / python3.exe on PATH (never a Microsoft Store alias)
        3. the Windows Python launcher `py -3`

      Returns a hashtable:
        @{ Found; Source ('venv'|'python'|'py'); Exe; PrefixArgs; Version;
           Display; Error }
      The venv is preferred on purpose: once it exists every later step uses it
      and the global python/py commands are no longer needed.
    #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [string]$MinimumVersion = '3.10',
        [switch]$Quiet
    )

    $result = @{
        Found = $false; Source = $null; Exe = $null; PrefixArgs = @()
        Version = $null; Display = $null; Error = $null
    }
    $minimum = [version]($MinimumVersion + '.0')

    # ---- 1. project virtual environment
    if (Test-Path -LiteralPath $Paths.VenvPython) {
        $venvVersion = Get-PythonVersion -PythonExe $Paths.VenvPython
        if ($venvVersion -and $venvVersion -ge $minimum) {
            $result.Found = $true
            $result.Source = 'venv'
            $result.Exe = $Paths.VenvPython
            $result.Version = $venvVersion
            $result.Display = $Paths.VenvPython
            if (-not $Quiet) { Write-Ok "Python $venvVersion (project virtual environment)" }
            return $result
        }
        if (-not $Quiet) {
            Write-Warn "the project virtual environment has an unusable Python ($venvVersion) - looking for another one"
        }
    }

    # ---- 2. python.exe / python3.exe on PATH
    $candidates = @()
    foreach ($name in @('python', 'python3')) {
        try {
            $commands = @(Get-Command $name -All -ErrorAction Stop)
        } catch {
            continue
        }
        foreach ($command in $commands) {
            if ($command.Source) { $candidates += $command.Source }
        }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-StorePythonStub -Path $candidate) {
            if (-not $Quiet) { Write-Warn "ignoring the Microsoft Store alias for python: $candidate" }
            continue
        }
        $version = Get-PythonVersion -PythonExe $candidate
        if (-not $version) { continue }
        if ($version -lt $minimum) {
            if (-not $Quiet) { Write-Warn "ignoring Python $version at $candidate (needs $MinimumVersion or newer)" }
            continue
        }
        $result.Found = $true
        $result.Source = 'python'
        $result.Exe = $candidate
        $result.Version = $version
        $result.Display = $candidate
        if (-not $Quiet) { Write-Ok "Python $version ($candidate)" }
        return $result
    }

    # ---- 3. the Windows Python launcher
    $pyCommand = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $pyPath = $pyCommand.Source
        if (-not $pyPath) { $pyPath = 'py' }
        try {
            $banner = (& $pyPath -3 --version 2>&1 | Out-String)
            $version = Get-VersionFromText -Text $banner
        } catch {
            $version = $null
            $banner = $_.Exception.Message
        }
        if ($version -and $version -ge $minimum) {
            $result.Found = $true
            $result.Source = 'py'
            $result.Exe = $pyPath
            $result.PrefixArgs = @('-3')
            $result.Version = $version
            $result.Display = "$pyPath -3"
            if (-not $Quiet) {
                Write-Ok "Python $version (Windows launcher: $pyPath -3)"
            }
            return $result
        }
        if (-not $Quiet) {
            if ($version) {
                Write-Warn "the Windows launcher reports Python $version, which is older than $MinimumVersion"
            } else {
                Write-Warn "the Windows launcher (py) was found but 'py -3 --version' failed"
            }
        }
    }

    $result.Error = "no usable Python $MinimumVersion or newer was found"
    return $result
}

function Invoke-PythonCommand {
    <# Run a Python command with the interpreter found by Find-UsablePython. #>
    param(
        [Parameter(Mandatory = $true)]$Python,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $all = @()
    if ($Python.PrefixArgs) { $all += $Python.PrefixArgs }
    $all += $Arguments
    return (& $Python.Exe @all 2>&1)
}

function New-ProjectVirtualEnv {
    <#
      Create <repo>\.venv, using the virtual environment's own Python if it is
      already usable, otherwise the discovered interpreter.  Returns $true on
      success.
    #>
    param(
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)]$Python
    )

    $arguments = @('-m', 'venv', $Paths.VenvDir)
    $all = @()
    if ($Python.PrefixArgs) { $all += $Python.PrefixArgs }
    $all += $arguments

    Write-Info "creating the virtual environment with: $($Python.Display)"
    try {
        $output = (& $Python.Exe @all 2>&1 | Out-String)
    } catch {
        Write-LauncherLog "venv creation threw: $($_.Exception.Message)" 'ERROR'
        return $false
    }
    if ($LASTEXITCODE -ne 0) {
        Write-LauncherLog "venv creation failed (exit $LASTEXITCODE): $output" 'ERROR'
        return $false
    }
    return (Test-Path -LiteralPath $Paths.VenvPython)
}

function Show-PythonMissingHelp {
    <# The single place that explains what to install when no Python is usable. #>
    param([string]$MinimumVersion = '3.10')

    Write-Err 'Python was not found.'
    Write-Host '' -ForegroundColor Yellow
    Write-Host "        This project needs Python $MinimumVersion or newer." -ForegroundColor Yellow
    Write-Host '        1) Download it from https://www.python.org/downloads/' -ForegroundColor Yellow
    Write-Host '        2) During setup tick "Add python.exe to PATH"' -ForegroundColor Yellow
    Write-Host '        3) Then run SETUP.bat again' -ForegroundColor Yellow
    Write-Host '' -ForegroundColor Yellow
    Write-Host '        Already installed but not detected? Try these in a terminal:' -ForegroundColor Gray
    Write-Host "           py -3 --version        (Windows launcher)" -ForegroundColor Gray
    Write-Host "           python --version       (must print $MinimumVersion or newer)" -ForegroundColor Gray
}

function Get-NodeVersion {
    try {
        $output = & node --version 2>&1 | Select-Object -First 1
        if ($output -match 'v?(\d+)\.(\d+)\.(\d+)') {
            return [version]("$($matches[1]).$($matches[2]).$($matches[3])")
        }
    } catch { }
    return $null
}

function Test-ModelFile {
    param([Parameter(Mandatory = $true)]$Paths, [Parameter(Mandatory = $true)]$Config)

    $path = $Config.ModelPath
    if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
        $item = Get-Item -LiteralPath $path
        if ($item.Length -gt 0) { return @{ Found = $true; Path = $path; Size = $item.Length } }
        return @{ Found = $false; Path = $path; Size = 0 }
    }
    return @{ Found = $false; Path = $path; Size = 0 }
}

function Test-SecretPresence {
    <# Are the two secrets configured?  Values are never returned. #>
    param([Parameter(Mandatory = $true)]$Paths)

    $config = @{}
    foreach ($file in @($Paths.EnvFile, (Join-Path $Paths.RepoRoot '.env'))) {
        foreach ($entry in (Read-EnvFile -Path $file).GetEnumerator()) {
            if ($entry.Value -ne '') { $config[$entry.Key] = $entry.Value }
        }
    }
    $missing = @()
    foreach ($name in $script:SecretNames) {
        $value = $null
        if ($config.ContainsKey($name)) { $value = $config[$name] }
        if (-not $value) { $value = [System.Environment]::GetEnvironmentVariable($name) }
        if ([string]::IsNullOrWhiteSpace($value)) { $missing += $name }
    }
    return @{ Complete = ($missing.Count -eq 0); Missing = $missing }
}

function Initialize-StorageDirs {
    <# Create the directories the backend writes to. Never deletes anything. #>
    param([Parameter(Mandatory = $true)]$Paths)

    $created = @()
    foreach ($dir in @($Paths.UploadsDir, $Paths.TempDir, $Paths.LogsDir, $Paths.RuntimeDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $created += $dir
        }
    }
    return @($created)
}

function Open-Browser {
    param([Parameter(Mandatory = $true)][string]$Url)

    try {
        Start-Process $Url | Out-Null
        return $true
    } catch {
        Write-LauncherLog "could not open browser: $($_.Exception.Message)" 'WARN'
        return $false
    }
}

function Show-FinalScreen {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)]$ModelInfo,
        [Parameter(Mandatory = $true)]$Paths,
        [string]$Status = 'RUNNING'
    )

    $line = '=' * 56
    Write-Host ''
    Write-Host $line -ForegroundColor DarkCyan
    Write-Host '  Skin Lesion AI Platform' -ForegroundColor Cyan
    Write-Host $line -ForegroundColor DarkCyan
    Write-Host ''
    Write-Host ("  Status      : " + $Status)
    Write-Host ("  Frontend    : " + $Config.FrontendUrl)
    Write-Host ("  Backend     : " + $Config.BackendUrl)
    Write-Host ("  API Docs    : " + $Config.BackendUrl + "/docs")
    Write-Host ("  Health      : " + $Config.HealthUrl)
    Write-Host ''
    Write-Host ("  Model       : " + $ModelInfo.Architecture + " / " + (Split-Path -Leaf $ModelInfo.Path))
    Write-Host ("  Model ver   : " + $ModelInfo.Version)
    Write-Host ("  Device      : " + $ModelInfo.Device)
    Write-Host ''
    Write-Host ("  Backend log : " + $Paths.BackendLog)
    Write-Host ("  Frontend log: " + $Paths.FrontendLog)
    Write-Host ("  Launcher log: " + $Paths.LauncherLog)
    Write-Host ''
    Write-Host '  Stop        : double click STOP.bat'
    Write-Host '  Status      : double click STATUS.bat'
    Write-Host ''
    Write-Host '  AI-assisted results are for reference only and are NOT a' -ForegroundColor Yellow
    Write-Host '  medical diagnosis. Always consult a qualified doctor.' -ForegroundColor Yellow
    Write-Host ''
    Write-Host $line -ForegroundColor DarkCyan
}

function Get-ModelSummaryFromApi {
    param([Parameter(Mandatory = $true)]$Config)

    $summary = [pscustomobject]@{
        Architecture = 'unknown'
        Version      = 'unknown'
        Device       = 'unknown'
        Available    = $false
        Path         = $Config.ModelPath
    }
    $probe = Invoke-HttpProbe -Url $Config.ModelInfoUrl -TimeoutSeconds 10
    if ($probe.Ok -and $probe.Status -eq 200) {
        try {
            $payload = $probe.Body | ConvertFrom-Json
            $summary.Architecture = [string]$payload.architecture
            $summary.Version = [string]$payload.model_version
            $summary.Device = [string]$payload.device
            $summary.Available = [bool]$payload.available
        } catch { }
    }
    return $summary
}

function Wait-ForUser {
    <# Pause only when the launcher owns a real console window. #>
    param([string]$Message = 'Press Enter to close this window...')

    if ([System.Environment]::UserInteractive) {
        try {
            Write-Host ''
            Read-Host -Prompt $Message | Out-Null
        } catch { }
    }
}
