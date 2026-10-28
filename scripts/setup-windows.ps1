# Runs with Windows PowerShell 5.1, included with Windows 10/11.
[CmdletBinding()]
param([switch]$VenvOnly, [switch]$NoPrompt, [switch]$CheckOnly, [string]$PythonPath = '')

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDirectory = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvDirectory 'Scripts\python.exe'
$DiagnosticPath = Join-Path $ProjectRoot 'setup-diagnostics.txt'
$script:Diagnostics = [Collections.Generic.List[string]]::new()
$script:Candidates = [Collections.Generic.List[string]]::new()
$script:Seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$ProbeCode = "import json, struct, sys; print(json.dumps(dict(executable=sys.executable, major=sys.version_info[0], minor=sys.version_info[1], bits=struct.calcsize('P')*8)))"

function Add-Candidate([string]$Executable) {
    if ([string]::IsNullOrWhiteSpace($Executable)) { return }
    $Executable = [Environment]::ExpandEnvironmentVariables($Executable.Trim().Trim('"'))
    if ((Test-Path -LiteralPath $Executable -PathType Leaf) -and $script:Seen.Add($Executable)) {
        [void]$script:Candidates.Add($Executable)
    }
}

function Get-PythonInfo([string]$Executable) {
    try {
        $OutputLines = & $Executable -c $ProbeCode 2>$null
        if ($LASTEXITCODE -ne 0) {
            [void]$script:Diagnostics.Add("Cannot run: $Executable (exit $LASTEXITCODE)")
            return $null
        }
        $Info = ($OutputLines -join "`n") | ConvertFrom-Json
        [void]$script:Diagnostics.Add("$Executable -> Python $($Info.major).$($Info.minor), $($Info.bits)-bit")
        if ($Info.bits -ne 64 -or $Info.major -ne 3 -or $Info.minor -notin @(11, 12)) { return $null }
        return $Info
    } catch {
        [void]$script:Diagnostics.Add("Cannot inspect: $Executable - $($_.Exception.Message)")
        return $null
    }
}

function Add-RegisteredPython {
    foreach ($Hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($View in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $BaseKey = $null; $PythonKey = $null
            try {
                $BaseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($Hive, $View)
                $PythonKey = $BaseKey.OpenSubKey('Software\Python')
                if ($null -eq $PythonKey) { continue }
                foreach ($Company in $PythonKey.GetSubKeyNames()) {
                    $CompanyKey = $PythonKey.OpenSubKey($Company)
                    try {
                        foreach ($Tag in $CompanyKey.GetSubKeyNames()) {
                            $InstallKey = $CompanyKey.OpenSubKey("$Tag\InstallPath")
                            if ($null -eq $InstallKey) { continue }
                            try {
                                Add-Candidate ([string]$InstallKey.GetValue('ExecutablePath'))
                                $Directory = [string]$InstallKey.GetValue('')
                                if ($Directory) { Add-Candidate (Join-Path $Directory 'python.exe') }
                            } finally { $InstallKey.Close() }
                        }
                    } finally { $CompanyKey.Close() }
                }
            } catch {
                [void]$script:Diagnostics.Add("Registry lookup unavailable: $($_.Exception.Message)")
            } finally {
                if ($PythonKey) { $PythonKey.Close() }
                if ($BaseKey) { $BaseKey.Close() }
            }
        }
    }
}

function Find-Python {
    # List only: do not ask the launcher to install a missing version.
    $Launcher = Get-Command 'py.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Launcher) {
        try {
            $Listing = & $Launcher.Source -0p 2>$null
            foreach ($Line in $Listing) {
                if ([string]$Line -match '(?<path>[A-Za-z]:\\.+?\.exe)"?\s*$') { Add-Candidate $Matches['path'] }
            }
        } catch { [void]$script:Diagnostics.Add("Launcher listing unavailable: $($_.Exception.Message)") }
    }
    foreach ($CommandName in @('python.exe', 'python3.exe', 'python3.12.exe', 'python3.11.exe')) {
        foreach ($Command in @(Get-Command $CommandName -CommandType Application -All -ErrorAction SilentlyContinue)) {
            # Skip Store stubs, which can open the Store instead of a runtime.
            if ($Command.Source -notmatch '\\Microsoft\\WindowsApps\\') { Add-Candidate $Command.Source }
        }
    }
    Add-RegisteredPython
    $Patterns = @()
    if ($env:LOCALAPPDATA) { $Patterns += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe' }
    if ($env:ProgramFiles) { $Patterns += Join-Path $env:ProgramFiles 'Python3*\python.exe' }
    if (${env:ProgramFiles(x86)}) { $Patterns += Join-Path ${env:ProgramFiles(x86)} 'Python3*\python.exe' }
    if ($env:SystemDrive) { $Patterns += "$($env:SystemDrive)\Python3*\python.exe" }
    if ($env:USERPROFILE) {
        foreach ($Relative in @('anaconda3\python.exe', 'miniconda3\python.exe', '.pyenv\pyenv-win\versions\3.1*\python.exe')) {
            $Patterns += Join-Path $env:USERPROFILE $Relative
        }
    }
    foreach ($Pattern in $Patterns) {
        foreach ($File in @(Get-ChildItem -Path $Pattern -File -ErrorAction SilentlyContinue)) { Add-Candidate $File.FullName }
    }
    $Compatible = @()
    foreach ($Candidate in $script:Candidates) {
        $Info = Get-PythonInfo $Candidate
        if ($Info) { $Compatible += $Info }
    }
    return ($Compatible | Sort-Object minor -Descending | Select-Object -First 1)
}

function Select-Python {
    Write-Host 'Select python.exe from your Python 3.12 or 3.11 installation.' -ForegroundColor Cyan
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $Dialog = New-Object System.Windows.Forms.OpenFileDialog
        try {
            $Dialog.Title = 'UltraEnhance: select your installed Python 3.12 or 3.11'
            $Dialog.Filter = 'Python executable (python.exe)|python.exe|Executable files (*.exe)|*.exe'
            $Dialog.FileName = 'python.exe'
            $Dialog.RestoreDirectory = $true
            if ($env:LOCALAPPDATA -and (Test-Path (Join-Path $env:LOCALAPPDATA 'Programs\Python'))) {
                $Dialog.InitialDirectory = Join-Path $env:LOCALAPPDATA 'Programs\Python'
            }
            if ($Dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $Dialog.FileName }
            return ''
        } finally { $Dialog.Dispose() }
    } catch { return (Read-Host 'Full path to your python.exe').Trim().Trim('"') }
}

$SetupExit = 0
try {
    Write-Host 'UltraEnhance AI setup - Python 3.12 / 3.11, 64-bit' -ForegroundColor Cyan
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'The selected Python executable does not exist.' }
        $Python = Get-PythonInfo $PythonPath
    } elseif ((Test-Path -LiteralPath $VenvPython) -and -not $CheckOnly) {
        $Python = Get-PythonInfo $VenvPython
        if (-not $Python) { throw 'The existing .venv is broken or unsupported. Rename that folder and run Setup again.' }
    } else { $Python = Find-Python }
    if (-not $Python -and -not $NoPrompt -and -not $PythonPath) {
        Write-Host 'Automatic discovery did not find a compatible Python. You can select it directly.'
        $SelectedPath = Select-Python
        if ($SelectedPath) { $Python = Get-PythonInfo $SelectedPath }
    }
    if (-not $Python) {
        foreach ($Line in $script:Diagnostics) { Write-Host $Line }
        throw 'No compatible interpreter was selected. Use a 64-bit Python 3.12 or 3.11 python.exe; details are in setup-diagnostics.txt.'
    }
    Write-Host "Using Python $($Python.major).$($Python.minor) ($($Python.bits)-bit): $($Python.executable)" -ForegroundColor Green
    if (-not $CheckOnly) {
        if (-not (Test-Path -LiteralPath $VenvPython)) {
            & $Python.executable -m venv $VenvDirectory
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the application virtual environment.' }
        }
        $EnvironmentInfo = Get-PythonInfo $VenvPython
        if (-not $EnvironmentInfo) { throw 'The application virtual environment could not be validated. Rename .venv and run Setup again.' }
        if (-not $VenvOnly) {
            & $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
            if ($LASTEXITCODE -ne 0) { throw 'Python was found, but dependency installation failed. Review the pip error above.' }
            Write-Host 'Setup complete. Double-click Launch-UltraEnhance.cmd.' -ForegroundColor Green
        }
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    [void]$script:Diagnostics.Add($_.Exception.Message)
    $SetupExit = 1
} finally {
    try { [System.IO.File]::WriteAllLines($DiagnosticPath, $script:Diagnostics, [Text.UTF8Encoding]::new($false)) }
    catch { Write-Warning "Could not save setup diagnostics: $($_.Exception.Message)" }
}
exit $SetupExit
